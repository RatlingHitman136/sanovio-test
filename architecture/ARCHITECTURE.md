# Article Equivalence Loop — Architecture

Design of the prototype: a **hospital node** per hospital and a central **supplier hub**, connected only through the purchaser's client. This document describes the design as decided; column-level schemas are in [data-model.md](data-model.md) and the UML diagrams are listed in [charts.md](charts.md) (rendered to `../charts/png/`).

## Contents
1. Overview · 2. Scope and constraints · 3. Source data · 4. System shape · 5. Technology stack · 6. Repository layout and modules · 7. Templates and attribute registry · 8. Comparison · 9. Enrichment · 10. Data placement and storage · 11. Assessment lifecycle · 12. Background work · 13. LLM pipelines · 14. API · 15. Candidate search · 16. The requirement · 17. Identity, keys and secrets · 18. Deployment · 19. The full loop as REST calls · 20. Frontend (later) · 21. Demo data and scenarios · 22. Implementation stages · 23. Design decisions · 24. Assumptions and open questions · 25. Related documents

---

## 1. Overview

Hospital purchasers want to know whether a supplier's catalog item can replace an article they already buy.

- **The purchaser** starts from an existing hospital article, searches supplier catalogs, and picks a candidate.
- **The system** compares the two attribute by attribute. Deterministic comparators decide what they can; an LLM judges only what they leave open; **rules in code** turn the per-attribute results into a verdict.
- **Missing data becomes questions** — to the supplier for gaps in the catalog item, to the purchaser for gaps in the hospital article. Answers are stored as new, sourced facts, and the comparison runs again.
- **The loop stops** when a verdict is decisive, the round cap is reached, nothing changed, or every blocking gap is unavailable. A purchaser always confirms the outcome.

The system is split in two so that hospital data can stay inside the hospital:

| Part | Holds | Runs |
|---|---|---|
| **Hospital node** (one per hospital, may sit behind the hospital firewall) | the hospital's articles, their facts and identifiers, users, the egress log | parsers + one LLM normalization pass at ingestion (hospital's own key); builds requirements; signs hub assertions |
| **Supplier hub** (central, operated by us) | tenants, supplier catalogs and facts, the attribute registry, assessments, questions, answers | search, judging, extraction, attribute proposals (our key) |
| **Purchaser client** (demo CLI now, SPA later) | nothing persistent; both tokens in memory | the only component that talks to both |

**The node and the hub never connect to each other.** Hospital data reaches the hub only as a *requirement*: typed technical attribute values under an opaque reference, built through an allowlist at the node and logged there.

## 2. Scope and constraints

- **Backend only** for now: FastAPI (Python), exercised through Swagger UI, curl and a scripted demo client. A React/TypeScript frontend is a later phase (§20).
- **uv** manages Python and every Python library.
- **Tiered Claude models** keep LLM cost down (§13).
- **Data ingestion is out of scope.** The sample files show what the data looks like; seeds are hand-written canonical JSON.
- **The starting point is an existing hospital article.** Free-text requirement entry is not planned.
- **Focus categories:** syringes and hypodermic needles; other categories use a generic template.
- **Timebox:** 3–5 days; the implementation stages in §22 add up to ≈5½ days.
- The development machine has Python 3.14 + uv and Java (for the diagrams); no Node or Docker.

## 3. Source data

### 3.1 Hospital article list: `sample-challenge-v01(Tabelle3).csv`
- **Format:** Latin-1 encoding, German headers, Excel artifacts (GTIN/EAN prefixed with `'` to keep leading zeros), dot decimal for prices.
- **Fields:**

  | Column | Meaning | Canonical field |
  |---|---|---|
  | internal_id | hospital's own ID | `internal_id` |
  | Artikelbezeichnung | short article name, **the only descriptive field** (e.g. "Einmalspritze 10 ml Luer-Lock steril") | `name` → attributes extracted from it |
  | Marke | brand / manufacturer | `brand` |
  | Artikelnummer | manufacturer article number | identifier `MANUFACTURER_REF` |
  | Jahresmenge | annual quantity | `annual_quantity` |
  | Bestellmengeneinheit | order unit (Box, Stk, Pack, Dose, Rolle) | `order_unit` |
  | Basismengeneinheiten pro BME | base units per order unit | `base_units_per_order_unit` |
  | Basismengeneinheit | base unit (Stück, Tuch, Rolle) | `base_unit` |
  | GTIN / EAN | identifiers | identifiers `GTIN`, `EAN` (check-digit validated) |
  | MDR-Klasse | I / IIa | fact `mdr_class` |
  | Netto-Zielpreis + Währung | target net price per base unit, CHF | `target_net_price`, `currency` |

- **Consequences for the design:**
  - **The hospital side is the data-poor side.** Technical attributes sit inside a short German name ("0,8 × 40 mm", "Latex puderfrei M"). Normalization must parse German text, decimal commas and "×".
  - **The names are regular enough for rules:** a product word (Einmalspritze, Kanüle, Nitrilhandschuh), numbers with units, and known connector/material words. This makes rule-based normalization at the node realistic (D42).
  - **Identifiers are unreliable.** 7/10 GTINs and 9/10 EANs fail the check digit, and in 9/10 rows the EAN is not the GTIN without its leading zero. Article numbers don't match the catalogs.
  - **Wide category spread:** about 8 categories (gloves, wound set, syringe, infusion set, mask, needle, wipes, urine cup, plaster).
  - **Commercially sensitive fields** (price, annual quantity, brand currently bought) are present. They stay on the node.

### 3.2 Supplier catalogs: `product_catalog_01.pdf` (B. Braun, 43 pages), `product_catalog_02.pdf` (BD, 22 pages)
- **Two-level structure: product family → variants.**
  - **A family** (e.g. "Injekt® Luer Lock Solo", "BD Plastipak™ Spritzen mit BD Luer-Lok™-Ansatz") has a description, *Produkteigenschaften* (product properties) bullets and standards. These apply to all its variants.
  - **A variant table** has one row per article number.
- **Family-level fields seen:**
  - product type (2-part / 3-part syringe, safety needle, blunt fill needle, filter needle)
  - connector (Luer, Luer-Lock, NRFit®, catheter tip, oral)
  - component materials (barrel PP, plunger PE, stopper polyisoprene / synthetic rubber)
  - "not made with" silicone oil / BPA / latex / DEHP / PVC
  - individually sterile packed, single use
  - standards (DIN EN ISO 7886-1, 7864, 80369-6)
  - pump compatibility, intended use
- **Variant-level fields seen:**
  - **Syringes:** nominal volume and usable volume ("10 ml, nutzbar bis 12 ml"), cone position (zentrisch/exzentrisch), graduation step, heparin IU scale
  - **Needles:** gauge, inch length, outer diameter × length (mm), inner diameter, wall thickness (regulär / dünnwandig), bevel (Lang-/Kurzschliff), colour code, needle size included
  - **Both:** packaging (e.g. "12 × 100 Stück" per carton, "100 / 1.200" VE/UK), article number, PZN, HiMiV
- **Not present:** GTIN/EAN, MDR class, price, sterilization method, shelf life. Only notified-body numbers (0050, 0318) are printed.
- **Consequences:** these are the fields the supplier will naturally be asked about. Identifiers vary by scheme: manufacturer article number, PZN and HiMiV (German), GTIN (hospital). Catalogs are public-facing documents, so central LLM processing of them raises no hospital privacy concern.

### 3.3 Where the two sides overlap
Only **syringes** (CSV row 3) and **hypodermic needles** (CSV row 6) appear in both. The B. Braun catalog holds the hospital's *current* products; BD offers the *competitor alternatives*. Demo scenarios (§21) are built on these pairs.

## 4. System shape

```
      Hospital network (firewall: nothing from outside connects in)      │         Internet
                                                                          │
 ┌──────────────────────────── HOSPITAL NODE (per hospital) ───────────┐  │  ┌─────────────── SUPPLIER HUB (central, ours) ───────────────┐
 │ FastAPI :8001                                                       │  │  │ FastAPI :8000                                              │
 │  articles · identifiers · article facts · projection                │  │  │  tenants + public keys · token exchange                    │
 │  normalization at init (parsers + LLM, hospital key)                │  │  │  catalogs (families/variants) · supplier facts · projection│
 │  requirement builder · egress log · limits                          │  │  │  search · candidates · hints                               │
 │  hub-assertion signer · article lookup by ref · user names          │  │  │  assessments · rounds · questions · answers · events       │
 │  node.db (synchronous; no job queue)                                │  │  │  judge / normalize / extract (Anthropic) · worker · hub.db │
 │  secrets: node Ed25519 PRIVATE key · hospital Anthropic key         │  │  │  secrets: Anthropic key                                    │
 └─────────────────────────────▲───────────────────────────────────────┘  │  │  DB: tenant PUBLIC keys, hashed tokens                     │
                               │ LAN HTTPS + node token                   │  └──────────────────────────────▲─────────────────────────────┘
                               │                                          │                                 │ HTTPS + hub token
                    ┌──────────┴──────────────────────────────────────────┴─────────────────────────────────┴───┐
                    │ PURCHASER CLIENT (demo CLI now, SPA later): the ONLY component that talks to both            │
                    │  carries: requirements node → hub · template definitions hub → node · assertions node → hub   │
                    │  holds: node token + hub token in memory only                                                │
                    └───────────────────────────────────────────────────────────────────────────────────────────────┘
                                                                                                    ▲
                                                                     SUPPLIER CLIENT ── HTTPS ──────┘ (hub only)

   No network path node ⇄ hub in either direction. One signed object type: hub assertions (node key).
```

- **Hospital node** (`apps/hospital-node`): owns everything the hospital's article list contains. It has **no hub URL** in its settings, only the hub's audience string and public key, so it cannot call the hub.
- **Supplier hub** (`apps/supplier-hub`): multi-tenant. Knows hospitals only as **tenants** (ID, public keys, pseudonymous alias) and purchasers only as **pseudonymous principals**. Never receives hospital article master data.
- **Core** (`packages/equivalence-core`): plain Python with no FastAPI, SQLAlchemy or LLM imports, fully unit-tested. Holds the template model and loader (definitions come from the hub registry; YAML files seed it), parsers, synonym matching, identifier validation, comparators, fact precedence, `record_hash`, verdict rules, `identifier_evidence`, the strict `RequirementPayload` model, and sign/verify helpers for hub assertions. The **state machine and stop conditions live in the hub** (only the hub runs the loop).
- **What crosses the gap** (always through the client):

  | Direction | Object | Signed? | Contents |
  |---|---|---|---|
  | node → hub | **hub assertion** (`assertion+jwt`, ≤5 min) | node key | tenant, pseudonymous subject, scope |
  | node → hub | **requirement** (plain JSON, strict schema) | no | `article_ref`, `template_code`, shareable attribute values, coarse origins, unknown/unavailable/withheld lists, answered purchaser question IDs; product hints only if the hospital enables them |
  | hub → node | **variant attributes** (plain JSON) | no | effective attributes of one catalog variant, when the purchaser marks it as the current product |
  | hub → node | **template definition** (plain JSON) | no | the current definition of one category: attribute definitions (type, unit, options, labels, synonyms) with criticality, comparison rule and `shareable` flag (D52) |

- **Ingestion boundary:** seeds follow the canonical model (§10). Future import adapters would produce the same format. Not built now.
- **Read models:** `article_projection` (node) and `item_search_projection` (hub) hold current resolved attributes; both use the core's resolver and `record_hash`.

## 5. Technology stack

| Concern | Choice |
|---|---|
| Python and packages | **uv only.** One **uv workspace** at the repo root (`[tool.uv.workspace] members = ["packages/*", "apps/*", "tools/*"]`) with one committed `uv.lock`. Members depend on the core through `[tool.uv.sources] equivalence-core = { workspace = true }`. Commands: `uv sync`, `uv add --package supplier-hub …`, `uv run --package hospital-node …`. `uv python pin` (≥3.12; the installed 3.14 is fine). No pip, venv, poetry or requirements.txt. |
| Web API (both services) | **FastAPI** + Uvicorn |
| Schemas / config | **Pydantic v2**, `pydantic-settings` (one settings class and `.env` per service) |
| Database layer | **SQLAlchemy 2.0** (typed ORM, synchronous sessions) + **Alembic**, one migration history per service |
| Databases | **SQLite** (WAL) per service: `var/node_ksp.db`, `var/hub.db`; Postgres by changing `DATABASE_URL`. **Never shared** between services. |
| Background jobs | **Hub only:** job table + worker thread (normalization, judging, extraction, projection). The node has no queue (D53): its one LLM pass runs at seed/startup, and everything after that is synchronous (D56). |
| LLM | **`anthropic` SDK** behind an `LLMClient` interface (Anthropic adapter + `FakeLLM`) in the shared workspace package **`packages/llm-client`**, used by **both** services (the core stays LLM-free). Hub: judge, normalize_item, extract, propose, simulate (our key). Node: `normalize_article` only, **run once at initialization**, with the hospital's own key (D42, D56). |
| LLM output | Structured outputs (`messages.parse`) using Pydantic models, validated on return, one repair retry |
| Prompts | Versioned **Jinja2** files; the prompt version is stored with every result |
| Units and parsing | **pint**; own parsers for German decimal commas, "×" dimensions, inch fractions (½, ¼, ⅜), gauge ↔ outer diameter (ISO 6009), synonym dictionaries. **In the core**, so node and hub parse identically. |
| Identifiers | Own GS1 mod-10 check-digit validator (core) |
| Category templates | **Hub registry** (database tables; §7.2). Seeded from YAML (`pyyaml`) in the core. The core holds the Pydantic `TemplateDefinition` model and loader. The client syncs the current definition per category to each node as plain JSON (D52). |
| Signatures and tokens | **PyJWT[crypto]** (uses `cryptography`) for Ed25519 JWS, used for **hub assertions only** (node key; D52 removed the hub-signed bundles). Algorithm pinned to `EdDSA` with the key type fixed to Ed25519 (PyJWT 2.14 does not know the RFC 9864 name `Ed25519`); `none` and HMAC never accepted. Requirements are plain JSON validated by a strict schema. |
| Auth | **Node:** local accounts (`pwdlib[argon2]`), opaque bearer tokens hashed in the node DB. **Hub:** supplier and operator accounts the same way; purchasers only via **token exchange** (§17). `HTTPBearer` dependencies check role and tenant. |
| Architecture checks | **import-linter** contracts: `hospital_node` ⟂ `supplier_hub`; `equivalence_core` imports no app, no `llm_client` and no FastAPI/SQLAlchemy/anthropic; `llm_client` imports no app and no domain code; both apps reach the Anthropic SDK only through `llm_client`; the demo client imports neither app. |
| API clients | Swagger UI on each service (`:8001/docs` node, `:8000/docs` hub). **`tools/demo-client`**: typer + httpx + rich CLI that plays purchaser (node + hub) and supplier (hub), bridging the two services exactly as the SPA will. |
| Dev dependencies (root) | `pytest`, `httpx`, `ruff`, `mypy`, `import-linter` |

**Tooling**

