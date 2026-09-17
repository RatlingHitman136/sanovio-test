# Every Python command runs through uv (see CLAUDE.md).
.PHONY: setup keys dev dev-hub dev-node lint format test charts

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

dev:
	$(MAKE) -j2 dev-hub dev-node

dev-hub:
	uv run --package supplier-hub uvicorn supplier_hub.main:create_app --factory \
		--port 8000 --env-file apps/supplier-hub/.env

dev-node: .secrets/node_ksp_ed25519.pem
	uv run --package hospital-node uvicorn hospital_node.main:create_app --factory \
		--port 8001 --env-file apps/hospital-node/.env

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run lint-imports

# Format first: `ruff check --fix` exits non-zero on anything it cannot fix.
format:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest

charts:
	bash charts/render.sh
