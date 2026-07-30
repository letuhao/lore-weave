#!/usr/bin/env bash
# scripts/eventgen-validate.sh — L2.G CI gate (RAID cycle 8).
#
# The generated event bindings under contracts/events/generated/ must be exactly
# what `eventgen` produces from _registry.yaml — no more, no less, and all of it
# in the repository. Four ways that can be false, all four checked here:
#
#   1. CONTENT DRIFT   a generated file was hand-edited (ignored DO NOT EDIT) or
#                      never regenerated after _registry.yaml changed.
#   2. ORPHAN          an event left the registry but its generated file stayed.
#   3. MISSING ON DISK the generator produces a file the working tree lacks.
#   4. UNTRACKED       the file exists on disk but is NOT IN THE REPOSITORY.
#
# ## Why (4) is here — it shipped, and the old gate said PASS (2026-07-30)
#
# Commit `d0a5eecf4` added `ruleset.epoch_activated` and committed the four
# BARRELS that reference it — rust/mod.rs, python/__init__.py, ts/index.ts,
# registry_generated.go — while the three per-event modules they import were
# left untracked. In a fresh clone `pub mod ruleset_epoch_activated_v1;` names
# a file that is not there.
#
# Nothing consumes the Rust/TS/Python bindings YET, so nothing was red — and
# that is exactly why it would have stayed broken. The debt lands on whoever
# wires the first consumer in, on a machine where the file was never generated,
# far from the commit that caused it.
#
# This gate ran and printed PASS, because it asked `git diff`, and **`git diff`
# compares the working tree against the index for TRACKED files only.** A file
# git has never heard of is not a difference — it is invisible. The check's
# subject was "files git already knows about", which is precisely the set that
# cannot contain the bug. That is the NV-3 shape (the scope never reaches it),
# and it is the same untracked-blindness that had been recorded as non-vacuity
# register row 26 one day earlier in a different gate — recorded, and not
# carried across. Intent is not a mechanism.
#
# So (4) is written in the POSITIVE direction: every file present under
# $out_dir must appear in `git ls-files`. The tempting form —
# `git ls-files --others --exclude-standard` — would go vacuous the moment
# someone gitignored the generated tree, which is exactly the adjacent decision
# (NV-4) that would silently defeat it.
#
# Generation now happens into a TEMPORARY directory rather than in place. The
# old in-place regeneration meant the gate could only ever report drift it had
# just finished erasing, and it mutated the working tree on every CI run.
#
# Exit 0 = generated tree is correct and committed. Non-zero = CI fails.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

out_dir="contracts/events/generated"

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
  rm -f tools/eventgen/eventgen tools/eventgen/eventgen.exe
}
trap cleanup EXIT

echo "[eventgen-validate] building eventgen tool…"
(cd tools/eventgen && go build -o eventgen .) \
  || { echo "[eventgen-validate] FAIL — eventgen build error"; exit 1; }

echo "[eventgen-validate] generating a reference tree…"
./tools/eventgen/eventgen \
  --registry contracts/events/_registry.yaml \
  --events-dir contracts/events \
  --out-dir   "$tmp_dir" \
  --target    all >/dev/null \
  || { echo "[eventgen-validate] FAIL — eventgen run error"; exit 1; }

# --- (1)(2)(3) content, orphans, missing — one recursive comparison ----------
if ! diff -r "$tmp_dir" "$out_dir" >/dev/null 2>&1; then
  echo "[eventgen-validate] FAIL — $out_dir does not match what eventgen produces."
  echo "    'Only in $tmp_dir'  = generated but MISSING from the working tree"
  echo "    'Only in $out_dir'  = ORPHAN, its event is no longer in the registry"
  echo "    'Files ... differ'  = content drift (hand-edited, or stale)"
  echo "    Run: make eventgen     # then commit the regenerated files"
  diff -r "$tmp_dir" "$out_dir" || true
  exit 1
fi

# --- (4) every generated file is actually IN THE REPOSITORY ------------------
# Positive direction on purpose: on-disk minus tracked. Asking git for
# "untracked files" would answer "none" the moment the tree were gitignored.
on_disk="$(cd "$out_dir" && find . -type f | sed 's|^\./||' | sort)"
tracked="$(git ls-files -- "$out_dir" | sed "s|^$out_dir/||" | sort)"
not_committed="$(comm -23 <(printf '%s\n' "$on_disk") <(printf '%s\n' "$tracked"))"

if [ -n "$not_committed" ]; then
  echo "[eventgen-validate] FAIL — generated files exist on disk but are NOT COMMITTED:"
  printf '    %s\n' $not_committed
  echo
  echo "    The barrels (rust/mod.rs, python/__init__.py, ts/index.ts) import these"
  echo "    modules by name. Committing the barrels without them gives a clone that"
  echo "    does not compile — and every local build keeps passing, because the"
  echo "    files are right there on YOUR disk."
  echo "    Run: git add $out_dir"
  exit 1
fi

echo "[eventgen-validate] PASS — $out_dir matches _registry.yaml and is fully committed"
exit 0
