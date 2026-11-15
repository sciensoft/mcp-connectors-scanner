#!/usr/bin/env bash
# Register with a short-lived token, run, and unregister on shutdown.
# RUNNER_REG_TOKEN is single-use and expires in an hour; it is never stored.
set -euo pipefail
cd /home/runner/actions-runner

: "${RUNNER_REPO_URL:?}" "${RUNNER_REG_TOKEN:?}"
NAME="${RUNNER_NAME:-scanner-runner}"
LABELS="${RUNNER_LABELS:-scanner}"

if [ ! -f .runner ]; then
  ./config.sh --unattended --ephemeral=false --replace \
    --url "$RUNNER_REPO_URL" --token "$RUNNER_REG_TOKEN" \
    --name "$NAME" --labels "$LABELS" --work /home/runner/_work
fi
unset RUNNER_REG_TOKEN

cleanup() { ./config.sh remove --token "${RUNNER_REMOVE_TOKEN:-none}" >/dev/null 2>&1 || true; }
trap 'kill -TERM "$child" 2>/dev/null; wait "$child"; cleanup' TERM INT

./run.sh &
child=$!
wait "$child"
