# Article Equivalence Loop — UML diagrams (Appendix B)

What `charts/` holds, what each review round changes, and the criteria for calling a round done.
Companion to the prototype plan ([design-plan.md](design-plan.md)) and `architecture/data-model.md`.

---

### Status
- **Done:** `charts/` renders 21 diagrams covering the v3 split, the attribute registry and rounds 5–10 (PlantUML 1.2026.8 via `charts/render.sh`, Smetana layout, no Graphviz). Verified for round 7: render exits 0 with 21 SVG + 21 PNG, all 13 changed PNGs were checked, and `grep -riE "article_identifiers|item_identifiers|identifier_scheme|ArticleIdentifier|ItemIdentifier" charts/src charts/README.md` finds nothing.
- **Next design change** reuses the same tooling, style file, render script and rules.

### Round 10 update (done)
Node LLM normalization restored at ingestion (D42 revised, D56) and the last of the D52 template-version references removed.

| # | File | Change |
|---|---|---|
| 01 | `use_cases` | "Normalize articles at ingestion (parsers + LLM, hospital key)"; the node actor becomes "Node seed / startup" (there is no worker, D53) |
| 02 | `component` | Normalization component reads the hospital Anthropic key; `N_SEC` carries it; `RequirementIntake` / `AttributeRegistry` labels lose "versions" and "signed bundles"; the gap note names assertions as the only signed object |
| 03 | `packages` | Node `llm (normalize_article, ingestion only)` package restored |
| 05a | `node_domain_classes` | `LlmCall` back in a new `Ingestion` package with a note that it is one batched call; `ArticleFact.llm_call`; projection `template_version` → `definition_hash` |
| 05b | `hub_domain_classes` | `CategoryTemplate.bundle_jws` gone; `Requirement` and `Assessment` lose `template_version` |
| 06 | `application_classes` | `TemplateSyncService.current()/install(definition)`; `search(requirement, supplier_id, limit)`; `TemplateService` becomes definition/update/definition_hash; no `sign bundle` edge |
| 07a | `node_database_er` | `llm_calls` entity and `article_facts.llm_call_id` restored; projection `definition_hash` |
| 07b | `hub_database_er` | `category_templates` loses `bundle_jws`/`bundle_kid`; `requirements`/`assessments` lose `template_version`; `assessment_rounds` → `definition_hash` |
| 08 | `assessment_states` | No `upgrade_template` on the two re-entry transitions; `input_hash` uses `definition_hash` |
| 12, 17 | `seq_candidate_search`, `act_requirement_flow` | The `NOT_NORMALIZED` branch is gone (D53); `TEMPLATE_VERSION_UNSUPPORTED` → unknown `template_code` |
| 06, 19 | `application_classes`, `act_attribute_lifecycle` | `NormalizationService.normalize_batch` / `normalize_stale_on_startup` / `merge`; `TemplateRegistry.get(code)`; no `hub_public_keys()`; merge and reject drawn as deferred (D55) |

Verified: `bash charts/render.sh` exits 0 with 21 SVG + 21 PNG; a sweep for `template_version`, `bundle`, `upgrade_template`, `NOT_NORMALIZED`, `relax`, `cursor`, `pinned`, `DRAFT|PUBLISHED` and `hub_public_keys` over `charts/src` finds nothing; 02, 05a, 06, 07a, 07b, 17 and 19 were checked visually.

### Round 9 update (done)
Apply the §10 pre-implementation review (D52–D55): unsigned template definitions, no node job queue, no node LLM, trimmed search surface.

| # | File | Change |
|---|---|---|
| 01 | `use_cases` | "Install template definition (validate, rebuild)"; "Get template definition"; curate step updates the definition instead of publishing a version |
| 02 | `component` | Node loses its worker component and the hub-JWKS secret; hub loses its Ed25519 private key; TemplateSync validates instead of verifying |
| 03 | `packages` | Node loses the `jobs` and `llm (optional)` packages; core `exchange` loses the template bundle |
| 05a | `node_domain_classes` | Remove the `Infrastructure` package (`Job`, `LlmCall`), `NodeJobKind` and `ArticleFact.llm_call`; `TemplateVersion` becomes the definition cache |
| 06 | `application_classes` | Remove the `node jobs` package and `TemplateBundle`; fold `RateLimiter` into `EgressLog`; normalization is called synchronously |
| 07a | `node_database_er` | Remove `jobs` and `llm_calls` and their relations; `template_versions` becomes the definition cache |
| 10 | `job_states` | Hub-only queue |
| 11 | `seq_full_loop` | `GET /templates` + `PUT /templates {definition}`; assertions are the only signed object |
| 12 | `seq_candidate_search` | `POST /search {requirement, supplier_id?, limit}`; no cursor or relaxation hints (D54) |
| 13 | `act_assess_job` | `input_hash` uses `definition_hash` instead of a template version |
| 18 | `act_key_lifecycle` | No hub key to install; one key pair in the system |
| 19 | `act_attribute_lifecycle` | Approve updates the definition; nodes sync by `updated_at`; no publish/sign step |

