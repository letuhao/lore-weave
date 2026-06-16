#!/usr/bin/env bash
# L3.B projection coverage gate (PRR-32 / PRR-09).
#
# Cross-references contracts/events/_registry.yaml (the AUTHORITATIVE event_type
# list) against the event-type string literals handled in the apply_event arms
# of crates/projections/*/src/lib.rs. A registered event with NO projection
# handler that is also NOT in the allowlist below FAILs the build.
#
# This makes the L3.B "every event type is accounted for" criterion actually
# ENFORCEABLE (previously there was no such gate — PRR-32) and pins the current
# coverage state honestly (PRR-09): 5/14 registered events are projected; the
# rest are consumed by writers/seeders/history (by-design) or are a tracked
# deferred gap.
#
# Exit 0 = clean; 1 = uncovered+unallowlisted event(s); 2 = misuse.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
registry="$repo_root/contracts/events/_registry.yaml"

if [[ ! -f "$registry" ]]; then
  echo "[projection-coverage] FAIL — registry missing at $registry"
  exit 2
fi

# Registered event_types (authoritative).
mapfile -t registered < <(grep -oE '^[[:space:]]*-[[:space:]]*name:[[:space:]]*\S+' "$registry" | sed -E 's/.*name:[[:space:]]*//')
if [[ ${#registered[@]} -eq 0 ]]; then
  echo "[projection-coverage] FAIL — no event_type names parsed from registry"
  exit 2
fi

# Event-type string literals handled by some projection apply_event arm.
handled="$(grep -rhoE '"[a-z][a-z_]*\.[a-z_.]+"' "$repo_root"/crates/projections/*/src/lib.rs 2>/dev/null | tr -d '"' | sort -u)"

# Registered events that legitimately have NO projection (consumed by writers /
# history / seeders, or ephemeral) — OR a tracked deferred gap. Adding an event
# here REQUIRES a reason; this is the audit trail for "why no projection".
declare -A allow=(
  [reality.created]="by-design: handled by world-service reality_seeder, not a read-model projection"
  [world.tick]="by-design: ephemeral world clock; no read-model projection"
  [xreality.canon.promoted]="by-design: cross-reality trigger consumed by meta-worker canon_writer fanout"
  [canon.change.recorded]="by-design: meta-worker canon_history_writer (append-only history table)"
  [admin.canon.override.requested]="by-design: meta-worker override writers (audit), not projected"
  [admin.canon.override.consented]="by-design: meta-worker override writers (audit), not projected"
  [admin.canon.override.vetoed]="by-design: meta-worker override writers (audit), not projected"
  [admin.canon.override.compensating]="by-design: meta-worker force_propagate compensating writer"
  [xreality.user.erased]="by-design: handled by meta-worker user_erased_writer (P2/071) — GDPR erasure is a per-reality pc_projection scrub + meta player_character_index scrub, NOT a read-model projection rebuild"
)

violations=0
covered=0
for ev in "${registered[@]}"; do
  if grep -qx "$ev" <<<"$handled"; then
    covered=$((covered + 1))
    continue
  fi
  if [[ -n "${allow[$ev]+set}" ]]; then
    echo "[projection-coverage] allowlisted — $ev: ${allow[$ev]}"
    continue
  fi
  echo "[projection-coverage] FAIL — registered event '$ev' has NO projection handler and is NOT allowlisted. Add an apply_event arm in crates/projections/*, or allowlist it with a reason."
  violations=$((violations + 1))
done

echo "[projection-coverage] ${covered}/${#registered[@]} registered events have a projection handler; $(( ${#registered[@]} - covered )) consumed elsewhere/deferred (see allowlist above)."

if [[ $violations -gt 0 ]]; then
  echo "[projection-coverage] FAIL — $violations uncovered + unallowlisted event(s)"
  exit 1
fi
echo "[projection-coverage] PASS"
exit 0
