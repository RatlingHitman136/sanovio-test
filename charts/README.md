# Charts: UML diagrams for the Article Equivalence Loop (v3: hospital node + central supplier hub)

Rendered diagrams of the prototype design. Sources are PlantUML text files in `src/`; images are generated into `svg/` (sharp at any zoom, best for the large diagrams) and `png/` (quick preview). All content follows the plan in `~/.claude/plans/encapsulated-wondering-pixel.md` (section numbers below refer to it).

**Architecture in one sentence:** a hospital node (one per hospital, can run behind the hospital firewall) keeps article data; a central supplier hub keeps catalogs, questions, answers and assessments; the two never connect, and the purchaser's client carries everything between them: signed hub assertions and template bundles, plus plain-JSON requirements and variant attributes. Assessments and verdicts live only at the hub; the client adds article and user names from the node.

Colour key used across diagrams: blue = hospital node, green = supplier hub, orange = shared `equivalence-core` library.

## Re-render

```bash
bash charts/render.sh
```

Needs only Java. The first run downloads a pinned PlantUML jar (v1.2026.8, SHA-256 checked) into `charts/.tools/` (not versioned). Rendering stops on the first syntax error instead of producing error images.

## Notation in brief

| Symbol | Meaning |
|---|---|
| solid arrow `-->` | association / call / message |
| dashed arrow `..>` | dependency, «include», «extend», «derive» |
| red dashed arrow «forbidden» | dependency that import-linter rejects |
| filled diamond | composition (the part cannot exist without the whole) |
| hollow triangle, solid line | generalization (subclass) |
| hollow triangle, dashed line | realization (implements an interface) |
| `[0..1]`, `0..*`, `1..*` | multiplicity |
| `«derived»` | computed from other data, rebuildable |
| `«append-only»` | rows are only ever added |
| `«no FK»` | id from the other service; no database link |
| `[guard]` on a transition | condition that must hold |
| crow's foot `o{` / `\|{` | zero-or-many / one-or-many (ER) |
| `*` before a column (ER) | NOT NULL |

## Diagrams

### 01 Use cases (§4.10, §4.12)
Actors (purchaser, node admin, supplier user, hub operator, node and hub workers, LLM provider) and what each can do on the node and on the hub; cross-system «include» links are carried out by the client.
[SVG](svg/01_use_cases.svg)

![01 use cases](png/01_use_cases.png)

### 02 Components (§4.1)
Hospital node, supplier hub and the shared core, with the purchaser and supplier clients; where the private keys, the Anthropic key and the databases live. No connector between node and hub.
[SVG](svg/02_component.svg)

![02 components](png/02_component.png)

### 03 Packages / project structure (§4.2, D40)
The uv workspace (`packages/equivalence-core`, `apps/hospital-node`, `apps/supplier-hub`, `tools/demo-client`), allowed dependencies, forbidden node ⇄ hub imports and the import-linter contracts.
[SVG](svg/03_packages.svg)

![03 packages](png/03_packages.png)

### 04 Deployment (§4.16)
Prototype on one machine (hub :8000, nodes :8001/:8002), on-prem node behind a hospital firewall, and a managed node run by us in an isolated environment.
[SVG](svg/04_deployment.svg)

![04 deployment](png/04_deployment.png)

### 05a Node domain model: class diagram (Appendix N.1–N.11)
Users with `hub_subject_id`, articles with `article_ref` and current product, facts (attributes **and** identifiers, round 7), projection with `record_hash`, `requirement_hash` and an `identifiers` section, egress log, installed template versions. No assessment table (N.8 removed in round 6), no identifier table (N.4 removed in round 7).
[SVG](svg/05a_node_domain_classes.svg)

![05a node domain classes](png/05a_node_domain_classes.png)

### 05b Hub domain model: class diagram (Appendix H.1–H.22)
Tenants, public signing keys, pseudonymous principals, catalog, supplier facts (identifiers included), attribute registry with `kind = ATTRIBUTE | IDENTIFIER` (definitions, versioned category templates with criticality, proposals), requirements, assessments (with pseudonymous assignee), rounds, questions, answers, events.
[SVG](svg/05b_hub_domain_classes.svg)

![05b hub domain classes](png/05b_hub_domain_classes.png)

### 06 Application design: class diagram (§4.4–§4.9, §4.13–§4.15)
Node services (RequirementBuilder, RateLimiter, AssertionSigner, EgressLog, ReferenceLinkService, UserDirectoryService, TemplateSyncService), hub services (TokenExchangeService, RequirementIntake, CandidateSearchService, CatalogService, AssessmentService, AttributeRegistryService, TemplateService, …), the core (comparators, FactResolver, VerdictRules, `RequirementPayload`, `Jws` for assertions and template bundles, `IdentifierEvidence`), LLM client and job handlers.
[SVG](svg/06_application_classes.svg)

