#!/usr/bin/env python3
"""epoch-emit-trigger-gate — Q0b B3's emit path is UNBUILT, and this is what says so.

WHY A GATE AND NOT A NOTE
-------------------------
`Q0b` built the two halves that can be built: `B1` (the binding store — a
reality's ruleset digest, one append-only row per epoch) and `B2` (the island
seam — `RLS-D8`, the new `Arc` applied *between* two `step()` calls). `B3`, the
path that actually EMITS `RulesetEpochActivated`, was deliberately not built,
because three constraints are unresolved and none of them is a coding detail:

  1. **`admin-cli` is Go and cannot append.** `ChannelWriter::append` fences on a
     per-`(reality, channel)` writer lease (`DP-A16`); only the lease-holder may
     append. So the admin tool cannot write the event itself — it must ask the
     lease-holder to. That seam does not exist.
  2. **The `S5` chokepoint is unimplemented.** `RLS-A14` names it as the producer
     (`EVT-T8` Administrative, `EVT-P8` forbidding every non-admin-cli emitter),
     and there is nothing there yet to be the producer.
  3. **`dp::channel_pause` has zero occurrences.** `RLS-A14` wants N committed
     events, one per affected channel, and `RLS-D17` forbids a reality-wide
     barrier — which is only safe if a channel can be paused. It cannot.

That paragraph, in a handoff, is exactly the kind of thing this repo has now
watched evaporate several times: `D-PUBLISHER-DROPS-RULESET-PIN` was fixed and
still cited as an open blocker in four places, including the row of the very task
that was fixing it. **Prose does not survive; a check that reds does.**

WHAT THIS GATE ASSERTS, AND WHEN IT GOES RED
--------------------------------------------
Today: `ruleset.epoch_activated` appears in **no** event registry entry and has
**no** emit site. That is a measurement, re-taken on every run — not a constant.

It reds the day either appears. That is the whole point: the emit path cannot be
built *by accident* without someone deleting this file, and deleting it puts the
three constraints above into a diff a human reads. This is the same device as
`s1b_has_no_subject_yet_and_says_so`, which reded on the exact day `quantities`
arrived — the only tracked item in this project that has ever woken itself up.

NON-VACUITY (docs/standards/non-vacuity.md)
-------------------------------------------
- **NV-2, the subject varies.** The finding is a grep over the working tree, so
  its value changes the moment the tree does. Bite-proven: adding a `ruleset.*`
  entry to `_registry.yaml` reds it (see `--self-test`, which performs that
  mutation against an in-memory copy rather than describing it).
- **NV-3, the scope is a predicate.** Emit sites are found by walking every
  tracked non-doc source file, not an enumerated list, so a producer written
  tomorrow in a service that does not exist yet is in scope.
- **NV-4, the adjacent decision that would defeat it** is *renaming the event*.
  A gate keyed only on the literal `ruleset.epoch_activated` would be silently
  defeated by `ruleset.epoch_switched`. So it also reds on **any** `ruleset.*`
  registry entry and on the Rust/Go type name `RulesetEpochActivated`.
- **NV-5, no escape hatch.** There is no allowlist. The way out is to delete the
  file, which is visible.

    python scripts/epoch-emit-trigger-gate.py
    python scripts/epoch-emit-trigger-gate.py --self-test
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "contracts" / "events" / "_registry.yaml"

# The dotted event name, its Rust/Go type name, and the whole `ruleset.*`
# namespace. Three spellings so a rename does not walk past the gate (NV-4).
TYPE_NAME = "RulesetEpochActivated"
DOTTED = "ruleset.epoch_activated"
NAMESPACE = re.compile(r"^\s*-\s+name:\s*(ruleset\.[a-z0-9_.]+)\s*$", re.M)

# Where a mention is PROSE about the unbuilt path rather than an implementation
# of it. Design docs describe `RLS-A14` at length and must keep being able to;
# this gate is about code. `scripts/` is excluded for the same reason — this
# file's own docstring names the event twice.
def _is_source(rel: str) -> bool:
    if rel.startswith(("docs/", "scripts/")) or rel.endswith(".md"):
        return False
    return rel.endswith((".rs", ".go", ".ts", ".py", ".sql", ".yaml", ".yml", ".json"))


def _tracked() -> list[str]:
    r = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    return [f for f in r.stdout.split() if _is_source(f)]


def registry_entries(text: str | None = None) -> list[str]:
    """Every `ruleset.*` event_type declared in the SoT registry.

    Takes optional text so `--self-test` can bite it with a mutated copy instead
    of writing to the real file — a self-test that cannot mutate its subject
    proves only that the code parses.
    """
    if text is None:
        text = REGISTRY.read_text(encoding="utf-8") if REGISTRY.exists() else ""
    return NAMESPACE.findall(text)


def emit_sites() -> list[tuple[str, int, str]]:
    """(file, line, text) for every source mention of the event.

    A *mention* is deliberately over-broad: a struct definition, a match arm, a
    string literal all count. There is no way to name this event in source
    without intending to produce or consume it, and a gate that tried to
    distinguish "real" emit sites from decorative ones would be guessing.
    """
    out: list[tuple[str, int, str]] = []
    for rel in _tracked():
        p = REPO / rel
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if TYPE_NAME not in body and DOTTED not in body:
            continue
        for n, line in enumerate(body.splitlines(), 1):
            if TYPE_NAME in line or DOTTED in line:
                out.append((rel, n, line.strip()[:100]))
    return out


BLOCKERS = """
  1. admin-cli is Go and CANNOT append — ChannelWriter::append fences on a
     per-(reality, channel) writer lease (DP-A16). The authorise -> the
     lease-holder-appends seam does not exist.
  2. The S5 chokepoint that RLS-A14 names as the producer is unimplemented.
  3. dp::channel_pause has zero occurrences, so the N-events-one-per-channel
     shape RLS-A14 wants cannot be delivered without a reality-wide barrier,
     which RLS-D17 forbids.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    entries = registry_entries()
    sites = emit_sites()

    if not entries and not sites:
        print("epoch-emit-trigger-gate: OK — Q0b B3 is still unbuilt "
              f"(no ruleset.* event registered, no source names {TYPE_NAME}). "
              "This gate reds the day a producer appears.")
        return 0

    print("epoch-emit-trigger-gate: RED — the RulesetEpochActivated emit path has "
          "acquired a producer.\n")
    for e in entries:
        print(f"  registry entry: {e}")
    for rel, n, line in sites:
        print(f"  {rel}:{n}  {line}")
    print("\nThat is the trigger firing, not a bug. Q0b B3 was left unbuilt because "
          "three constraints are unresolved:")
    print(BLOCKERS)
    print("Answer them in the change that adds the producer, then DELETE this gate "
          "and close D-Q0B-EMIT-PATH. Do not allowlist your way past it — the whole "
          "value of this file is that the emit path cannot be built without someone "
          "reading the three lines above.")
    return 1


