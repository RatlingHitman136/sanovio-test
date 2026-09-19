# CLAUDE.md

Working rules and project map for the Article Equivalence Loop prototype. The design lives in [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md); read the relevant section before changing code.

## Rules

1. **Clean code, no redundancy.** Follow Python best practice: type hints everywhere, small functions with one job, clear names, no dead code, no speculative abstractions or "might need it later" parameters. Before writing a helper, check whether `equivalence-core` already provides it, and reuse it instead of duplicating logic.

2. **Modular and separately testable.** Every module has one responsibility and its own tests. Pass dependencies in (settings, HTTP clients, database sessions, LLM clients, clocks) instead of importing them as globals, so each module can be tested without the others. External services are always faked in tests (`FakeLLM`, `httpx.MockTransport`, temporary files); no test calls a real API or needs network access.

3. **Never touch git history.** Never run `git init`, `git add`, `git commit`, `git push`, `git rebase`, `git reset` or anything else that stages or changes history. When a logical checkpoint is reached — at the latest at the end of every stage — stop and tell the user it is a good time to commit, with a one-line suggested commit message. The user commits manually.

4. **uv only for Python; npm only for the browser apps.** Use uv for Python versions, libraries and commands (`uv sync`, `uv add --package <member> …`, `uv run …`). No pip, venv, poetry or requirements files. JavaScript lives in `frontend/` and uses npm workspaces (Node 22). Add a dependency only in the change that first uses it.

5. **The architecture documents are the source of truth.** `architecture/ARCHITECTURE.md`, `architecture/data-model.md` and the diagrams in `charts/` describe the target. If the implementation needs to diverge, stop and raise it first. When a change is agreed, update the documents — and re-render the diagrams with `make charts` — in the same step as the code.

6. **Service boundaries are hard.**
   - `hospital_node` and `supplier_hub` never import each other and never call each other over the network; the purchaser client is the only bridge.
   - `equivalence_core` imports neither app, no `llm_client`, and no web, database or LLM library.
   - Both apps reach the Anthropic SDK only through `packages/llm-client`, and share plumbing only through `packages/service-kit`; neither package imports an app or any domain code.
   - `hospital_node` imports no HTTP client.
   - `make lint` enforces these with import-linter; never weaken a contract to make a change pass.

7. **Security defaults.**
   - No secret in code, logs, test fixtures, error messages or API responses.
   - Keys are loaded from files outside version control (`.secrets/`, mode 0600).
   - Hospital data leaves the node only through the requirement allowlist (ARCHITECTURE §16); never bypass it.

8. **Stage discipline.** Work one stage at a time, in the order of ARCHITECTURE §22. A stage is done only when its "ends with" check passes and `make lint` and `make test` are green. Then report what was built, suggest a commit, and wait for the go-ahead before starting the next stage.

9. **Quality gates.** `ruff` (lint and format), `mypy --strict` on every package, `pytest`. Code, identifiers and docs are in English. Comments explain *why*, not *what*.

## Project structure

Status: ✅ exists (stages 0–8 done).