![06 application classes](png/06_application_classes.png)

### 07a Node database schema: ER diagram (Appendix N)
[SVG](svg/07a_node_database_er.svg)

![07a node database ER](png/07a_node_database_er.png)

### 07b Hub database schema: ER diagram (Appendix H)
[SVG](svg/07b_hub_database_er.svg)

![07b hub database ER](png/07b_hub_database_er.png)

### 08 Assessment lifecycle at the hub: state machine (§4.7)
Includes the requirement self-transition for purchaser answers, the send-questions guards and the template upgrade option; the verdict stays at the hub after RESOLVED (no copy at the node).
[SVG](svg/08_assessment_states.svg)

![08 assessment states](png/08_assessment_states.png)

### 09 Question lifecycle: state machine (§4.7, H.15)
Supplier branch at the hub; purchaser branch answered at the node and delivered in a new requirement.
[SVG](svg/09_question_states.svg)

![09 question states](png/09_question_states.png)

### 10 Background job lifecycle: state machine (§4.8, H.18, N.9)
One queue per service.
[SVG](svg/10_job_states.svg)

![10 job states](png/10_job_states.png)

### 11 Full loop through the client bridge: sequence diagram (§4.12)
Scenario 1 end to end: node login, assertion, token exchange, template sync, the two search passes around "current product", assessment requirement, round 1, questions, supplier answers, extraction, round 2, resolve, assessment list joined with node article and user names.
[SVG](svg/11_seq_full_loop.svg)

![11 full loop sequence](png/11_seq_full_loop.png)

### 12 Candidate search: sequence diagram (§4.13)
Requirement built, rate-limited and logged at the node; validated and used by `POST /search` at the hub, with product-hint matching; the same endpoint serves the first and the second (post-current-product) pass; error branches 429 / 409 / 422.
[SVG](svg/12_seq_candidate_search.svg)

![12 candidate search sequence](png/12_seq_candidate_search.png)

### 13 ASSESS job at the hub: activity diagram (§4.4, §4.7)
Starts with `identifier_evidence`: `SAME_TRADE_ITEM` ends the round as EQUIVALENT with no judge call. Otherwise the hospital side comes from the current requirement; `input_hash` from `requirement_hash` + supplier `record_hash` + template version.
[SVG](svg/13_act_assess_job.svg)

![13 assess job activity](png/13_act_assess_job.png)

### 14 Answers and enrichment: activity diagram (§4.5, §4.7)
Purchaser path (node fact → requirement → hub) and supplier path (submit, facts, extraction, re-judge).
[SVG](svg/14_act_answer_enrichment.svg)

![14 answer enrichment activity](png/14_act_answer_enrichment.png)

### 15 Projection rebuild on both sides: activity diagram (§4.6, N.6, H.11)
One core resolver, two read models; `record_hash` vs `requirement_hash`.
[SVG](svg/15_act_projection_rebuild.svg)

![15 projection rebuild activity](png/15_act_projection_rebuild.png)

### 16 Token exchange: sequence diagram (§4.15)
Node login → node-signed assertion (egress row) → hub checks (typ, alg, kid, signature, aud, exp, jti) → hub token → expiry and re-exchange.
[SVG](svg/16_seq_token_exchange.svg)

![16 token exchange sequence](png/16_seq_token_exchange.png)

### 17 Requirement flow: activity diagram (§4.14)
Allowlist build, withheld attributes, optional product hints, rate limits and egress log at the node; strict schema intake and search vs assessment handling at the hub; why the requirement is not signed.
[SVG](svg/17_act_requirement_flow.svg)

![17 requirement flow activity](png/17_act_requirement_flow.png)

### 18 Signing key lifecycle: activity diagram (§4.15)
Onboarding with out-of-band fingerprint confirmation, rotation with overlap window, revocation cascade.
[SVG](svg/18_act_key_lifecycle.svg)

![18 key lifecycle activity](png/18_act_key_lifecycle.png)

### 19 New attribute lifecycle: activity diagram (§4.3.1, D43–D45)
A free question gets an attribute proposal from the LLM (with a duplicate check and no criticality). The attribute becomes PROVISIONAL on send, and the supplier's answer is shared with all hospitals as additional information. The curator then approves (sets criticality), merges or rejects; a new template version is published, and clients sync it to the nodes.
[SVG](svg/19_act_attribute_lifecycle.svg)

![19 attribute lifecycle activity](png/19_act_attribute_lifecycle.png)
