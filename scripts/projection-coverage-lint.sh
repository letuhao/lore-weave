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
# coverage state honestly (PRR-09): the rest are consumed by
# writers/seeders/history (by-design) or are a tracked deferred gap.
#
# **The ratio is PRINTED, not restated here.** This line used to say "5/14
# registered events are projected"; measured 2026-08-12 the gate reports
# **4/16**. A figure in a docstring has no measurement rule and goes stale by
# construction — the same defect this repo's figures-gate exists to catch, in
# the header of a gate. Run it; the number is in the output.
#
# Exit 0 = clean; 1 = uncovered+unallowlisted event(s); 2 = misuse / selftest
# failure / the scan reached nothing.
#
# RED-ABILITY PROOF (`GATE-TEETH`, 2026-08-12), plus the arm the allowlist
# never had. Every row below is an EXEMPTION, and an exemption with no shrink
# arm is permanent by default: nothing reds when an allowlisted event is
# deregistered, and nothing reds when one GAINS a projection and the row's
# reason expires. `npc.said`'s row even states its own retirement trigger in
# prose — *"when the actor/NPC track ships an emitter, this row must be
# replaced"* — with no mechanism to notice. Both directions now red.
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
  # DP-Ch21's per-channel page-flip counter (turn-loop T2, 2026-08-11). NOT the
  # dp-kernel TurnContext request lifecycle — four things in this repo are called
  # a "turn"; see docs/plans/2026-08-11-turn-loop-RUN-STATE.md §1.1.
  #
  # No read-model projection by design: its consumer is the channel TIMELINE.
  # DP-Ch21 says subscribers receive it "via subscribe_channel_events_durable
  # like any other channel event", and the durable state it needs already exists
  # as a column — channel_writer_state.last_turn_number, written in the same
  # statement that allocates the event (0020). A projection would be a second
  # SSOT for a number the writer already holds authoritatively.
  #
  # ⚠ This is NOT the same claim as "nothing consumes it". DP-Ch16's
  # DurableEventStream is unbuilt, so today the event is written and read by
  # nobody but its own tests. That gap belongs to 14_durable_subscribe, which is
  # still in dp-oracle-coverage's NO_PRODUCER table and will red when it ships.
  [channel.turn_boundary]="by-design: channel-timeline event delivered by durable subscribe (DP-Ch16); its durable state is channel_writer_state.last_turn_number, not a read model"
  # Arrived with the game-logic promotion (merge 2026-08-02) — registered with owner
  # commit-service and no projection arm, which reds this lint. Allowlisted after reading the
  # emitter, not to make the gate green: `epoch_commit.rs` calls it an EVT-T8 ADMINISTRATIVE
  # TRANSCRIPTION — one event per affected channel, appended by that channel's own
  # lease-holding writer, recording a decision already durably audited in
  # `reality_ruleset_binding`. The epoch it announces is enforced by `ChannelWriter::append`
  # CASing on `channel_writer_state.current_epoch`, so the state is the writer's, not a read
  # model's. Same shape as the admin.canon.override.* rows above. Confirmed no
  # `crates/projections/*` arm reads it. FLAGGED for the game track's owner: this classification
  # was made from the emitter by the branch that merged main, not by the author of the event.
  [ruleset.epoch_activated]="by-design: EVT-T8 administrative transcription; per-channel writer state (channel_writer_state.current_epoch), authorisation audited in reality_ruleset_binding — no read-model projection"
  [xreality.user.erased]="by-design: handled by meta-worker user_erased_writer (P2/071) — GDPR erasure is a per-reality pc_projection scrub + meta player_character_index scrub, NOT a read-model projection rebuild"
  # 2026-08-09 — NOT the same kind of row as the others above, and the difference
  # is worth stating rather than hiding behind matching syntax.
  #
  # Every other entry here says "consumed ELSEWHERE": a writer, a history table,
  # a seeder. This one says NOTHING CONSUMES IT AND NOTHING PRODUCES IT.
  # `npc.said` had a projection; migration `0017` DROPPED it, along with the rest
  # of the `pc_*`/`npc_*` family, because those ten tables had a projector, a
  # rebuilder, a golden fixture, an oracle and a benchmark — and no producer at
  # all. `tablemap.go:19` and `live_test.go:109` both record it by name.
  #
  # Measured 2026-08-09: every occurrence of the string in service code is a
  # TEST FIXTURE (`archive_loop`, `parquet_writer`, `poll_loop`, `redisemit`,
  # `dispatch`), where it serves as a representative event_type. No emitter.
  #
  # So the honest status is "registered contract for an unbuilt track", and the
  # registry's own header — "AUTHORITATIVE list of every event_type EMITTED by
  # LoreWeave services" — does not currently describe it. Deregistering it is
  # the defensible alternative and is deliberately NOT done here: it would touch
  # generated Rust for v1+v2 and fixtures across five services, which is a
  # change that needs its own plan rather than a line in an allowlist.
  #
  # TRIGGER: when the actor/NPC track ships an emitter, this row must be
  # replaced by a projection arm — or, if that track is abandoned, by removing
  # the event from `_registry.yaml`. Either way the row goes.
  [npc.said]="no producer and no consumer: its projection was dropped by migration 0017 with the pc_*/npc_* orphan family; every remaining occurrence is a test fixture. Registered contract for the unbuilt actor/NPC track — see the comment above for the trigger that retires this row"
)

