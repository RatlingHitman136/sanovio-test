# Article Equivalence Loop — data model (Appendix A)

Full column types and example rows for both services: the hospital node (N.*) and the central supplier hub (H.*).
Companion to the prototype plan ([design-plan.md](design-plan.md), see §4.6 for placement and §6 for the decisions behind it) and to `architecture/charts.md`, which renders the same model as UML.

---

### A.0 Conventions (both services)
- **Types** are Postgres names. SQLAlchemy maps them to SQLite for the prototype: `uuid` → `CHAR(32)`, `jsonb` → `JSON`, `timestamptz` → `DATETIME` (UTC), `numeric` → `NUMERIC`.
- **Primary keys:** `id uuid` (UUIDv7). Examples use short aliases (`art_03`, `var_plastipak_ll_10`) for readability.
- **Cross-service references** (`hub_variant_id`, `hub_fact_id`, `hub_question_id`, `article_ref`, `hub_subject_id`…) are `text` columns **without foreign keys**, named after the other side. Neither database can join the other.
- **Enums** are `text` + `CHECK`; Python `StrEnum` in code.
- **Money:** `numeric(12,4)` (node only).
- **Timestamps:** every table has `created_at timestamptz NOT NULL`; mutable tables add `updated_at`.
- **Append-only tables:** facts (except `superseded_by_id`, `retracted_at` at the node and `withdrawn_at` / `withdrawn_by` at the hub), `egress_log`, `requirements`, `assessment_rounds`, `events`, `llm_calls`, submitted `answers`.
- **Hashes** are `char(64)` SHA-256 hex (shortened in examples).
- **Typed `value` shapes** (both sides):

  | Type | Example |
  |---|---|
  | number | `{"type":"number","value":10,"unit":"ml"}` (template's canonical unit; pint converts) |
  | boolean | `{"type":"bool","value":true}` |
  | enum | `{"type":"enum","value":"LUER_LOCK"}` |
  | text | `{"type":"text","value":"Polypropylen"}` |
  | list | `{"type":"list","value":["DIN_EN_ISO_7886_1"]}` |
  | identifier | `{"type":"identifier","scheme":"GTIN","value":"04040456781234","checksum_valid":true}` (round 7; `scheme` per side: node `GTIN`, `EAN`, `MANUFACTURER_REF`, `PHARMACODE`; hub `GTIN`, `SUPPLIER_ARTICLE_NO`, `PZN`, `HIMIV`. `checksum_valid` NULL when the scheme has no check digit) |

- **Example data:** BD's MDR class / DEHP / ISO answers are **simulated** (hidden datasheet); everything else comes from the example CSV/PDFs.

---

### Hospital node (one database per hospital; examples from node `ten_ksp`)

### N.1 `users`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| email | text | NO | unique (lower-cased) |
| password_hash | text | NO | argon2id |
| role | text | NO | CHECK `PURCHASER`, `NODE_ADMIN` |
| display_name | text | NO | |
| hub_subject_id | text | NO | unique; random `sub_` + 20 Crockford base32 chars (no I, L, O, U); the only user identifier the hub ever sees. Regenerating it makes the person a new principal at the hub. The client maps hub creator/resolver/assignee subjects back to names with it (`GET /users`). A retired subject is never reused or deleted (`is_active = false` keeps the row), so old hub attributions stay resolvable. |
| is_active | boolean | NO | default true |

| id | email | password_hash | role | display_name | hub_subject_id | is_active |
|---|---|---|---|---|---|---|
| usr_anna | anna.meier@demo-ksp.example | $argon2id$v=19$m=65536… | PURCHASER | Anna Meier | sub_7QF2M4XK9P3TZC8W1N6R | true |
| usr_itadm | it-admin@demo-ksp.example | $argon2id$v=19$m=65536… | NODE_ADMIN | KSP IT | sub_K2D9V7H4Q1M8X5B3T6YZ | true |

### N.2 `api_tokens`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| user_id | uuid | NO | FK users |
| token_hash | char(64) | NO | unique; SHA-256 of the random token (returned once at login) |
| expires_at | timestamptz | NO | 8 h |
| revoked_at | timestamptz | YES | set on logout |
| last_used_at | timestamptz | YES | |

| id | user_id | token_hash | expires_at | revoked_at | last_used_at |
|---|---|---|---|---|---|
| ntok_1 | usr_anna | 9f2c…e1 | 2026-09-16T17:00Z | NULL | 2026-09-16T09:12Z |

### N.3 `hospital_articles`
MDR class is an attribute, so it lives in `article_facts`. GTIN, EAN and article number are identifier-typed rows in the same table (D50); only `data_quality_issues`, a property of the identifier *set*, stays on the article.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| internal_id | text | NO | unique; hospital's own ID |
| article_ref | text | NO | unique; random `ar_` + 12 Crockford base32 chars (60 bits); the only article identifier sent to the hub; never derived from other fields; used by `GET /articles?article_ref=` to join hub assessments |
| name | text | NO | Artikelbezeichnung, as given |
| brand | text | YES | Marke |
| annual_quantity | integer | YES | Jahresmenge |
| order_unit | text | YES | `Box`, `Pack`, `Stk`… |
| base_units_per_order_unit | integer | YES | |
| base_unit | text | YES | `Stück`, `Tuch`, `Rolle` |
| target_net_price | numeric(12,4) | YES | per base unit |
| currency | char(3) | YES | ISO 4217 |
| category_code | text | YES | template code |
| category_source | text | YES | CHECK `RULES`, `LLM_SUGGESTED`, `PURCHASER`; re-normalization may replace `RULES`/`LLM_SUGGESTED`, never `PURCHASER` |
| category_set_by | uuid | YES | FK users; NULL when set by rules or LLM |
| category_set_at | timestamptz | YES | |
| reference_hub_variant_id | text | YES | hub variant ID of the current product (no FK; never sent to the hub) |
| reference_label | text | YES | label of the hub variant, for display |
| reference_source | text | YES | CHECK `CLIENT_REPORTED`: values supplied by the client from the hub catalog (unsigned, D37) |
| reference_linked_by / reference_linked_at | uuid / timestamptz | YES | |
| content_hash | char(64) | NO | hash of the source fields |
| normalized_hash | char(64) | YES | content_hash at the last normalization; equal = skip |
| data_quality_issues | jsonb | NO | default `[]` |
| raw | jsonb | NO | original record exactly as received |

| id | internal_id | article_ref | name | brand | annual_quantity | order_unit | base_units_per_order_unit | target_net_price | currency | category_code | category_source | reference_hub_variant_id |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| art_03 | 3 | ar_5MZQ4K7T2V9C | Einmalspritze 10 ml Luer-Lock steril | B. Braun | 15000 | Pack | 100 | 0.1200 | CHF | syringe_single_use | PURCHASER | var_injekt_ll_10 |
| art_06 | 6 | ar_H8R2WX3N6J4D | Kanüle Sterican 0,8 × 40 mm | B. Braun | 18000 | Pack | 100 | 0.0600 | CHF | hypodermic_needle | RULES | NULL |
| art_01 | 1 | ar_Q7C1PV5M9K2T | Nitrilhandschuh Sensicare Ice blau L | Medline | 4000 | Box | 200 | 0.0190 | CHF | generic_consumable | RULES | NULL |

More columns for these rows:
- art_03: `category_set_by = usr_anna`, `reference_label = "Injekt® Luer Lock Solo 10 ml (4606728V)"`, `data_quality_issues = ["GTIN_EAN_MISMATCH","EAN_CHECKSUM_INVALID"]`
- art_06: `data_quality_issues = ["GTIN_EAN_MISMATCH","GTIN_CHECKSUM_INVALID","EAN_CHECKSUM_INVALID"]`

`raw` for art_03: `{"internal_id":"3","Artikelbezeichnung":"Einmalspritze 10 ml Luer-Lock steril","Marke":"B. Braun","Artikelnummer":"9154010","Jahresmenge":"15000","Bestellmengeneinheit":"Pack","Basismengeneinheiten pro BME":"100","Basismengeneinheit":"Stück","GTIN":"'04040456781234","EAN":"'4040456781237","MDR-Klasse":"IIa","Netto-Zielpreis":"0.12","Währung":"CHF"}`

### N.4 (removed in round 7)
`article_identifiers` is gone (D50). Identifiers are identifier-typed rows in `article_facts` (N.5) with `attribute_key` = the scheme's registry key (`gtin`, `ean`, `manufacturer_ref`, `pharmacode`). `checksum_valid` lives inside the value; cross-identifier problems stay on the article as `data_quality_issues` (N.3), because they are a property of the set, not of one value.

**`checksum_valid`:** multiply digits alternately by 3 and 1 from the right, sum; check digit = (10 − sum mod 10) mod 10. GTIN `04040456781234` → sum 76 → 4 → `true`. EAN `4040456781237` has the same body, so its check digit must also be 4, not 7 → `false`. A valid check digit proves the number is well-formed, not that it belongs to this product.

### N.5 `article_facts`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| article_id | uuid | NO | FK hospital_articles |
| attribute_key | text | NO | must exist in the article's template, or be an identifier definition (`kind = IDENTIFIER`, never part of a template) |
| value | jsonb | YES | typed value, including the `identifier` shape (A.0); NULL only when source = `UNAVAILABLE` |
| raw_value | text | YES | original text |
| source | text | NO | CHECK `HOSPITAL_MASTER`, `EXTRACTION`, `REFERENCE_ITEM`, `PURCHASER_ANSWER`, `UNAVAILABLE` |
| method | text | YES | CHECK `RULES`, `LLM`; set for `EXTRACTION` |
| evidence_quote | text | YES | exact supporting text (never sent to the hub) |
| confidence | numeric(3,2) | YES | LLM extraction only |
| hub_variant_id / hub_fact_id | text | YES | for `REFERENCE_ITEM`: where the copied value came from |
| hub_question_id | text | YES | for `PURCHASER_ANSWER`/`UNAVAILABLE` given in reply to a hub question |
| created_by | uuid | YES | FK users; NULL = system |
| parser_version | text | YES | core version for `RULES` |
| llm_call_id | uuid | YES | FK llm_calls |
| model_id / prompt_version | text | YES | |
| created_at | timestamptz | NO | when the fact was written; the resolver's tie-breaker |
| superseded_by_id | uuid | YES | FK article_facts: the fact that replaced this one |
| retracted_at | timestamptz | YES | withdrawn with no replacement: a re-normalization that no longer finds the value, or an undone current product |

`superseded_by_id` and `retracted_at` are the only columns ever updated; a fact is current while both are NULL.

Partial index `(article_id, attribute_key) WHERE superseded_by_id IS NULL AND retracted_at IS NULL`.

| id | article | attribute_key | value | raw_value | source | method | evidence_quote | hub_* | created_by |
|---|---|---|---|---|---|---|---|---|---|
| afct_01 | art_03 | nominal_volume_ml | `{"type":"number","value":10,"unit":"ml"}` | 10 ml | EXTRACTION | RULES | Einmalspritze 10 ml Luer-Lock steril | – | NULL |
| afct_02 | art_03 | connector | `{"type":"enum","value":"LUER_LOCK"}` | Luer-Lock | EXTRACTION | RULES | Einmalspritze 10 ml Luer-Lock steril | – | NULL |
| afct_03 | art_03 | mdr_class | `{"type":"enum","value":"IIA"}` | IIa | HOSPITAL_MASTER | – | – | – | NULL |
| afct_04 | art_03 | design | `{"type":"enum","value":"TWO_PART"}` | Zweiteilige Einmalspritzen | REFERENCE_ITEM | – | – | hub_variant_id var_injekt_ll_10, hub_fact_id fct_40 | usr_anna |
| afct_40 | art_03 | gtin | `{"type":"identifier","scheme":"GTIN","value":"04040456781234","checksum_valid":true}` | '04040456781234 | HOSPITAL_MASTER | – | – | – | NULL |
| afct_41 | art_03 | ean | `{"type":"identifier","scheme":"EAN","value":"4040456781237","checksum_valid":false}` | '4040456781237 | HOSPITAL_MASTER | – | – | – | NULL |
| afct_30 | art_06 | wall_type | `{"type":"enum","value":"REGULAR"}` | regular | PURCHASER_ANSWER | – | – | hub_question_id q_9 | usr_anna |

### N.6 `article_projection` (derived, rebuildable)
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| article_id | uuid | NO | unique FK |
| category_code | text | YES | |
| definition_hash | char(64) | NO | hash of the template definition this projection was built against (D52) |
| attributes | jsonb | NO | effective typed values per attribute |
| attribute_origin | jsonb | NO | coarse origin per attribute: `MASTER`, `EXTRACTED`, `REFERENCE`, `PURCHASER` (what the requirement may carry) |
| identifiers | jsonb | NO | identifier facts as a **list** (`[{scheme, value, checksum_valid, fact_id}]`), kept out of `attributes` so precedence is unaffected; they are still part of `record_hash`. Read only by product hints (D47) and the client-side identifier check; never mapped into a requirement |
| attribute_fact_ids | jsonb | NO | attribute → fact ID (node-internal) |
| unknown_attributes / unavailable_attributes | jsonb | NO | |
| record_hash | char(64) | NO | core `record_hash` over **all** resolved attributes, unavailable marks and identifier facts; drives local change detection (rebuilds, "requirement outdated" hints) |
| requirement_hash | char(64) | NO | equals `RequirementPayload.requirement_hash()` of the requirement built from this projection (ARCHITECTURE §16): `template_code`, the **shareable** attributes, the unknown/unavailable/withheld lists and `product_hints` when the hospital sends them. The hub computes the same hash over the requirement it receives. A change to a non-shareable attribute (e.g. `units_per_order_unit`) changes `record_hash` but not `requirement_hash` |
| updated_at | timestamptz | NO | |

| article_id | category_code | attributes | attribute_origin | unknown_attributes | record_hash | requirement_hash |
|---|---|---|---|---|---|---|
| art_03 | syringe_single_use | `{"nominal_volume_ml":10,"connector":"LUER_LOCK","sterile":true,"mdr_class":"IIA","design":"TWO_PART","cone_position":"CENTRIC","graduation_step_ml":0.5,"latex_free":true,"dehp_free":true,"iso_7886_1_compliant":true}` (typed shapes abbreviated) | `{"nominal_volume_ml":"EXTRACTED","connector":"EXTRACTED","sterile":"EXTRACTED","mdr_class":"MASTER","design":"REFERENCE",…}` | `["needle_included","pump_compatible"]` | f19b… | c3d0… |

### N.7 `egress_log` (append-only)
Records what the node **issued** to the client for the hub (requirements, hub assertions). It cannot prove delivery (D34).

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| kind | text | NO | CHECK `ASSERTION`, `REQUIREMENT` |
| article_id | uuid | YES | FK hospital_articles; NULL for assertions |
| user_id | uuid | NO | FK users: who requested it |
| content | jsonb | YES | exact requirement issued; for assertions the claims only (never the token). NULL only on an alert-only row: a request refused with 429 issued nothing, but the attempt must stay visible |
| content_sha256 | char(64) | YES | NULL exactly when `content` is |
| jti / kid | text | YES | assertions only |
| alert | text | YES | CHECK `RATE_80_PERCENT`, `RATE_EXCEEDED`, `UNUSUAL_DAILY_VOLUME` |
| created_at | timestamptz | NO | index (user_id, created_at) for rate limits |

CHECK: `content` and `content_sha256` are set unless `alert = RATE_EXCEEDED`. Only rows with content count towards a rate limit.

| id | kind | article_id | user_id | content (excerpt) | jti | alert | created_at |
|---|---|---|---|---|---|---|---|
| egr_1 | ASSERTION | NULL | usr_anna | `{"iss":"ten_ksp","sub":"sub_7QF2…","aud":"sanovio-hub","scope":"purchaser","exp":…}` | asr_01J9A… | NULL | 09:10:02 |
| egr_2 | REQUIREMENT | art_03 | usr_anna | `{"article_ref":"ar_5MZQ4K7T2V9C","template_code":"syringe_single_use","attributes":{…},"unknown_attributes":["design","cone_position",…],"product_hints":null}` | NULL | NULL | 09:13:40 |
| egr_3 | REQUIREMENT | art_03 | usr_anna | `{"article_ref":"ar_5MZQ4K7T2V9C",…,"unknown_attributes":["needle_included","pump_compatible"]}` (after marking the current product) | NULL | NULL | 09:14:10 |
| egr_4 | REQUIREMENT | art_03 | usr_anna | same content as egr_3 (assessment) | NULL | NULL | 09:15:00 |

### N.8 (removed in round 6)
The former `assessment_links` table is gone (D49). Assessments, verdicts and assignees live only at the hub (H.13); the client joins them to local articles by `article_ref` (N.3) and to user names by `hub_subject_id` (N.1). Numbering of N.9–N.11 is kept.

### N.9 (removed in round 9)
`jobs` is gone from the node (D53): there is no queue and no worker thread. Normalization runs in a batch at ingestion and projection rebuilds run inside the writing transaction. The hub keeps its queue (H.18).

### N.10 `llm_calls` (node; append-only)
Same columns as H.19, with `purpose` CHECK `NORMALIZE_ARTICLE` and no `assessment_id`. (At the hub, `assessment_id` gets its foreign key when the assessments table arrives in stage 5.) One row per `normalize_article` call — in the demo, **one row after `make seed`** covers all ten articles (D56). This is the hospital's audit trail for the only data that leaves the node other than requirements: the article names, sent to the hospital's **own** LLM account (D42). `request` never contains the API key; empty when `NORMALIZE_MODE=rules`. The node's table also carries `created_at`. A repair retry is logged as its own row, and every extracted fact names the call it came from (`llm_call_id`).

| id | purpose | model | prompt_version | input_tokens | output_tokens | latency_ms | cost_usd |
|---|---|---|---|---|---|---|---|
| nllm_1 | NORMALIZE_ARTICLE | claude-sonnet-5 | normalize_article_v1 | 1450 | 820 | 5200 | ≈0.011 |

### N.11 `template_versions` (a cache of the current definition per category; the name is kept for continuity)
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| code | text | NO | **unique**: one current definition per category (D52) |
| definition | jsonb | NO | attributes with type, unit, options, labels, synonyms, criticality, rule, shareable flag; plain JSON from the hub, validated against the core `TemplateDefinition` model |
| definition_hash | char(64) | NO | SHA-256 over the canonical definition; the third term of the hub's `input_hash` (H.14) |
| hub_updated_at | timestamptz | NO | the hub's `updated_at` for this definition; the client syncs when the hub's is newer |
| installed_by | uuid | NO | FK users |
| installed_at | timestamptz | NO | |

| id | code | definition_hash | hub_updated_at | installed_by | installed_at |
|---|---|---|---|---|---|
| tv_1 | syringe_single_use | 4c81… | 2026-09-18T08:10Z | usr_anna | 2026-09-18T08:31Z |
| tv_2 | hypodermic_needle | 9ae0… | 2026-09-15T08:00Z | usr_itadm | 2026-09-15T08:00Z |

Node settings (not tables):
- `EGRESS_DENY_ATTRIBUTES`: attribute keys never sent
- `SHARE_PRODUCT_HINTS`: default `false`
- `EGRESS_DAILY_ALERT_PER_USER`: issued objects per user and day that raise `UNUSUAL_DAILY_VOLUME` (default 300)
- `NODE_SEED_PASSWORD`: the password `hospital-node seed` gives the demo accounts
- `REQUIREMENT_RATE_LIMIT_PER_HOUR`: default 120
- `ASSERTION_RATE_LIMIT_PER_HOUR`: default 30

---

### Supplier hub (one multi-tenant database)

### H.1 `organizations`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| code | text | NO | unique, readable id (`ten_ksp`, `org_bd`): what a node signs as `iss` and what the operator CLI addresses. Internal references stay UUIDs |
| name | text | NO | real name; for hospitals visible to operators only (unless disclosed) |
| type | text | NO | CHECK `HOSPITAL`, `SUPPLIER`, `OPERATOR` |
| supplier_facing_alias | text | YES | required for `HOSPITAL`; unique |
| disclose_name_to_suppliers | boolean | NO | default false |
| language | varchar(2) | NO | default `de`; language of questions sent to this organization |
| country | varchar(2) | YES | |
| cors_origin | text | YES | hospital SPA origin (later phase) |
| is_active | boolean | NO | inactive tenant → exchanges refused |

| id | name | type | supplier_facing_alias | disclose_name_to_suppliers | language | country |
|---|---|---|---|---|---|---|
| ten_ksp | Demo Kantonsspital | HOSPITAL | Hospital H-7F3A | false | de | CH |
| ten_spital2 | Demo Spital Zwei | HOSPITAL | Hospital H-2C91 | false | de | CH |
| org_bd | BD | SUPPLIER | NULL | false | de | CH |
| org_bbraun | B. Braun | SUPPLIER | NULL | false | de | DE |
| org_ops | Sanovio Operations | OPERATOR | NULL | false | en | CH |

### H.2 `tenant_signing_keys`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| tenant_id | uuid | NO | FK organizations (type HOSPITAL) |
| kid | text | NO | unique across all tenants |
| public_jwk | jsonb | NO | `{"kty":"OKP","crv":"Ed25519","x":"…"}`; CHECK no private member `d` |
| fingerprint | char(64) | NO | SHA-256 of the canonical JWK (RFC 7638 thumbprint), confirmed out of band |
| not_before | timestamptz | NO | |
| not_after | timestamptz | YES | set when rotated out |
| revoked_at | timestamptz | YES | immediate rejection |
| registered_by | uuid | NO | FK users (operator) |

| id | tenant_id | kid | public_jwk | fingerprint | not_before | not_after | revoked_at |
|---|---|---|---|---|---|---|---|
| tsk_1 | ten_ksp | ksp-2026-09 | `{"kty":"OKP","crv":"Ed25519","x":"11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"}` | 5b1e…90 | 2026-09-01T00:00Z | NULL | NULL |
| tsk_0 | ten_ksp | ksp-2025-09 | `{"kty":"OKP","crv":"Ed25519","x":"…"}` | a07c…3d | 2025-09-01T00:00Z | 2026-09-01T00:20Z | NULL |
| tsk_2 | ten_spital2 | sp2-2026-09 | `{"kty":"OKP","crv":"Ed25519","x":"…"}` | e44f…18 | 2026-09-10T00:00Z | NULL | NULL |

### H.3 `hospital_principals`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| tenant_id | uuid | NO | FK organizations |
| subject_id | text | NO | `sub` from assertions; unique (tenant_id, subject_id) |
| first_seen_at / last_seen_at | timestamptz | NO | |
| is_blocked | boolean | NO | operator can block one principal without revoking the tenant key (stage 9: `POST /admin/tenants/{id}/principals/{sub}/block`; blocking also revokes the principal's hub tokens) |

| id | tenant_id | subject_id | first_seen_at | last_seen_at | is_blocked |
|---|---|---|---|---|---|
| prn_1 | ten_ksp | sub_7QF2M4XK9P3TZC8W1N6R | 2026-09-16T09:10Z | 2026-09-16T16:30Z | false |

### H.4 `users` (supplier users and operators; no hospital staff)
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| org_id | uuid | NO | FK organizations (type SUPPLIER or OPERATOR) |
| email | text | NO | unique |
| password_hash | text | NO | argon2id |
| role | text | NO | CHECK `SUPPLIER`, `OPERATOR`; must match the organization type |
| display_name | text | NO | |
| is_active | boolean | NO | deactivating (operator, stage 9) revokes the user's tokens; an operator cannot deactivate their own account |

| id | org_id | email | role | display_name |
|---|---|---|---|---|
| usr_bd1 | org_bd | catalog@bd-demo.example | SUPPLIER | BD Catalog Team |
| usr_bb1 | org_bbraun | katalog@bbraun-demo.example | SUPPLIER | B. Braun Katalog |
| usr_ops | org_ops | ops@sanovio-demo.example | OPERATOR | Hub Operator |

### H.5 `api_tokens`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| user_id | uuid | YES | FK users (login tokens) |
| principal_id | uuid | YES | FK hospital_principals (exchanged tokens); exactly one of user_id / principal_id |
| tenant_id | uuid | YES | set for exchanged tokens |
| kid | text | YES | key that signed the exchanged assertion; revocation cascades by kid |
| assertion_jti | text | YES | |
| token_hash | char(64) | NO | unique |
| expires_at | timestamptz | NO | 30 min exchanged; 8 h login |
| revoked_at / last_used_at | timestamptz | YES | |

| id | user_id | principal_id | tenant_id | kid | token_hash | expires_at |
|---|---|---|---|---|---|---|
| htok_1 | NULL | prn_1 | ten_ksp | ksp-2026-09 | 4ab0…77 | 2026-09-16T09:40Z |
| htok_2 | usr_bd1 | NULL | NULL | NULL | 0c9e…2f | 2026-09-16T22:00Z |

### H.6 `used_assertion_jtis`
| Column | Type | Null | Notes |
|---|---|---|---|
| jti | text | NO | PK |
| tenant_id | uuid | NO | |
| expires_at | timestamptz | NO | rows deleted after expiry (a replay after that fails on `exp` anyway) |

| jti | tenant_id | expires_at |
|---|---|---|
| asr_01J9A… | ten_ksp | 2026-09-16T09:15:02Z |

### H.7 `product_families`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| supplier_id | uuid | NO | FK organizations |
| manufacturer | text | NO | |
| brand_name | text | YES | e.g. `Plastipak™` |
| name | text | NO | family title as printed |
| product_type | text | YES | subtitle as printed |
| category_code | text | YES | |
| category_source | text | YES | CHECK `LLM_SUGGESTED`, `SUPPLIER` |
| category_set_by / category_set_at | uuid / timestamptz | YES | |
| description / properties_text | text | YES | as printed |
| source_document / source_page | text / integer | YES | |
| content_hash / normalized_hash | char(64) | NO / YES | |
| raw | jsonb | NO | |

| id | supplier_id | manufacturer | brand_name | name | product_type | category_code | properties_text (excerpt) | source_document | source_page |
|---|---|---|---|---|---|---|---|---|---|
| fam_bd_plastipak_ll | org_bd | BD | Plastipak™ | BD Plastipak™ Spritzen mit BD Luer-Lok™-Ansatz ohne Kanüle | Dreiteilige Spritzen | syringe_single_use | "Der latexfreie Stopfen verhindert das Auslaufen … Sterile Einzelverpackung, Einmalgebrauch." | product_catalog_02.pdf | 13 |
| fam_bb_injekt_ll | org_bbraun | B. Braun | Injekt® | Injekt® Luer Lock Solo | Zweiteilige Einmalspritzen mit Luer-Lock-Ansatz | syringe_single_use | "Nicht hergestellt mit Silikonöl, Bisphenol A, Latex, DEHP und PVC · Einzeln steril verpackt · gefertigt nach der DIN EN ISO-Norm 7886-1" | product_catalog_01.pdf | 6 |
| fam_bb_sterican | org_bbraun | B. Braun | Sterican® | Sterican® Standard-Einmalkanülen | Standard-Einmalkanülen zur Injektion | hypodermic_needle | "gefertigt nach der DIN EN ISO-Norm 7864" | product_catalog_01.pdf | 26 |
| fam_bd_microlance | org_bd | BD | Microlance™ | BD Microlance™ Injektionskanülen | Injektionskanülen | hypodermic_needle | "Dreifacher Präzisionsfacettenschliff · Sterile Einzelverpackung, Einmalgebrauch." | product_catalog_02.pdf | 6 |

### H.8 `product_variants`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| family_id | uuid | NO | FK product_families |
| supplier_id | uuid | NO | FK organizations |
| article_no | text | NO | unique (supplier_id, article_no) |
| label | text | NO | |
| order_unit | text | YES | |
| units_per_order_unit / order_units_per_shipping_unit | integer | YES | |
| source_row | jsonb | NO | table row as printed |
| source_page | integer | YES | |
| is_active | boolean | NO | |
| content_hash | char(64) | NO | |

| id | family_id | article_no | label | order_unit | units_per_order_unit | order_units_per_shipping_unit | source_page |
|---|---|---|---|---|---|---|---|
| var_plastipak_ll_10 | fam_bd_plastipak_ll | 300912 | 10 ml, zentrisch | Packung | 100 | 4 | 13 |
| var_emerald_luer_10 | fam_bd_emerald | 307736 | 10 ml, zentrisch | Packung | 100 | 12 | 12 |
| var_injekt_ll_10 | fam_bb_injekt_ll | 4606728V | 10 ml, nutzbar bis 12 ml | Packung | 100 | 12 | 6 |
| var_sterican_21g_40 | fam_bb_sterican | 4657527B | 21 G × 1½" · 0,80 × 40 mm | Packung | 100 | 40 | 26 |
| var_microlance_21g_40 | fam_bd_microlance | 304432 | 21 G 1½" · Nr. 2 | Packung | 100 | 50 | 6 |

`source_row` examples:
- var_plastipak_ll_10: `{"Volumen":"10 ml","Ansatz":"zentrisch","Graduierung":"unterteilt in 0,2 ml","Produkt-Nr.":"300912","VE / UK":"100 / 400"}`
- var_injekt_ll_10: `{"Größe":"10 ml, nutzbar bis 12 ml","Konus":"Zentrisch","Graduierung":"0,5 ml","VE / Karton":"12 x 100 Stück","Art.-Nr.":"4606728V","PZN":"00611005","HiMiV":"03.29.01.1052"}`
- var_microlance_21g_40: `{"Größe":"21 G 1 1/2\" – Nr. 2","Außendurchmesser (mm)":"0,8","Länge (mm)":"40","Wandstärke":"dünnwandig","Farbcode":"grün","Produkt-Nr.":"304432","VE / UK":"100 / 5.000"}`

### H.9 (removed in round 7)
`item_identifiers` is gone (D50). Supplier identifiers are identifier-typed rows in `item_facts` (H.10), variant-scoped, with `attribute_key` = `gtin`, `supplier_article_no`, `pzn` or `himiv`, `source` `CATALOG` or `SUPPLIER_ANSWER`, and the existing `answer_id` / `superseded_by_id` provenance. They are read only by search matching and `identifier_evidence` (D51).

### H.10 `item_facts` (supplier facts)
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| family_id / variant_id | uuid | YES | exactly one set = scope (`CHECK num_nonnulls(...) = 1`) |
| attribute_key | text | NO | must exist in `attribute_definitions` (any status) |
| value | jsonb | YES | NULL only for `UNAVAILABLE` |
| raw_value | text | YES | |
| source | text | NO | CHECK `CATALOG`, `EXTRACTION`, `SUPPLIER_ANSWER`, `UNAVAILABLE` |
| evidence_quote | text | YES | |
| confidence | numeric(3,2) | YES | LLM only |
| answer_id | uuid | YES | FK answers |
| created_by | uuid | YES | FK users; NULL = system |
| llm_call_id | uuid | YES | FK llm_calls |
| model_id / prompt_version | text | YES | |
| superseded_by_id | uuid | YES | FK item_facts |
| withdrawn_at / withdrawn_by | timestamptz / uuid | YES | a supplier took back its own fact (stage 8); FK users. Only `SUPPLIER_ANSWER` and `UNAVAILABLE` facts can be withdrawn |

Partial indexes `(variant_id, attribute_key)` and `(family_id, attribute_key)` `WHERE superseded_by_id IS NULL AND withdrawn_at IS NULL`: a fact is current while both are NULL.

| id | scope → item | attribute_key | value | raw_value | source | evidence_quote | conf. | answer_id | created_by | model / prompt |
|---|---|---|---|---|---|---|---|---|---|---|
| fct_40 | family → fam_bb_injekt_ll | design | `{"type":"enum","value":"TWO_PART"}` | Zweiteilige Einmalspritzen | EXTRACTION | Zweiteilige Einmalspritzen mit Luer-Lock-Ansatz | 0.99 | – | NULL | claude-sonnet-5 / normalize_v1 |
| fct_10 | family → fam_bd_plastipak_ll | design | `{"type":"enum","value":"THREE_PART"}` | Dreiteilige Spritzen | EXTRACTION | Dreiteilige Spritzen | 0.99 | – | NULL | claude-sonnet-5 / normalize_v1 |
| fct_11 | variant → var_plastipak_ll_10 | graduation_step_ml | `{"type":"number","value":0.2,"unit":"ml"}` | unterteilt in 0,2 ml | CATALOG | – | – | – | NULL | – |
| fct_12 | variant → var_plastipak_ll_10 | cone_position | `{"type":"enum","value":"CENTRIC"}` | zentrisch | CATALOG | – | – | – | NULL | – |
| fct_20 | family → fam_bd_plastipak_ll | mdr_class | `{"type":"enum","value":"IIA"}` | IIa | SUPPLIER_ANSWER | – | – | ans_01 | usr_bd1 | – |
| fct_21 | family → fam_bd_plastipak_ll | dehp_free | `{"type":"bool","value":true}` | Zylinder und Stopfen enthalten kein DEHP. | SUPPLIER_ANSWER | Zylinder und Stopfen enthalten kein DEHP. | 0.93 | ans_02 | usr_bd1 | claude-haiku-4-5 / extract_answer_v1 |
| fct_31 | variant → var_microlance_21g_40 | inner_diameter_mm | NULL | – | UNAVAILABLE | – | – | ans_07 | usr_bd1 | – |

**Superseding:** a later correction adds a new fact and sets `superseded_by_id` on the old one; nothing is deleted.

**Supplier edits (stage 8):** a value a supplier sets in its catalog is a `SUPPLIER_ANSWER` fact (or `UNAVAILABLE`) with `created_by` set and no `answer_id`, at family scope or as a variant override. Withdrawing it sets `withdrawn_at` / `withdrawn_by`; the older value then resolves again.

### H.11 `item_search_projection` (derived, variant rows only)
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| variant_id | uuid | NO | unique FK |
| supplier_id | uuid | NO | |
| category_code | text | YES | |
| display_name | text | NO | |
| attributes | jsonb | NO | effective values (family facts copied down); GIN index in Postgres |
| attribute_fact_ids | jsonb | NO | |
| unknown_attributes | jsonb | NO | template attributes without a value |
| additional_attributes | jsonb | NO | values of PROVISIONAL attributes with fact IDs; shown as information, never filtered or judged |
| identifiers | jsonb | NO | identifier facts as a list (`[{scheme, value, checksum_valid, fact_id}]`); GIN-indexed for `(scheme, value)` lookup by search and `identifier_evidence`; never compared as attributes |
| search_text | text | NO | canonical rendering (later: full-text + embeddings) |
| record_hash | char(64) | NO | core `record_hash` over resolved attributes **and** identifiers; feeds `input_hash`, so an answered identifier counts as progress |
| updated_at | timestamptz | NO | |
| *(later)* search_tsv / embedding | tsvector / halfvec(1024) | YES | |

| id | variant_id | supplier_id | category_code | display_name | attributes | unknown_attributes | record_hash |
|---|---|---|---|---|---|---|---|
| prj_1 | var_plastipak_ll_10 | org_bd | syringe_single_use | BD Plastipak™ Luer-Lok™ 10 ml (300912) | `{"nominal_volume_ml":10,"connector":"LUER_LOCK","cone_position":"CENTRIC","design":"THREE_PART","graduation_step_ml":0.2,"sterile":true,"single_use":true,"latex_free":true,"units_per_order_unit":100}` | `["mdr_class","dehp_free","iso_7886_1_compliant"]` | 7be1… |
| prj_2 | var_emerald_luer_10 | org_bd | syringe_single_use | BD Emerald™ Luer 10 ml (307736) | `{"nominal_volume_ml":10,"connector":"LUER","cone_position":"CENTRIC","design":"TWO_PART","graduation_step_ml":0.2,"sterile":true}` | `["mdr_class","dehp_free","latex_free"]` | 41d8… |

(After round 2 of scenario 1, prj_1's `unknown_attributes` becomes `[]` and its `record_hash` changes.)

### H.12 `requirements` (assessment requirements only; append-only)
*Written from stage 5 on: a search validates a requirement, uses it and discards it (§15); only an assessment stores one.*
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| tenant_id | uuid | NO | FK organizations; taken from the hub token |
| assessment_id | uuid | NO | FK assessments |
| requirement_version | smallint | NO | |
| article_ref | text | NO | |
| template_code | text | NO | the category; the hub validates against its current definition (D52) |
| payload | jsonb | NO | the requirement as received and validated |
| requirement_hash | char(64) | NO | core hash over attributes + unknown/unavailable/withheld lists |
| answered_question_ids | jsonb | NO | default `[]` |
| received_by_principal_id | uuid | NO | FK hospital_principals |
| created_at | timestamptz | NO | |

| id | assessment_id | article_ref | template_code | answered_question_ids | requirement_hash | received_by_principal_id | created_at |
|---|---|---|---|---|---|---|---|
| req_1 | asm_1 | ar_5MZQ4K7T2V9C | syringe_single_use | `[]` | c3d0… | prn_1 | 09:15:00 |
| req_5 | asm_3 | ar_H8R2WX3N6J4D | hypodermic_needle | `[]` | 0e1a… | prn_1 | 10:02:00 |
| req_6 | asm_3 | ar_H8R2WX3N6J4D | hypodermic_needle | `["q_9"]` | 8d57… | prn_1 | 10:15:10 |

### H.13 `assessments`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| hospital_tenant_id | uuid | NO | FK organizations (owner) |
| supplier_id | uuid | NO | FK organizations |
| article_ref | text | NO | opaque; no FK |
| variant_id | uuid | NO | FK product_variants |
| current_requirement_id | uuid | YES | FK requirements; set in the transaction that creates the assessment. Nullable only because `assessments` and `requirements` reference each other (created with `use_alter`); a reset clears it before deleting rows |
| template_code | text | NO | the category being assessed; no version pinning (D52) |
| status | text | NO | CHECK `ASSESSING`, `NEEDS_QUESTION_REVIEW`, `AWAITING_ANSWERS`, `PROPOSED_RESOLUTION`, `NEEDS_MANUAL_DECISION`, `FAILED`, `RESOLVED`, `CANCELLED` |
| current_round / max_rounds | smallint | NO | default max 3 |
| proposed_verdict | text | YES | CHECK `EQUIVALENT`, `EQUIVALENT_WITH_DEVIATIONS`, `NOT_EQUIVALENT` |
| final_verdict | text | YES | CHECK the above + `UNDETERMINED` |
| resolution_kind | text | YES | CHECK `CONFIRMED`, `OVERRIDDEN`, `MANUAL` |
| resolution_note | text | YES | required when OVERRIDDEN |
| manual_reason | text | YES | CHECK `ROUND_CAP`, `NO_PROGRESS`, `BLOCKING_UNAVAILABLE` |
| version | integer | NO | optimistic lock |
| created_by_principal_id / resolved_by_principal_id | uuid | NO / YES | FK hospital_principals |
| assigned_to_principal_id | uuid | YES | FK hospital_principals; responsible purchaser (pseudonymous); does not restrict access |
| resolved_at | timestamptz | YES | |
| created_at | timestamptz | NO | list order |

Partial unique index: `(hospital_tenant_id, article_ref, variant_id) WHERE status NOT IN ('RESOLVED','CANCELLED')`. Index `(hospital_tenant_id, assigned_to_principal_id, status)` for "my assessments".

| id | hospital_tenant_id | article_ref | variant_id | template_code | status | current_round | proposed_verdict | final_verdict | resolution_kind | manual_reason | version |
|---|---|---|---|---|---|---|---|---|---|---|---|
| asm_1 | ten_ksp | ar_5MZQ4K7T2V9C | var_plastipak_ll_10 | syringe_single_use | RESOLVED | 2 | EQUIVALENT_WITH_DEVIATIONS | EQUIVALENT_WITH_DEVIATIONS | CONFIRMED | NULL | 7 |
| asm_2 | ten_ksp | ar_5MZQ4K7T2V9C | var_emerald_luer_10 | syringe_single_use | PROPOSED_RESOLUTION | 1 | NOT_EQUIVALENT | NULL | NULL | NULL | 2 |
| asm_3 | ten_ksp | ar_H8R2WX3N6J4D | var_microlance_21g_40 | hypodermic_needle | NEEDS_MANUAL_DECISION | 2 | NULL | NULL | NULL | BLOCKING_UNAVAILABLE | 6 |

### H.14 `assessment_rounds` (append-only)
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| assessment_id | uuid | NO | FK; unique (assessment_id, round_no) |
| round_no | smallint | NO | |
| requirement_id | uuid | NO | FK requirements: the hospital side that was judged |
| supplier_record_hash | char(64) | NO | projection `record_hash` of the variant at judging time |
| input_hash | char(64) | NO | SHA-256(`requirement_hash` + `supplier_record_hash` + `definition_hash` of the template used); no-progress check (D52) |
| input_snapshot | jsonb | NO | supplier effective record + requirement attributes as judged (replay) |
| identifier_evidence | text | NO | CHECK `SAME_TRADE_ITEM`, `NO_INFORMATION`; with `SAME_TRADE_ITEM` the round has no comparator results and no `llm_call_id` (D51) |
| comparator_results / attribute_judgments | jsonb | NO | |
| rule_verdict | text | NO | incl. `INSUFFICIENT_DATA` |
| llm_verdict | text | YES | |
| llm_confidence | numeric(3,2) | YES | |
| disagreement | boolean | NO | |
| rationale | text | YES | |
| extra_concerns | jsonb | NO | |
| outcome_status | text | NO | |
| definition_hash / prompt_version / model_id | text | NO | `definition_hash` records exactly which template definition this round judged (D52) |
| llm_call_id | uuid | YES | FK llm_calls |
| created_at | timestamptz | NO | |

| id | assessment_id | round_no | requirement_id | input_hash | rule_verdict | llm_verdict | llm_confidence | disagreement | rationale | outcome_status |
|---|---|---|---|---|---|---|---|---|---|---|
| rnd_1 | asm_1 | 1 | req_1 | 51aa… | INSUFFICIENT_DATA | INSUFFICIENT_DATA | 0.86 | false | Volume, connector, cone and sterility match; MDR class, DEHP status and ISO 7886-1 are missing for the BD product. | NEEDS_QUESTION_REVIEW |
| rnd_2 | asm_1 | 2 | req_1 | 9c03… | EQUIVALENT_WITH_DEVIATIONS | EQUIVALENT_WITH_DEVIATIONS | 0.88 | false | All critical attributes match. 3-part vs 2-part design (major); finer graduation 0.2 ml is acceptable. | PROPOSED_RESOLUTION |

**`attribute_judgments` elements (rnd_2):** the hospital side cites the requirement, not node fact IDs. Every element is exactly what `equivalence_core.comparators.Judgment` produces: `status` is one of `MATCH`, `ACCEPTABLE_DEVIATION`, `MISMATCH`, `UNKNOWN`, `UNAVAILABLE`, `INFO` or `NEEDS_JUDGE` (§8.4), the supplier side carries the winning fact's `scope` (`VARIANT` or `FAMILY`, from the core resolver's `ResolvedValue`), and a gap adds `missing` (`HOSPITAL` / `SUPPLIER` / `BOTH`) plus `askable`, which is false for attributes the hospital withheld.
- `{"attribute":"design","criticality":"major","hospital":{"value":"TWO_PART","origin":"REFERENCE","requirement_id":"req_1"},"supplier":{"value":"THREE_PART","fact_id":"fct_10","scope":"FAMILY"},"status":"MISMATCH","decided_by":"COMPARATOR","rule":"exact"}`
- `{"attribute":"graduation_step_ml","criticality":"major","hospital":{"value":0.5,"origin":"REFERENCE","requirement_id":"req_1"},"supplier":{"value":0.2,"fact_id":"fct_11","scope":"VARIANT"},"status":"ACCEPTABLE_DEVIATION","decided_by":"COMPARATOR","rule":"same_or_finer"}`
- `{"attribute":"stopper_material","criticality":"minor","hospital":{"value":"Polyisopren","origin":"REFERENCE","requirement_id":"req_1"},"supplier":{"value":"latexfreier Stopfen","fact_id":"fct_13","scope":"FAMILY"},"status":"MATCH","decided_by":"LLM","confidence":0.8,"rationale":"Both describe a latex-free elastomer stopper."}`

### H.15 `questions`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| assessment_id | uuid | NO | FK |
| round_id | uuid | YES | FK assessment_rounds; NULL for a question the purchaser adds during review |
| addressee | text | NO | CHECK `SUPPLIER`, `PURCHASER` |
| attribute_key | text | YES | NULL while an attribute proposal for a free question / extra concern is pending; then an existing key or a new PROVISIONAL key |
| text | text | NO | supplier questions never contain requirement values or hospital identity |
| language | varchar(2) | NO | |
| expected_answer | jsonb | NO | `{type, unit?, options?}`; for an identifier question `{"type":"identifier","scheme":"GTIN"}` |
| rationale | text | YES | shown to the purchaser only |
| origin | text | NO | CHECK `LLM`, `TEMPLATE`, `PURCHASER` |
| status | text | NO | CHECK `DRAFT`, `SENT`, `ANSWERED`, `UNAVAILABLE`, `WITHDRAWN` |
| edited_by_purchaser | boolean | NO | |
| answered_in_requirement_id | uuid | YES | FK requirements; PURCHASER questions only |
| sent_at | timestamptz | YES | |
| created_at | timestamptz | NO | |

| id | assessment_id | round_id | addressee | attribute_key | text | expected_answer | origin | status | answered_in_requirement_id |
|---|---|---|---|---|---|---|---|---|---|
| q_1 | asm_1 | rnd_1 | SUPPLIER | mdr_class | Welche MDR-Risikoklasse hat BD Plastipak™ Luer-Lok™ 10 ml (300912)? | `{"type":"enum","options":["I","I_S","I_M","I_R","IIA","IIB","III"]}` | LLM | ANSWERED | NULL |
| q_2 | asm_1 | rnd_1 | SUPPLIER | dehp_free | Sind Zylinder, Kolben und Stopfen frei von DEHP? | `{"type":"bool"}` | LLM | ANSWERED | NULL |
| q_3 | asm_1 | rnd_1 | SUPPLIER | iso_7886_1_compliant | Wird die Spritze nach DIN EN ISO 7886-1 gefertigt? | `{"type":"bool"}` | LLM | ANSWERED | NULL |
| q_4 | asm_1 | rnd_1 | SUPPLIER | peel_off_label | Enthält die Packung ein abziehbares Dokumentationsetikett? | `{"type":"bool"}` | PURCHASER | ANSWERED | NULL |
| q_20 | asm_1 | rnd_1 | SUPPLIER | gtin (identifier definition) | Wie lautet die GTIN der Handelseinheit von BD Plastipak™ Luer-Lok™ 10 ml (300912)? | `{"type":"identifier","scheme":"GTIN"}` | PURCHASER | ANSWERED | NULL |
| q_9 | asm_3 | rnd_5 | PURCHASER | wall_type | Which wall type does your current needle have? | `{"type":"enum","options":["REGULAR","THIN"]}` | TEMPLATE | ANSWERED | req_6 |
| q_12 | asm_3 | rnd_5 | SUPPLIER | inner_diameter_mm | Wie gross ist der Innendurchmesser von BD Microlance™ 21 G 1½" (304432)? | `{"type":"number","unit":"mm"}` | LLM | UNAVAILABLE | NULL |

(q_9's text no longer quotes the article name: the hub doesn't have it; the client shows the question next to the article from the node.)

### H.16 `answers` (supplier answers only)
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| question_id | uuid | NO | FK; unique; question addressee must be SUPPLIER |
| answered_by | uuid | NO | FK users (supplier) |
| value | jsonb | YES | validated against `expected_answer` |
| comment | text | YES | |
| cannot_provide | boolean | NO | |
| applies_to_family | boolean | NO | |
| is_draft | boolean | NO | |
| submitted_at | timestamptz | YES | |
| extraction_status | text | NO | CHECK `NOT_NEEDED`, `PENDING`, `EXTRACTED`, `UNCLEAR` |

| id | question_id | answered_by | value | comment | cannot_provide | applies_to_family | is_draft | submitted_at | extraction_status |
|---|---|---|---|---|---|---|---|---|---|
| ans_01 | q_1 | usr_bd1 | `{"type":"enum","value":"IIA"}` | NULL | false | true | false | 2026-09-16T14:02Z | NOT_NEEDED |
| ans_02 | q_2 | usr_bd1 | NULL | Zylinder und Stopfen enthalten kein DEHP. | false | true | false | 2026-09-16T14:02Z | EXTRACTED |
| ans_03 | q_3 | usr_bd1 | `{"type":"bool","value":true}` | gemäss Konformitätserklärung | false | true | false | 2026-09-16T14:02Z | NOT_NEEDED |
| ans_07 | q_12 | usr_bd1 | NULL | Nicht spezifiziert. | true | false | false | 2026-09-16T15:40Z | NOT_NEEDED |

### H.17 `events` (append-only timeline / audit)
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| assessment_id | uuid | NO | FK |
| actor_user_id | uuid | YES | FK users (supplier/operator) |
| actor_principal_id | uuid | YES | FK hospital_principals; at most one actor column set; both NULL = system |
| type | text | NO | CHECK `CREATED`, `ROUND_COMPLETED`, `STATUS_CHANGED`, `REQUIREMENT_RECEIVED`, `QUESTION_EDITED`, `QUESTION_ADDED`, `QUESTIONS_SENT`, `PURCHASER_ANSWERS_RECEIVED`, `ANSWERS_SUBMITTED`, `FACTS_ADDED`, `ATTRIBUTE_PROPOSED`, `ASSIGNED`, `RESOLVED`, `CANCELLED`, `JOB_FAILED` |
| from_status / to_status | text | YES | |
| data | jsonb | NO | |
| created_at | timestamptz | NO | |

| id | assessment_id | actor | type | from_status | to_status | data | created_at |
|---|---|---|---|---|---|---|---|
| evt_1 | asm_1 | prn_1 | CREATED | NULL | ASSESSING | `{"variant_id":"var_plastipak_ll_10","requirement_id":"req_1"}` | 09:15:00 |
| evt_2 | asm_1 | system | ROUND_COMPLETED | ASSESSING | NEEDS_QUESTION_REVIEW | `{"round_no":1,"rule_verdict":"INSUFFICIENT_DATA","questions":["q_1","q_2","q_3"]}` | 09:15:31 |
| evt_4 | asm_1 | prn_1 | QUESTIONS_SENT | NEEDS_QUESTION_REVIEW | AWAITING_ANSWERS | `{"question_ids":["q_1","q_2","q_3"]}` | 09:20:00 |
| evt_5 | asm_1 | usr_bd1 | ANSWERS_SUBMITTED | AWAITING_ANSWERS | ASSESSING | `{"answer_ids":["ans_01","ans_02","ans_03"]}` | 14:02:00 |
| evt_7 | asm_1 | system | ROUND_COMPLETED | ASSESSING | PROPOSED_RESOLUTION | `{"round_no":2,"rule_verdict":"EQUIVALENT_WITH_DEVIATIONS"}` | 14:02:58 |
| evt_8 | asm_1 | prn_1 | RESOLVED | PROPOSED_RESOLUTION | RESOLVED | `{"final_verdict":"EQUIVALENT_WITH_DEVIATIONS","resolution_kind":"CONFIRMED"}` | 16:30:12 |
| evt_21 | asm_3 | prn_1 | PURCHASER_ANSWERS_RECEIVED | NULL | NULL | `{"requirement_id":"req_6","question_ids":["q_9"]}` | 10:15:10 |
| evt_3 | asm_1 | prn_1 | ASSIGNED | NULL | NULL | `{"assigned_to_principal_id":"prn_1"}` (client showed "Anna Meier" from the node) | 09:16:20 |

### H.18 `jobs`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| kind | text | NO | CHECK `NORMALIZE_ITEM`, `ASSESS`, `EXTRACT_ANSWERS`, `PROPOSE_ATTRIBUTE`, `REBUILD_PROJECTION` (the dev simulator runs inside its request) |
| payload | jsonb | NO | IDs only, no foreign keys |
| dedupe_key | text | YES | unique |
| status | text | NO | CHECK `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED` |
| attempts / max_attempts | smallint | NO | default 0 / 3 |
| run_after | timestamptz | NO | |
| locked_at / locked_by | timestamptz / text | YES | |
| last_error | text | YES | |
| finished_at | timestamptz | YES | |

| id | kind | payload | dedupe_key | status | attempts | last_error |
|---|---|---|---|---|---|---|
| job_2 | ASSESS | `{"assessment_id":"asm_1","round_no":1}` | assess:asm_1:1 | SUCCEEDED | 1 | NULL |
| job_5 | EXTRACT_ANSWERS | `{"assessment_id":"asm_1","answer_ids":["ans_02"]}` | extract:asm_1:1 | SUCCEEDED | 1 | NULL |
| job_6 | ASSESS | `{"assessment_id":"asm_1","round_no":2}` | assess:asm_1:2 | QUEUED | 1 | APIConnectionError: timeout (retrying) |
| job_7 | REBUILD_PROJECTION | `{"family_id":"fam_bd_plastipak_ll"}` | projection:family:fam_bd_plastipak_ll:14:02 | SUCCEEDED | 1 | NULL |

### H.19 `llm_calls` (append-only)
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| purpose | text | NO | CHECK `NORMALIZE_ITEM`, `JUDGE`, `EXTRACT_ANSWER`, `PROPOSE_ATTRIBUTE`, `SIMULATE_SUPPLIER`, `COMPARE_TEXT` (stage 8) |
| model | text | NO | |
| effort | text | YES | |
| prompt_version | text | NO | |
| assessment_id | uuid | YES | FK |
| request | jsonb | NO | messages + output schema name (never the API key, never tenant name or `article_ref`) |
| response | jsonb | YES | |
| stop_reason | text | YES | |
| input_tokens / output_tokens / cache_read_tokens / cache_write_tokens | integer | NO | |
| latency_ms | integer | NO | |
| cost_usd | numeric(10,6) | YES | |
| error | text | YES | |

| id | purpose | model | effort | prompt_version | assessment_id | stop_reason | input_tokens | output_tokens | cache_read_tokens | latency_ms | cost_usd |
|---|---|---|---|---|---|---|---|---|---|---|---|
| llm_07 | NORMALIZE_ITEM | claude-sonnet-5 | medium | normalize_v1 | NULL | end_turn | 1840 | 610 | 0 | 4200 | ≈0.0098 |
| llm_12 | JUDGE | claude-opus-5 | high | judge_v1 | asm_1 | end_turn | 2700 | 2600 | 5200 | 21000 | ≈0.08 |
| llm_31 | EXTRACT_ANSWER | claude-haiku-4-5 | NULL | extract_answer_v1 | asm_1 | end_turn | 620 | 90 | 0 | 900 | ≈0.0011 |

### H.20 `attribute_definitions`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| key | text | NO | unique; snake_case, language-neutral |
| kind | text | NO | CHECK `ATTRIBUTE`, `IDENTIFIER`; `IDENTIFIER` rows can never be added to a category template, so they never get a criticality or a comparison rule (D50) |
| value_type | text | NO | CHECK `number`, `bool`, `enum`, `text`, `list`, `identifier` |
| unit | text | YES | canonical unit for numbers |
| options | jsonb | YES | enum codes |
| labels | jsonb | NO | `{"de": …, "en": …}`; neutral wording (validated) |
| synonyms | jsonb | NO | default `{}`; spelling variants → code (used by parsers at node and hub) |
| question_hint | jsonb | YES | per-language hint for question wording |
| status | text | NO | CHECK `PROVISIONAL`, `APPROVED`, `DEPRECATED` |
| origin | text | NO | CHECK `SEED`, `PROPOSAL` |
| proposal_id | uuid | YES | FK attribute_proposals |
| merged_into_id | uuid | YES | FK attribute_definitions; set when an operator merges the attribute (stage 9), which also makes it `DEPRECATED` |
| approved_by / approved_at | uuid / timestamptz | YES | FK users (operator) |
| created_at / updated_at | timestamptz | NO | |

| id | key | value_type | unit | options | labels (en) | status | origin | proposal_id |
|---|---|---|---|---|---|---|---|---|
| atd_1 | mdr_class | enum | NULL | `["I","I_S","I_M","I_R","IIA","IIB","III"]` | MDR risk class | APPROVED | SEED | NULL |
| atd_2 | connector | enum | NULL | `["LUER","LUER_LOCK","NRFIT","CATHETER","ORAL"]` | Connector | APPROVED | SEED | NULL |
| atd_3 | nominal_volume_ml | number | ml | NULL | Nominal volume | APPROVED | SEED | NULL |
| atd_50 | gtin | identifier (`kind = IDENTIFIER`) | NULL | NULL | GTIN | APPROVED | SEED | NULL |
| atd_41 | peel_off_label | bool | NULL | NULL | Peel-off documentation label | APPROVED (PROVISIONAL until 2026-09-18) | PROPOSAL | prop_1 |

### H.21 `category_templates`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| code | text | NO | **unique**: one current definition per category (D52) |
| parent_code | text | YES | e.g. `generic_consumable`; parent attributes are merged in when the definition is served |
| attributes | jsonb | NO | `[{key, criticality, comparison_rule, tolerance?, shareable}]`; keys must be APPROVED attributes |
| definition_hash | char(64) | NO | SHA-256 over the canonical definition; feeds `input_hash` (H.14) and the node's sync check |
| change_note | text | YES | what the last curation changed |
| updated_by / updated_at | uuid / timestamptz | NO | FK users (operator); the node syncs when this is newer than its copy |
| created_at | timestamptz | NO | |

| id | code | parent_code | attributes (excerpt) | change_note | updated_at |
|---|---|---|---|---|---|
| ctp_1 | syringe_single_use | generic_consumable | `[{"key":"nominal_volume_ml","criticality":"critical","comparison_rule":"exact","shareable":true}, {"key":"connector","criticality":"critical","comparison_rule":"exact","shareable":true}, …, {"key":"peel_off_label","criticality":"major","comparison_rule":"exact","shareable":true}]` | Added peel_off_label (proposal prop_1) | 2026-09-18T08:10Z |
| ctp_2 | hypodermic_needle | generic_consumable | `[{"key":"gauge","criticality":"critical","comparison_rule":"exact","shareable":true}, …]` | Seed | 2026-09-15T08:00Z |

### H.22 `attribute_proposals`
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| question_id | uuid | NO | FK questions; unique |
| assessment_id | uuid | NO | FK assessments |
| category_code | text | NO | category of the assessment |
| result | text | YES | CHECK `EXISTING`, `NEW`, `IDENTIFIER`; NULL while the job runs, and when the validator rejected the model's proposal (status `REJECTED`, reason in `review_note`; the question is still sent, its answer becomes no fact) |
| matched_attribute_id | uuid | YES | FK attribute_definitions (result EXISTING) |
| proposal | jsonb | YES | `{key, type, unit, options, labels, rationale}` (result NEW) |
| attribute_id | uuid | YES | FK attribute_definitions: the PROVISIONAL attribute created on send |
| status | text | NO | CHECK `PENDING`, `MATCHED`, `PROVISIONAL`, `APPROVED`, `MERGED`, `REJECTED`, `ROUTED` (identifier question: the scheme went to the question and no attribute was created) |
| identifier_key | text | YES | set with result `IDENTIFIER`: the identifier definition the question takes as its `attribute_key` |
| reviewed_by / reviewed_at | uuid / timestamptz | YES | FK users (operator) |
| review_note | text | YES | |
| llm_call_id | uuid | YES | FK llm_calls |
| created_at / updated_at | timestamptz | NO | |

| id | question_id | category_code | result | proposal | attribute_id | status | reviewed_by | review_note |
|---|---|---|---|---|---|---|---|---|
| prop_1 | q_4 | syringe_single_use | NEW | `{"key":"peel_off_label","value_type":"bool","labels":{"de":"Abziehbares Dokumentationsetikett","en":"Peel-off documentation label"}}` | atd_41 | APPROVED | usr_ops | major for syringes; added to 1.1 |
| prop_2 | q_17 | hypodermic_needle | EXISTING | NULL | NULL (matched atd_9 `wall_type`) | MATCHED | NULL | NULL |
| prop_3 | q_20 | syringe_single_use | IDENTIFIER | NULL (`identifier_key = gtin`) | atd_50 | ROUTED | NULL | identifier definition, no comparable attribute |

Stage 9: an operator decides a PROVISIONAL proposal by approve, merge (status `MERGED`, `review_note` required) or reject (status `REJECTED`, `review_note` required; `result` stays `NEW`, unlike an automatic rejection). Every proposal pointing at the same `attribute_id` is decided together.

### H.23 `operator_actions` (append-only audit, stage 9)
| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | NO | PK |
| operator_id | uuid | NO | FK users (OPERATOR) |
| action | text | NO | CHECK `TENANT_CREATED`, `SIGNING_KEY_REGISTERED`, `SIGNING_KEY_REVOKED`, `PRINCIPAL_BLOCKED`, `PRINCIPAL_UNBLOCKED`, `PROPOSAL_APPROVED`, `PROPOSAL_MERGED`, `PROPOSAL_REJECTED`, `TEMPLATE_EDITED`, `SUPPLIER_CREATED`, `USER_CREATED`, `USER_DEACTIVATED`, `USER_REACTIVATED`, `PASSWORD_RESET`, `FAMILY_RENORMALIZED`, `JOB_RETRIED` |
| target_type | text | NO | `tenant`, `signing_key`, `principal`, `attribute_proposal`, `template`, `organization`, `user`, `family`, `job` |
| target_id | text | NO | a readable id where there is one (tenant code, kid, email, template code), else the UUID |
| data | jsonb | NO | what changed (e.g. the template edit, a key's fingerprint); never a password or key material |
| created_at | timestamptz | NO | indexed; the console lists newest first |

| id | operator_id | action | target_type | target_id | data |
|---|---|---|---|---|---|
| opa_1 | usr_ops | SIGNING_KEY_REGISTERED | signing_key | ksp-2026-09 | `{"tenant":"ten_ksp","fingerprint":"…"}` |
| opa_2 | usr_ops | PROPOSAL_APPROVED | attribute_proposal | prop_1 | `{"category":"syringe_single_use","criticality":"major","rule":"exact",…}` |
| opa_3 | usr_ops | PASSWORD_RESET | user | catalog@bd-demo.example | `{}` |

---