Also applied: `architecture/data-model.md` (N.9/N.10 removed, N.11 and H.21 reduced, H.14 `input_hash`).

### Round 8 update (done)
Drop the "find similar" pivot from the prototype (D46). The only second search is the automatic one after a result is marked as the current product, run on the extended parameter set.

| # | File | Change |
|---|---|---|
| 01 | `use_cases` | Remove the "Find similar to this (pivot search)" usecase and its actor/extend relations |
| 02 | `component` | `CandidateSearch` label: "two passes, product hints" |
| 06 | `application_classes` | `CandidateSearchService.search(...)` loses `like_variant_id`; `-apply_pivot` removed |
| 11 | `seq_full_loop` | Remove the "find similar to this" block; the re-search is labelled as the second pass |
| 12 | `seq_candidate_search` | Remove the `opt like_variant_id` step, `like_variant_id` from the request and `pivot` / `pivot_conflicts` from the response; row-actions note now lists two actions |

Also applied: `charts/README.md` (diagram 11 and 12 descriptions). Verified: render exits 0 with 21 SVG + 21 PNG, all five changed PNGs checked, and `grep -riE "like_variant|pivot|find similar" charts/src charts/README.md` returns only the deliberate line in 12 stating that no pivot mode exists.

### Round 7 update (done)
| # | File | Change |
|---|---|---|
| 05a | `node_domain_classes` | Remove `ArticleIdentifier`; `ArticleFact.value : TypedValue` note gains the `identifier` shape; `TypedValue.type` gains `identifier`; `ArticleProjection.identifiers : JSON` |
| 07a | `node_database_er` | Remove entity `article_identifiers` and its relations; `article_projection.identifiers`; note that identifier rows are facts |
| 05b | `hub_domain_classes` | Remove `ItemIdentifier`; `ItemSearchProjection.identifiers`; `AttributeDefinition.kind` (ATTRIBUTE or IDENTIFIER); `AssessmentRound.identifier_evidence`; `AttributeProposal.identifier_key` |
| 07b | `hub_database_er` | Remove entity `item_identifiers` and its relations; `item_search_projection.identifiers` (GIN); `attribute_definitions.kind` + `value_type identifier`; `assessment_rounds.identifier_evidence`; drop `questions.identifier_scheme` |
| 03 | `packages` | Core gains the `identifier_evidence` package; `hub_services` depends on it |
| 06 | `application_classes` | Core: `IdentifierEvidence +evaluate(hospital_identifiers, supplier_identifiers)`; `AssessmentService` calls it before `Comparator`; node `ArticleService` writes identifier facts |
| 13 | `act_assess_job` | New first step: `identifier_evidence` → `SAME_TRADE_ITEM` short-circuits to PROPOSED_RESOLUTION (no comparators, no judge); else `NO_INFORMATION` and identifier facts are dropped from the comparison |
| 08 | `assessment_states` | Note the `SAME_TRADE_ITEM` path into PROPOSED_RESOLUTION without a judge call |
| 12 | `seq_candidate_search` | Identifier matching reads the projection's `identifiers` section |
| 14 | `act_answer_enrichment` | Supplier path splits: attribute answer → fact → re-judge; identifier answer → check digit → identifier fact, no re-judge |
| 19 | `act_attribute_lifecycle` | Proposal outcome `IDENTIFIER` exits early to an identifier definition (no criticality, never in a template) |
| 01 | `use_cases` | Hub: "Recognize same trade item (identifier evidence)"; node: identifiers set through article facts |
| 15 | `act_projection_rebuild` | Both lanes: identifier facts collected as a set into the `identifiers` section, excluded from `record_hash` inputs for attributes |

Applied and verified. Also fixed while rendering: in 13 the `NO_INFORMATION` branch inherited the *Hub worker* swimlane after the short-circuit branch switched lanes; an explicit `|Domain (core + hub)|` restores it (same failure mode as the round-5 fix in 19).