# --- PREDICATES, extracted so cases can drive them --------------------------

# Is $1 among the newline-separated handled literals in $2?
is_handled() {
  grep -qx -- "$1" <<<"$2"
}

# Allowlist rows whose event is no longer REGISTERED. $1 = allow keys, $2 = registered.
stale_allow_rows() {
  comm -23 <(printf '%s\n' "$1" | grep . | sort -u) <(printf '%s\n' "$2" | grep . | sort -u)
}

# Allowlist rows for events that NOW HAVE a projection — the reason expired.
# $1 = allow keys, $2 = handled.
expired_allow_rows() {
  comm -12 <(printf '%s\n' "$1" | grep . | sort -u) <(printf '%s\n' "$2" | grep . | sort -u)
}

run_lint() {
  local violations=0 covered=0 ev allow_keys stale expired
  allow_keys="$(printf '%s\n' "${!allow[@]}")"

  # REACH FLOOR on the HANDLED side. The registered side is already floored
  # above. If the projections glob stops matching, `handled` is empty; today
  # that is loud (four covered events would go uncovered and unallowlisted), but
  # it is loud only by ACCIDENT — the day the last non-allowlisted event gains a
  # row, an empty `handled` becomes a silent full pass.
  if [[ -z "$(printf '%s\n' "$handled" | grep . || true)" ]]; then
    echo "[projection-coverage] FAIL — parsed ZERO event literals from"
    echo "  crates/projections/*/src/lib.rs. Every coverage answer below would be"
    echo "  'uncovered', and once every event is allowlisted that reads as a clean pass."
    exit 2
  fi

  for ev in "${registered[@]}"; do
    if is_handled "$ev" "$handled"; then
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

  # **THE SHRINK ARMS.** An allowlist that can only grow stops being read. Both
  # directions, because a row dies two different ways.
  stale="$(stale_allow_rows "$allow_keys" "$(printf '%s\n' "${registered[@]}")")"
  if [[ -n "$stale" ]]; then
    echo "[projection-coverage] FAIL — allowlist row(s) whose event is no longer registered:"
    printf '    %s\n' $stale
    echo "  The exemption outlived its subject. Delete the row."
    violations=$((violations + 1))
  fi
  expired="$(expired_allow_rows "$allow_keys" "$handled")"
  if [[ -n "$expired" ]]; then
    echo "[projection-coverage] FAIL — allowlist row(s) for event(s) that NOW HAVE a projection:"
    printf '    %s\n' $expired
    echo "  The reason expired the moment the arm landed. Delete the row."
    violations=$((violations + 1))
  fi

  echo "[projection-coverage] ${covered}/${#registered[@]} registered events have a projection handler; $(( ${#registered[@]} - covered )) consumed elsewhere/deferred (see allowlist above)."

  if [[ $violations -gt 0 ]]; then
    echo "[projection-coverage] FAIL — $violations uncovered + unallowlisted event(s)"
    exit 1
  fi
  echo "[projection-coverage] PASS — ${#registered[@]} registered, $covered projected, ${#allow[@]} allowlisted, all rows live"
  exit 0
}

selftest() {
  local h=$'reality.frozen\nchannel.created'

  is_handled 'reality.frozen' "$h" || { echo "[projection-coverage] SELFTEST FAIL — a handled event was not matched"; exit 2; }
  if is_handled 'reality.froze' "$h"; then
    echo "[projection-coverage] SELFTEST FAIL — a PREFIX matched; -x anchoring is gone"; exit 2
  fi
  if is_handled 'nope.event' "$h"; then
    echo "[projection-coverage] SELFTEST FAIL — an unhandled event matched (vacuous)"; exit 2
  fi

  # Shrink arm 1 — a row whose event left the registry.
  if [[ -z "$(stale_allow_rows $'a.gone\nb.live' $'b.live\nc.other')" ]]; then
    echo "[projection-coverage] SELFTEST FAIL — a STALE allowlist row (event deregistered) was not reported"; exit 2
  fi
  if [[ -n "$(stale_allow_rows $'b.live' $'b.live\nc.other')" ]]; then
    echo "[projection-coverage] SELFTEST FAIL — a LIVE allowlist row was reported stale (cry-wolf)"; exit 2
  fi

  # Shrink arm 2 — a row whose event gained a projection.
  if [[ -z "$(expired_allow_rows $'a.now_projected\nb.still_exempt' $'a.now_projected')" ]]; then
    echo "[projection-coverage] SELFTEST FAIL — an EXPIRED allowlist row (event now projected) was not reported"; exit 2
  fi
  if [[ -n "$(expired_allow_rows $'b.still_exempt' $'a.now_projected')" ]]; then
    echo "[projection-coverage] SELFTEST FAIL — a still-unprojected row was reported expired (cry-wolf)"; exit 2
  fi

  # Neither arm may fire on empty input — that would make every clean run red.
  if [[ -n "$(stale_allow_rows '' '')" || -n "$(expired_allow_rows '' '')" ]]; then
    echo "[projection-coverage] SELFTEST FAIL — a shrink arm fires on empty input"; exit 2
  fi

  echo "[projection-coverage] SELFTEST PASS — handled-matching is exact (a prefix does not count)"
  echo "  and refuses an unhandled event; both shrink arms report a dead row — deregistered"
  echo "  and now-projected — while leaving live rows alone and staying silent on empty input"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
