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

## Running the demo
Fill in the two `.env` files first: `NODE_SEED_PASSWORD` and `HUB_SEED_PASSWORD` (the passwords the
demo accounts get), plus the hospital's own `ANTHROPIC_API_KEY` in `apps/hospital-node/.env`.
Without a key set `NORMALIZE_MODE=rules` — the parsers alone then read the article names and
nothing leaves the machine. The hub runs offline with `LLM_MODE=fake`.

```bash
make seed         # both databases: 10 articles at the node, 6 families / 54 variants at the hub,
                  # and the node's public keys registered at the hub
make dev          # hub on :8000, node on :8001
make demo-node    # in another terminal: login, articles, a requirement, an assertion, the egress log
make demo-search  # node + hub: a requirement, the token exchange, the candidate search
```

`demo-node` prints exactly what would leave the hospital and keeps asking for requirements until the
node answers 429. `demo-search` shows the other half: the assertion exchanged for a hub token, then
BD Plastipak™ and B. Braun Injekt® as candidates while BD Emerald™ is excluded by its Luer cone.

## Checks
```bash
make lint     # ruff, format check, mypy strict, import boundaries
make test     # all unit tests
```

## Status
Stages 0–4 of 7 done: workspace and tooling; the shared core (values, templates, parsers, facts,
requirement, assertions and comparison); the **hospital node**, which runs standalone — accounts and tokens, the 10 demo articles with their
facts and projections, normalization (parsers plus one `normalize_article` call at ingestion), the
current-product link, the requirement allowlist with its egress log and rate limits, and signed hub
assertions; and the **supplier hub** foundation — supplier and operator logins, tenants with their
registered node keys and the token exchange, the attribute registry, both catalogs read from the
client's PDFs, and candidate search. Next: stage 5 (the assessment loop: questions, judge, answers).
See ARCHITECTURE §22 for the stage plan.