```
sanovio/
├── CLAUDE.md                     ✅ this file
├── README.md                     ✅ what the project is, how to run it
├── Makefile                      ✅ setup, keys, seed, dev, dev-node, dev-hub, demo-node, demo-search,
│                                    demo, eval, lint, format, test, charts
├── pyproject.toml                ✅ uv workspace root, dev tools, ruff / mypy / pytest / import-linter config
├── uv.lock  .python-version      ✅
├── architecture/                 ✅ ARCHITECTURE.md (design), data-model.md (tables),
│                                    charts.md (diagram inventory), design-plan.md (design history)
├── charts/                       ✅ PlantUML sources (src/), renders (svg/, png/), render.sh
├── data_examples/                ✅ client sample files (never committed)
├── packages/
│   ├── llm-client/               ✅ LLMClient protocol, Anthropic adapter, FakeLLM, prompts, prices,
│   │                                RecordingLLM + usage summary (evals)
│   ├── service-kit/              ✅ db base, clock, argon2id + bearer tokens, error → HTTP mapping,
│   │                                ERROR_RESPONSES for OpenAPI
│   └── equivalence-core/         shared library, plain Python
│       └── src/equivalence_core/
│           ├── values.py         ✅ typed value shapes (AttributeValue excludes identifiers)
│           ├── hashing.py        ✅ canonical JSON + SHA-256 for every compared hash
│           ├── ids.py            ✅ article_ref / subject id patterns (Crockford base32)
│           ├── quality.py        ✅ DataQualityIssue flags
│           ├── identifiers.py    ✅ scheme lists per side, GS1 check digit, identifier problems
│           ├── validation.py     ✅ a typed value checked against its attribute definition
│           ├── service_info.py   ✅ health response shared by both services and the demo client
│           ├── templates/        ✅ model, loader, seed/*.yaml (definitions + 3 templates)
│           ├── parsers/          ✅ numbers, units, gauge, dimensions, packaging, synonyms, text,
│           │                        standards (canonical designations), wording (canonical free text)
│           ├── facts.py          ✅ precedence, resolver, record_hash
│           ├── exchange/         ✅ keys, requirement, assertion, jws
│           ├── comparators.py    ✅ per-attribute judgments; comparator decisions are final
│           ├── verdict_rules.py  ✅ the §8.5 verdict table + the judge-merge rule
│           └── identifier_evidence.py  ✅ SAME_TRADE_ITEM | NO_INFORMATION (never a mismatch)
├── apps/
│   ├── hospital-node/            one per hospital, port 8001
│   │   └── src/hospital_node/
│   │       ├── main.py           ✅ app factory + lifespan (loads secrets, normalizes changed articles)
│   │       ├── cli.py            ✅ keygen, migrate, seed, create-user, eval
│   │       ├── alembic/ seed/    ✅ migrations and the demo datasets, shipped in the package
│   │       ├── core/             ✅ settings, secrets, db, clock, security, migrations
│   │       ├── api/v1/           ✅ health, auth, users, articles, reference, requirements,
│   │       │                        hub_assertions, egress, templates, admin, dev
│   │       ├── models/ schemas/  ✅ node tables N.1–N.11 and the API bodies
│   │       ├── services/         ✅ articles, facts, normalization, projection, requirement_builder,
│   │       │                        egress_log, llm_calls, assertion_signer, reference_link, auth,
│   │       │                        user_directory, template_sync, seed
│   │       ├── llm/              ✅ normalize_article pipeline + prompt (ingestion only)
│   │       └── evals/            ✅ golden_extraction.yaml, extraction (rules vs llm + parsers)
│   └── supplier-hub/             central, port 8000
│       └── src/supplier_hub/
│           ├── main.py           ✅ app factory
│           ├── cli.py            ✅ migrate, seed, create-operator, register-tenant, worker, eval
│           ├── alembic/ seed/    ✅ migrations, both catalogs, scripted fake readings,
│           │                        synthetic hidden datasheets (dev simulator)
│           ├── core/             ✅ settings, db, migrations
│           ├── api/v1/           ✅ health, auth, admin (+ attribute proposals), templates, catalog,
│           │                        search, assessments, supplier, dev
│           ├── models/ schemas/  ✅ H.1–H.22
│           ├── services/         ✅ auth, tenants_keys, token_exchange, attribute_registry,
│           │                        templates, catalog, normalization, projection,
│           │                        requirement_intake, candidate_search, seed, assessment, assess,
│           │                        questions, supplier_inbox, enrichment, resolution,
│           │                        attribute_proposals, supplier_simulator, supplier_catalog
│           ├── domain/           ✅ state_machine, stop_conditions
│           ├── llm/              ✅ normalize_item, judge, extract_answer, propose_attribute,
│           │                        simulate_supplier, compare_text + prompts; fakes (scripted)
│           ├── jobs/             ✅ queue, worker, handlers
│           └── evals/            ✅ golden verdicts + comments, verdicts, answers
├── tools/
│   └── demo-client/              ✅ api (shared client, ApiError), node, hub, session (401 re-exchange,
│                                    template sync), scenarios/ 1–4, cli: health, node-demo, demo-search,
│                                    scenario
├── tests/e2e/                    ✅ both apps in-process: scenarios 1–4, isolation (6), registry (7)
├── openapi/                      ✅ node.json, hub.json: exported specs (`make openapi`; a test keeps them current)
├── frontend/                     ✅ npm workspaces (ARCHITECTURE §20), TypeScript strict
│   ├── packages/api/             ✅ generated OpenAPI types, openapi-fetch clients, ApiError,
│   │                                PurchaserSession (node login → assertion → hub, 401 renewal,
│   │                                template sync), HubSession
│   ├── packages/ui/              ✅ shadcn-style components on Radix + Tailwind: shell, sign-in,
│   │                                badges, typed value view/input from `expected_answer`, dialog
│   ├── apps/purchaser/           ✅ served by the node: assessments, articles, search, current
│   │                                product, assessment detail with questions both ways
│   ├── apps/supplier/            ✅ served by the hub: inbox, answer form, simulator (dev), catalog
│   │                                with family pages (edit family values, override per variant)
│   └── e2e/                      ✅ Playwright: scenario 1 across both apps (own ports + var/e2e)
├── .secrets/                     created by `make keys` (git-ignored)
└── var/                          SQLite files (git-ignored)
```