### Round 6 update (done)
| # | File | Change |
|---|---|---|
| 01 | `use_cases` | Remove "Track assessment links / assign purchaser" and "Record reported verdict" at the node; add node "Look up articles and user names"; add hub "Assign purchaser / my assessments" |
| 02 | `component` | Node: routers without assessment_links (+ users); ReferenceLink component without AssessmentLinks; add UserDirectory |
| 03 | `packages` | Node services: remove assessment_links, add user_directory |
| 05a | `node_domain_classes` | Remove `AssessmentLink` and its note |
| 05b | `hub_domain_classes` | `Assessment.assigned_to : HospitalPrincipal [0..1]` |
| 06 | `application_classes` | Remove AssessmentLinkService; add UserDirectoryService; `AssessmentService +assign(assessment_id, subject_id, principal)` |
| 07a | `node_database_er` | Remove `assessment_links` and its relations |
| 07b | `hub_database_er` | `assessments.assigned_to_principal_id` + relation to hospital_principals |
| 08 | `assessment_states` | RESOLVED note: no verdict report to the node |
| 11 | `seq_full_loop` | Remove link creation and verdict report; add assignee + list joined with node lookups |

Also applied: `charts/README.md` (architecture sentence, 05a, 06, 05b, 08 and 11 descriptions). Node diagrams now show `GET /articles?article_ref=` and `GET /users` in place of the link table; hub diagrams show `assigned_to_principal_id`, the `ASSIGNED` event and the `(tenant, assignee, status)` index.

### Round 5 update (done)
| # | File | Change |
|---|---|---|
| 01 | `use_cases` | "Build requirement" replaces the envelope; "Link reference product" becomes "Mark current product (preview conflicts)"; add "Find similar to this"; "Store verified verdict" → "Record reported verdict"; remove "Get signed variant snapshot" → "Get variant attributes" |
| 02 | `component` | Node: RequirementBuilder + RateLimiter (no signing); ReferenceLink without signature checks. Hub: RequirementIntake; CandidateSearch with pivot and product hints; AttestationService removed. Signed objects note: assertions and template bundles only |
| 03 | `packages` | Service names (requirement_builder, rate_limits, requirement_intake); core `exchange` = requirement, assertion, template bundle, jws |
| 05a | `node_domain_classes` | `EgressLog` replaces `OutboundEnvelope`; `HospitalArticle.reference_source`; `AssessmentLink` without attestation; `ArticleProjection.requirement_hash`; settings note (product hints, rate limits, `EGRESS_DENY_ATTRIBUTES`) |
| 05b | `hub_domain_classes` | `Requirement` replaces `RequirementEnvelope` (no jti/kid/jws); `Question.answered_in_requirement`; `Assessment.current_requirement` |
| 06 | `application_classes` | Node: RequirementBuilder, RateLimiter, ReferenceLinkService (preview/set), AssessmentLinkService (report). Hub: RequirementIntake, CandidateSearchService (pivot, hints); AttestationService removed. Core: RequirementPayload, HubAssertion, TemplateBundle; Jws only for the latter two |
| 07a | `node_database_er` | `egress_log`; `reference_source`; assessment_links without attestation; `requirement_hash` |
| 07b | `hub_database_er` | `requirements` table; renamed foreign keys; events without `ATTESTATION_ISSUED` |
| 08 | `assessment_states` | Requirement wording; RESOLVED note: verdict reported to the node, no attestation |
| 09 | `question_states` | Purchaser branch via new requirement |
| 11 | `seq_full_loop` | **Rewrite:** single search, current product with preview and re-search, find similar, plain requirements, reported verdict |
| 12 | `seq_candidate_search` | **Rewrite:** requirement → search → pivot and product-hint steps → row actions |
| 13 | `act_assess_job` | Requirement wording; `input_hash` from `requirement_hash` |
| 14 | `act_answer_enrichment` | Purchaser path via new requirement |
| 15 | `act_projection_rebuild` | `requirement_hash` over the shareable subset |
| 16 | `seq_token_exchange` | `egress_log` instead of the old envelope table; rate-limit check at the node |
| 17 | `act_requirement_flow` | **Replaces** `17_act_envelope_build`: allowlist build, product hints, rate limits and egress log at the node; strict schema intake at the hub; "why not signed" note |
| 18 | `act_key_lifecycle` | Hub key signs template bundles only; no stored-envelope re-verification |
| 19 | `act_attribute_lifecycle` | `EGRESS_DENY_ATTRIBUTES` wording |

Unchanged: 04 (deployment), 10 (job states).

**Round 5 update is done when:**
- `bash charts/render.sh` exits 0 with 21 SVG + 21 PNG
- the old `17_act_envelope_build` source and renders are removed
- `grep -riE "envelope|attestation|snapshot" charts/src` finds nothing
- every changed PNG has been checked against §4.4, §4.7, §4.13–§4.15 and Appendix A (N.3, N.6–N.8, H.12–H.14)
- `charts/README.md` is updated

