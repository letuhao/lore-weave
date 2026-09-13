#!/usr/bin/env bash
# emit-migration-0013-lint.sh — drift guard for the W3.4 content checksum.
#
# The Go emit path (tests/workload-gen `-emit`, emit.go insertEventsSQL) and the
# dp-kernel append BOTH stamp events.content_sha256 with the migration-0013
# column. A drill that builds its OWN per-reality events DB and then runs `wg
# -emit` MUST therefore apply 0013_events_content_sha256, or the INSERT fails on
# the missing column. This guard flags any script that:
#
#   (a) sets up its own events baseline  (mentions `0002_events_table`), AND
#   (b) invokes the wg emit path         (a ` -emit` flag — leading space so the
#                                         pgbench file `scale-emit.sql` etc. do
#                                         NOT false-match), BUT
#   (c) does NOT apply `0013_events_content_sha256`.
#
# Scripts that rely on `scale-rig.sh migrate` (no own 0002) are NOT flagged — the
# rig's migrate path already applies 0013. Scripts that emit via raw pgbench (no
# ` -emit` wg flag) are NOT flagged — they don't reference content_sha256.
#
# Exit 0 = clean; 1 = an emit script missing 0013; 2 = misuse / selftest failure.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

# violates TEXT — echoes "MISSING-0013" when the text is an own-baseline emit
# script that omits 0013, else nothing. Returns 0 always.
# 🔴 ANSWERS BY EXIT STATUS, NOT BY STDOUT — the same lesson as the `$(cat "$f")`
# note in `run_lint` below, one call deeper. This echoed `MISSING-0013` and every caller then
# asked `[ -n "$(violates ...)" ]`, so a command substitution that came back EMPTY under CI load
# was indistinguishable from the verdict "clean". That is how `--selftest` failed in CI on
# 2026-09-05 with *"did NOT flag an own-baseline emit script missing 0013 (vacuous)"* while
# passing locally, bare and with the flag, on the same bytes.
#
# In the SELFTEST an empty capture is a loud false alarm. In `run_lint` the same empty capture is
# a FALSE NEGATIVE — a script that really is missing 0013 reads as clean and the lint says PASS.
# That is the worse direction, and it was live on every one of the 191 files this scans.
#
# A status cannot come back empty. 0 = violates, 1 = clean, and no subshell stands between the
# predicate and its caller.
# violates_file FILE -> 0 violates, 1 clean, 3 vanished mid-scan.
#
# 🔴 THE FILE IS NEVER BUFFERED INTO A VARIABLE, and this is the THIRD attempt at that:
#
#   1. `$(cat "$f")` INLINED into the test. A read returning nothing -- or PART of the file --
#      was indistinguishable from a script that genuinely omits 0013. On 2026-08-08 this
#      flagged scale-rig.sh on one run and ledger-verify-smoke.sh on the next, both of which
#      CONTAIN 0013_events_content_sha256.
#   2. Read into a variable, then check the status. That catches a FAILED read and is still
#      wrong, because a TRUNCATED read exits 0. On 2026-09-13 two all-gates runs of the SAME
#      commit disagreed: one reported scale-rig.sh and standing-integrity-gate-smoke.sh as
#      missing 0013 -- both contain it -- while the other passed. Same bytes, same minute.
#
# A status check cannot see a short read, so the buffer had to go. `grep` reads the FILE, which
# removes the copy that was being truncated, and it tells the three outcomes apart by exit
# status: 0 found, 1 absent, >1 could not read. A finding now requires all three greps to have
# completed; anything else is a read error and says nothing about the script.
violates_file() {
  local f="$1" rc
  _g() {
    grep -q -- "$1" "$f" 2>/dev/null
    rc=$?
    if [ "$rc" -gt 1 ]; then
      [ -e "$f" ] || return 3
      echo "[emit-0013] FAIL -- could not read $f (grep exit $rc)." >&2
      echo "  -> this is a READ failure, not a finding. Nothing about the script is implied." >&2
      exit 1
    fi
    return "$rc"
  }
  _g "0002_events_table" || { rc=$?; [ "$rc" -eq 3 ] && return 3; return 1; }
  _g " -emit"            || { rc=$?; [ "$rc" -eq 3 ] && return 3; return 1; }
  _g "0013_events_content_sha256" && return 1
  rc=$?
  [ "$rc" -eq 3 ] && return 3
  return 0
}