Each workspace member keeps its tests in its own `tests/` directory.

## Commands

| Command | What it does |
|---|---|
| `make setup` | `uv sync --all-packages` (a plain `uv sync` at the root would drop the members); creates each app's `.env` from `.env.example` if missing |
| `make keys` | node signing keys for `ten_ksp` and `ten_spital2` in `.secrets/` (never overwrites) |
| `make seed` | seed node and hub and register the node keys (`make seed-node` / `make seed-hub` for one); needs `NODE_SEED_PASSWORD` and `HUB_SEED_PASSWORD` |
| `make demo-node` | walk through the standalone node (needs `make dev-node` running) |
| `make demo-search` | node + hub: requirement, token exchange, candidate search (needs `make dev`) |
| `make demo SCENARIO=n` | §21 scenario 1–4 over HTTP, ending with its checks (needs `make dev`; run after `make seed`, in order) |
| `make eval` | model quality on hand-labelled data, results in `var/evals/` (real API; `EVAL_LLM=fake` runs it offline) |
| `make dev` | hub on :8000 and node on :8001 (`make dev-hub`, `make dev-node` for one) |
| `make lint` | ruff, format check, mypy strict, import contracts, plus eslint, prettier and tsc for `frontend/` |
| `make format` | ruff format + auto-fixable lint |
| `make test` | pytest for every workspace member and `tests/e2e`, plus Vitest for `frontend/` |
| `make ui-setup` | `npm ci` in `frontend/` (Node 22; once: `npx playwright install chromium` for `ui-e2e`) |
| `make ui-dev` | purchaser app on :5173 and supplier app on :5174, proxying to `make dev` |
| `make ui-build` | build both apps; serve them via `PURCHASER_UI_DIR` (node) and `SUPPLIER_UI_DIR` (hub) |
| `make ui-lint` / `make ui-test` | eslint + prettier + tsc / Vitest (both also run by `make lint` / `make test`) |
| `make ui-e2e` | Playwright: scenario 1 in a browser through both apps, on ports 18000/18001/15173/15174 |
| `make openapi` | re-export both OpenAPI specs and regenerate the apps' typed clients |
| `make charts` | re-render the UML diagrams |