def self_test() -> int:
    fails = []

    # BITE 1 — the registry arm must actually detect an entry. Mutated in memory:
    # the gate is about a claim over the tree, and a self-test that only reads the
    # tree proves the parser runs, not that the check can fail.
    bitten = "events:\n  - name: ruleset.epoch_activated\n    aggregate: reality\n"
    if registry_entries(bitten) != ["ruleset.epoch_activated"]:
        fails.append("registry arm did not detect an injected ruleset.* entry — "
                     "the gate cannot fail, which makes it a claim, not a check")

    # BITE 2 — and it must red on a RENAME too, or an adjacent decision (calling it
    # `epoch_switched`) defeats it silently. This is the NV-4 arm.
    renamed = "events:\n  - name: ruleset.epoch_switched\n    aggregate: reality\n"
    if registry_entries(renamed) != ["ruleset.epoch_switched"]:
        fails.append("registry arm is keyed on one literal name — a rename walks "
                     "past it (NV-4: an adjacent decision defeats the check)")

    # And the negative control, without which both bites above pass for a function
    # that returns everything it is shown.
    if registry_entries("events:\n  - name: npc.said\n    aggregate: npc\n"):
        fails.append("registry arm matched an unrelated event — it is not "
                     "discriminating, so its greens mean nothing")

    # The scope must stay a walk, not a list. If someone replaces `_tracked()`
    # with an enumerated set of files, a producer written tomorrow in a new
    # service is default-uncovered (NV-3).
    if len(_tracked()) < 100:
        fails.append(f"_tracked() returned only {len(_tracked())} files — the scope "
                     "has stopped reaching the tree")

    # The blocker text is the deliverable when this reds. An empty one turns a
    # firing trigger into an unexplained CI failure someone reverts.
    for token in ("DP-A16", "S5", "dp::channel_pause", "RLS-D17"):
        if token not in BLOCKERS:
            fails.append(f"the RED message no longer names {token} — the reader gets "
                         "a failure with no design question attached")

    if fails:
        print("epoch-emit-trigger-gate SELF-TEST FAILED:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("epoch-emit-trigger-gate: self-test OK — both arms bite (an injected "
          "registry entry AND a renamed one red it), an unrelated event does not, "
          "the scope is a tree walk, and the RED message still carries the three "
          "blockers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
