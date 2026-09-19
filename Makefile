# Every Python command runs through uv (see CLAUDE.md).
.PHONY: setup keys seed seed-node seed-hub dev dev-hub dev-node demo-node demo-search demo eval lint format test charts \
	ui-setup ui-dev ui-build ui-lint ui-test ui-e2e openapi

NODE_KEYS := .secrets/node_ksp_ed25519.pem .secrets/node_spital2_ed25519.pem

setup:
	uv sync --all-packages
	@for app in apps/hospital-node apps/supplier-hub; do \
		[ -f $$app/.env ] || { cp $$app/.env.example $$app/.env && echo "created $$app/.env"; }; \
	done

# File targets: existing keys are left alone, so re-running is safe.
keys: $(NODE_KEYS)

.secrets/node_ksp_ed25519.pem:
	uv run --package hospital-node hospital-node keygen --out $@ --kid ksp-2026-09

.secrets/node_spital2_ed25519.pem:
	uv run --package hospital-node hospital-node keygen --out $@ --kid sp2-2026-09

# Replaces both databases with the demo data and registers the node keys at the hub.
seed: seed-node seed-hub

# NODE_SEED_PASSWORD and, in llm mode, ANTHROPIC_API_KEY come from apps/hospital-node/.env.
seed-node: .secrets/node_ksp_ed25519.pem
	uv run --package hospital-node --env-file apps/hospital-node/.env hospital-node seed --reset

# HUB_SEED_PASSWORD and, in anthropic mode, ANTHROPIC_API_KEY come from apps/supplier-hub/.env.
seed-hub: $(NODE_KEYS)
	uv run --package supplier-hub --env-file apps/supplier-hub/.env supplier-hub seed --reset
	uv run --package supplier-hub --env-file apps/supplier-hub/.env supplier-hub register-tenant \
		--tenant ten_ksp --jwk-file .secrets/node_ksp_ed25519.pub.jwk.json
	uv run --package supplier-hub --env-file apps/supplier-hub/.env supplier-hub register-tenant \
		--tenant ten_spital2 --jwk-file .secrets/node_spital2_ed25519.pub.jwk.json

dev:
	$(MAKE) -j2 dev-hub dev-node

dev-hub:
	uv run --package supplier-hub uvicorn supplier_hub.main:create_app --factory \
		--port 8000 --env-file apps/supplier-hub/.env

dev-node: .secrets/node_ksp_ed25519.pem
	uv run --package hospital-node uvicorn hospital_node.main:create_app --factory \
		--port 8001 --env-file apps/hospital-node/.env

# Walks through the standalone node; needs `make dev-node` running in another terminal.
demo-node:
	uv run --package demo-client --env-file apps/hospital-node/.env demo-client node-demo

# Node and hub together: a requirement, the token exchange and a candidate search (`make dev`).
demo-search:
	uv run --package demo-client --env-file apps/hospital-node/.env demo-client demo-search

# One §21 scenario over HTTP (`make demo SCENARIO=1..4`); supplier answers come from the
# hub's dev simulator. Needs `make dev` running.
SCENARIO ?= 1
demo:
	uv run --package demo-client --env-file apps/hospital-node/.env \
		--env-file apps/supplier-hub/.env demo-client scenario $(SCENARIO)

# Model quality on hand-labelled data (§9), results in var/evals/. Needs the real API:
# NORMALIZE_MODE=llm + key at the node, LLM_MODE=anthropic + key at the hub.
# EVAL_LLM=fake runs the same harness offline (node rules only, hub scripted fake).
eval:
ifeq ($(EVAL_LLM),fake)
	uv run --package hospital-node --env-file apps/hospital-node/.env hospital-node eval --mode rules
	uv run --package supplier-hub --env-file apps/supplier-hub/.env supplier-hub eval --fake
else
	uv run --package hospital-node --env-file apps/hospital-node/.env hospital-node eval --mode both
	uv run --package supplier-hub --env-file apps/supplier-hub/.env supplier-hub eval
endif

lint: ui-lint
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run lint-imports

# Format first: `ruff check --fix` exits non-zero on anything it cannot fix.
format:
	uv run ruff format .
	uv run ruff check --fix .
	cd frontend && npm run format

test: ui-test
	uv run pytest

# --- Browser apps (ARCHITECTURE §20): npm only for JS, Node 22 required -------------------
ui-setup:
	@node --version | grep -q '^v2[2-9]' || (echo "Node 22 or newer is required (see README)"; exit 1)
	cd frontend && npm ci

# Purchaser app on :5173 (talks to the node on :8001 and the hub on :8000), supplier app on
# :5174 (hub); needs `make dev` running.
ui-dev:
	cd frontend && npm run dev

# Built apps: point PURCHASER_UI_DIR (node) and SUPPLIER_UI_DIR (hub) at the dist folders.
ui-build:
	cd frontend && npm run build

ui-lint:
	cd frontend && npm run lint

ui-test:
	cd frontend && npm test

# Scenario 1 in a real browser through both apps. Starts its own hub, node and dev servers on
# ports 18000/18001/15173/15174 with databases in var/e2e/, so `make dev` can keep running.
# First time: `cd frontend && npx playwright install chromium`.
ui-e2e:
	cd frontend && npm run e2e

# Re-export both OpenAPI documents and regenerate the apps' typed clients from them.
openapi:
	uv run --package hospital-node hospital-node openapi --out openapi/node.json
	uv run --package supplier-hub supplier-hub openapi --out openapi/hub.json
	cd frontend && npm run gen

charts:
	bash charts/render.sh