- **Makefile:** `setup`, `keys` (dev signing keys), `seed`, `dev` (hub :8000 + node :8001 together), `dev-hub`, `dev-node`, `demo-node`, `test`, `lint` (ruff, mypy, import-linter), `eval`, `demo`. Every Python target runs through `uv run`.
- **Per-service `.env.example`:**
  - `apps/hospital-node/.env.example`: `NODE_TENANT_ID`, `NODE_SIGNING_KEY_FILE`, `NODE_SIGNING_KID`, `HUB_AUDIENCE`, `ANTHROPIC_API_KEY` (the hospital's own), `NORMALIZE_MODE=llm|rules`, `NORMALIZE_BATCH_SIZE`, `EGRESS_DENY_ATTRIBUTES`, `SHARE_PRODUCT_HINTS`, rate limits, `EGRESS_DAILY_ALERT_PER_USER`, `NODE_SEED_PASSWORD`, `DATABASE_URL`, `APP_ENV`.
  - `apps/supplier-hub/.env.example`: `ANTHROPIC_API_KEY`, `LLM_MODE=anthropic|fake`, model and effort per pipeline, `MAX_ROUNDS`, `HUB_AUDIENCE`, `CORS_ORIGINS`, `DATABASE_URL`, `APP_ENV`.
- `.gitignore`: `data_examples/`, `.secrets/`, `var/`, `.env`, `charts/.tools/`.
- `architecture/ARCHITECTURE.md` (this document) and a README with the demo script.

## 6. Repository layout and modules

```
sanovio/
  pyproject.toml              # workspace root: members, dev deps, ruff/mypy/import-linter config
  uv.lock  .python-version  Makefile  README.md  .gitignore
  architecture/               # ARCHITECTURE.md (the design), data-model.md (all tables), charts.md (diagram inventory)
  packages/
    llm-client/src/llm_client/    # LLMClient interface, Anthropic adapter, FakeLLM, prompts, pricing
    equivalence-core/src/equivalence_core/
      templates/              # TemplateDefinition model + loader; seed/*.yaml (the three starting templates)
      parsers/                # numbers (German), dimensions, inch fractions, gauge, packaging, synonyms
      identifiers.py          # GS1 mod-10, data-quality checks
      validation.py           # a typed value checked against its attribute definition
      comparators.py          # exact, tolerance, same_or_finer, same_or_more, gauge_diameter
      facts.py                # precedence per side, family → variant merge, canonical JSON, record_hash
      verdict_rules.py
      identifier_evidence.py    # SAME_TRADE_ITEM | NO_INFORMATION (D51); never returns a mismatch
      exchange/
        requirement.py        # RequirementPayload (extra="forbid"), ProductHints, requirement_hash
        assertion.py          # HubAssertion claims model
        jws.py                # sign(claims, private_key, kid, typ) / verify(token, key_lookup, typ, aud) (Ed25519 only)
  apps/
    hospital-node/
      pyproject.toml  alembic.ini  .env.example
      src/hospital_node/
        main.py               # app factory; lifespan loads secrets and normalizes changed articles (D56)
        alembic/  seed/       # migrations and the demo datasets, shipped inside the package
        core/                 # settings, db, clock, security (node tokens), secrets loader, migrations
        models/  schemas/
        api/v1/               # auth, articles, users, requirements, hub_assertions, reference, egress, templates, admin
        services/             # articles (category, corrections), facts (the one write path), normalization
                              # (rules | llm), projection, requirement_builder, assertion_signer,
                              # reference_link (preview / set / undo), egress_log (also the rate limits),
                              # llm_calls, seed, auth, user_directory, template_sync
        llm/                  # normalize_article pipeline + prompt (runs at seed/startup only)
        cli.py                # keygen, migrate, seed, create-user
      tests/                  # unit/, integration/
    supplier-hub/
      pyproject.toml  alembic.ini  alembic/  .env.example
      src/supplier_hub/
        main.py
        core/                 # settings, db, security (hub tokens, supplier logins), secrets loader (Anthropic key)
        models/  schemas/
        api/v1/               # auth, token_exchange, admin (tenants, keys), catalog, search, assessments, supplier, dev
        services/             # tenants_keys, token_exchange, requirement_intake, candidate_search (product hints), projection,
                              # assessment, questions, enrichment, resolution,
                              # attribute_registry (proposals, curation), templates (current definitions)
        domain/               # state_machine, stop_conditions
        llm/
          client.py  anthropic_client.py  fake_client.py  outputs.py
          pipelines/          # normalize_family, judge, extract_answer, propose_attribute, simulate_supplier
          prompts/            # *_v1.j2
        jobs/                 # NORMALIZE_ITEM, ASSESS, EXTRACT_ANSWERS, PROPOSE_ATTRIBUTE, SIMULATE_SUPPLIER, REBUILD_PROJECTION
        cli.py                # seed, create-operator, register-tenant
      seed/                   # suppliers, users, catalog families/variants, hidden datasheets, tenants
      evals/                  # golden.jsonl, run.py
      tests/
  tools/
    demo-client/src/demo_client/   # typer + httpx + rich; scenario scripts driving node + hub
  tests/e2e/                  # starts hub + node(s) in-process, runs scenarios through the demo client
  charts/                     # PlantUML sources + rendered SVG/PNG
  .secrets/                   # dev keys from `make keys` (git-ignored)
  var/                        # SQLite files (git-ignored)
```

### 6.1 Modules

**`packages/equivalence-core`** — shared, plain Python; imports no web framework, database or LLM library.

| Module | Responsibility |
|---|---|
| `values.py` | the typed value shapes (A.0 of the data model); `AttributeValue` is the same union without identifiers, used by the requirement |
| `hashing.py` | canonical JSON and SHA-256 behind `record_hash`, `requirement_hash` and `definition_hash` |
| `ids.py` | random `article_ref` and the id patterns (Crockford base32) |
| `quality.py` | `DataQualityIssue` flags (checksum and GTIN/EAN problems, gauge/diameter disagreement) |
| `templates/` | `TemplateDefinition` model, YAML seed loader (attribute definitions kept separate from per-template settings, as in the hub registry), `definition_hash`, category keywords |
| `parsers/` | German decimals, units (pint), `×` dimensions, inch fractions, gauge ↔ outer diameter, packaging, synonym matching, and `extract_attributes` for a whole article name |
| `identifiers.py` | fixed identifier-scheme lists per side; GS1 check digit; problems between identifiers (`GTIN_EAN_MISMATCH` …) |
| `validation.py` | `validate_value`: a typed value checked against its attribute definition (enum spellings become codes, numbers the canonical unit), used for everything the parsers did not produce |
| `facts.py` | source precedence per side, family → variant merge, identifier facts kept as a set, `record_hash` |
| `comparators.py` | exact, tolerance, same-or-finer, same-or-more, gauge ↔ diameter |
| `verdict_rules.py` | per-attribute results → verdict |
| `identifier_evidence.py` | `SAME_TRADE_ITEM` or `NO_INFORMATION`; never a mismatch |
| `exchange/requirement.py` | strict `RequirementPayload` (`extra="forbid"`), `requirement_hash` |
| `exchange/assertion.py` | `HubAssertion` claims model |
| `exchange/keys.py` | Ed25519 key generation, owner-only storage, public JWK and RFC 7638 fingerprint |
| `exchange/jws.py` | Ed25519 `sign` / `verify`: pinned algorithm, `typ`, `aud`, expiry against an injected clock, `kid` bound to the issuer |

**`apps/hospital-node`**

| Layer | Modules |
|---|---|
| `core/` | settings, database (SQLAlchemy + Alembic), injected clock, node-token security, secrets loader (node private key; the hospital's Anthropic key comes from settings) |
| `models/` + Alembic | `users`, `api_tokens`, `hospital_articles`, `article_facts`, `article_projection`, `egress_log`, `llm_calls`, `template_versions` |
| `llm/` | `normalize_article` pipeline, prompt and output schema; the client itself comes from `packages/llm-client` — used only at ingestion |
| `services/` | `articles` · `facts` (the single fact write path) · `normalization` (batch at ingestion, re-run at startup for changed articles, parser/LLM merge) · `projection` · `requirement_builder` · `egress_log` (also the per-user rate limits) · `llm_calls` · `assertion_signer` · `reference_link` (preview / set / undo) · `auth` · `user_directory` · `template_sync` · `seed` |
| `api/v1/` | `auth`, `articles`, `users`, `requirements`, `hub_assertions`, `reference`, `egress`, `templates`, `admin` |
| `cli.py` | `keygen`, `migrate`, `seed`, `create-user` |

The node has **no job queue** (D53). Until the hub exists, `template_sync` loads definitions from the core YAML; afterwards the client pushes the hub's definitions through the same `PUT /templates`.

**`apps/supplier-hub`**

| Layer | Modules |
|---|---|
| `core/` | settings, database, hub-token security, secrets loader (Anthropic key) |
| `models/` + Alembic | tenants and identity, catalog and facts, attribute registry, assessment loop, `jobs`, `llm_calls` |
| `services/` | `tenants_keys` · `token_exchange` · `requirement_intake` · `candidate_search` · `projection` · `catalog` · `templates` · `attribute_registry` · `assessment` · `questions` · `enrichment` · `resolution` |
| `domain/` | `state_machine`, `stop_conditions` |
| `llm/` | `LLMClient`, Anthropic adapter, FakeLLM; pipelines `normalize_item`, `judge`, `extract_answer`, `propose_attribute`, `simulate_supplier` |
| `jobs/` | queue + worker; handlers `NORMALIZE_ITEM`, `REBUILD_PROJECTION`, `ASSESS`, `EXTRACT_ANSWERS`, `PROPOSE_ATTRIBUTE`, `SIMULATE_SUPPLIER` |
| `api/v1/` | `auth`, `token_exchange`, `admin`, `catalog`, `search`, `templates`, `assessments`, `supplier`, `dev` |
| `cli.py` | `seed`, `create-operator`, `register-tenant` |

**`packages/llm-client`** — the `LLMClient` protocol with its typed request and call record, the Anthropic adapter (adaptive thinking, effort, structured outputs, prompt caching, one repair retry), `FakeLLM`, per-model prices and the Jinja2 prompt loader. Each service keeps its own prompts and writes the returned call record to its own `llm_calls` table.

**`tools/demo-client`** — one session holding both tokens, silent re-exchange on 401, template sync, one script per scenario. **`tests/e2e`** — hub and node in-process, with a second tenant at the hub.

**Enforced boundaries** (import-linter): the node and the hub never import each other; the core imports neither; the node imports no HTTP client; the demo client imports neither app.

## 7. Templates and attribute registry

### 7.1 Category templates, based on the example data

Every attribute has: a key, type, unit, **criticality** (critical / major / minor), a **comparison rule**, a question hint, synonyms and a **`shareable` flag** (whether the value may be part of a requirement sent to the hub; default true for technical attributes, false for commercial ones such as `units_per_order_unit`). Criticality levels are **proposals for the client to confirm** (client question 2). Output codes are language-neutral (e.g. `LUER_LOCK`); labels are German/English. Templates live in the **hub's attribute registry** (§7.2). The three below are seeded from YAML; the hub registry is authoritative and the node holds a synced copy of the current definition (D52).

| Template | Attributes (criticality · rule) |
|---|---|
| **generic_consumable** (all categories; the others add to it) | mdr_class (critical · exact), sterile (critical · exact), single_use (critical · exact), latex_free (critical · exact), dehp_free (major · exact), pvc_free (minor), bpa_free (minor), standards (major · must include the hospital's), units_per_order_unit (minor · shown as info; **not shareable**) |
| **syringe_single_use** | nominal_volume_ml (critical · exact), usable_volume_ml (minor · same or more), connector `LUER\|LUER_LOCK\|NRFIT\|CATHETER\|ORAL` (critical · exact), cone_position `CENTRIC\|ECCENTRIC` (major · exact), design `TWO_PART\|THREE_PART` (major · exact), graduation_step_ml (major · same or finer), special_scale e.g. heparin IU (major · exact if present), needle_included (critical · exact), safety_mechanism (critical · exact), pump_compatible (major · must hold if the hospital's does), light_protected (major · exact), silicone_oil_free (minor), barrel/plunger/stopper material (minor · semantic), ISO 7886-1 (major) |
| **hypodermic_needle** | gauge (critical · exact; **authoritative**), outer_diameter_mm (cross-check only, not compared separately: filled in from gauge when missing; if a source's OD disagrees with its own gauge, a data-quality flag is raised and gauge wins), length_mm (critical · exact), inner_diameter_mm (major · ±0.02), wall_type `REGULAR\|THIN` (major · exact), bevel `LONG\|SHORT\|BLUNT` (major · exact), purpose `INJECTION\|FILLING\|FILTER\|IRRIGATION` (critical · exact), filter_um (critical · exact if present), safety_mechanism (critical · exact), connector (critical · exact), colour_code (minor · derived), ISO 7864 (major) |

Articles in uncovered categories (gloves, masks…) use `generic_consumable` alone and are marked `limited_template: true`.

**Seed layout** (`equivalence_core/templates/seed/`): `attributes.yaml` holds each attribute's definition once — type, unit, options, labels and synonyms — and each template file lists only its per-category settings (criticality, rule, tolerance, `shareable`) plus the **category keywords** used to suggest a category from an article name (`Einmalspritze`, `Spritze` → syringe; `Kanüle` → needle). When several keywords match, the one appearing first in the name wins, because German article names lead with the noun. When a whole name is scanned, only the listed synonym phrases are matched, never bare option codes, so a short code such as `I` cannot be picked up by accident.

### 7.2 Attribute registry: who owns templates, and how new attributes are added

- **Owner: the hub.** The registry has two parts:
  - **Attribute definitions:** key, type, unit, enum options, DE/EN labels, synonyms, question hint.
  - **Category templates** (one current definition per category, D52): which attributes a category uses, each with criticality, comparison rule and `shareable` flag.

  Criticality belongs to the template, not the attribute, because one attribute can be critical in one category and minor in another.
- **Who sets criticality:** only the curator (operator role; client question 20 may move this to a hospital panel).
  - The seed levels are our proposal for the client to confirm (client question 2).
  - The LLM never sets criticality: `propose_attribute` has no criticality field, and the judge decides only MATCH / DEVIATION / MISMATCH / UNKNOWN per attribute.
  - Suppliers never set it: they are the party being judged.
  - Individual purchasers never set it: verdicts must stay comparable across hospitals. Their case-by-case control is an OVERRIDDEN resolution with a note.
- **Seed:** the three templates above are YAML files in the core (`templates/seed/`) and are loaded into the registry at `make seed`. From then on the registry is the source of truth; YAML is used only for seeding and tests.
- **Code stays in the core:** value types, parsers and comparison rules. A new attribute must use an existing type and rule; a new rule needs a software release.
- **Nodes get copies:** the client fetches the current definition from the hub and installs it at the node as plain JSON, validated against the core model (D52).

**How a new attribute appears, from question to shared data**
1. **A question without an attribute.** A purchaser adds a free question, or the judge raises an extra concern (`attribute_key = NULL`). Example: "Does the pack include a peel-off documentation label?"
2. **Proposal** (job PROPOSE_ATTRIBUTE, pipeline `propose_attribute`). The pipeline compares the question with the registry and returns either:
   - an **existing key**, which the question simply takes, or
   - a **new definition**, e.g. `peel_off_label`, bool, labels "Abziehbares Dokumentationsetikett" / "Peel-off documentation label", or
   - an **identifier definition** (`gtin`, `supplier_article_no`, `pzn`, `himiv`; registry `kind = IDENTIFIER`) when the question asks for a product number rather than a property. The question takes that key, **no comparable attribute is created**, and the answer becomes an identifier fact (D50).

   Labels must be neutral: a validator rejects product, brand, supplier, hospital or alias names. The result goes to `attribute_proposals`. `send-questions` answers 409 `ATTRIBUTE_PROPOSAL_PENDING` until proposals are done, usually a few seconds.
3. **Provisional attribute.** When the question is sent, a new definition becomes an `attribute_definitions` row with status `PROVISIONAL`, and the question gets its key and a typed `expected_answer`. Withdrawn drafts never create attributes.
4. **The supplier answers** as for any question → `item_facts` rows with the provisional key (variant or family scope).
5. **Visible to all hospitals at once.** Provisional values appear as **additional information** (`item_search_projection.additional_attributes`) in:
   - catalog views
   - search candidates
   - every hospital's comparison view for that variant

   They are never hard filters, never judged, never asked automatically and never part of requirements.
6. **Curation (operator only):**
   - **Approve:** final key and labels, category, criticality, comparison rule, `shareable` flag, synonyms.
   - **Merge** into an existing attribute: facts are re-added under the target key and the old ones superseded.
   - **Reject:** the attribute becomes `DEPRECATED`; its facts are kept for audit but no longer shown.

   Suppliers and purchasers never set criticality.
7. **Approve.** The curator adds the attribute to the category definition (D52: no version bump, no signing).
8. **Other hospitals.** The client installs the updated definition at their nodes, and article projections rebuild with `peel_off_label` listed as unknown. As a major attribute it becomes a purchaser question in their next assessments. BD's value already exists, so BD is not asked again.

**Template changes in running work (D52)**
- **No pinning, no version negotiation.** The hub keeps one current definition per category. Each `assessment_round` stores the definition it judged inside `input_snapshot`, so any past round stays replayable and auditable even after the curator adds an attribute.
- **Effect of a change mid-loop:** the next round of an open assessment simply uses the new definition; a newly added attribute shows up as an unknown and becomes a question, which is the desired behaviour for a prototype with one curator. `input_hash` covers the requirement and the supplier record, so the added attribute changes the requirement and the round counts as progress.
- **Sync:**
  1. After the token exchange, the client compares `GET /templates` at the hub and at the node (per category, by `updated_at`).
  2. If the hub's is newer, it fetches the definition and calls `PUT /templates` at the node.
  3. The node validates the definition against the core model, replaces the stored definition for that category and rebuilds its projections (D52: unsigned, no version history). The rebuild runs in the same transaction as the install (ten articles, no LLM call), so there is no pending state and no extra error code; attributes the new definition adds simply start out unknown. Installing a definition never re-reads article names: only a content change does that (D56).
- **Hospital control over egress:** the node setting `EGRESS_DENY_ATTRIBUTES` withholds attributes even when the template marks them `shareable: true`. They are listed in the requirement's `withheld_attributes`, judged UNKNOWN, and never turned into purchaser questions.
- **Limit:** a hospital can't record its own value for a provisional attribute until the curator approves it into the category definition.

## 8. Core idea: compare attribute by attribute

1. **Facts per side, produced where the data lives:**
   - **Hospital article (node):** CSV-shaped fields map directly (MDR class → fact, packaging → columns). The `name` goes through **normalization at the node**, which returns facts with quotes (e.g. "10 ml" → nominal_volume_ml=10, "Luer-Lock" → connector=LUER_LOCK, "steril" → sterile=true) and a category suggestion.
     - **When it runs (D56):** once, in a batch, at `make seed` / article import, and again at startup for any article whose `content_hash ≠ normalized_hash`. A restart with unchanged articles makes **no** LLM call, and serving traffic never does — so the node needs no key to answer requests, only to ingest.
     - **Modes (`NORMALIZE_MODE`):**
       - `llm` (**default**): `normalize_article` (claude-sonnet-5) with **the hospital's own API key**, batched (`NORMALIZE_BATCH_SIZE`, default 25 articles per call) with the category template in a cached prompt prefix. Returns per article: facts with the exact quote they came from, plus a category suggestion.
       - `rules` (fallback, no key): core parsers + synonym dictionaries + the keyword → category table (Einmalspritze/Spritze → `syringe_single_use`, Kanüle → `hypodermic_needle`, else `generic_consumable`).
       - **The two are combined, not alternatives.** The parsers always run; on any disagreement about a number with a unit the parser wins, because that is where models slip (D8). The LLM adds what regex cannot reach — implied booleans, materials, and a better category guess for irregular names.
     - **When:** on article creation/seed and when content changes. Parameters exist before any search.
     - **Category:** stored with `category_source` (`RULES`, `LLM_SUGGESTED` or `PURCHASER`), `category_set_by`, `category_set_at`. A re-run may replace `RULES`/`LLM_SUGGESTED`, never `PURCHASER`. Search warns while unconfirmed.
     - **Corrections:** `PUT /articles/{id}/facts/{attribute_key}` at the node (source `PURCHASER_ANSWER`), without a question round.
     - **Unknowns are never guessed:** anything the name doesn't say stays unknown until a reference link, a correction or a purchaser question fills it.
   - **Supplier family (hub):** description + properties bullets → family-level facts through `normalize_item` (claude-sonnet-5, our key). Catalog text is supplier-published, not hospital data. Category follows the same `category_source` rule; the supplier can confirm it.
   - **Supplier variant (hub):** table fields map to variant-level facts through the core parsers.
   - **Brand-name spellings are normalized before comparison** (core synonym dictionaries, same on both sides):
     - "Luer-Lock", "Luer Lock", "BD Luer-Lok™", "LL" → `LUER_LOCK`
     - "Luer", "Luer-Ansatz", "Luer-Slip" → `LUER`
     - "NRFit®" → `NRFIT`; "zentrisch" → `CENTRIC`; "dünnwandig" → `THIN`

     Unrecognized values stay text and go to the judge's semantic path, so a spelling variant can never become a false critical mismatch.
   - **Effective record** of a variant = variant facts over family facts (§9). Results are cached by content hash.
2. **Current product (node, optional, set from search results):** in the single candidate search (§15), the purchaser can mark a result as **"this is our current product"**.
   - The client fetches that variant's effective attributes from the hub (`GET /catalog/variants/{id}/attributes`) and passes them to the node.
   - The node shows a **preview**: which unknown attributes get filled and which known values conflict. Conflicting values need an explicit choice; `PURCHASER_ANSWER` facts always win.
   - Accepted values become `REFERENCE_ITEM` facts with the hub variant and fact IDs, stored **as reported by the client** without a hub signature. A purchaser can enter any value as a correction anyway (D37).
   - **Identifier facts are never copied by the reference link**: the supplier's GTIN identifies the supplier's trade item, not the hospital's article row, and copying it would let the hospital's record claim an identifier it never had — and then match itself in `identifier_evidence`. The preview lists them as information only; a purchaser who really wants one enters it explicitly as a `PURCHASER_ANSWER` identifier fact.
   - **The link is stored only at the node.** The hub is never told which product a hospital currently buys.
   - One current product per article: choosing another replaces the previous values, and `DELETE /articles/{id}/reference` undoes it.
   - Always chosen by the purchaser. Identifier matches from product hints (§15) only highlight a candidate, never link it.
3. **Identifiers: asymmetric evidence, never a comparison (both sides):**
   - Identifiers are **identifier-typed facts** carrying `scheme`, `value` and a `checksum_valid` flag (GS1 mod-10; `NULL` for schemes without a check digit). `false` identifiers are never used for linking, hints or evidence.
   - Problems *between* identifiers are stored on the article as `data_quality_issues` (`GTIN_EAN_MISMATCH`, `GTIN_CHECKSUM_INVALID`, `EAN_CHECKSUM_INVALID`).
   - **Hospital identifiers stay on the node by default.** A hospital can enable `SHARE_PRODUCT_HINTS` (D47). The requirement then also carries brand, manufacturer article number and GTIN (only with a valid check digit), which the hub uses to highlight exact catalog matches in search.
   - Prices, quantities and internal IDs never leave the node at all. **Article names leave once, to the hospital's own LLM account, during normalization** (D42, D56) — never to the hub, and never with any other field attached.
   - Catalog identifiers (article no., PZN, HiMiV) live at the hub as identifier facts on the variant. A supplier can also be **asked** for one; the answer is check-digit validated and becomes an `item_facts` row with `source = SUPPLIER_ANSWER` (D50).
4. **Comparison (hub, on the requirement):**
   - The hospital side of every comparison is the **requirement's attribute values**; the supplier side is the variant's effective record.
   - **`identifier_evidence` runs first (D51).** If a check-digit-valid GTIN — or manufacturer article no. together with the manufacturer — matches on both sides, the result is `SAME_TRADE_ITEM`: the round stops there with verdict EQUIVALENT, no comparators and no judge call. Otherwise the result is `NO_INFORMATION` and identifier facts are dropped from the comparison entirely. They can never yield MISMATCH, an unknown or a question. The hospital side is present only when the hospital sends product hints (D47); with hints off the same check runs in the client, which holds both sides, and nothing about it reaches the hub.
   - **Deterministic comparators run next and are final** (`equivalence_core/comparators.py`): exact enums, booleans and numbers, tolerances, same-or-finer / same-or-more, list inclusion, required-if-the-hospital-needs-it. Every template attribute gets one judgment, which is what the round stores (data-model H.14).
   - **Statuses.** `MATCH`, `ACCEPTABLE_DEVIATION`, `MISMATCH` and `UNKNOWN` are the four the judge may also return. Three more come only from the comparators:
     - `UNAVAILABLE` — a side answered "cannot provide". It blocks like an unknown, but §11's stop condition 4 has to tell the two apart.
     - `INFO` — `info_only` and `derived` attributes (`units_per_order_unit`, `outer_diameter_mm`, `colour_code`). Shown, never counted, never asked: the outer diameter is a cross-check of the gauge, not a comparison of its own (§7.1).
     - `NEEDS_JUDGE` — deliberately left undecided: `semantic` rules, and any pair whose value types don't line up (an enum against free text), so a spelling variant can never become a false critical mismatch.
   - Each judgment also records **which side is missing** and whether the gap **may be asked**: attributes the hospital withheld (`EGRESS_DENY_ATTRIBUTES`, §16) are judged `UNKNOWN` and never turned into a question.
   - **The LLM judge handles only attributes the comparators left undecided** (e.g. "nicht hergestellt mit Latex" vs "latexfreier Stopfen"). For each: `MATCH | ACCEPTABLE_DEVIATION | MISMATCH | UNKNOWN`, confidence, rationale, cited supplier fact IDs and requirement attributes. `verdict_rules.apply_judgments` merges them: it fills only `NEEDS_JUDGE` entries and reports the discarded ones, so a judgment for an attribute the comparators already decided can never change a verdict.
5. **The verdict comes from rules in code (core):**

   | Condition (checked in order) | Verdict |
   |---|---|
   | `identifier_evidence` = `SAME_TRADE_ITEM` | **EQUIVALENT** (reason `SAME_TRADE_ITEM`, no judge call; still confirmed by a purchaser) |
   | Any critical MISMATCH | **NOT_EQUIVALENT** (early stop, no questions) |
   | Any critical/major UNKNOWN | **INSUFFICIENT_DATA** |
   | Any major MISMATCH, or a deviation on a critical/major attribute | **EQUIVALENT_WITH_DEVIATIONS** |
   | Otherwise | **EQUIVALENT** (minor unknowns listed but don't block) |

   "UNKNOWN" above means any gap: `UNKNOWN`, `UNAVAILABLE`, or an attribute that was left to the judge and never judged (a failed or skipped judge call degrades to INSUFFICIENT_DATA rather than to a verdict). `verdict_rules.decide` returns the verdict together with the mismatches, the accepted deviations, the blocking gaps and — separately — those the other side already declared unavailable, which is what §11's stop conditions and the question builder read.

   The LLM's own overall verdict is kept as a cross-check; disagreement is flagged.
6. **Missing data and who gets asked:**
   - **Unknown on the supplier side** → question to the **supplier** (hub).
   - **Unknown in the requirement** → question to the **purchaser**, answered at the node and returned in a new requirement (§11). Or the purchaser marks the current product.
   - Questions are phrased in the judge call (template fallback). Supplier-facing questions use the supplier's language and **never reveal the hospital's values, name or identity** (only the alias).
   - Up to 3 extra concerns outside the template. A question raised for one of them starts an attribute proposal (§7.2).
7. **Guardrails:**
   - Schema validation on every LLM output; citations to unknown fact IDs → UNKNOWN; the LLM never supplies values.
   - Supplier text and requirement values are passed inside marked data blocks (prompt-injection defence).
   - Code decides the verdict and a purchaser confirms.
   - Every requirement is validated at the hub against the current template schema (unknown fields rejected). Hub assertions are signature-checked (§17).

## 9. Enrichment: add facts, never overwrite

- **Facts only grow, on both sides:**
  - **Node `article_facts`:** sources `HOSPITAL_MASTER | EXTRACTION (method RULES or LLM) | REFERENCE_ITEM | PURCHASER_ANSWER | UNAVAILABLE`.
  - **Hub `item_facts`:** scope `FAMILY | VARIANT`; sources `CATALOG | EXTRACTION | SUPPLIER_ANSWER | UNAVAILABLE`.
  - Each fact holds: attribute, typed value + unit, source, quote, answer/question reference, author, time, model and prompt version, `superseded_by`.
- **Precedence (core `facts.py`):**
  - Supplier side: answer > variant catalog > family catalog > extraction.
  - Hospital side: purchaser answer > reference item > article master data > extraction.
  - **Identifier facts are exempt from precedence:** every live row per scheme is kept (a base-unit and a carton GTIN coexist) and lands in the projection's `identifiers` section, not in `attributes`.
- **Where supplier answers apply:** by default the **variant**; "applies to the whole product family" writes a family-scoped fact.
- **Answer form** (supplier at the hub; purchaser at the node): typed input, optional comment, "cannot provide".
  - A typed value becomes a fact directly.
  - Supplier comment only → `extract_answer` at the hub; unclear → stays UNKNOWN, follow-up next round.
  - Purchaser answers are typed only at the node (no LLM needed; the purchaser picks from the expected answer type).
  - "Cannot provide" → `UNAVAILABLE` (never asked again).
  - **Identifier answers** (question whose attribute is an identifier definition): the value is check-digit validated and stored as an identifier-typed fact with `source = SUPPLIER_ANSWER` and its `answer_id`. It feeds `identifier_evidence` and search matching only — never a comparator, an unknown or the judge prompt. An invalid check digit is kept with `checksum_valid = false` and never used. The node mirror is `PUT /articles/{id}/facts/{attribute_key}` with an identifier value (source `PURCHASER_ANSWER`). (D50, D51)
- **Sources are visible everywhere:** every value returned by either service carries its fact ID, source, quote, author and time. `GET /supplier/catalog/families/{id}` (hub) returns the fact history of a family and its variants; `GET /articles/{id}` (node) the article's.

## 10. Data placement and storage

Full column types and example rows: [data-model.md](data-model.md).

**Placement principle:** data lives with the party it describes. Anything about the hospital's purchasing stays on the node; anything about supplier products and the supplier conversation lives at the hub. The two databases are joined **only by opaque IDs** carried by the client (`article_ref`, `hub_subject_id`, `variant_id`), never by foreign keys.

**Hospital node tables (8), one database per hospital:**

| Group | Table | Purpose |
|---|---|---|
| Identity | `users` | purchasers and node admins; each with a random `hub_subject_id` |
| | `api_tokens` | hashed node bearer tokens |
| Master data | `hospital_articles` | the article list (CSV-shaped fields), `article_ref`, category + provenance, reference link, data-quality issues |
| Facts | `article_facts` | attribute **and identifier** values with sources; only ever added to |
| | `article_projection` | current resolved attributes + `identifiers` section per article (derived) |
| Exchange | `egress_log` | every requirement and hub assertion the node issued, with exact content (records issuance, not delivery); per-user counts for rate limits and alerts |
| | `llm_calls` | every `normalize_article` request the node made, with tokens and cost (N.10); the hospital's audit trail for what left to its LLM account |
| Templates | `template_versions` | the current definition per category, synced from the hub by the client (D52: unsigned, no history) |

Trust material is not in the node database: the node's private key and the hub's public key are files loaded at startup (§17).

**Supplier hub tables (21), one multi-tenant database:**

| Group | Table | Purpose |
|---|---|---|
| Tenants & identity | `organizations` | hospital tenants, suppliers, operator; supplier-facing alias and disclosure flag for hospitals |
| | `tenant_signing_keys` | hospital public keys (JWK) with kid, validity and revocation |
| | `hospital_principals` | pseudonymous purchaser subjects per tenant (first/last seen) |
| | `users` | supplier users and operators (passwords) |
| | `api_tokens` | hashed hub tokens: supplier/operator logins and exchanged purchaser tokens |
| | `used_assertion_jtis` | replay protection for assertions |
| Attribute registry | `attribute_definitions` | every attribute or identifier scheme ever defined: `kind`, type, unit, options, labels, synonyms, status (`PROVISIONAL`, `APPROVED`, `DEPRECATED`) |
| | `category_templates` | one current definition per category: attributes with criticality, rule, shareable flag (D52) |
| | `attribute_proposals` | LLM proposals from questions without an attribute; curation outcome |
| Catalog | `product_families`, `product_variants` | supplier catalogs (identifiers are facts, H.10) |
| Facts & read model | `item_facts`, `item_search_projection` | supplier attribute and identifier facts; resolved variant rows with an `identifiers` section (derived) |
| Assessment loop | `requirements` | requirements received for assessments (search requirements are not stored) |
| | `assessments` | keyed by `(hospital tenant, article_ref, variant)`: status, verdicts, current requirement, pseudonymous assignee |
| | `assessment_rounds` | one judgment per round with requirement, input snapshot, model and prompt version |
| | `questions` / `answers` | questions to supplier or purchaser; supplier answers |
| | `events` | timeline and audit per assessment (actor: user or principal) |
| Infrastructure | `jobs`, `llm_calls` | work queue; every LLM request with tokens and cost |

**Ownership and access**
- **Node:** single hospital; any purchaser can view articles. The node keeps **no copy of assessments**: lists, status, verdicts and assignees come from the hub, and the client joins them to local articles by `article_ref` and to local user names by `hub_subject_id`.
- **Hub:** an assessment belongs to the **hospital tenant** (`hospital_tenant_id`); the supplier organization is the counterparty.
  - Any principal of that tenant can act on it; any user of the supplier organization can answer its requests.
  - Accountability at the hub uses pseudonymous principals (`created_by_principal_id`, `resolved_by_principal_id`, `assigned_to_principal_id`). Mapping a principal to a person is possible **only at the node** (`users.hub_subject_id`).
- Four-eyes approval is not enforced (client question 5).

**What the hub can and cannot know about a hospital**

| Hub knows | Hub never receives |
|---|---|
| tenant ID and operator-visible hospital name; alias | article names, internal IDs (names go only to the hospital's **own** LLM account at ingestion, D42/D56 — never here) |
| `article_ref` (random, stable per article) | EAN and identifiers with invalid check digits |
| brand, manufacturer article no., valid GTIN, **only if the hospital enables product hints** | brand, manufacturer article no. and GTIN while product hints are off (default) |
| template attribute values and unknowns in submitted requirements | prices, annual quantities, order units |
| pseudonymous purchaser subjects | purchaser names, e-mails, passwords |
| which variants were assessed for an `article_ref`, and the verdicts | which product the hospital buys today (reference link) |

**Residual risk (documented, accepted for the prototype):** a precise attribute set can hint at the current product (e.g. values copied from a reference link). Mitigations:
- Requirements carry only coarse origins (`REFERENCE`, not the variant).
- Hub operator access is audited, and suppliers never see requirements.
- Catalog reads, such as fetching a variant's attributes when the purchaser marks the current product, are not persisted beyond short-retention access logs.

The random `article_ref` is a reference, not an anonymization measure: the attribute set can act as a quasi-identifier (EDPB/ENISA).

**Current values: the projections (read models)**
- Built by the core resolver in four steps: drop superseded rows → keep the highest-precedence source per attribute → variant over family (hub) → list template attributes still missing.
- **Node `article_projection`:** feeds `GET /articles/{id}`, the requirement builder and local article search.
- **Hub `item_search_projection`:** variant rows only; feeds candidate search, round snapshots and catalog browsing.
- Never the source of truth; `REBUILD_PROJECTION` recomputes on fact changes (a family change rebuilds its variants).
- **Hashes** (core: SHA-256 over canonical JSON):
  - `record_hash` covers all resolved attributes of a projection row **and its identifier facts**, so a newly answered GTIN changes the supplier `record_hash` and the next round is not rejected as "no progress" — it is exactly the round in which `identifier_evidence` may now return `SAME_TRADE_ITEM`.
  - The node also stores `requirement_hash` over the shareable subset only, for its own change detection, **plus `product_hints` when the hospital sends them** (same reason). The hub computes the same core hash over the requirement it receives.
  - **The no-progress check runs at the hub** on `requirement_hash` + supplier `record_hash` (§11, H.14).
- `attribute_fact_ids` traces values; `search_text` feeds later full-text/embeddings at the hub.

**Storage estimates (illustrative, not measured).** ~1M supplier variants / ~100k families at the hub; ~40k articles per hospital across ~50 hospital nodes / ~200 suppliers.

| Where | Data | Rows | Size |
|---|---|---|---|
| Node (per hospital) | `article_facts` (≈8 per article, +20% history) | ~400k | ~100 MB |
| Node | `egress_log` (≈30/day per purchaser) | ~150k/yr | ~250 MB/yr |
| Hub | `item_facts` (≈10 per variant, ≈15 per family, +20% history) | ~14M | ~3.5 GB + ~2 GB indexes |
| Hub | identifier facts inside `item_facts` (≈5 per variant) / `item_search_projection` | ~5M / ~1M | ~0.5 GB / ~1 GB |
| Hub | `requirements` (assessment requirements only) | ~250k/yr | ~0.5 GB/yr |
| Hub | `assessment_rounds` (100k assessments/yr) | ~200k/yr | ~4 GB/yr |
| Hub | `llm_calls` | ~600k/yr | ~12 GB/yr; needs a retention policy or object storage |

- **Node:** SQLite is enough for a single hospital (tens of thousands of articles, a handful of purchasers). Postgres only if the hospital prefers it.
- **Hub:** SQLite for the prototype; Postgres in production (GIN index on projection `attributes`).
- **The practical bottleneck is LLM cost at the hub:** normalization ≈ $0.01–0.02 per family (Sonnet 5); judgment ≈ $0.10–0.15 per round (Opus 5). Moving hospital normalization to rules removes the per-article LLM cost entirely.

**Search and vectors (later, hub only)**
- **Prototype:** deterministic search on the hub projection (§15); the node offers simple local article search (`q` on name/internal ID).
- **Next step, inside hub Postgres:** hard filters on projection JSON; German full-text + `pg_trgm`; `pgvector` over `search_text`; reciprocal rank fusion.
- **The semantic query text must come from the requirement** (canonical attribute rendering), not from article names, so hybrid search adds no new data leaving the node.
- **Vectors only find candidates; they never decide equivalence.** A dedicated vector database only beyond ~10–50M vectors, fed by an outbox.
- **Embeddings:** Voyage AI multilingual, or a local multilingual model (BGE-M3, multilingual-E5).

## 11. Assessment state machine (hub) and when the loop stops

```
                 purchaser creates (POST /assessments with requirement)
                                   │
                                   ▼
 ┌──────── retry ─────────── ┌───────────┐ ── decisive verdict ──────────────────────────► PROPOSED_RESOLUTION
 │                           │ ASSESSING │ ── INSUFFICIENT_DATA with askable gaps ──────► NEEDS_QUESTION_REVIEW
 FAILED ◄─ job retries ───── └───────────┘ ── round cap / no progress / blocking unavail. ► NEEDS_MANUAL_DECISION
            exhausted              ▲
                                   │ all supplier answers submitted (extract, then re-judge)
                                   │ or send-questions with no supplier questions
 NEEDS_QUESTION_REVIEW ── send-questions (no open PURCHASER questions) ──► AWAITING_ANSWERS ──┘
 PROPOSED_RESOLUTION ── confirm / override (reason) ──► RESOLVED
 PROPOSED_RESOLUTION ── request more info ──► NEEDS_QUESTION_REVIEW
 NEEDS_MANUAL_DECISION ── extra round ──► AWAITING_ANSWERS      NEEDS_MANUAL_DECISION ── manual verdict ──► RESOLVED
 any non-final state ── cancel ──► CANCELLED
```
(Rendered as a state diagram: [08](../charts/png/08_assessment_states.png).)

- **A round** = one judgment + its questions + all answers.
- **Purchaser-addressed questions (node ↔ hub via client):**
  1. The hub creates them with `addressee = PURCHASER`; the client shows them next to the article.
  2. The purchaser answers at the node: `PUT /articles/{id}/facts/{attribute_key}` with `hub_question_id`, or "cannot provide" → `UNAVAILABLE` fact.
  3. The client asks the node for a new requirement with `answered_question_ids`, and posts it to the hub: `POST /assessments/{id}/requirements`.
  4. The hub validates the requirement, sets `current_requirement_id`, and marks those questions `ANSWERED` (or `UNAVAILABLE` when the attribute is in `unavailable_attributes`) with `answered_in_requirement_id`.
  5. `send-questions` is refused (409) while PURCHASER questions are still `DRAFT`/`SENT`, or the purchaser withdraws them. If no supplier questions remain, the re-judge starts at once.
- **Supplier questions:** the round waits in AWAITING_ANSWERS until the supplier **submits the full batch** (drafts allowed; submit refused until every question has a value, comment or "cannot provide").
- **Stop conditions:**
  1. Decisive verdict → PROPOSED_RESOLUTION.
  2. `round_no ≥ MAX_ROUNDS` (3) → NEEDS_MANUAL_DECISION.
  3. **No progress:** `input_hash` = SHA-256(`requirement_hash` + supplier `record_hash` + **template definition hash**). Unchanged from the previous round → NEEDS_MANUAL_DECISION. (D52 replaced the version string with a hash of the definition itself, so a curator's change still counts as progress.)
  4. Every blocking gap UNAVAILABLE (on either side) → NEEDS_MANUAL_DECISION.
  5. Manual resolve, from any state except ASSESSING.
- **Cancel** from any non-final state.
- **Template definition:** the current one is used each round and the round records it in `input_snapshot` (D52). `send-questions` answers 409 while attribute proposals are pending.
- **Final verdicts:** EQUIVALENT, EQUIVALENT_WITH_DEVIATIONS, NOT_EQUIVALENT, UNDETERMINED. Resolution kind: `CONFIRMED | OVERRIDDEN | MANUAL`.
- **After resolve:** nothing is written to the node. The hub is the only record of assessments and verdicts, visible to every purchaser of the hospital; a hospital-side export of resolved decisions is a later feature (D49).
- **Assignee:** `PUT /assessments/{id}/assignee {subject_id}` sets `assigned_to_principal_id` (any principal of the tenant; event `ASSIGNED`). It doesn't restrict access.
- **Integrity:** allowed moves in one table (`supplier_hub/domain/state_machine.py`); every change writes an `events` row; `version` column for optimistic locking.

## 12. Background work

- **The hub runs a queue; the node does not (D53).** At the hub: job row in the same transaction as the state change; worker thread polls ~1s; conditional-UPDATE claim; retries ×3 with growing delay; stuck jobs requeued at startup; unique `dedupe_key`). The queue lives only in the hub app, not in the core, because the core has no database code.
- **Node chains:**
  - **The node has no queue (D53).** Articles are normalized in a batch at seed/import and at startup when stale (D56): parsers + one LLM call per batch → facts → projection. A single article created or edited later is normalized inline in that request.
  - Fact correction, purchaser answer, reference link → projection rebuild in the same transaction.
  - Template definition installed → rebuild every article of that category inside the installing transaction (a loop over ten articles), so a requirement either sees the old definition or the new one.
  - **Requirement building** reads the projection and refuses with 429 above the per-user rate limit.
- **Hub chains:**
  - family/variant seeded or changed → NORMALIZE_ITEM → REBUILD_PROJECTION
  - supplier fact change (typed answer) → REBUILD_PROJECTION
  - assessment created → NORMALIZE_ITEM only if the family is stale → ASSESS (a `SAME_TRADE_ITEM` result ends the job before any LLM call)
  - new requirement accepted and no supplier questions open → ASSESS
  - supplier answers complete → EXTRACT_ANSWERS → REBUILD_PROJECTION → ASSESS
  - question created without `attribute_key` (purchaser free question or judge extra concern) → PROPOSE_ATTRIBUTE
  - attribute merged or rejected → REBUILD_PROJECTION for the affected variants
- **Separate process:** `uv run --package supplier-hub python -m supplier_hub.jobs.worker` for Postgres deployments.

## 13. LLM pipelines (tiered models) and who pays

| Pipeline | Service | Model | Settings | Key | Input → output |
|---|---|---|---|---|---|
| `judge` | hub | **claude-opus-5** | adaptive thinking, effort `high` | ours | template + requirement values + variant facts + final comparator results + past Q&A → judgments for undecided attributes, overall verdict + reasoning, question wording (addressee, language), extra concerns |
| `normalize_item` | hub | **claude-sonnet-5** | adaptive thinking, effort `medium` | ours | family description / properties text + template → facts with quotes + category suggestion |
| `extract_answer` | hub | **claude-haiku-4-5** | no thinking | ours | question + attribute definition + supplier comment → typed value or "unclear" |
| `propose_attribute` | hub | **claude-sonnet-5** | adaptive thinking, effort `medium` | ours | question text + category template + registry keys and labels → existing key, or a new definition (key, type, unit, options, neutral DE/EN labels, rationale) |
| `simulate_supplier` (dev) | hub | **claude-haiku-4-5** | no thinking | ours | questions + hidden datasheet → answers |
| `normalize_article` | node | **claude-sonnet-5** | adaptive thinking, effort `medium` | **hospital's** | a batch of German article names + the category template → per article: facts with quotes + category suggestion. Runs only at seed/import and at a stale startup (D56); never while serving a request |

**Adapter rules (both services):**
- Model and effort set per pipeline in settings.
- No `temperature` or other sampling parameters (Opus 5 and Sonnet 5 reject them).
- Structured outputs via `messages.parse`; quotes are schema fields (native citations can't be combined with structured outputs).
- Opus 5 requests enable server-side refusal fallbacks; `stop_reason` checked before reading output.
- Prompt caching on the unchanging system prompt + template prefix.
- Every call logged to that service's `llm_calls` (never the key).
- `LLM_MODE=fake` runs deterministically offline.
- **The judge prompt never receives hospital identity or identifiers**: only requirement attributes (without `article_ref` or product hints) and the supplier's *attribute* facts. Identifier facts are filtered out before the prompt is built.

## 14. API (both `/api/v1`, REST, typed through OpenAPI)

**Hospital node** (`:8001`, reachable only on the hospital network)
- **Auth:** `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`
- **Articles:**
  - `GET /articles?q=` (local search on name / internal ID); the same endpoint takes `?article_ref=ar_1,ar_2` for the hub-assessment join
  - `GET /articles/{id}`: category + source, current attributes with sources, unknown attributes, identifiers with `checksum_valid`, `data_quality_issues`, reference link, `article_ref` (the client uses it to fetch this article's assessments from the hub)
  - `PUT /articles/{id}/category`, `PUT /articles/{id}/facts/{attribute_key}` (optional `hub_question_id`, `cannot_provide`)
  - Identifiers go through the same facts endpoint with an identifier value (`{"type":"identifier","scheme":"GTIN","value":"…"}`): the node computes `checksum_valid` and recomputes `data_quality_issues`
  - `POST /articles/{id}/reference/preview {variant_id, label, attributes}` → `{fills, conflicts}`
  - `PUT /articles/{id}/reference {variant_id, label, attributes, conflict_choices}`, `DELETE /articles/{id}/reference`
- **Exchange:**
  - `POST /articles/{id}/requirement {answered_question_ids?}` → `{requirement, egress_id}`. Plain JSON: shown to the purchaser as "what leaves the hospital" and passed to the hub unchanged. Rate-limited per user (429).
  - `POST /hub-assertions` → `{assertion, expires_at}` (scope `purchaser`; rate-limited)
  - `GET /egress?from_=&to=&article_id=&user_id=` (node admin): the egress log with per-user counts of issued objects and the number of alerts
- **Lookups for the client** (to show hub assessments with local names):
  - `GET /users?include_inactive=true` → display name, role and `hub_subject_id` of this hospital's users (authenticated node users only). Deactivated users and retired `hub_subject_id`s are kept and returned, so the creator, resolver or assignee of an old assessment stays resolvable; a subject the node no longer knows is shown as the raw `sub_…`.
- **Admin:** `GET /admin/signing-key` (public JWK + fingerprint for registration at the hub)
- **Templates:** `GET /templates` (current definition per category with `updated_at`), `PUT /templates {definition, updated_at?}` (validates against the core model, stores, rebuilds that category's projections in the same transaction; `updated_at` is the hub's, so the client can tell when to sync again; PURCHASER or NODE_ADMIN)
- **Dev** (`APP_ENV=dev`): `POST /dev/reset-seed {dataset?}` (NODE_ADMIN; replaces all node data, so every session ends)

**Supplier hub** (`:8000`, internet-facing)
- **Auth:**
  - `POST /auth/login` (supplier users, operators), `POST /auth/logout`, `GET /auth/me`
  - `POST /auth/token-exchange {assertion}` → `{access_token, expires_at, tenant_alias}` (purchasers)
- **Operator admin:**
  - `POST /admin/tenants`, `GET /admin/tenants`
  - `POST /admin/tenants/{id}/signing-keys {public_jwk, not_before}`, `POST /admin/tenants/{id}/signing-keys/{kid}/revoke`
  - `GET /admin/attribute-proposals?status=`, `POST /admin/attribute-proposals/{id}/approve {key, labels, type, unit, options, category_code, criticality, comparison_rule, shareable, synonyms}` (adds the attribute to the category's DRAFT version), `POST .../merge {attribute_key}`, `POST .../reject {note}`
  - `PATCH /admin/templates/{code}` (edit the current definition; used by approve)
- **Any authenticated hub user (purchaser, supplier, operator):**
  - `GET /templates` (current definition per category with `updated_at`), `GET /templates/{code}`
  - `GET /attributes?category=&status=` (registry, including provisional attributes)
- **Purchaser (exchanged token, tenant-scoped):**
  - `GET /suppliers`
  - `POST /search {requirement, supplier_id?, limit?}` (§15; D54)
  - `GET /catalog/variants?supplier=&category=&q=&volume_ml=&connector=&gauge=&length_mm=`, `GET /catalog/families/{id}`
  - `GET /catalog/variants/{id}/attributes` → effective attributes with fact IDs (for "current product")
  - `POST /assessments {requirement, variant_id}` → 202; 409 with the existing ID if an assessment for (tenant, `article_ref`, variant) is already open
  - `GET /assessments?status=&article_ref=&assigned_to=me|{subject_id}`: one row per assessment with `article_ref`, variant, supplier, status, verdict, round and the creator/assignee `subject_id` — the fields the client needs for the join
  - `GET /assessments/{id}` (everything: comparison rows, rounds, questions, events, creator/resolver/assignee subject IDs)
  - `PUT /assessments/{id}/assignee {subject_id}` (any principal of the tenant; the hub upserts the principal if unseen)
  - `POST /assessments/{id}/requirements {requirement, version}`
  - `POST|PATCH /assessments/{id}/questions[/{qid}]` (an identifier question is a normal question whose attribute is an identifier definition)
  - `POST /assessments/{id}/send-questions {version}`
  - `POST /assessments/{id}/resolve {verdict, note, version}`
  - `POST /assessments/{id}/request-more-info`, `.../extra-round`, `.../retry`, `.../cancel`
  - Assessment, catalog and search responses include `additional_information`: provisional attribute values with source, not judged
- **Supplier:**
  - `GET /supplier/requests`, `GET /supplier/requests/{assessment_id}` (supplier questions, own variant/family, hospital **alias** only)
  - `PUT /supplier/requests/{assessment_id}/answers` (drafts), `POST /supplier/requests/{assessment_id}/submit`
  - `GET /supplier/catalog`, `GET /supplier/catalog/families/{id}`
- **Dev** (`APP_ENV=dev`): `POST /dev/assessments/{id}/simulate-supplier`, `POST /dev/reset-seed`

**Access control:**
- Hub: purchaser tokens are bound to one tenant; every assessment query filters by `hospital_tenant_id`, and the hospital of a requirement is always taken from the token, never from the body. Suppliers see only their organization's requests and never requirements. Operators administer tenants but have no purchaser endpoints.
- Node: single hospital; roles `PURCHASER`, `NODE_ADMIN`.
- Errors: **401** bad/expired token or signature; **403** wrong role or tenant mismatch; **404** resource of another tenant; **409** version conflict, invalid transition, open purchaser questions, `ATTRIBUTE_PROPOSAL_PENDING` (hub), `NOT_NORMALIZED` for an article without a projection (node); **422** validation (including unknown requirement fields), incomplete batch, unresolved current-product conflicts; **429** rate limit (node).

## 15. Candidate search: one `POST /search` at the hub, run twice around "current product"

Deterministic, read-only, no LLM call, **nothing stored at the hub**. The same endpoint serves both passes: the **first search** runs on the thin requirement built from the article alone; the purchaser marks one result as the current product, which enriches the article at the node; the **second search** runs automatically on that extended parameter set. There is no pivot / "find similar" mode — a hospital's requirement is the only thing a search is ever built from (D46).

1. **At the node (`POST /articles/{id}/requirement`):**
   - Authorize the node user and check the rate limit (429).
   - The projection must exist (it is written synchronously with the article, D53).
   - Build the requirement through the allowlist (§16), write the egress row, and return it with a `category_unconfirmed` warning.
2. **At the hub:**
   - Authorize the exchanged token; the hospital comes from the token.
   - Validate the requirement against the current template schema (unknown fields → 422).
3. **Build the search spec** from the template + requirement:
   - **Hard filters:** category, plus every *critical* attribute with a known hospital value and an exact/tolerance rule. **"A known contradiction excludes, an unknown passes."**
   - **Soft criteria:** remaining known attributes, ranking only.
   - **Ignored:** attributes in `unknown_attributes` / `withheld_attributes` → returned as `hospital_gaps`, with a hint to mark the current product.
   - **Options:** `supplier_id` (none = all suppliers, so the current product can appear) and `limit` (D54).
4. **Query** `item_search_projection`: active variants matching hard filters (JSON path conditions; GIN in Postgres, `json_extract` in SQLite). Removals are counted per filter into `excluded_by`.
5. **Product hints** (only if present in the requirement, D47): an exact match on a valid GTIN, or on manufacturer article no. + manufacturer, sets `identifier_match: GTIN | ARTICLE_NO` and ranks that candidate first. Matching reads the projection's `identifiers` section by `(scheme, value)` (GIN index in Postgres, `json_extract` in SQLite). It is still pre-checked and never linked automatically.
6. **Pre-check each candidate** with the core comparators: MATCH 1 / ACCEPTABLE_DEVIATION 0.7 / UNKNOWN 0.3 / MISMATCH 0, weighted critical 3 · major 2 · minor 1, normalized to 0–1.
   - Sort order: identifier match → fewest critical unknowns → score → coverage.
   - Flags: `open_assessment_id` / `last_verdict` for this tenant's `article_ref`; supplier identifier warnings.
   - Provisional attribute values go into `additional_information` (§7.2).
7. **Response 200:**
   - `search_spec`, `hospital_gaps`, `excluded_by`
   - `candidates[]`: variant, family, supplier, article_no, score, coverage, counts, per-attribute pre-check, flags, `identifier_match`, `additional_information`
8. **The client completes the view:**
   - It marks `is_current_product` from the node's reference variant (the hub doesn't know it) and shows the article name from the node.
9. **Row actions** (two):
    - **This is our current product:**
      1. H `GET /catalog/variants/{id}/attributes`
      2. N `POST /articles/{id}/reference/preview` → fills and conflicts; the purchaser resolves conflicts
      3. N `PUT /articles/{id}/reference` (values stored as `REFERENCE_ITEM`)
      4. N `POST …/requirement` → H `POST /search` again, automatically: the new requirement carries the filled attributes, so the spec gains hard filters and soft criteria (the "extended parameter set")
    - **Start assessment:** N `POST …/requirement` → H `POST /assessments {requirement, variant_id}` → loop §19.
10. **After the loop:** enriched supplier facts rebuild the hub projection, so later searches by any hospital rank that variant with better coverage.
11. **Later:** a semantic recall stage (pgvector over `search_text`, query text rendered from the requirement) before step 6, with the same response format.

## 16. The requirement: the only hospital data that leaves the node

**Format:** plain JSON, validated on both sides by the core model `equivalence_core.exchange.RequirementPayload` (`extra="forbid"`). **Not signed** (D34): minimization comes from the node's allowlist and the hub's strict schema. The hospital is always taken from the hub token, never from the body.

| Field | Example | Notes |
|---|---|---|
| `requirement_version` | `1` | the only version so far; anything else is rejected |
| `article_ref` | `ar_5MZQ4K7T2V9C` | random 60 bits as 12 Crockford base32 characters (no I, L, O, U), stable per article, **not derived** from internal ID |
| identifier keys | — | identifier schemes are a fixed list in the core (`GTIN`, `EAN`, `MANUFACTURER_REF`, `PHARMACODE` at the node; `GTIN`, `SUPPLIER_ARTICLE_NO`, `PZN`, `HIMIV` at the hub), **not** registry lookups, because the node has no copy of the registry  |
| `template_code` | `syringe_single_use` | the category the node built the requirement for; the hub validates against its current definition (D52) |
| `attributes` | `{"nominal_volume_ml":{"type":"number","value":10,"unit":"ml"}, "connector":{"type":"enum","value":"LUER_LOCK"}, …}` | only template attributes with `shareable: true`; typed values; no quotes, no raw text |
| `attribute_origin` | `{"nominal_volume_ml":"EXTRACTED","design":"REFERENCE","mdr_class":"MASTER","wall_type":"PURCHASER"}` | coarse: `MASTER`, `EXTRACTED`, `REFERENCE`, `PURCHASER`; no fact IDs, no variant IDs |
| `unknown_attributes` | `["needle_included","pump_compatible"]` | |
| `unavailable_attributes` | `[]` | purchaser said "cannot provide" |
| `withheld_attributes` | `[]` | removed by the node's `EGRESS_DENY_ATTRIBUTES`; judged UNKNOWN, never asked |
| `answered_question_ids` | `["q_9"]` | hub question IDs this requirement answers |
| `product_hints` | `null` | only with `SHARE_PRODUCT_HINTS=true`: `{brand, manufacturer_article_no, gtin}`; GTIN only with a valid check digit; built by a separate function from the projection's `identifiers` section — the payload model itself has no identifiers field; consumed by search and `identifier_evidence`, never shown to the judge |
| `limited_template` | `false` | |

**Allowlist builder (node `services/requirement_builder.py`):**
- Input is the article projection only, never the article row. Name, internal ID, price, quantities, order units, `raw`, `data_quality_issues`, reference variant ID, evidence quotes and user IDs **cannot** be reached.
- Product hints come from a separate function, only when `SHARE_PRODUCT_HINTS=true`, limited to brand, manufacturer article no. and checksum-valid GTIN.
- Output passes through `RequirementPayload`; unknown keys fail.
- Free-text attribute values (e.g. `stopper_material`) are included only when the template marks the attribute `shareable: true` and the value is a synonym-normalized code or a short text of at most 60 characters. Otherwise the attribute is sent as unknown.
- Attributes listed in `EGRESS_DENY_ATTRIBUTES` move to `withheld_attributes`.
- Every issued requirement is written to `egress_log` (exact content + SHA-256) **before** it is returned. The log records issuance; the client could still choose not to send it.

**`requirement_hash`** is the SHA-256 of the canonical JSON of `template_code`, `attributes`, the three status lists (sorted) and `product_hints`. It deliberately leaves out `article_ref`, `answered_question_ids` and `attribute_origin`: sending the same content again, or only re-labelling where a value came from, is not progress for the stop condition in §11.

**Rate limits and alerts (node, D48):**
- Per user: `REQUIREMENT_RATE_LIMIT_PER_HOUR` (default 120) and `ASSERTION_RATE_LIMIT_PER_HOUR` (default 30); above the limit → 429.
- Reaching 80% of a limit writes `RATE_80_PERCENT` on that row; crossing `EGRESS_DAILY_ALERT_PER_USER` issued objects in a day (default 300) writes `UNUSUAL_DAILY_VOLUME`. A refused request writes an alert-only row (`RATE_EXCEEDED`, no content), committed even though the request fails, so bulk extraction stays visible in `GET /egress`.
- Signatures can't stop a compromised purchaser app, because injected script has the app's privileges. Limits bound what it can extract and make it visible.

**At the hub:**
- **Search:** validated, used, discarded. Only tenant, time and counts go to the access log (short retention).
- **Assessments:** stored in `requirements` with `requirement_hash` and referenced by rounds.

**Why it is not signed (D34):**
- The purchaser's client already receives all article data from the node, and the hub schema already enforces minimization.
- A node signature would add two things: protection against requirements injected with a stolen hub token (which can already read and resolve that hospital's assessments), and provable completeness of the egress log.
- If hospitals require the latter, wrap the same `RequirementPayload` in a node-signed JWS (`typ: requirement+jwt`): about ½ day, with no data model change.

## 17. Identity, keys and secrets

**Principle:** every secret stays on the side that uses it, and each side holds only **public** keys of the other. A leaked hub database lets nobody act as a hospital; a leaked node database lets nobody act as the hub or another hospital.

**Key material and credentials**

| Item | Kind | Lives at | Storage (prototype → production) | Used for |
|---|---|---|---|---|
| Node signing key | Ed25519 **private** | node only | `.secrets/node_ksp_ed25519.pem`, mode 0600, path from `NODE_SIGNING_KEY_FILE`, loaded once at startup, never in DB/logs/API → hospital key vault or HSM/KMS with a sign operation (key not exportable) | signing hub assertions |
| Node public key | Ed25519 public JWK + SHA-256 fingerprint | hub `tenant_signing_keys` | database row | verifying the above |
| Anthropic API key (hub) | secret | hub only | `.env` (git-ignored) → secret manager, injected as env var | judge, normalize, extract, simulate |
| Node user passwords | argon2id hash | node DB | | node login |
| Supplier/operator passwords | argon2id hash | hub DB | | hub login |
| Bearer tokens | 256-bit random, SHA-256 hash stored | issuing service's DB | token shown once | API access |
| Node token, hub token (client) | bearer | client memory only | never localStorage/disk; CLI keeps them in process | calls to each service |

**Why not a shared API key per hospital:** a shared secret must be stored at the hub, where one database leak would let an attacker act for every hospital; it has no expiry, identifies no user, and on-prem nodes would need to receive and protect a secret we issued. Key pairs avoid all four problems, and the node never needs a network path to the hub to use them.

**Token exchange (purchaser → hub)**
1. The purchaser logs in at the node (node token).
2. `POST /hub-assertions` (node): the node signs
   `header {alg:"EdDSA", typ:"assertion+jwt", kid:"ksp-2026-09"}`
   `claims {iss:"ten_ksp", sub:"sub_7QF2…" (users.hub_subject_id), aud:"sanovio-hub", scope:"purchaser", iat, exp: iat+300, jti}`
   and writes an egress row `ASSERTION` (claims only, never the token).
3. The client posts it to hub `POST /auth/token-exchange`. The hub checks, in order:
   - `typ` = `assertion+jwt` and `alg` = `EdDSA` (anything else → 401)
   - `kid` belongs to tenant `iss`, is not revoked, and `now` is within `not_before`/`not_after`
   - signature, `aud`, `exp` (≤ 5 min after `iat`), `iat` not in the future (±60 s skew)
   - `jti` not in `used_assertion_jtis` (then inserted with its expiry)
   - tenant active; `scope` allowed
4. The hub upserts `hospital_principals (tenant, subject)` and issues an opaque hub token (30 min, stored hashed with `tenant_id`, `principal_id`, `kid`).
5. **No refresh tokens.** On expiry the client repeats 2–4. Revoking a key also revokes every hub token issued from it (`api_tokens.kid`).

**Signed objects and their checks**

| `typ` | Signed by | Verified by | Extra checks |
|---|---|---|---|
| `assertion+jwt` | node | hub | single-use `jti`; ≤5 min |

Template definitions are plain JSON, validated against the core `TemplateDefinition` model at the node (D52).

**JWT checks for both (RFC 8725):**
- **Algorithm pinned:** `EdDSA`, and the verifying key must be an Ed25519 public key. (RFC 9864's more specific name `Ed25519` is not supported by PyJWT 2.14; switching to it later needs no data change.) `none` and HMAC are rejected.
- **Explicit `typ`,** checked per endpoint (`assertion+jwt` is the only accepted value), so a token minted for anything else is rejected.
- **`kid` must belong to the claimed issuer:** the tenant named in `iss`.
- **Claims:** `iss`, `aud`, `iat`, `exp` and `jti` are required; `aud` validated; `exp` and `iat` checked with ±60 s skew against a clock passed in by the caller. Keys are never taken from token headers (`jwk`, `jku`, `x5u` ignored).

Requirements and variant attributes are plain JSON over TLS with bearer tokens (D34, D37).

**Onboarding a hospital**
1. Operator: `POST /admin/tenants {name, supplier_facing_alias, disclose_name_to_suppliers:false}` → `ten_…`.
2. Node admin: `uv run --package hospital-node hospital-node keygen --kid ksp-2026-09` → writes the private key (0600) and prints the public JWK + fingerprint.
3. The public JWK goes to the operator by any channel; **the fingerprint is confirmed out of band** (phone/ticket) before `POST /admin/tenants/{id}/signing-keys`.
4. Node admin sets `NODE_TENANT_ID` and `HUB_AUDIENCE`.

**Rotation and revocation**
- **Rotation (node):** generate a new key with a new `kid` → register it at the hub → switch `NODE_SIGNING_KID` → after 5 minutes (the assertion lifetime) set `not_after` on the old key.
- **Revocation:** `POST /admin/tenants/{id}/signing-keys/{kid}/revoke` → immediate rejection of assertions with that `kid` and revocation of hub tokens issued from it.
- **Dev:** `make keys` generates dev keys for `ten_ksp` and `ten_spital2` into `.secrets/`; `make seed` registers the public keys through the hub admin CLI.

**Supplier and operator access:** direct login at the hub (password + bearer token), later SSO. Operators never get purchaser scope.

## 18. Network and deployment modes

- **Hard rule:** no connection between node and hub in either direction. The node has no hub URL and no HTTP client dependency; the hub has no node URLs. A test checks that `hospital_node` never imports `httpx`/`requests` (import-linter forbidden contract).
- **Modes (same node artifact in all):**

  | Mode | Node | Hub | Browser / client |
  |---|---|---|---|
  | **Prototype (local)** | `uv run` on `127.0.0.1:8001` (second node on `:8002` for isolation tests), SQLite `var/node_ksp.db` | `127.0.0.1:8000`, `var/hub.db` | demo CLI / Swagger with two base URLs |
  | **On-prem node** | hospital VM or container behind the firewall; inbound only from the hospital LAN; outbound: the LLM API only, and only while ingesting articles (D56) — never to the hub | central (ours), public HTTPS | workstation reaches node on LAN and hub over outbound HTTPS |
  | **Managed node** | we run a separate instance per hospital: own database (not a shared schema), own secrets, own subdomain, no network route to the hub, operator access audited | central | same as above, node over internet HTTPS with IP allowlist |

- **Production path:** Postgres per side; hub worker as a separate process; keys in KMS/Vault; TLS everywhere; hub CORS allowlist per tenant SPA origin; access logs with short retention.

## 19. The full loop as REST calls (scenario 1)

N = node (`:8001`), H = hub (`:8000`), C = client carrying data between them.

| # | Actor | Request | Result / state |
|---|---|---|---|
| 0 | P | N `POST /auth/login` → N `POST /hub-assertions` → H `POST /auth/token-exchange {assertion}`; client syncs the template definition to N if the hub's is newer | node token; hub token bound to tenant `ten_ksp`, subject `sub_7Q…` (both in client memory) |
| 1 | P | N `GET /articles?q=Spritze`, N `GET /articles/art_03`; optional N `PUT …/category`, N `PUT …/facts/{attribute}` | category + source, attributes, unknowns, identifier flags, data-quality issues (all local) |
| 2 | P | N `POST /articles/art_03/requirement` → H `POST /search {requirement}` (§15) | egress row; one ranked list across suppliers: Injekt 4606728V and Omnifix near the top, Plastipak 300912 close behind. Requirement not stored at H |
| 3 | P | optional **current product** on the Injekt row: H `GET /catalog/variants/var_injekt_ll_10/attributes` → N `POST /articles/art_03/reference/preview` → N `PUT /articles/art_03/reference` → N `POST …/requirement` → H `POST /search {requirement}` | 8 unknowns filled as `REFERENCE_ITEM`, no conflicts; the second search runs on the **extended parameter set** (more hard filters, more soft criteria) and re-ranks. **Hub is not told about the link** |
| 4 | P | N `POST /articles/art_03/requirement` → H `POST /assessments {requirement, variant_id:"var_plastipak_ll_10"}` | **202**, `ASSESSING`, round 1; requirement stored; 409 with the existing ID if already open for (tenant, `article_ref`, variant) |
| 5 | P | optional H `PUT /assessments/{id}/assignee {subject_id}`; lists via H `GET /assessments?assigned_to=me` + N `GET /articles?article_ref=…` + N `GET /users` | assignee stored at H as a pseudonymous principal; names joined in the client |
| 6 | W(H) | ASSESS: `identifier_evidence` (short-circuits to EQUIVALENT on `SAME_TRADE_ITEM`) → requirement attributes + variant effective record → comparators → judge (Opus 5) → verdict rules | round 1 = INSUFFICIENT_DATA; DRAFT questions → `NEEDS_QUESTION_REVIEW` |
| 7 | P | poll H `GET /assessments/{id}`; C joins hospital-side display names from the node | comparison rows, verdicts, questions, events |
| 8 | P | H `PATCH/POST …/questions`; for PURCHASER questions: N `PUT /articles/art_03/facts/{attr} {value, hub_question_id}` → N `POST …/requirement {answered_question_ids}` → H `POST /assessments/{id}/requirements {requirement, version}`; then H `POST …/send-questions {version}` | PURCHASER questions ANSWERED; SUPPLIER questions SENT → `AWAITING_ANSWERS` (straight to `ASSESSING` if none) |
| 9 | S | H `POST /auth/login`, `GET /supplier/requests` (sees "Hospital H-7F3A"), `GET …/{id}`, `PUT …/answers`, `POST …/submit` | 422 lists unanswered questions if incomplete; else typed values → facts, comments → EXTRACT → `ASSESSING` round 2 (dev: `POST /dev/assessments/{id}/simulate-supplier`) |
| 10 | W(H) | EXTRACT_ANSWERS (Haiku 4.5) → REBUILD_PROJECTION → ASSESS round 2 | EQUIVALENT_WITH_DEVIATIONS → `PROPOSED_RESOLUTION` |
| 11 | P | H `POST /assessments/{id}/resolve {verdict, note, version}` | `RESOLVED` |
| 12 | any | H `GET /supplier/catalog/families/{id}` | new supplier facts with sources, reused by future assessments from any hospital |

If the hub token expires mid-flow (401), the client repeats step 0's assertion + exchange (no refresh tokens). State-changing hub requests carry `version` → **409** on conflict.

## 20. Frontend (later phase)

**Stack**

| Concern | Choice |
|---|---|
| Runtime | Node 22 LTS + npm (uv only handles Python) |
| Build | **Vite** + **React 19** + **TypeScript** (strict) |
| Routing / server state | **React Router 7** (library mode), **TanStack Query** |
| UI | **Tailwind CSS v4** + **shadcn/ui** (Radix) + lucide-react |
| Forms | react-hook-form + zod |
| API client | **openapi-typescript + openapi-fetch**, **two generated clients** (node OpenAPI, hub OpenAPI) |
| Two origins | **Purchaser SPA is served by the hospital node** (works on the hospital network, same origin as the node API) and calls the hub cross-origin. The hub's CORS allowlist holds each tenant's registered SPA origin. **Supplier SPA is served by the hub.** Bearer tokens in headers (no cookies) → no CSRF. Tokens live **in memory only** (no localStorage); a reload means login + exchange again. |
| Tests | Vitest + Testing Library; **Playwright** happy path against both services |

**Screens**

- **Purchaser SPA (served by the node):**
  - **Assessments list:** from hub `GET /assessments` (status, verdict, assignee subject); the client adds article names (node `GET /articles?article_ref=`) and user names (node `GET /users`).
  - **Articles:** list with identifier warning badges, category, reference link. Detail page shows facts and sources.
  - **"What leaves the hospital" panel:** before every search or assessment, the requirement JSON is shown.
  - **Search and new assessment:** pick an article → one result list. Each row has two actions:
    - *this is our current product* (preview, then an automatic second search on the extended parameter set)
    - *start assessment*
  - **Assessment detail:**
    - identifier banner when the client's local check matches a valid identifier on both sides ("same trade item — this is the product you already buy"), with a one-click resolve
    - comparison table: attribute | hospital value (+ source, joined locally from the node) | supplier value (+ source, scope) | judgment | criticality (identifiers are shown above it, never as a row)
    - verdict card (rule verdict, LLM verdict + confidence, disagreement flag, reasoning)
    - question panel: "to supplier" (edit/withdraw/add/send) and "for you" (answer inline → node fact → new requirement)
    - round history, timeline, assignee picker (node users), resolve dialog
- **Supplier SPA (served by the hub):** inbox; request detail (typed answer, comment, "cannot provide", "applies to whole family", draft, submit); catalog with enriched facts.
- **Shared:** login per service, silent re-exchange of the hub token when it expires, role guards, "Simulate supplier" (dev). TanStack Query polls every 2s while ASSESSING.

## 21. Demo data and scenarios

**Seed** (hand-written canonical JSON inside each service's package; no importer; the demo accounts get `NODE_SEED_PASSWORD` from the node's `.env`):
- **Hub:**
  - **Tenants:** `ten_ksp` ("Demo Kantonsspital", alias "Hospital H-7F3A") and `ten_spital2` ("Demo Spital Zwei", alias "Hospital H-2C91"), each with a registered dev public key; an operator user.
  - **Suppliers:** **B. Braun** and **BD**, one user each.
  - **Catalogs** from the example PDFs (~6 families / ~25 variants per supplier), `source_document` + page. Examples:
    - B. Braun: Injekt® Luer Lock Solo (4606728V, 10 ml, usable to 12 ml, centric, 0.5 ml step, 12 × 100), Sterican® (4657527B, 21 G × 1½", 0.80 × 40 mm, ID 0.58 mm, 40 × 100)
    - BD: Plastipak™ Luer-Lok™ (300912, 10 ml, centric, 0.2 ml step, 100/400), Emerald™ Luer (307736, 10 ml, centric, 0.2 ml step, 100/1.200), Microlance™ (304432, 21 G 1½", 0.8 × 40 mm, thin wall, green, 100/5.000)
  - **Hidden datasheets** (simulator ground truth only, marked synthetic): MDR class, GTIN, DEHP status, inner diameter.
- **Node `ten_ksp`:** the **10 articles from the example CSV**, all fields as given (including invalid identifiers), one purchaser (Anna Meier) and one node admin. `make seed` normalizes all ten in **one** `normalize_article` call (FakeLLM offline, the hospital's key with `NORMALIZE_MODE=llm`).
- **Node `ten_spital2`:** 2 articles and one purchaser, only for isolation tests.
- **Keys:** `make keys` before `make seed`.
- **Templates:** `make seed` loads the YAML seeds into the hub registry (all attributes `APPROVED`) and installs the definitions at both nodes (D52).

**Scenarios** (all on real example-data pairs):
1. **Full loop:** CSV #3 "Einmalspritze 10 ml Luer-Lock steril" (B. Braun, MDR IIa) vs **BD Plastipak™ Luer-Lok™ 10 ml (300912)**.
   - One search from the thin requirement lists Injekt® Luer Lock Solo 10 ml and Omnifix® near the top. The name fits both, which is why a person must choose.
   - The purchaser assigns the assessment to themselves (`PUT /assessments/{id}/assignee`, event `ASSIGNED`); the client shows "Anna Meier" by resolving the subject at the node.
   - The purchaser marks Injekt as the current product: the preview fills 8 unknowns without conflicts, and the automatic second search — now on the extended parameter set — re-ranks the list.
   - Round 1: volume, connector, cone and sterile match; graduation 0.2 vs 0.5 ml acceptable (finer); design 3-part vs 2-part is a major deviation.
   - Unknown: MDR class (critical), DEHP-free (major), ISO 7886-1 (major) at the supplier → INSUFFICIENT_DATA → 3 supplier questions.
   - The supplier (or simulator) answers: MDR class typed + "applies to whole family", DEHP as German free text, ISO yes/no. The supplier sees only "Hospital H-7F3A".
   - Round 2 → EQUIVALENT_WITH_DEVIATIONS → confirm → RESOLVED, visible at the hub to every purchaser of the hospital.
   - Check: the node egress log holds the assertion and the requirements issued in this run (first search, re-search after marking the current product, assessment). None contains name, brand, GTIN, price or quantity (product hints off).
2. **Early stop:** CSV #3 vs **BD Emerald™ Luer 10 ml (307736)** → connector Luer vs Luer-Lock critical mismatch → NOT_EQUIVALENT in round 1, no questions. (Also: the search excludes Emerald via `excluded_by.connector`.)
3. **Purchaser question via requirement + manual decision:** CSV #6 "Kanüle Sterican 0,8 × 40 mm" (no reference link) vs **BD Microlance™ 21 G 1½" (304432)**.
   - Outer diameter and length match (0.8 mm ↔ 21 G).
   - The requirement lists `wall_type` unknown → PURCHASER question → purchaser answers "regular" at the node → new requirement with `answered_question_ids`.
   - MDR class and inner diameter go to the supplier; the supplier answers MDR class but "cannot provide" the inner diameter.
   - Thin vs regular wall (major deviation) + inner diameter UNAVAILABLE → NEEDS_MANUAL_DECISION → manual verdict.
4. **Unreliable identifiers (node-local):** CSV #6 vs **B. Braun Sterican® 21 G × 1½" (4657527B)**.
   - Article number 4657689 ≠ 4657527B and the GTIN check digit fails → warnings and `data_quality_issues` at the node.
   - Run twice. With product hints off, nothing identifier-related reaches the hub. With `SHARE_PRODUCT_HINTS=true`, the invalid GTIN is still withheld and the manufacturer article number is sent but matches nothing, so Sterican is found by attributes alone.
   - All attributes match; MDR class asked → round 2 EQUIVALENT.
   - The purchaser also asks B. Braun for the **GTIN** (question on the `gtin` identifier definition, origin PURCHASER). The answer is check-digit validated into an identifier fact (`SUPPLIER_ANSWER`); it enters no comparison and changes no verdict, and the proposal row records result `IDENTIFIER`, status `ROUTED`.
   - Re-run with `SHARE_PRODUCT_HINTS=true` **after** that answer: the hospital's own GTIN for art_06 is invalid, so `identifier_evidence` stays `NO_INFORMATION` and the verdict is unchanged — the asymmetry in action. Scenario 1's art_03 (valid GTIN) is used to exercise the `SAME_TRADE_ITEM` short circuit against its own current product: verdict EQUIVALENT with zero judge calls.
5. **Uncovered category (optional):** CSV #1 nitrile glove → generic template only; `limited_template: true` in requirement and response.
6. **Security and isolation (automated, no LLM):**
   - requirement with an extra field (`name`, `target_net_price`) → 422; requirement for an unknown `template_code` → 422
   - a `ten_spital2` token posting a requirement with a `ten_ksp` `article_ref` → stored under `ten_spital2` only and never linked to `ten_ksp` data; a `ten_spital2` principal requesting `ten_ksp` assessments → 404
   - replayed assertion → 401; expired assertion → 401; revoked `kid` → 401 and existing hub tokens from it rejected
   - requirement issuance above the per-user limit → 429 and an egress alert
7. **New attribute shared across hospitals:** during scenario 1's review step, the `ten_ksp` purchaser adds the free question "Does the pack include a peel-off documentation label?"
   - PROPOSE_ATTRIBUTE finds no existing key and proposes `peel_off_label` (bool). When the questions are sent, the attribute becomes PROVISIONAL.
   - BD answers "yes" for the whole family.
   - A `ten_spital2` purchaser searches with its own syringe article: Plastipak shows `additional_information.peel_off_label = true`, and its verdicts don't change.
   - The operator approves the attribute as **major** in `syringe_single_use`.
   - The client syncs the `ten_spital2` node, whose projection now lists `peel_off_label` as unknown. A new `ten_spital2` assessment against Plastipak asks the purchaser, not BD.
   - The open `ten_ksp` assessment picks the attribute up in its next round; the rounds already judged keep their stored definition (D52).

## 22. Implementation stages

Each stage is implemented and tested on its own. The hospital node is complete and demoable before any hub code exists.

| # | Stage | Days | Depends on | Ends with |
|---|---|---|---|---|
| 0 | Workspace and tooling | ½ | — | `make dev` serves both `/docs`; `make lint` passes; `make keys` writes node key pairs |
| 1 | Core: what the node needs | ½ | 0 | core unit tests pass on the real German strings and the 10 CSV identifiers |
| 2 | Hospital node, standalone | 1 | 1 | `make seed` then `make demo-node`: login, 10 normalized articles, a clean requirement, an assertion, the egress log and a 429 |
| 3 | Core: comparison | ¼ | 1 | the verdict table (§8) reproduced by tests |
| 4 | Hub foundation: tenants, catalog, search | 1 | 1, 3 | a real node assertion exchanged; a real node requirement searched; Emerald excluded by connector |
| 5 | Hub loop: assessment, questions, answers | 1¼ | 4 | scenarios 1–3 complete under FakeLLM; a `SAME_TRADE_ITEM` round makes no judge call |
| 6 | Demo client, e2e, evals, docs | 1 | 2, 5 | `make demo SCENARIO=1..4` with fake and real keys; e2e suite green |

**Total ≈5½ days.** The one remaining cut that gets under five days is the attribute registry's runtime path (proposals → provisional → approve, and scenario 7), about ½ day.

**Deferred** (documented, additive): template versioning and signed bundles · a job queue at the node · search paging and relaxation · curation merge/reject · extra concerns from the judge · `.http` collections · a second node process in e2e.

## 23. Design decisions

Each decision lists the alternatives considered, why this one was chosen, and what would change it. Superseded decisions are kept, struck through, for traceability.

| # | Decision | Alternatives | Why this one | Would change if the client says… |
|---|---|---|---|---|
| D1 | Python/FastAPI for both services | Full TypeScript, Django | Strongest LLM and data tools. Pydantic serves as API, LLM output and requirement schemas. Matches the user's uv/Pydantic tools. Free OpenAPI per service. | A TS/Java backend is required |
| D2 | React + Vite SPAs (later phase): purchaser SPA served by the node, supplier SPA by the hub | Next.js, HTMX | Logged-in tools with no SEO; a static bundle is easy to ship inside an on-prem node. | Public pages / Next.js standard |
| D3 | **SQLite per service**, ready for Postgres | Postgres from day 1 | Nothing to install; a hospital node with tens of thousands of articles never outgrows SQLite; the hub moves to Postgres in production. | Hosted hub at scale → Postgres + compose |
| D4 | Job table + worker thread **at the hub** (the node has none, D53) | Celery/RQ/arq + Redis; one shared queue | Survives restarts, retries, visible state, no extra infrastructure. A shared queue would be a forbidden link between node and hub. | Bulk volume at the hub → Redis queue |
| D5 | Polling (`GET /assessments/{id}` at the hub) | Server-sent events, WebSockets | Async two-sided work; updates only matter during LLM runs. | Live chat-like interaction wanted |
| D6 | **Attribute-level comparison with templates based on the real catalog fields**; templates kept in the hub registry (D43) | LLM compares whole descriptions | Auditable per-attribute evidence; catalogs already structure products this way; missing data follows from the comparison; also the natural unit for a minimal requirement. | They name a standard (eCl@ss/GMDN/GS1) → map templates to it |
| D7 | **Code decides the verdict**; the LLM verdict is a cross-check | LLM verdict alone | Consistent thresholds, testable, explainable, resists injection. | "LLM only", or existing scoring rules |
| D8 | Deterministic comparators and parsers first, and final, **in the shared core** | LLM judges everything; separate code per side | Units, decimal commas, gauges and inch fractions are where LLMs slip. One implementation guarantees node and hub read "0,8 × 40 mm" the same way. | — |
| D9 | **Canonical model: product family → variant** | One flat row per supplier item | Both catalogs share properties per family; one answer can cover a whole family. | Their catalog feed is flat per SKU |
| D10 | **Identifier evidence is asymmetric: a check-digit-valid match is near-proof (D51), a difference is no information; hospital identifiers stay on the node unless the hospital enables product hints (D47)** | GTIN match ⇒ equivalent with no review; identifiers compared like attributes | Most example GTIN/EAN check digits fail, and equivalent products from different manufacturers always carry different GTINs — so a difference must never reach a verdict. A valid match, however, means the same trade item: since round 7 it short-circuits the round to EQUIVALENT (D51), still confirmed by a purchaser, and never auto-links a current product. | Pack-level GTIN noise → demote `SAME_TRADE_ITEM` to a strong prior instead of a short circuit (D51) |
| D11 | **Questions addressed to supplier *or* purchaser; optional reference link** | Hospital-side gaps → manual decision only | The hospital side is thin; the purchaser knows the current product. | Rich hospital master data → purchaser questions become rare |
| D12 | Facts only added, with full sources and scope, on both sides | Overwrite fields | Liability: who said what and when; judgments can be replayed. | — |
| D13 | Supplier enrichment shared at the hub; Q&A private per tenant; **hospital facts never shared** | Enrichment per hospital | "Enrich the supplier record"; hospital facts describe the hospital's purchasing and stay on its node. | Hospitals must not benefit from each other's questions → per-tenant fact scope |
| D14 | Suppliers see neither the hospital's article nor, by default, the hospital's name | Show both | The current article is often a competitor's product; purchasing interest is commercially sensitive. | Sharing allowed → `disclose_name_to_suppliers` per tenant |
| D15 | Purchaser reviews questions and confirms verdicts | Fully automatic | Avoids spamming suppliers; a person stays accountable for substitutions (MDR). | Automation wanted → per-tenant flags |
| D16 | Clear stop conditions + manual decision state | Unbounded loop | Every path ends in a state a person can act on. | Different cap / SLA |
| D17 | Typed answers + optional free text + "cannot provide" + "applies to family" | Free text only | Exact values without an LLM; nuance still possible. Purchaser answers are typed only, so the node needs no LLM for them. | Email-only suppliers → extraction for everything |
| D18 | Re-judge only after a complete supplier batch | Per answer / partial submits | Fewer calls, consistent judgments. | — |
| D19 | **German input, language-neutral codes, supplier-language questions** | English-only | CH market data; codes keep comparisons and requirements language-independent. | FR/IT suppliers → org language setting |
| D20 | **Tiered Claude models behind a thin in-house interface; no LangChain/LangGraph** | One model everywhere; frameworks | User choice on tiers; a fixed workflow is a state machine, and frameworks would hide prompts and state we must audit. | Data residency / mandated provider → new adapter |
| D21 | **Opaque bearer tokens per service; purchasers reach the hub only via token exchange** (D36) | Cookie sessions, one shared login, JWT access tokens | REST clients send a header easily; tokens can be revoked; no CSRF; the hub never handles hospital passwords. | Hospital SSO → OIDC at the node, exchange unchanged |
| D22 | **Deterministic candidate search on a requirement at the hub** (`POST /search`) | Node-side search over a catalog copy; LLM ranking; embeddings | Catalogs stay central and fresh; the requirement carries only what filters need; same comparators as the assessment; POST keeps it out of URLs and logs. | Semantic proposals wanted → pgvector recall with query text from the requirement |
| D23 | Hand-written canonical seed; ingestion out of scope (user decision) | CSV importer, PDF extraction | The canonical model is the stable contract later adapters target. | — (next phase: adapters) |
| D24 | Simulator with hidden datasheets + FakeLLM | Two humans to demo | One presenter can close the loop; offline tests; eval ground truth. | — |
| D25 | Frontend (later phase): openapi-typescript (two clients), shadcn/ui + Tailwind, English UI | Hand types/tRPC; MUI; i18n now | Types come straight from Pydantic; quick, editable UI. | Design system / DE-FR UI |
| D26 | **Read models on both sides** (`article_projection`, `item_search_projection`) | Query facts directly; views | Resolving precedence per request is slow; resolved rows are traceable and rebuildable; the requirement builder reads only the projection, which also enforces the allowlist. | — |
| D27 | **Relational store; hybrid search inside hub Postgres later** | Vector database as the main store | Equivalence needs exact values, history, transactions and access control. | >10–50M vectors → dedicated vector database fed by an outbox |
| D28 | **Hub assessments owned by the hospital tenant; creator, resolver and assignee recorded as pseudonymous principals; names resolved at the node** | Owned by users; assignee and verdict copy in a node table (`assessment_links`) | Staff change; the hub holds pseudonyms only, never staff identities; one source of truth avoids a node copy that goes stale; every purchaser of the hospital sees the same list. | Four-eyes approval → approver role, resolver principal ≠ creator principal |
| D29 | **`category_source` + `category_set_by/at`** on articles and families | No provenance | The category selects the template for normalization, requirement, search and comparison; human choices must survive re-normalization. | Classified data feed → `IMPORT` source |
| D30 | **Start from existing articles; normalize at the node on creation; direct fact corrections** | Free-text requirement entry; normalize at the hub | Matches the brief; article names never leave the node. | New needs without an article → free-text entry at the node (~½ day) |
| D31 | **Identifier quality checked at two levels**: `checksum_valid` inside each identifier fact value, `data_quality_issues` on the article for problems *between* identifiers (node-side) | Ignore; reject invalid rows | 7/10 invalid GTINs, 9/10 mismatches in the sample. | Clean identifiers confirmed |
| D32 | **Split into hospital node (per hospital) and central supplier hub** (user decision) | Multi-tenant monolith with row-level security; separate schema per hospital | Hospitals can keep article data on their own firewalled servers; a breach of one side exposes only that side. | No hospital requires isolation → node instances can still be run by us (D41) |
| D33 | **Client as the only bridge; no server-to-server link** (user decision) | Node pushes to hub (outbound webhook); hub pulls from node (VPN) | No inbound firewall rules, no outbound integration, no VPN; every transfer is triggered by a purchaser action. Cost: the client orchestrates more calls, which the demo client and later SPA hide. | Batch/background sync needed (e.g. nightly re-assessment) → optional outbound-only node agent |
| D34 | **Plain requirement (JSON) built by allowlist at the node, strict template schema at the hub, opaque `article_ref`, issuance log** | Node-signed envelope (JWS); send the article record | Minimization comes from the allowlist and the hub schema, not from a signature. The client already receives all article data, so a signature would only add protection against injection with a stolen hub token (which can already read and resolve that hospital's assessments) and provable egress completeness. Saves ~½ day; the stable `article_ref` still lets the hub dedupe and show past verdicts without knowing the article. | Hospitals require provable egress control → wrap the same payload in a node signature (~½ day) |
| D35 | **Judging stays central, on the requirement** | Judge at the node (supplier facts sent to the node, LLM at each hospital) | One LLM key and prompt set; question drafting needs supplier context that lives at the hub; the node stays small and LLM-free. **Tradeoff:** the hub (not suppliers) sees template attribute values of a hospital's needs. | Attribute values themselves are confidential → node-side judging with a hub "comparison kit" per variant (+~1½ days) |
| D36 | **Per-hospital Ed25519 key pair; node-signed short assertions exchanged for hub tokens** | Shared API key per hospital; mTLS; OAuth client credentials | No shared secret at the hub; works without any node → hub connectivity; short-lived and single-use; per-user attribution without identities; rotation by `kid`, central revocation. Ed25519: small keys, fast, no parameter choices. | Hospital IdP federation required → hub trusts IdP via OIDC in addition |
| D37 | **No hub-signed snapshots or verdicts: the node stores current-product values as reported by the client; verdicts stay at the hub only** | Hub-signed variant snapshots and verdict attestations | A purchaser can enter any value as a correction anyway, so a signature would only protect the "reference item" label; verdicts need no node copy (D28, D49). Saves ~½ day. | Hospital needs a tamper-evident decision record → hub-signed export (D49) |
| D38 | **Secrets per side:** private keys in files/KMS outside databases; LLM key only where the pipeline runs; tokens in client memory only | Keys in DB; one `.env` for everything; tokens in localStorage | Limits every leak to one side and one purpose; a database dump contains only public keys and hashes. | Hospital mandates HSM → sign through PKCS#11/KMS adapter (interface already isolated in `jws.py`) |
| D39 | **Pseudonymous hospital toward suppliers; pseudonymous purchaser principals at the hub** | Real names everywhere | Suppliers don't need the buyer's identity to answer technical questions; the hub needs accountability, not identities. | Disclosure wanted per tenant (flag exists) |
| D40 | **One uv workspace: shared `equivalence-core` + two apps + demo client; import-linter contracts** | Two repositories; one package with two entry points | One lock file and one version of parsers, comparators and the template model for both sides (template *content* comes from the hub registry); import contracts make the split enforceable in CI. | Separate teams per side → publish the core as a versioned wheel |
| D41 | **Same node artifact for on-prem and managed hosting** | Managed hospitals share the hub database | One code path to test; switching a hospital between modes is a move, not a migration of data models. | — |
| D42 | **LLM normalization at the node by default, with the hospital's own key, combined with the deterministic parsers** (revised) | Rules only; always LLM per request; send names to the hub for normalization | Rules alone stop at what regex can reach and leave most attributes unknown, which pushes work onto the purchaser at the worst moment — the first search. The LLM reads implied properties and irregular names; the parsers stay authoritative for numbers with units (D8), so the model can add knowledge but not corrupt measurements. The key is the **hospital's**, so names never reach us or the hub, and `rules` remains a no-key fallback. | A hospital forbids any external processing → `NORMALIZE_MODE=rules` for that node, no code change |
| D43 | **Hub-owned attribute registry with one current definition per category (D52); YAML only as seed** (user requirement) | Static YAML in the core, changed by software release; per-hospital templates | New attributes must become visible to all hospitals without a release; one shared definition keeps comparisons consistent across hospitals; criticality per template lets an attribute matter differently per category. | The client adopts a taxonomy (eCl@ss/GS1 GDSN) → import it into the registry |
| D44 | **New attributes from questions: LLM proposal with duplicate check → PROVISIONAL (shared immediately, information only) → operator approval sets criticality and updates the category definition** | Auto-add with LLM-chosen criticality; nothing shared before approval; suppliers define attributes | Meets "visible to other hospitals" at once, while verdict rules stay under control and suppliers can't steer what counts as critical; the duplicate check and neutral labels keep the registry clean and leak-free. | Q20/Q21 answers: hospital panel curates; or sharing only after approval |
| D45 | ~~Template bundles hub-signed, assessments pinned to a version, hub accepts current + previous~~ **superseded by D52** (unsigned definition sync, no versioning); the node's `EGRESS_DENY_ATTRIBUTES` veto survives | Node pulls templates from the hub; always latest version for open assessments | Keeps the no-connection rule (D33); verdicts don't change mid-loop; nodes that sync late keep working; the hospital keeps final control over what leaves. | Background sync allowed → node agent pulls bundles |
| D46 | **One search endpoint, run twice: thin requirement → mark current product → automatic second search on the extended parameter set. No "find similar" pivot** (user decision, revised) | Separate reference-link lookup before searching; a `like_variant_id` pivot mode as a third action | Recognizing the current product and finding alternatives are the same query, so one list removes a step. The pivot was dropped from the prototype: it duplicated what the enriched requirement already achieves, needed its own conflict semantics (`pivot_conflicts`, anchoring rules) to stop drift, and added an API mode, response fields and tests for a case the second search covers. Every search is now built from the hospital requirement alone, which also keeps the egress story trivial. Saves ~¼ day. | Purchasers want alternatives to a *catalog* item they don't own → reintroduce the pivot as `like_variant_id`, anchored to the requirement (~¼ day) |
| D47 | **Product hints (brand, manufacturer article no., valid GTIN) as a per-hospital setting, off by default; prices, quantities, internal IDs and article names never leave** | Never send identifiers; always send them | Prices and volumes are competitively sensitive (EU horizontal guidelines, hub-and-spoke risk). Brand/GTIN are only moderately sensitive, often public through award notices, and the attribute set already hints at the product. Hints enable exact matching when identifiers are clean. | Client question 15 answers |
| D48 | **Per-user rate limits and volume alerts on requirement and assertion issuance at the node** | No limits | A compromised purchaser app can't be stopped by signatures (injected script has the app's privileges); limits and alerts bound and expose bulk extraction. | — |
| D49 | **No assessment copy at the node; a hospital decision archive is a later export** | Node table `assessment_links` kept in sync by the client | The hub already holds every assessment per tenant; a client-synced copy goes stale and adds endpoints and tests. Without the hub nobody can work on assessments anyway, so an offline list adds little. Saves ~¼ day. | Hospital requires an on-prem record of substitution decisions → periodic export of resolved assessments (hub-signed if it must be tamper-evident) |
| D50 | **Identifiers are facts with an `identifier` value type; `article_identifiers` and `item_identifiers` are removed** | Separate identifier tables per side | One storage and provenance mechanism: identifiers gain source, author, `answer_id` / `hub_question_id` and supersedence, which the dedicated tables lacked, and an answered identifier needs no second write path. The properties that made a separate table attractive are preserved by rules instead of by schema: identifier definitions carry `kind = IDENTIFIER` and are never in a category template (so no criticality, no comparison rule), the projections keep them in an `identifiers` section rather than in `attributes` (so the one-value-per-key invariant holds and several GTINs coexist), and `identifier_evidence` is the only stage that reads them (D51). **Cost accepted:** the egress guarantee is no longer "the column does not exist" but "the payload model has no identifiers field", enforced by a test; `(scheme, value)` lookups become a JSON index on a larger table. | The exemption rules prove leaky in practice → split identifier facts back out into their own table (same value shape, ~½ day) |
| D51 | **`identifier_evidence` before the comparators: a valid identifier match is near-proof and short-circuits the round to EQUIVALENT; a difference is no information** | Ignore identifiers during assessment (previous design); compare them like attributes | Equivalent products from different manufacturers **always** have different GTINs, so a mismatch carries no signal and must never reach a verdict — but an exact match on a check-digit-valid GTIN means the same trade item, which is stronger evidence than any attribute comparison and saves a ~$0.10 judge round. Asymmetric evidence cannot be expressed in the `MATCH / DEVIATION / MISMATCH / UNKNOWN` vocabulary, so it gets its own stage rather than a comparator. With product hints off the hub has no hospital identifiers, so the client performs the same check locally and nothing leaves the node. | Pack-level GTINs prove noisy → restrict `SAME_TRADE_ITEM` to manufacturer article no. + manufacturer, or make it a strong prior instead of a short circuit |
| D52 | **Prototype templates sync unsigned, one current definition per category; no version history, pinning or `upgrade_template`** | Signed `template+jwt` bundles with version pinning and current+previous acceptance (D45, previous design) | The registry requirement (D43: new attributes reach every hospital without a release) is met by syncing the *definition*; the version machinery was protecting against a risk a single-operator demo does not have — rules changing mid-loop — which the round's stored `input_snapshot` already records. Removes the hub signing key, the hub JWKS, `/.well-known/jwks.json`, node version history, two error codes and the `upgrade_template` branches. Saves ~1 day and leaves exactly one signed object type in the system. | Two hospitals run different template versions in production → reinstate D45's bundles and pinning (~1 day) |
| D53 | **No job queue at the node: normalization and projection rebuild run synchronously on write** | Job table + worker thread mirroring the hub (D4, previous design) | Ten seeded articles, rules-based parsing in milliseconds. The queue added a table, a worker thread, retry logic and the `NOT_NORMALIZED` / `retry_after_s` round-trip that every demo script has to handle. The hub keeps its queue, where LLM calls make it necessary. | Node-side LLM normalization returns, or articles arrive in bulk imports → reinstate the queue (~½ day) |
| D54 | **Search takes `supplier_id` and `limit` only; no `relax`, no cursor paging, no relaxation hints** | Full paging and relaxation surface | The seed catalog is ~50 variants across two suppliers. Paging and relaxation are real features for a real catalog and cost API surface, response fields and tests here for no demonstrable behaviour. `excluded_by` already explains an empty list. | Catalogs of realistic size → add cursor paging and `relax` (~¼ day) |
| D55 | **The former cut list is the default scope:** curation is approve-only, no extra concerns, no `.http` files, one node in e2e (two tenants at the hub). (Node `llm` normalization was on this list and has been **restored** by D42/D56.) | Full scope with a fallback cut list | A cut list that is only used when time runs out is a plan for running out of time. Making these deferred by default is what brings the estimate inside the stated 3–5 day timebox, and every item remains a documented, additive feature. | More time than the timebox → restore in the listed order |
| D56 | **The node's LLM pass runs once at initialization, not per request and not on a queue** (user decision) | A job queue at the node; normalizing lazily on first search; re-normalizing on every boot | Ingestion is the only moment article text needs reading, and it is a batch of ten in the demo — so one cached-prefix call at seed covers everything, and `content_hash ≠ normalized_hash` makes a restart free. Serving a search or building a requirement then needs no key, no network and no waiting, which also keeps D53's "no queue at the node" intact. | Articles arrive continuously from an ERP feed → a small ingestion worker, still outside the request path (~½ day) |

## 24. Assumptions and open questions

### 24.1 Working assumptions

- The purchaser picks the variant.
- Focus on syringes and needles; other categories use the generic template.
- Identifiers are unreliable; hospital identifiers stay on the node.
- Technical equivalence only; price stays at the node as context.
- Manufacturer = supplier; supplier questions in German; English UI.
- Suppliers use a portal and see neither the hospital article nor the hospital name.
- Shared supplier enrichment, private Q&A.
- Purchaser reviews questions and confirms; at most 3 rounds.
- Anthropic Claude (tiered models) at the hub; at the node, one batched `normalize_article` call at ingestion using the hospital's own key, with the parsers authoritative for numbers.
- Example files are used in a private repo but not committed.
- Any purchaser of the hospital can resolve; no four-eyes approval.
- Search starts from existing hospital articles.
- Both hosting modes are possible; workstations can reach node (LAN) and hub (HTTPS) at once.
- Template attribute values under a random reference may leave the hospital; brand and GTIN only if a hospital opts in.
- Local node accounts; file-based keys in the prototype.
- We (operator) curate new attributes; provisional attributes are shared with all hospitals as information only.
- Local run, one assessment at a time.

When the client replies, update §23 and §24.

### 24.2 Questions to the client

Each question carries the assumption the design uses until it is answered; §23 says what changes with a different answer.

**Part A: scope and process**
1. **How are candidates chosen?** Does the purchaser pick the supplier item to compare, or should the system search catalogs and propose candidates?
   *Assumption: the purchaser picks, helped by search and filters on normalized attributes (e.g. volume, connector, gauge).*
2. **What does "equivalent" mean?** Clinically/functionally substitutable, or technically identical? Should we follow a standard (GS1/GDSN, eCl@ss, UNSPSC, GMDN/EMDN)? Who decides which attributes are critical for each category?
   *Assumption: functional substitutability; outcomes Equivalent / Equivalent with deviations / Not equivalent / Insufficient data. We propose critical/major/minor levels for syringes and needles, for you to review.*
3. **How do suppliers take part?** Portal login or emailed link? May a supplier see which article the hospital uses today (often a competitor's product)?
   *Assumption: portal login; the supplier sees only the questions and their own product.*
4. **Who benefits from enrichment?** Should data from supplier answers update the supplier's product for all hospitals, or only the one that asked?
   *Assumption: shared across hospitals, with full source tracking; the Q&A conversation stays private.*
5. **Who has the final say?** Can the LLM close an assessment alone, or must a purchaser confirm? Does confirming need a second person (four-eyes principle) or a specific approver role? Should purchasers review questions before sending? Maximum number of rounds?
   *Assumption: the LLM proposes and any purchaser of the hospital confirms (no second approval); questions are reviewed first; at most 3 rounds, then a manual decision.*
6. **LLM provider and data rules:** where may data be processed (CH/EU)? Any approved providers (e.g. Azure OpenAI Switzerland, Mistral, self-hosted)? Cost budget?
   *Assumption: Anthropic Claude behind a swappable adapter.*

**Part B: the example data**
7. **Identifiers:** in the article list, most GTIN/EAN check digits don't validate, the EAN is not the GTIN without its leading zero, and article numbers don't appear in the catalogs (e.g. "Kanüle Sterican 0,8 × 40 mm" is listed as 4657689; the B. Braun catalog lists Sterican 21 G × 1½" 0,80 × 40 mm as 4657527B). Is this anonymisation, or should we expect unreliable identifiers in real data?
   *Assumption: identifiers are unreliable hints. We validate check digits and never treat an identifier match alone as proof of equivalence.*
8. **Category coverage:** the catalogs cover syringes and needles, while the article list spans about 8 categories (gloves, masks, wound care, infusion sets…). Should the prototype focus on syringes and needles?
   *Assumption: yes. Other categories use a generic attribute set.*
9. **Commercial fields:** are annual volume, target price and pack sizes part of the assessment (e.g. price per unit, savings), or context only? Neither catalog contains prices, GTINs or MDR classes. Should those be asked of the supplier?
   *Assumption: technical equivalence only. MDR class and GTIN are asked of the supplier; price stays at the hospital as context.*
10. **Supplier and language:** is the "supplier" the manufacturer (B. Braun, BD) or a distributor? The data is German. Which language should questions to suppliers use (DE/FR/IT)?
    *Assumption: manufacturer = supplier; supplier-facing questions follow the supplier's language setting (default German); the app UI is in English.*
11. **Use of the samples:** we analysed the files locally to work out the field structure. The prototype will keep hand-copied article rows and catalog excerpts in a private repository and send catalog text to an LLM API (Anthropic). Please confirm that's acceptable.
    *Assumption: acceptable; the raw files themselves are not committed.*
12. **How data will arrive in production** (ERP exports, BMEcat/GS1 feeds, PDF brochures, portal entry)? This is not needed for the prototype; it informs our design for later imports.

**Part C: hospital-hosted data and security**

We plan to split the system in two. A **hospital node** keeps a hospital's article data and can run on the hospital's own server. A **central supplier hub**, run by us, holds supplier catalogs, questions and answers, and the assessments. The two servers never connect to each other; only the purchaser's app talks to both.

13. **Hosting:** which hospitals require the node on their own premises? Would others accept a node we host for them, with its own separate database and keys? What does on-prem infrastructure usually look like (Linux VM, Kubernetes, Windows Server)?
    *Assumption: both modes use the same software; the prototype runs both servers locally.*
14. **Network access:** can purchaser workstations reach the node on the hospital network *and* an internet HTTPS service (the hub) at the same time? Are proxies or allowlists needed?
    *Assumption: yes, outbound HTTPS to the hub is allowed; nothing from outside connects into the hospital.*
15. **What may leave the hospital:** to search and assess, the hub needs the article's technical attributes (e.g. "10 ml, Luer-Lock, sterile, MDR IIa") under a random reference number. Prices, annual volumes, internal IDs and article names never leave the node. Brand, manufacturer article number and GTIN help find your current product exactly: may a hospital choose to send them, or must they always stay inside? Please note that a precise set of technical attributes can hint at the product even without them.
    *Assumption: attributes may leave; brand and GTIN stay inside unless a hospital switches them on. Every requirement the node issues is logged there, so the hospital can audit it.*
16. **Processing article names:** the node reads attributes out of short German article names. May the node send those names to an external LLM with the hospital's own account, or must this stay inside the hospital?
    *Assumption: the node calls an LLM **with the hospital's own account** once, when articles are first loaded, and combines it with deterministic parsers. Only the short article name is sent, never prices, quantities or identifiers, and every call is logged at the node. A rules-only mode stays available for hospitals that refuse any external processing.*
17. **Hospital login:** should purchasers log in with the hospital's identity provider (e.g. Microsoft Entra ID, AD FS)?
    *Assumption: local accounts on the node in the prototype; single sign-on on the node later. The hub trusts the node's signed statements, never hospital passwords.*
18. **Hospital identity toward suppliers:** may suppliers see which hospital asks?
    *Assumption: suppliers see a pseudonym (e.g. "Hospital H-7F3A"); a hospital can choose to show its name.*
19. **Key management:** do hospitals have a key vault or hardware security module for the node's signing key? Is there a required rotation interval?
    *Assumption: a protected key file in the prototype; a key vault in production; yearly rotation.*
20. **New attributes:** when a purchaser asks something the attribute lists don't cover, the system proposes a new attribute. Who should approve new attributes and decide how important they are (critical/major/minor): us as operator, a hospital panel, or each hospital?
    *Assumption: we curate centrally; until approved, a new attribute is shown as information only and never affects a verdict.*
21. **Sharing new attributes:** may a supplier's answer to one hospital's free question become an attribute visible to all hospitals? The question text stays private; only a neutral attribute name (e.g. "peel-off documentation label") and the supplier's value are shared.
    *Assumption: yes, the same as other supplier answers (question 4).*

## 25. Related documents

| Document | Contents |
|---|---|
| [data-model.md](data-model.md) | conventions and typed value shapes; node tables N.1–N.11 and hub tables H.1–H.22 with column types and example rows |
| [charts.md](charts.md) | the 21 UML diagrams and how each has changed |
| `../charts/png/` | rendered diagrams: 01 use cases · 02 components · 03 packages · 04 deployment · 05a/05b domain classes · 06 application classes · 07a/07b database schemas · 08 assessment states · 09 question states · 10 job states · 11 full loop · 12 candidate search · 13 ASSESS job · 14 answers and enrichment · 15 projection rebuild · 16 token exchange · 17 requirement flow · 18 key lifecycle · 19 attribute lifecycle |
