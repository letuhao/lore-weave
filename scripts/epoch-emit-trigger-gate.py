#!/usr/bin/env python3
"""epoch-emit-trigger-gate — who is allowed to APPEND a ruleset epoch switch.

THIS GATE CHANGED ITS CLAIM ON 2026-07-30, AND THE HANDOVER IS THE POINT
-----------------------------------------------------------------------
It shipped as an **asserted trigger**: `RulesetEpochActivated` had no producer,
`Q0b B3` was unbuilt, and three constraints were unresolved. It reded on the
day the event was registered — exactly as designed — and printed those three
constraints for whoever caused it. That was its whole job, and it did it.

**All three turned out to be answered or wrong**, which is why this file now
guards something else instead of being deleted:

  1. *"admin-cli is Go and cannot append."* True, and IRRELEVANT. It does not
     need to. `ChannelWriter::append` CASes on
     `channel_writer_state.current_epoch`, so only the lease-holder may append —
     but the ADMIN ACT is writing the `reality_ruleset_binding` row, which
     admin-cli already does through `meta_write`. The lease-holder merely
     TRANSCRIBES that decision into its own channel. That IS the
     authorise -> lease-holder-appends seam.
  2. *"the S5 chokepoint is unimplemented."* Its job is to authorise the admin
     act, and `activate_reality_epoch` + admin-cli's auth already do that.
  3. *"`dp::channel_pause` has zero occurrences."* This one DISSOLVED. It was on
     the list because the first reading assumed the admin had to coordinate one
     switch across N channels. It does not: each channel's own writer appends
     its own event when it sees the binding move, so there is no barrier to
     avoid and `RLS-D17` is satisfied by construction. `channel_pause` is not
     needed and should not be built.

WHAT IS GUARDED NOW
-------------------
The event exists; **the producer does not yet** (`B3b`/`B3c` wire the spine to
the binding signal). The invariant that matters from here is not *"nothing
emits it"* but:

    RulesetEpochActivated may be appended ONLY from the channel-writer path.

Anything else — admin-cli, game-server, a projector, a worker — would be
claiming a channel position it does not hold the lease for, and `EVT-P8` would
be satisfied on paper by a process that cannot honour it. So: the type may be
NAMED anywhere (a consumer must match on it), but it may be CONSTRUCTED only
inside `services/commit-service/` and the contracts package that declares it.

NON-VACUITY
-----------
- **The subject varies** (`NV-2`): the finding is a grep over the tree, and
  `--self-test` constructs the violating shape rather than describing it.
- **The scope is a predicate** (`NV-3`): every tracked source file is walked, so
  a service that does not exist yet is in scope the day it does.
- **The adjacent decision that would defeat it** (`NV-4`) is a *rename*, so the
  Go struct name, the dotted event name, and the whole `ruleset.*` registry
  namespace are all checked.

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
def _is_test(rel: str) -> bool:
    """A TEST file, which may name this event freely.

    Not a convenience exemption — a correctness one. The gate's subject is *who
    may APPEND to a channel*, and appending requires the writer lease, a
    Postgres pool and a `channel_writer_state` row. A test that feeds a fixture
    event to a CONSUMER holds none of those; it is exercising the reader.

    This arm was added on 2026-07-30 because the gate reddened on
    `game-server/src/wire/turnOutcome.test.ts`, which builds a
    `{event_type: 'ruleset.epoch_activated'}` object to prove the room SKIPS
    administrative events rather than dying on them. Forbidding that would
    forbid testing the consumer — the gate would be demanding that a real bug
    stay untested in order to stay green.

    A PREDICATE, not a list: any file whose name or path marks it as a test is
    covered, including ones written tomorrow. It is deliberately narrow — a
    non-test file with identical content still reds, which the self-test bites.
    """
    name = rel.rsplit("/", 1)[-1]
    return (
        ".test." in name
        or ".spec." in name
        or name.endswith(("_test.go", "_test.py"))
        or name.startswith("test_")
        or "/tests/" in f"/{rel}"
    )


def _is_source(rel: str) -> bool:
    if rel.startswith(("docs/", "scripts/")) or rel.endswith(".md"):
        return False
    if _is_test(rel):
        return False
    return rel.endswith((".rs", ".go", ".ts", ".py", ".sql", ".yaml", ".yml", ".json"))


def _tracked() -> list[str]:
    # `--others --exclude-standard` is LOAD-BEARING, and leaving it out made this
    # gate VACUOUS — a bare `git ls-files` cannot see a file that has not been
    # `git add`ed, so a brand-new producer is invisible until the commit that
    # introduces it has already been made. Bite-proven: a Go producer dropped
    # into `services/admin-cli/` and a TS one into `services/game-server/` were
    # both reported GREEN.
    #
    # The same defect was fixed in `deferral-gate` a few hours earlier and not
    # carried across — which is the honest reason it is written out here rather
    # than left as a flag: a sibling gate copied the shape without the fix, and
    # a comment is what stops the third copy. The self-test passed throughout,
    # because it exercises the regexes in memory; only running it against the
    # real tree with a real violation showed the scope was blind (NV-3, and
    # exactly why NV-6 demands the tree-level bite as well as the fixture).
    r = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                       cwd=REPO, capture_output=True, text=True)
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


# Where the type may be CONSTRUCTED. `contracts/events` declares it; the
# channel writer lives in `commit-service`. Everything else may name it (a
# consumer has to match on it) but may not build one — see the module doc.
#
# `tools/eventgen` is the CODE GENERATOR, added 2026-07-30 when it reddened the
# gate for real: its per-event field map names every event by its dotted string,
# because naming them all is its entire job. It emits TYPES, never events, and it
# reaches neither Redis nor Postgres — so it can no more append to a channel than
# a header file can. This is the one widening that is a category, not an
# exception, and the self-test still fails a fourth entry: an authority check
# whose allowlist keeps growing is green by construction.
AUTHORISED_PREFIXES = ("contracts/events/", "services/commit-service/", "tools/eventgen/")

# What "constructing" looks like in each language the repo emits from. Not a
# mere mention: `RulesetEpochActivatedV1{` in Go, `RulesetEpochActivated {` or
# `::RulesetEpochActivated(` in Rust, and the dotted name used as an
# event_type STRING (which is how a Python or TS producer would emit it
# without ever naming the struct — the arm a Go/Rust-only check would miss).
CONSTRUCTORS = (
    re.compile(rf"{TYPE_NAME}(?:V\d+)?\s*\{{"),
    re.compile(rf"::{TYPE_NAME}(?:V\d+)?\s*[({{]"),
    re.compile(rf"[\"']{re.escape(DOTTED)}[\"']"),
)

# A MATCH ARM IS NOT A CONSTRUCTION, and the first version of this gate could
# not tell them apart — `Event::RulesetEpochActivated { .. }` matched the same
# brace pattern as building one. Its own self-test caught it, which is the whole
# argument for writing negative controls: a gate that forbids CONSUMING an event
# is a gate someone switches off, and then it is guarding nothing at all.
#
# Two signals, both strong in the languages this repo emits from: a rest-pattern
# `{ .. }` only ever appears in a pattern, and `=>` on the same line means the
# braces are the left-hand side of an arm. Deliberately conservative — it fails
# toward permitting, which is visible in review, rather than toward blocking a
# legitimate consumer, which is not.
PATTERN_NOT_CONSTRUCTION = (
    re.compile(r"\{\s*\.\.\s*\}"),
    re.compile(r"=>"),
)


# A GENERATED NAME-CONSTANT MODULE IS NOT A PRODUCER (T30/OD-1, 2026-08-12).
#
# `eventgen` now emits event-type NAME constants for every registered event, in Go and in
# Python, so producers and consumers import a name instead of re-declaring a literal. One of
# those outputs — `sdks/python/loreweave_events/__init__.py` — necessarily contains the line
#
#     EVENT_RULESET_EPOCH_ACTIVATED = "ruleset.epoch_activated"
#
# and this gate read it as a producer. It was right to: a dotted event_type in quotes is
# exactly how a Python service emits without ever naming the struct, which is the arm BITE 3
# exists to catch.
#
# The fix is a CATEGORY, not an exception, and specifically NOT a fourth entry in
# AUTHORISED_PREFIXES — that list is capped at three by this gate's own self-test, and the cap
# is correct. A file `eventgen` wrote is a declaration surface regenerated from
# `_registry.yaml`: it holds constants and type definitions and reaches neither Redis nor
# Postgres, so it can no more append to a channel than a header file can. It also cannot HIDE
# a producer, which is the property that makes this safe rather than convenient — nobody can
# add a `bus.publish` to it, because the next `make eventgen` deletes it, and
# `scripts/eventgen-validate.sh` fails the build if the tree drifts from the registry.
#
# ⚠️ WHAT THIS DOES COST, STATED RATHER THAN DISCOVERED. Name constants weaken any
# literal-based check, here and everywhere: a producer can now write
#
#     await bus.publish(EVENT_RULESET_EPOCH_ACTIVATED, payload)
#
# and no line contains the dotted string. That hole arrived with the constants themselves, not
# with this exemption, and it is the price of removing the hand-mirrored literals
# (D-GLOSSARY-EVENTS-NO-SOT). Closing it needs a symbol-aware check — the constant's importers,
# not its spelling — which is a real piece of work and is recorded rather than pretended away.
GENERATED_MARKER = "Code generated by eventgen"


def _is_generated(body: str) -> bool:
    """True for a file eventgen wrote. Checked against the HEAD of the file only, so a
    source file that merely quotes the marker in a comment or a test fixture further down
    cannot exempt itself by mentioning it."""
    return GENERATED_MARKER in "\n".join(body.splitlines()[:6])


def unauthorised_constructors() -> list[tuple[str, int, str]]:
    """(file, line, text) for every CONSTRUCTION outside the authorised paths."""
    out: list[tuple[str, int, str]] = []
    for rel in _tracked():
        if rel.startswith(AUTHORISED_PREFIXES):
            continue
        try:
            body = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if TYPE_NAME not in body and DOTTED not in body:
            continue
        if _is_generated(body):
            continue
        for n, line in enumerate(body.splitlines(), 1):
            if any(q.search(line) for q in PATTERN_NOT_CONSTRUCTION):
                continue
            if any(q.search(line) for q in CONSTRUCTORS):
                out.append((rel, n, line.strip()[:100]))
    return out


def producers_in_commit_service() -> bool:
    """Does the ONE authorised service actually construct the event yet?

    The mirror of `unauthorised_constructors`: that asks *"is anyone building
    this who may not"*, this asks *"is the one who may actually doing it"*. Both
    are needed, because an event that nobody constructs anywhere passes the
    authority check trivially — the `NV-3` degenerate case, a check whose scope
    is empty.
    """
    for rel in _tracked():
        if not rel.startswith("services/commit-service/"):
            continue
        try:
            body = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in body.splitlines():
            if any(q.search(line) for q in PATTERN_NOT_CONSTRUCTION):
                continue
            if any(q.search(line) for q in CONSTRUCTORS):
                return True
    return False


HANDOFF = REPO / "docs/03_planning/LLM_MMO_RPG/SESSION_HANDOFF.md"
DEFERRAL_ID = "D-Q0B-EMIT-PATH"
BEGIN, END = "<!-- deferral-registry:begin", "<!-- deferral-registry:end"


def deferral_row_still_open() -> bool | None:
    """Is `D-Q0B-EMIT-PATH` still inside the machine-read deferral registry?

    `None` means the question could not be asked — the file or its markers are
    gone. That is returned rather than `False` on purpose: a shrink rule that
    answers *"no, the row is not there"* because it could not find the registry
    is a rule that reports success from a broken scope, which is the whole
    `NV-3` shape. The caller reds on `None`.
    """
    try:
        text = HANDOFF.read_text(encoding="utf-8")
    except OSError:
        return None
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < 0 or j < i:
        return None
    return DEFERRAL_ID in text[i:j]


WHY = """
  ChannelWriter::append CASes on channel_writer_state.current_epoch, so only the
  process holding that channel's WRITER LEASE can append to it. A producer
  anywhere else is claiming a channel position it does not hold — EVT-P8 would
  be satisfied on paper by a process that cannot honour it.

  The admin act is writing the `reality_ruleset_binding` row (admin-cli already
  does this through meta_write, and it is audited). The lease-holder TRANSCRIBES
  that decision into its own channel, one event per channel, no barrier
  (RLS-D17). If you need to cause a switch, write the binding - do not append
  the event.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    # The event must still BE registered. If someone deletes it from the SoT
    # while a consumer matches on it, that is the mirror failure and this gate
    # is the only thing looking at the pair.
    if not registry_entries():
        print("epoch-emit-trigger-gate: RED — no `ruleset.*` event is registered in "
              "contracts/events/_registry.yaml.\n\nThe epoch switch has a typed shape "
              "in the kernel (IngressItem::EpochSwitch) and a durable binding, but no "
              "declared wire event — so a switch can happen and nothing downstream can "
              "learn of it. Re-register it, or delete this gate deliberately.")
        return 1

    bad = unauthorised_constructors()
    if not bad:
        # OUTSTANDING WORK, PRINTED ON EVERY RUN — never silent.
        #
        # `B3a` registered the event; `B3b`/`B3c` (the spine consuming the
        # binding signal, and the writer appending) are NOT built. Nothing here
        # can force them to be — a gate cannot demand that code be written — so
        # this is a status line, not a failure. But it is a status line that
        # appears every time anyone runs the suite, which is the difference
        # between a tracked gap and a forgotten one, and it is what mechanises
        # D-Q0B-EMIT-PATH: the deferral is named HERE, in code, rather than only
        # in a handoff paragraph.
        #
        # The shrink rule is the second branch: once commit-service constructs
        # the event, the work is DONE and the deferral row must be deleted. The
        # gate says so rather than leaving a satisfied row on the board.
        if not producers_in_commit_service():
            print("epoch-emit-trigger-gate: OK, WITH OUTSTANDING WORK — "
                  "`ruleset.epoch_activated` is registered and nothing constructs it "
                  "outside the channel-writer path, but commit-service does not "
                  "construct it either: B3b (spine consumes the binding signal) and "
                  "B3c (the writer appends) are unbuilt. Tracked: D-Q0B-EMIT-PATH.")
        else:
            # THE SHRINK RULE, and it FAILS rather than suggests. A printed
            # "you may now delete this" is advice, and advice is what left
            # D-PUBLISHER-DROPS-RULESET-PIN cited as an open blocker in four
            # places after it was fixed. A row that outlives its debt is not
            # untidy, it is FALSE — the next planner reads it and re-scopes work
            # that already shipped.
            open_row = deferral_row_still_open()
            if open_row is None:
                print(f"epoch-emit-trigger-gate: RED — cannot read the deferral "
                      f"registry in {HANDOFF.relative_to(REPO)} (missing file, or the "
                      f"`deferral-registry:begin/end` markers are gone).\n\n"
                      "  The shrink rule below needs to ask whether "
                      f"{DEFERRAL_ID} is still listed. It will not answer 'no' "
                      "just because it could not look — a check reporting success "
                      "from a broken scope is worse than no check.")
                return 1
            if open_row:
                print(f"epoch-emit-trigger-gate: RED — {DEFERRAL_ID} is STILL LISTED "
                      "as an open deferral, but the work is done: commit-service "
                      "constructs `ruleset.epoch_activated`, which is exactly what "
                      "that row said was missing.\n\n"
                      f"  Delete the {DEFERRAL_ID} row from the deferral registry in\n"
                      f"  {HANDOFF.relative_to(REPO)}.\n\n"
                      "  A satisfied deferral left on the board is not untidy, it is\n"
                      "  FALSE: the next planner reads it and re-scopes work that has\n"
                      "  already shipped. This project did exactly that four times in\n"
                      "  one day, which is why this is a failure and not a reminder.")
                return 1
            print("epoch-emit-trigger-gate: OK — `ruleset.epoch_activated` is "
                  "registered and constructed ONLY by commit-service, which is where "
                  "the channel writer lease is held. B3 (a/b/c) is complete and its "
                  "deferral row is gone.")
        return 0

    print("epoch-emit-trigger-gate: RED — RulesetEpochActivated is constructed "
          "outside the channel-writer path.\n")
    for rel, n, line in bad:
        print(f"  {rel}:{n}  {line}")
    print(WHY)
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

    # BITE 3 — THE ARM THIS GATE NOW EXISTS FOR. Each of the four shapes a
    # producer can take must be caught, and the last one is the reason this is
    # not a Go/Rust grep: a Python or TypeScript service emits by writing the
    # dotted event_type as a STRING and never names the struct at all.
    for shape in (
        'ev := events.RulesetEpochActivatedV1{RealityID: id}',          # Go
        'let e = RulesetEpochActivatedV1 { reality_id };',              # Rust struct
        'Event::RulesetEpochActivated(payload)',                        # Rust enum
        'await bus.publish("ruleset.epoch_activated", payload)',        # string only
    ):
        if any(q.search(shape) for q in PATTERN_NOT_CONSTRUCTION) or not any(
                q.search(shape) for q in CONSTRUCTORS):
            fails.append(f"a producer written as `{shape.strip()}` would NOT be "
                         "caught — the gate reports authority it is not checking")

    # …and the negative control, without which the four above pass for a pattern
    # that matches everything. A CONSUMER must stay legal anywhere: matching on
    # the type is how a projector does its job.
    for legal in (
        'match ev { Event::RulesetEpochActivated { .. } => project(ev),',   # match arm
        '// see RulesetEpochActivated for why this is per-channel',         # prose
        'type Handler = fn(&RulesetEpochActivatedV1);',                     # a signature
    ):
        if not any(q.search(legal) for q in PATTERN_NOT_CONSTRUCTION) and any(
                q.search(legal) for q in CONSTRUCTORS):
            fails.append(f"`{legal.strip()}` was flagged as a construction — the gate "
                         "forbids CONSUMING the event, which is not the rule and "
                         "would push someone to switch it off")

    # The authorised set must stay SMALL and must actually contain the writer.
    # A prefix list that grew to include, say, `services/` would make every green
    # meaningless while still looking like a check.
    if "services/commit-service/" not in AUTHORISED_PREFIXES:
        fails.append("the channel writer's own service is not authorised — the gate "
                     "would forbid the one place that CAN legitimately append")
    # The generated-file exemption, both directions. Without the second arm it would be a
    # blanket "any file mentioning the marker is fine", which is how an exemption becomes a
    # hole — and the marker is a string anyone can type.
    _gen_head = "# Code generated by eventgen v0.1.0. DO NOT EDIT.\nEVENT_X = 1\n"
    if not _is_generated(_gen_head):
        fails.append("a file eventgen wrote is not recognised as generated — the name "
                     "constants it must contain would be read as a producer")
    _late = "\n".join(["x = 1"] * 20 + ["# Code generated by eventgen", "y = 2"])
    if _is_generated(_late):
        fails.append("a hand-written file claimed the generated marker far down the file "
                     "and was exempted — the check must look at the HEAD only")

    if len(AUTHORISED_PREFIXES) > 3 or any(q in ("services/", "crates/") for q in AUTHORISED_PREFIXES):
        fails.append(f"AUTHORISED_PREFIXES has widened to {AUTHORISED_PREFIXES} — an "
                     "authority check whose allowlist covers everything is green by "
                     "construction")

    # BITE 4 — THE SCOPE MUST SEE AN UNTRACKED FILE, and this arm exists because
    # it did not. `git ls-files` without `--others` is blind to anything not yet
    # `git add`ed, so a brand-new producer read as GREEN — the gate was vacuous
    # while its self-test passed, because the self-test only exercised regexes in
    # memory. Written as a check rather than a comment so the next sibling gate
    # that copies this shape cannot copy it without the fix.
    probe = REPO / "services" / ".epoch_gate_scope_probe.go"
    try:
        probe.write_text("package main\n", encoding="utf-8")
        seen = _tracked()
        if not any(p.endswith(".epoch_gate_scope_probe.go") for p in seen):
            fails.append("_tracked() cannot see an UNTRACKED file — a producer added "
                         "in the same commit that introduces it is invisible, which "
                         "makes every green meaningless (NV-3)")
    finally:
        probe.unlink(missing_ok=True)

    # BITE 5 — THE TEST EXEMPTION MUST NOT LEAK INTO PRODUCTION CODE. `_is_test`
    # lets a fixture name the event; the danger is that the predicate is loose
    # enough to swallow a real producer. Both directions are bitten: a genuine
    # test path must be exempt, and a production path that merely SITS NEAR one
    # must not be.
    exempt_must = [
        "services/game-server/src/wire/turnOutcome.test.ts",
        "services/commit-service/tests/epoch_signal.rs",
        "services/meta-outbox-relay/pkg/drain/drain_test.go",
        "services/x/tests/helpers/mod.rs",
    ]
    for rel in exempt_must:
        if not _is_test(rel):
            fails.append(f"_is_test({rel!r}) is False — a test that names the event "
                         "would red the gate, which would forbid TESTING the consumer")
    scoped_must = [
        "services/game-server/src/wire/turnOutcome.ts",
        "services/admin-cli/main.go",
        "services/game-server/src/rooms/ChannelRoom.ts",
        "services/latest/src/protest.rs",   # contains "test" and is NOT one
    ]
    for rel in scoped_must:
        if _is_test(rel):
            fails.append(f"_is_test({rel!r}) is True — the exemption has widened to "
                         "production code, so a real producer could hide behind it")

    # The RED message must carry the WHY. A bare "not allowed here" gets reverted.
    for token in ("channel_writer_state", "WRITER LEASE", "reality_ruleset_binding", "RLS-D17"):
        if token not in WHY:
            fails.append(f"the RED message no longer names {token} — the reader gets a "
                         "refusal with no explanation of who may append instead")

    if fails:
        print("epoch-emit-trigger-gate SELF-TEST FAILED:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("epoch-emit-trigger-gate: self-test OK — the registry arm bites on an "
          "injected entry AND on a renamed one, all four producer shapes are caught "
          "(including the string-only one a Python/TS service would use), consumers "
          "stay legal, the authorised set is still narrow, and the RED message says "
          "who may append instead.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
