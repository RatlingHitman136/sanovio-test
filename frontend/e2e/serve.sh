#!/usr/bin/env bash
# Starts one service for the browser e2e run, on its own ports and databases, so it never
# touches var/*.db or collides with `make dev`. Called by playwright.config.ts.
set -euo pipefail
cd "$(dirname "$0")/../.."
DATA=var/e2e
mkdir -p "$DATA"
export APP_ENV=dev NODE_SEED_PASSWORD=e2e-demo-password HUB_SEED_PASSWORD=e2e-demo-password

case "$1" in
  hub)
    export DATABASE_URL="sqlite:///$DATA/hub.db" LLM_MODE=fake CORS_ORIGINS=http://127.0.0.1:18001
    uv run --package supplier-hub supplier-hub seed --reset
    uv run --package supplier-hub supplier-hub register-tenant \
      --tenant ten_ksp --jwk-file .secrets/node_ksp_ed25519.pub.jwk.json
    exec uv run --package supplier-hub uvicorn supplier_hub.main:create_app --factory --port 18000
    ;;
  node)
    export DATABASE_URL="sqlite:///$DATA/node.db" NORMALIZE_MODE=rules \
      NODE_SIGNING_KEY_FILE=.secrets/node_ksp_ed25519.pem NODE_SIGNING_KID=ksp-2026-09 \
      HUB_URL=http://127.0.0.1:18000
    uv run --package hospital-node hospital-node seed --reset
    exec uv run --package hospital-node uvicorn hospital_node.main:create_app --factory --port 18001
    ;;
  *)
    echo "usage: $0 hub|node" >&2
    exit 2
    ;;
esac
