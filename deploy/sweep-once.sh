#!/usr/bin/env bash
# Run ONE full sweep in a separate, throwaway scanner container, then exit.
#
# Why a separate container: the always-on scanner wipes its work folder at the start
# and end of each sweep. A second sweep sharing that folder would delete scans in
# flight. This container has its own work area (tmpfs), so the two never touch.
# Results land in the same database; the latest grade per connector wins by time.
#
# Secrets come from an env file that is NOT in this repo (default ../.env,
# override with SCANNER_ENV_FILE). Nothing here prints them.

set -euo pipefail

ENV_FILE="${SCANNER_ENV_FILE:-$(dirname "$0")/../.env}"
IMAGE="${SCANNER_IMAGE:-localhost/mcp-connectors-scanner:latest}"
# Same three networks as the scanner service: private database, private scan network (to
# reach the server feed), and its own route out. See docker-compose.yaml.
NET_DB="${SCANNER_NET_DB:-mcpc_db}"
NET_SCAN="${SCANNER_NET_SCAN:-mcpc_scan}"
NET_OUT="${SCANNER_NET_OUT:-scanner_out}"
NAME="mcpc-scanner-sweep"
CONCURRENCY="${SCAN_CONCURRENCY:-32}"

[ -r "$ENV_FILE" ] || { echo "sweep-once: cannot read $ENV_FILE" >&2; exit 2; }

# One sweep at a time. flock keeps a second timer firing from starting another.
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/mcpc-sweep.lock"
flock -n 9 || { echo "sweep-once: a sweep is already running, skipping"; exit 0; }

# Leftover from a crashed earlier run.
podman rm -f "$NAME" >/dev/null 2>&1 || true

set -a; . "$ENV_FILE"; set +a

podman run --rm --init --name "$NAME" \
  --network "$NET_DB" --network "$NET_SCAN" --network "$NET_OUT" \
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

# Tidy up after the sweep. Rebuilding the scanner image leaves untagged older layers
# behind, and the container disk once reached 96% full because of them. This removes
# only images that no container uses and that carry no tag, so tagged images, running
# containers and volumes (the databases, the scan cache) are never touched. A failed
# prune must not turn a good sweep into a failed one, hence the `|| true`.
podman image prune -f > /dev/null 2>&1 || true
