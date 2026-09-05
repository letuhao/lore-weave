#!/usr/bin/env bash
# DQ-T88's on-path A/B — CONTROL (replay off, the shipped path) then ARM (replay on).
#
# 🔴 THE FLAG IS SET ON THE REAL COMPOSE SERVICE, and this script exists because the obvious
# alternative failed silently. A previous attempt used `docker compose run --service-ports`:
# that container joins the network and reports the setting as True inside itself, but it does
# NOT take over the compose SERVICE NAME the gateway routes to. The batch therefore hit the
# STOPPED container and produced 3 errors, 0/3 surfaced and zero replay log lines — a result
# that looks like a refuted remedy and is actually a plumbing mistake.
#
# 🔴 SO EACH ARM VERIFIES THE FLAG INSIDE THE RUNNING SERVICE BEFORE SPENDING THE GPU. An arm
# that cannot prove its own condition is not an arm.
#
# ONE ARM AT A TIME, CONCURRENCY 1. Parallel batches starve the single local GPU and every run
# dies of no_output_timeout, which reads as a refuted remedy — the same false negative twice.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1

SCEN=scripts/toolloop/scenarios-t88-replay-ab.json
OUT=docs/eval/toolloop/2026-09-02
K=${K:-5}

run_arm() {
  local name="$1" want="$2"
  echo "── ARM ${name}: REPLAY_PRIOR_TOOL_RESULTS=${want} ─────────────────────────"
  REPLAY_PRIOR_TOOL_RESULTS="${want}" docker compose -f infra/docker-compose.yml \
      up -d --force-recreate chat-service >/dev/null 2>&1
  # Health, then the flag — in that order, because a probe of a starting container reads stale.
  for _ in $(seq 1 30); do
    if docker ps --filter name=infra-chat-service-1 --format '{{.Status}}' | grep -q healthy; then
      break
    fi
    python -c "import time;time.sleep(2)"
  done
  local got
  got=$(docker exec infra-chat-service-1 python -c \
        "from app.config import settings; print(settings.replay_prior_tool_results)" 2>/dev/null)
  echo "   flag inside the running service: ${got:-<unreadable>}"
  case "${want}:${got}" in
    true:True|false:False) ;;
    *) echo "   REFUSING TO RUN: the service does not report the arm's own condition." \
            "Spending the GPU here would measure something other than the arm."; return 1 ;;
  esac
  timeout 5400 python scripts/toolloop/fe_runner.py "${SCEN}" \
      --repeats "${K}" --concurrency 1 --batch-id "t88-${name}" \
      --out "${OUT}/t88-${name}-raw.json" --batch-out "${OUT}/t88-${name}.json"
  echo "   replay log lines this arm: $(docker logs infra-chat-service-1 --since 90m 2>&1 \
        | grep -c 'replayed .* prior tool result')"
}

run_arm control false || exit 1
run_arm arm true      || exit 1

# Leave the service on the SHIPPED path whatever happened. The flag is adopted only by editing
# the default in config.py, never by leaving a container mutated.
echo "── restoring the shipped default ─────────────────────────────────────────"
docker compose -f infra/docker-compose.yml up -d --force-recreate chat-service >/dev/null 2>&1
docker exec infra-chat-service-1 python -c \
  "from app.config import settings; print('restored default:', settings.replay_prior_tool_results)"