### Registry update (done)
| # | File | Change |
|---|---|---|
| 01 | `use_cases` | Hub: propose attribute (worker), curate proposals / publish template version (operator), view additional information. Node: install template bundle |
| 02 | `component` | Hub: AttributeRegistry + TemplatePublisher; node: TemplateSync; template bundle as a signed object carried by the client |
| 05a | `node_domain_classes` | + `TemplateVersion` |
| 05b | `hub_domain_classes` | + `AttributeDefinition`, `CategoryTemplate`, `AttributeProposal`; `ItemSearchProjection.additional_attributes`; links to Question and ItemFact |
| 06 | `application_classes` | Hub: AttributeRegistryService, TemplateService, ProposeAttributePipeline + handler; node: TemplateSyncService; core: `TemplateDefinition`, `TemplateBundle` claims |
| 07a | `node_database_er` | + `template_versions` |
| 07b | `hub_database_er` | + `attribute_definitions`, `category_templates`, `attribute_proposals`; `additional_attributes`; new CHECK values |
| 08 | `assessment_states` | Guard `ATTRIBUTE_PROPOSAL_PENDING` on send-questions; `upgrade_template` on request-more-info / extra-round |
| 09 | `question_states` | Free question: proposal pending → key assigned (existing or PROVISIONAL) |
| 19 | `act_attribute_lifecycle` | **New:** question without attribute → proposal → provisional on send → supplier fact shared as information → curation (approve / merge / reject) → publish version → client syncs nodes → projections rebuild |

Registry update done when `bash charts/render.sh` exits 0 with 21 SVG + 21 PNG, each changed PNG checked against §4.3.1 and Appendix A (N.11, H.20–H.22), and `charts/README.md` lists diagram 19.

### v3 regeneration (done): changes per diagram
| # | File | Change |
|---|---|---|
| 01 | `use_cases` | Actors: Purchaser, Node admin, Supplier user, Hub operator, Worker, LLM provider. Add: build/inspect envelope, view egress log, exchange token, store verdict at node, register tenant key, rotate/revoke key |
| 02 | `component` | **Rewrite:** hospital node, supplier hub, core library, purchaser client and supplier client; no connector between node and hub; provided/required interfaces for envelope, assertion, snapshot, attestation |
| 03 | `packages` | **Rewrite:** uv workspace (`packages/equivalence-core`, `apps/hospital-node`, `apps/supplier-hub`, `tools/demo-client`, `tests/e2e`) with allowed dependency arrows and forbidden ones marked from import-linter |
| 04 | `deployment` | **Rewrite:** three modes (prototype local, on-prem node, managed node) with firewall boundary, secrets placement per node |
| 05 | `domain_classes` | **Split** into `05a_node_domain_classes` (N.1–N.10) and `05b_hub_domain_classes` (H.1–H.19); cross-service references shown as text attributes, not associations |
| 06 | `application_classes` | Group by service; add EnvelopeBuilder, AssertionSigner, ReferenceLinkService, AssessmentLinkService, EgressLog (node); TokenExchangeService, EnvelopeIntake, AttestationService, TenantKeyService (hub); `jws` sign/verify in core |
| 07 | `database_er` | **Split** into `07a_node_database_er` and `07b_hub_database_er` |
| 08 | `assessment_states` | Guard on send-questions (no open PURCHASER questions); envelope-received self-transition; attestation on RESOLVED |
| 09 | `question_states` | PURCHASER branch: ANSWERED/UNAVAILABLE via envelope |
| 10 | `job_states` | Note: one queue per service |
| 11 | `seq_full_loop` | **Rewrite:** lifelines Purchaser client, Node, Hub, Hub worker, LLM tiers, Supplier; steps of §4.12 |
| 12 | `seq_candidate_search` | **Rewrite:** node envelope → hub `POST /search` (§4.13) |
| 13 | `act_assess_job` | Hospital record comes from the current envelope; `input_hash` from envelope + supplier record hash |
| 14 | `act_answer_enrichment` | Supplier path unchanged; add purchaser path (node fact → envelope → hub) |
| 15 | `act_projection_rebuild` | Lanes for node (article) and hub (family/variant) using the same core resolver |
| 16 | `seq_token_exchange` | **New:** login → assertion signing + egress row → exchange checks → hub token → expiry → re-exchange |
| 17 | `act_envelope_build` | **New:** projection → allowlist → strict claims → hash → sign → egress row → return; hub intake checks |
| 18 | `act_key_lifecycle` | **New:** onboarding with fingerprint confirmation, rotation with overlap window, revocation cascade |

Old sources `05_domain_classes.puml` and `07_database_er.puml` and their rendered files are removed and replaced by the split versions. `charts/README.md` is updated with the new list and plan section links.

### Verification
- `bash charts/render.sh` exits 0; 20 SVG + 20 PNG files; no stale renders of removed sources.
- Each PNG viewed and checked against the v3 sections: 02–04 vs §4.1/§4.2/§4.16, 05a/05b/07a/07b vs Appendix A, 08–09 vs §4.7, 11–12 vs §4.12/§4.13, 16–18 vs §4.14/§4.15.
- Only files under `charts/` change in this step.
