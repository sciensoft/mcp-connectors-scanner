#!/usr/bin/env bash
# Run ONE full sweep in a separate, throwaway scanner container, then exit.
#
# Why a separate container: the always-on scanner wipes its work folder at the start
# and end of each sweep. A second sweep sharing that folder would delete scans in
# flight. This container has its own work area (tmpfs), so the two never touch.
# Results land in the same database; the latest grade per connector wins by time.
#
# Secrets come from an env file that is NOT in this repo (default ../.env.scanner,
# override with SCANNER_ENV_FILE). Nothing here prints them.

set -euo pipefail

ENV_FILE="${SCANNER_ENV_FILE:-$(dirname "$0")/../.env}"
IMAGE="${SCANNER_IMAGE:-localhost/mcp-connectors-scanner:latest}"
NETWORK="${SCANNER_NETWORK:-mcpc_vnet}"
NAME="mcpc-scanner-sweep"
CONCURRENCY="${SCAN_CONCURRENCY:-32}"

[ -r "$ENV_FILE" ] || { echo "sweep-once: cannot read $ENV_FILE" >&2; exit 2; }

# One sweep at a time. flock keeps a second timer firing from starting another.
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/mcpc-sweep.lock"
flock -n 9 || { echo "sweep-once: a sweep is already running, skipping"; exit 0; }

# Leftover from a crashed earlier run.
podman rm -f "$NAME" >/dev/null 2>&1 || true

set -a; . "$ENV_FILE"; set +a

podman run --rm --name "$NAME" \
  --network "$NETWORK" \
  --read-only --cap-drop ALL -u 10002:10002 \
  --tmpfs /work:size=6g,mode=1777 --tmpfs /tmp:size=512m,mode=1777 \
  -v mcp-connectors_mcpc_scanner_cache:/home/scanner \
  -e SCAN_INTERVAL_HOURS=0 \
  -e SCAN_CONCURRENCY="$CONCURRENCY" \
  -e SCAN_WORK_DIR=/work -e SCAN_OUT_DIR=/out \
  -e SCAN_FEED_URL="${SCAN_FEED_URL:-http://mcp-server:8080/internal/scanner/catalog}" \
  -e SCAN_FEED_TOKEN="$SCAN_FEED_TOKEN" \
  -e SCANNER_API_TOKEN="$SCANNER_API_TOKEN" \
  -e SCANNER_API_ADDR=127.0.0.1:9091 \
  -e SCANNER_DATABASE_URL="postgres://scanner:${SCANNER_DB_PASSWORD}@mcp-db:5432/scanner?sslmode=disable" \
  "$IMAGE"
