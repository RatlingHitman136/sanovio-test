# Article Equivalence Loop — prototype

Hospital purchasers compare an article they already buy with items in supplier catalogs. Deterministic comparators and an LLM judge decide equivalence attribute by attribute, missing data turns into questions for the supplier or the purchaser, and the answers enrich the records until the assessment is resolved.

The system is split into a **hospital node** (one per hospital, can run behind the hospital firewall) and a central **supplier hub**; the purchaser's client is the only bridge between them.

- Design: [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md)
- Data model: [`architecture/data-model.md`](architecture/data-model.md)
- Diagrams: [`architecture/charts.md`](architecture/charts.md), rendered in `charts/png/`
- Working rules and project map: [`CLAUDE.md`](CLAUDE.md)

## Requirements
[uv](https://docs.astral.sh/uv/) (Python 3.14 is installed by uv if missing), GNU make, and Java for re-rendering the diagrams.

## Getting started
```bash
make setup    # install every workspace member, create apps/*/.env from the examples
make keys     # node signing keys in .secrets/ (never overwritten)
make dev      # supplier hub on :8000, hospital node on :8001
uv run --package demo-client demo-client health   # both services should be "up"
```

API docs: http://127.0.0.1:8001/docs (node) and http://127.0.0.1:8000/docs (hub).

## The hospital node on its own
Fill in `apps/hospital-node/.env` first: `NODE_SEED_PASSWORD` (the password the demo accounts get)
and the hospital's own `ANTHROPIC_API_KEY`. Without a key, set `NORMALIZE_MODE=rules` — then the
parsers alone read the article names and nothing leaves the machine.

```bash
make seed       # migrate, load the 10 demo articles, normalize them (one LLM call in llm mode)
make dev-node   # node on :8001
make demo-node  # in another terminal: login, articles, a requirement, an assertion, the egress log
```

The demo prints exactly what would leave the hospital, and keeps asking for requirements until the
node answers 429 — the per-user rate limit and its alert in the egress log.

## Checks
```bash
make lint     # ruff, format check, mypy strict, import boundaries
make test     # all unit tests
```

## Status
Stages 0–3 of 7 done: workspace and tooling; the shared core (now including comparison: the
deterministic comparators, the verdict rules and identifier evidence); and the
**hospital node**, which runs standalone — accounts and tokens, the 10 demo articles with their
facts and projections, normalization (parsers plus one `normalize_article` call at ingestion), the
current-product link, the requirement allowlist with its egress log and rate limits, and signed hub
assertions. Next: stage 4 (hub foundation: tenants, catalog, search). See ARCHITECTURE §22 for
the stage plan.