run_lint() {
  local violations=0 scanned=0 f rc
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    violates_file "$f" && rc=0 || rc=$?
    if [ "$rc" -eq 3 ]; then
      # `--run-all` executes gates concurrently and the bite harnesses write a modified copy
      # beside the gate they are proving, so transient files appear and vanish under scripts/
      # mid-sweep. That is another gate operating normally, not a finding here.
      echo "[emit-0013] note -- $f vanished during the scan (transient file); skipped"
      continue
    fi
    scanned=$((scanned + 1))
    if [ "$rc" -eq 0 ]; then
      echo "[emit-0013] FAIL -- $f sets up its own events baseline + runs 'wg -emit' but does NOT apply 0013_events_content_sha256"
      echo "  -> add 0013_events_content_sha256 to its migration list (the emit path stamps events.content_sha256)."
      violations=$((violations + 1))
    fi
  done < <(find "$repo_root/scripts" -name '*.sh' -type f)
  if [ "$violations" -gt 0 ]; then exit 1; fi
  # scripts/ always holds shell scripts -- this one among them. Zero scanned means the find
  # failed, and reporting PASS on it would certify a tree nothing looked at.
  if [ "$scanned" -eq 0 ]; then
    echo "[emit-0013] FAIL -- no .sh files found under $repo_root/scripts; the scan, not the tree, is empty."
    exit 1
  fi
  echo "[emit-0013] PASS -- every own-baseline emit script applies 0013 ($scanned scanned)"
}

# --selftest is the non-vacuity BITE. It drives violates_file on REAL FILES, because that is the
# function run_lint uses. An earlier version tested a TEXT-taking helper that the lint had
# stopped calling -- so the self-test would have passed while the lint was broken, which is the
# same shape of vacuity this gate exists to catch in other people's fixtures.
selftest() {
  local d bad good gone rc
  d=$(mktemp -d)
  bad="$d/bad.sh"; good="$d/good.sh"; gone="$d/gone.sh"
  {
    echo 'for m in 0001_initial 0002_events_table 0005_events_outbox_table; do :; done'
    echo '"$WG" -seed 1 -profile x -emit -dsn "$DSN"'
  } > "$bad"
  {
    echo 'for m in 0001_initial 0002_events_table 0013_events_content_sha256; do :; done'
    echo '"$WG" -emit -dsn "$DSN"'
  } > "$good"

  violates_file "$bad" && rc=0 || rc=$?
  if [ "$rc" -ne 0 ]; then
    rm -rf "$d"
    echo "[emit-0013] SELFTEST FAIL -- did NOT flag an own-baseline emit script missing 0013 (vacuous)"; exit 2
  fi
  violates_file "$good" && rc=0 || rc=$?
  if [ "$rc" -eq 0 ]; then
    rm -rf "$d"
    echo "[emit-0013] SELFTEST FAIL -- flagged a script that DOES apply 0013"; exit 2
  fi
  # THE READ ARM, which is the half both previous fixes got wrong: a path that is not there must
  # come back "vanished" (3), never "violates" (0). Without this the truncation lesson above is a
  # comment rather than a check.
  violates_file "$gone" && rc=0 || rc=$?
  if [ "$rc" -ne 3 ]; then
    rm -rf "$d"
    echo "[emit-0013] SELFTEST FAIL -- a missing file reported $rc, not 3 (vanished); a read failure must never read as a finding"; exit 2
  fi
  rm -rf "$d"
  echo "[emit-0013] SELFTEST PASS -- flags a missing-0013 emit script, passes one with 0013, and reads a missing file as vanished rather than as a finding (non-vacuous)"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
