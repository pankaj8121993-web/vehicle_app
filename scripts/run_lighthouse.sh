#!/usr/bin/env bash
# Guarded orchestration for the FleetFlow Lighthouse audit (UX-R1 / P3-08).
#
# Seeds an isolated, disposable role fixture, starts the backend against it,
# builds and serves the frontend, logs in through the real API to obtain a
# session cookie, runs Lighthouse (desktop + mobile) against the four required
# pages with that real session, then tears the fixture down.
#
# Production is never touched: databases are disposable `fleetflow_role_e2e_*`
# names and all servers bind to 127.0.0.1.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO/.venv/bin"
# Pick free localhost ports so concurrent or leftover servers never collide.
pick_port() { python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()'; }
API_PORT="${LH_API_PORT:-$(pick_port)}"
WEB_PORT="${LH_WEB_PORT:-$(pick_port)}"
RUN_ID="$(python3 -c 'import secrets;print(secrets.token_hex(6))')"
DB_NAME="fleetflow_role_e2e_${RUN_ID}"
MONGO_URL="mongodb://127.0.0.1:27017"
OUT_DIR="${LH_OUT:-$REPO/test_reports/lighthouse}"
LH_NODE_PATH="${LH_NODE_PATH:-/tmp/claude-0/-app/c8dfae74-f6a6-41cd-9c83-846ec3515c09/scratchpad/node_modules}"

export FLEETFLOW_ROLE_E2E_ALLOW=true
export FLEETFLOW_ROLE_E2E_RUN_ID="$RUN_ID"
export FLEETFLOW_ROLE_E2E_PASSWORD="$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')"
export APP_ENV=test
export FLEETFLOW_CROSS_SITE_COOKIES=false

# ESM resolves bare specifiers by walking up node_modules from the script's
# directory (NODE_PATH is ignored), so expose the Lighthouse install there.
ln -sfn "$LH_NODE_PATH" "$REPO/scripts/node_modules"

BACK_PID=""; WEB_PID=""
cleanup() {
  [ -n "$BACK_PID" ] && kill "$BACK_PID" 2>/dev/null || true
  [ -n "$WEB_PID" ] && kill "$WEB_PID" 2>/dev/null || true
  rm -f "$REPO/scripts/node_modules"
  "$VENV/python" "$REPO/scripts/role_e2e_fixture.py" teardown --database "$DB_NAME" --mongo-url "$MONGO_URL" || true
}
trap cleanup EXIT

echo "== Seeding disposable fixture $DB_NAME =="
SEED_JSON="$("$VENV/python" "$REPO/scripts/role_e2e_fixture.py" seed --database "$DB_NAME" --mongo-url "$MONGO_URL")"
VEHICLE_ID="$(python3 -c "import json,sys;print(json.loads(sys.argv[1])['vehicle_id'])" "$SEED_JSON")"
ADMIN_USER="$(python3 -c "import json,sys;print(json.loads(sys.argv[1])['credentials']['org_admin']['username'])" "$SEED_JSON")"

echo "== Starting backend on :$API_PORT =="
( cd "$REPO/backend" && APP_ENV=test FLEETFLOW_CROSS_SITE_COOKIES=false MONGO_URL="$MONGO_URL" \
    DB_NAME="$DB_NAME" CORS_ORIGINS="http://127.0.0.1:$WEB_PORT" \
    "$VENV/python" -m uvicorn server:app --host 127.0.0.1 --port "$API_PORT" >/tmp/lh_backend.log 2>&1 ) &
BACK_PID=$!
for i in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$API_PORT/api/" >/dev/null 2>&1 && break
  sleep 1
done

echo "== Building and serving frontend on :$WEB_PORT =="
( cd "$REPO/frontend" && REACT_APP_BACKEND_URL="http://127.0.0.1:$API_PORT" npm run build >/tmp/lh_build.log 2>&1 )
( "$VENV/python" "$REPO/scripts/serve_spa.py" "$REPO/frontend/build" --port "$WEB_PORT" >/tmp/lh_web.log 2>&1 ) &
WEB_PID=$!
for i in $(seq 1 30); do
  curl -sf "http://127.0.0.1:$WEB_PORT" >/dev/null 2>&1 && break
  sleep 1
done

echo "== Logging in via real API as $ADMIN_USER =="
COOKIE="$(curl -s -c - -X POST "http://127.0.0.1:$API_PORT/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$FLEETFLOW_ROLE_E2E_PASSWORD\"}" \
  | awk '/fleet_session/ {print $7}')"
if [ -z "$COOKIE" ]; then echo "Login failed; backend log:"; tail -20 /tmp/lh_backend.log; exit 1; fi

echo "== Running Lighthouse (desktop + mobile) =="
mkdir -p "$OUT_DIR"
node "$REPO/scripts/lighthouse_audit.mjs" \
  --base-url "http://127.0.0.1:$WEB_PORT" \
  --cookie "$COOKIE" \
  --vehicle-id "$VEHICLE_ID" \
  --out "$OUT_DIR" \
  ${LH_EXTRA_ARGS:-}

echo "== Lighthouse complete; summary at $OUT_DIR/summary.json =="
