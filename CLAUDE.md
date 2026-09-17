# CLAUDE.md

Working rules and project map for the Article Equivalence Loop prototype. The design lives in [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md); read the relevant section before changing code.

## Rules

1. **Clean code, no redundancy.** Follow Python best practice: type hints everywhere, small functions with one job, clear names, no dead code, no speculative abstractions or "might need it later" parameters. Before writing a helper, check whether `equivalence-core` already provides it, and reuse it instead of duplicating logic.

2. **Modular and separately testable.** Every module has one responsibility and its own tests. Pass dependencies in (settings, HTTP clients, database sessions, LLM clients, clocks) instead of importing them as globals, so each module can be tested without the others. External services are always faked in tests (`FakeLLM`, `httpx.MockTransport`, temporary files); no test calls a real API or needs network access.

3. **Never touch git history.** Never run `git init`, `git add`, `git commit`, `git push`, `git rebase`, `git reset` or anything else that stages or changes history. When a logical checkpoint is reached — at the latest at the end of every stage — stop and tell the user it is a good time to commit, with a one-line suggested commit message. The user commits manually.

4. **uv only.** Use uv for Python versions, libraries and commands (`uv sync`, `uv add --package <member> …`, `uv run …`). No pip, venv, poetry or requirements files. Add a dependency only in the change that first uses it.

5. **The architecture documents are the source of truth.** `architecture/ARCHITECTURE.md`, `architecture/data-model.md` and the diagrams in `charts/` describe the target. If the implementation needs to diverge, stop and raise it first. When a change is agreed, update the documents — and re-render the diagrams with `make charts` — in the same step as the code.

6. **Service boundaries are hard.**
   - `hospital_node` and `supplier_hub` never import each other and never call each other over the network; the purchaser client is the only bridge.
   - `equivalence_core` imports neither app and no web, database or LLM library.
   - `hospital_node` imports no HTTP client.
   - `make lint` enforces these with import-linter; never weaken a contract to make a change pass.

7. **Security defaults.**
   - No secret in code, logs, test fixtures, error messages or API responses.
   - Keys are loaded from files outside version control (`.secrets/`, mode 0600).
   - Hospital data leaves the node only through the requirement allowlist (ARCHITECTURE §16); never bypass it.

8. **Stage discipline.** Work one stage at a time, in the order of ARCHITECTURE §22. A stage is done only when its "ends with" check passes and `make lint` and `make test` are green. Then report what was built, suggest a commit, and wait for the go-ahead before starting the next stage.

9. **Quality gates.** `ruff` (lint and format), `mypy --strict` on every package, `pytest`. Code, identifiers and docs are in English. Comments explain *why*, not *what*.

## Project structure

Status: ✅ exists after stage 0 · ⏳ filled by the stage in brackets.

```
sanovio/
├── CLAUDE.md                     ✅ this file
├── README.md                     ✅ what the project is, how to run it
├── Makefile                      ✅ setup, keys, dev, dev-node, dev-hub, lint, format, test, charts
├── pyproject.toml                ✅ uv workspace root, dev tools, ruff / mypy / pytest / import-linter config
├── uv.lock  .python-version      ✅
├── architecture/                 ✅ ARCHITECTURE.md (design), data-model.md (tables),
│                                    charts.md (diagram inventory), design-plan.md (design history)
├── charts/                       ✅ PlantUML sources (src/), renders (svg/, png/), render.sh
├── data_examples/                ✅ client sample files (never committed)
├── packages/
│   └── equivalence-core/         shared library, plain Python
│       └── src/equivalence_core/
│           ├── service_info.py   ✅ health response shared by both services and the demo client
│           ├── exchange/         ✅ keys (stage 0) · ⏳ requirement, assertion, jws [1]
│           ├── templates/        ⏳ [1] TemplateDefinition, YAML seeds, definition_hash
│           ├── parsers/          ⏳ [1] German numbers, dimensions, gauge, packaging, synonyms
│           ├── identifiers.py    ⏳ [1] GS1 check digit, identifier data-quality checks
│           ├── facts.py          ⏳ [1] precedence, merge, record_hash
│           ├── comparators.py    ⏳ [3]
│           ├── verdict_rules.py  ⏳ [3]
│           └── identifier_evidence.py  ⏳ [3]
├── apps/
│   ├── hospital-node/            one per hospital, port 8001
│   │   └── src/hospital_node/
│   │       ├── main.py           ✅ app factory + lifespan
│   │       ├── cli.py            ✅ keygen · ⏳ seed, create-user [2]
│   │       ├── core/             ✅ settings, secrets · ⏳ db, security [2]
│   │       ├── api/v1/           ✅ health · ⏳ auth, articles, users, requirements,
│   │       │                        hub_assertions, reference, egress, templates, admin [2]
│   │       ├── models/ schemas/  ⏳ [2]
│   │       ├── services/         ⏳ [2] articles, normalization, projection, requirement_builder,
│   │       │                        egress_log, assertion_signer, reference_link, user_directory,
│   │       │                        template_sync
│   │       └── llm/              ⏳ [2] normalize_article (ingestion only)
│   └── supplier-hub/             central, port 8000
│       └── src/supplier_hub/
│           ├── main.py           ✅ app factory
│           ├── core/             ✅ settings · ⏳ db, security, secrets [4]
│           ├── api/v1/           ✅ health · ⏳ auth, token_exchange, admin, catalog, search,
│           │                        templates [4] · assessments, supplier, dev [5]
│           ├── models/ schemas/  ⏳ [4, 5]
│           ├── services/         ⏳ [4, 5]
│           ├── domain/           ⏳ [5] state_machine, stop_conditions
│           ├── llm/              ⏳ [4, 5] client, pipelines, prompts
│           └── jobs/             ⏳ [4, 5] queue, worker, handlers
├── tools/
│   └── demo-client/              ✅ health · ⏳ scenario scripts [6]
├── tests/e2e/                    ⏳ [6]
├── .secrets/                     created by `make keys` (git-ignored)
└── var/                          SQLite files (git-ignored)
```

Each workspace member keeps its tests in its own `tests/` directory.

## Commands

| Command | What it does |
|---|---|
| `make setup` | `uv sync`; creates each app's `.env` from `.env.example` if missing |
| `make keys` | node signing keys for `ten_ksp` and `ten_spital2` in `.secrets/` (never overwrites) |
| `make dev` | hub on :8000 and node on :8001 (`make dev-hub`, `make dev-node` for one) |
| `make lint` | ruff, format check, mypy strict, import contracts |
| `make format` | ruff format + auto-fixable lint |
| `make test` | pytest for every workspace member |
| `make charts` | re-render the UML diagrams |
