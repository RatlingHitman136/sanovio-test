# Article Equivalence Loop — prototype

Hospital purchasers compare an article they already buy with items in supplier catalogs. Deterministic comparators and an LLM judge decide equivalence attribute by attribute, missing data turns into questions for the supplier or the purchaser, and the answers enrich the records until the assessment is resolved.

The system is split into a **hospital node** (one per hospital, can run behind the hospital firewall) and a central **supplier hub**; the purchaser's client is the only bridge between them.

- Design: [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md)
- Data model: [`architecture/data-model.md`](architecture/data-model.md)
- Diagrams: [`architecture/charts.md`](architecture/charts.md), rendered in `charts/png/`
- Working rules and project map: [`CLAUDE.md`](CLAUDE.md)

## Requirements
[uv](https://docs.astral.sh/uv/) (Python 3.14 is installed by uv if missing), GNU make, **Node.js 22** for the
browser apps, and Java for re-rendering the diagrams. On Ubuntu/WSL:

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
```

## Getting started
```bash
make setup    # install every workspace member, create apps/*/.env from the examples
make keys     # node signing keys in .secrets/ (never overwritten)
make dev      # supplier hub on :8000, hospital node on :8001
uv run --package demo-client demo-client health   # both services should be "up"
```

API docs: http://127.0.0.1:8001/docs (node) and http://127.0.0.1:8000/docs (hub).

## Running the demo
Fill in the two `.env` files first: `NODE_SEED_PASSWORD` and `HUB_SEED_PASSWORD` (the passwords the
demo accounts get). Offline, the node reads article names with its parsers (`NORMALIZE_MODE=rules`)
and the hub answers every model call from scripted fakes (`LLM_MODE=fake`); nothing leaves the
machine. With keys, see "Running with real models" below.

```bash
make seed               # both databases: 10 articles at the node, 6 families / 54 variants at
                        # the hub, and the node's public keys registered at the hub
make dev                # hub on :8000, node on :8001 (the hub's job worker runs inside it)
make demo-node          # the standalone node: articles, a requirement, an assertion, egress, 429
make demo-search        # node + hub: a requirement, the token exchange, the candidate search
make demo SCENARIO=1    # then 2, 3 and 4: the §21 scenarios, each ending with its checks
```

| Scenario | What happens |
|---|---|
| 1 · full loop | art_03 (10 ml Luer-Lock syringe): search, Injekt® marked as the current product, second search, assessment against BD Plastipak™, the purchaser's answers returned as a new requirement, BD's answers, round 2 EQUIVALENT_WITH_DEVIATIONS, resolved; the egress log and a leak check prove no name, brand, price or identifier left the node |
| 2 · early stop | the search leaves BD Emerald™ out (Luer, not Luer-Lock); an assessment opened anyway is NOT_EQUIVALENT in round 1 with no questions |
| 3 · manual decision | art_06 (21 G needle) against BD Microlance™: the purchaser answers the wall type, BD cannot give the inner diameter, the loop stops (BLOCKING_UNAVAILABLE) and the purchaser decides |
| 4 · unreliable identifiers | art_06 against B. Braun Sterican®: the node flags the article's broken GTIN/EAN, nothing identifier-like leaves it, the purchaser asks for B. Braun's GTIN (stored as an identifier, not compared), round 2 EQUIVALENT |

Supplier answers come from the hub's development simulator (`POST /dev/assessments/{id}/simulate-supplier`,
operators only, synthetic datasheets). The scenarios tell a first encounter: run them after
`make seed`, in order; a replay on the same data asks less, because both services remember.

## The browser apps
Two apps in `frontend/` (ARCHITECTURE §20): the **purchaser app**, served by each hospital node, and the
**supplier app**, served by the hub. The purchaser app is the bridge between the two services; the
node itself never calls the hub.

```bash
make ui-setup          # once: npm ci (and `cd frontend && npx playwright install chromium` for ui-e2e)
make dev               # hub :8000 and node :8001, as above
make ui-dev            # purchaser app http://127.0.0.1:5173, supplier app http://127.0.0.1:5174
```

Sign in as Anna (`anna.meier@demo-ksp.example`) in the purchaser app and as BD
(`catalog@bd-demo.example`) in the supplier app, with the seed passwords. Scenario 1 by hand:
Articles → *Einmalspritze 10 ml Luer-Lock steril* → **Search the hub** → Injekt: **This is our current
product** → Plastipak: **Start assessment** → answer "Questions for you" → **Send questions** → in the
supplier app open the request and **Let the simulator answer** (or answer by hand) → back in the
purchaser app round 2 appears → **Confirm verdict**.

Served the production way: `make ui-build`, then start the node with
`PURCHASER_UI_DIR=frontend/apps/purchaser/dist` and the hub with
`SUPPLIER_UI_DIR=frontend/apps/supplier/dist` (and `CORS_ORIGINS=http://127.0.0.1:8001`); open
http://127.0.0.1:8001/ and http://127.0.0.1:8000/. Tokens live in memory only: a reload signs you out.

`make ui-e2e` runs scenario 1 in a headless browser through both apps, on its own ports and databases
(`var/e2e/`), so a running `make dev` is not disturbed. Operators still work in Swagger (`:8000/docs`);
an operator section in the hub-served app comes later.

## Running with real models
Put `ANTHROPIC_API_KEY` in both `.env` files (the hospital's key at the node, Sanovio's at the hub),
set `NORMALIZE_MODE=llm` at the node and `LLM_MODE=anthropic` at the hub, then `make seed`, `make dev`
and `make demo SCENARIO=1..4` as above. Every call is logged with tokens and cost in each service's
`llm_calls` table; the key itself is never stored or logged.

## Evals
```bash
make eval                 # real API: model quality on hand-labelled data, results in var/evals/
EVAL_LLM=fake make eval   # the same harness offline (node parsers only, hub scripted fakes)
```
- **Node:** normalization of the 10 demo names against `hospital_node/evals/golden_extraction.yaml`,
  once with the parsers alone and once with the model plus parsers (target ≥90%).
- **Hub:** round-1 verdicts on 13 labelled article/variant pairs (target ≥85%), every critical gap
  turned into a question (100%), the judge on semantic attributes, and `extract_answer` on 10 German
  supplier comments. Cost and latency per model are reported for every run.

## Thresholds
| Setting | Default | Where |
|---|---|---|
| Hub assertion lifetime | 300 s, ±60 s clock skew | node signs, hub checks (`ASSERTION_LEEWAY_S`) |
| Exchanged hub session | 30 min, renewed silently by the client | hub `EXCHANGE_TTL_MINUTES` |
| Node and supplier logins | 8 h | `TOKEN_TTL_HOURS` |
| Requirements per purchaser | 120 / hour, alert at 80% | node `REQUIREMENT_RATE_LIMIT_PER_HOUR` |
| Assertions per purchaser | 30 / hour | node `ASSERTION_RATE_LIMIT_PER_HOUR` |
| Daily egress alert | 300 objects per user | node `EGRESS_DAILY_ALERT_PER_USER` |
| Rounds per assessment | 3 (an extra round adds one) | hub `MAX_ROUNDS` |
| Job retries | 3, with growing delay; stuck jobs requeued after 10 min | hub queue |
| CORS | off; named origins only, never `*` | hub `CORS_ORIGINS` |

## Runbook: a new hospital
1. At the hospital: `uv run --package hospital-node hospital-node keygen --out .secrets/node_<code>_ed25519.pem --kid <code>-<yyyy-mm>`.
   The private key stays on the node (mode 0600); the command prints the public JWK and its fingerprint.
2. At the hub, an operator creates the tenant (`POST /admin/tenants`) and registers the public JWK
   (`POST /admin/tenants/{id}/signing-keys`, or `supplier-hub register-tenant --tenant <code>
   --jwk-file <file>` on the hub host).
3. The operator reads the returned fingerprint to the hospital's IT by phone; both must match
   before the first purchaser signs in.
4. The purchaser client then exchanges node assertions for hub sessions and syncs the templates.

## Runbook: rotating a node key
1. Generate the new key with a new `kid` and register it at the hub with `not_before` set to the
   switch-over time; confirm the fingerprint as above.
2. At `not_before`, point the node at the new key (`NODE_SIGNING_KEY_FILE`, `NODE_SIGNING_KID`) and
   restart it.
3. Revoke the old `kid` (`POST /admin/tenants/{id}/signing-keys/{kid}/revoke`). Every hub session
   exchanged with it ends at once; purchasers are re-exchanged silently with the new key.

## Checks
```bash
make lint     # ruff, format check, mypy strict, import boundaries
make test     # every package, both apps, the demo client, the in-process e2e suite and the UI tests
make ui-e2e   # scenario 1 in a real browser through both apps
```

## Status
All nine stages done (ARCHITECTURE §22): the shared core, the standalone **hospital node**, the
**supplier hub** with its catalogs, search and the full **assessment loop**, the **demo client** with
the four scenarios, an in-process end-to-end suite and the evals, and the two **browser apps**
(purchaser, served by the node; supplier, served by the hub), refined in stage 8: suppliers edit
their catalog per family and per variant, the current product is highlighted in search results, the
comparison sorts and filters, and free text is compared by meaning ("nein" = "keine" without a model;
other rewordings by one small Haiku call per round). Next, when wanted: an operator section
in the hub-served app (attribute curation, hospitals and keys).
