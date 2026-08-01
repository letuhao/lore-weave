#!/usr/bin/env python3
"""deferral-gate — a deferral with no mechanism is a wish, and wishes evaporate.

THE MEASUREMENT THIS EXISTS TO ACT ON (2026-07-29)
--------------------------------------------------
The PO asked the right question: *"when should the unbuilt things be built — will
they be forgotten?"* So it was measured rather than guessed. Of the deferrals
tracked on the game tier, **9 of 19 were prose only** — a row in a handoff and
nothing else. And within a single day this project produced, unaided:

  · `D-PUBLISHER-DROPS-RULESET-PIN` cited as an open blocker in **four** places
    after it had been fixed — including the `Q1` row of doc 35 §12, which read
    *"Blocked on…"* while `Q1` was being built and shipped.
  · **six** CI legs red on `main` for four days with nobody acting.
  · a test that skipped unconditionally and could never un-skip.
  · **four** deferral rows fixed in the morning and still listed as open in the
    afternoon — drift created by the same agent that was writing the audit.

What survived, in the same day, was without exception **mechanical**:
`s1b_has_no_subject_yet_and_says_so` reded on the exact day its subject arrived;
`gate-wiring-gate`'s shrink rule forced six rows to be deleted rather than
annotated; a Rust exhaustive `match` refused to compile against a new field.

    Intent is not a mechanism. A deferral that only a human remembers
    is indistinguishable from one that was dropped.

WHAT THIS GATE REQUIRES
-----------------------
Every deferral id inside a **marked registry block** must be one of:

  MECHANISED  — named by at least one non-doc source file, with COMMENT LINES
                STRIPPED. A test, a `KNOWN_RED` row, an allowlist entry, a gate
                that reds on arrival. Something that changes colour by itself.
  PROSE_ONLY  — declared here, with a reason saying **what would wake it up**.
                This is a legitimate answer; some things genuinely have no
                mechanism today. It is not a legitimate *default*.

The comment stripping is the load-bearing part. A `// TODO(D-FOO)` in a `.rs`
file is prose that happens to live in a source file — it will never change
colour, and counting it would let every row satisfy the gate by being mentioned.
Bite-proven below in `--self-test`, and demonstrated on the real tree: two
`D-GATE-ROT-*` ids appear in `gate-wiring-gate.py` **only** inside the comment
recording that their rows were deleted, and this gate correctly refuses to call
them mechanised.

THE SHRINK RULE — INHERITED FROM gate-wiring-gate, AND THE POINT OF THE FILE
---------------------------------------------------------------------------
A `PROSE_ONLY` row **fails** when its id leaves the registry, or when the id
becomes mechanised. So the list shrinks as debt is paid instead of quietly
becoming the new normal. This is the same rule `file-ceiling-gate` applies to
allowlisted line counts and `gate-wiring-gate` to `KNOWN_RED`, and it is the only
one of the three devices in this repo that has ever forced a row to be *deleted*.

SCOPE — SAID OUT LOUD, BECAUSE IT IS NOT THE WHOLE REPO
-------------------------------------------------------
Obligation applies to ids inside a marked block. It is **not** every `D-*` in the
tree: **745** distinct ids are named by non-doc files and **~360** more live in
the platform-track registries, almost all of them historical. Retrofitting an
obligation onto all of them would produce a registry of hundreds of rows — which
is theatre, and worse than nothing, because a list that large is never read.

So: registry files WITHOUT a marker are **printed on every run**, with their raw
id counts, as an out-of-scope hole. A skip that prints is a known limit; a skip
that is silent is a claim of coverage. Widening to the platform track is tracked
as `D-DEFERRAL-GATE-PLATFORM-SCOPE` — which, being prose-only, needs a row in
this very file. That is not a joke; it is the gate applied to itself.

    python scripts/deferral-gate.py
    python scripts/deferral-gate.py --audit      # classify, do not judge
    python scripts/deferral-gate.py --self-test
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

BEGIN = "<!-- deferral-registry:begin"
END = "<!-- deferral-registry:end"

# A deferral id. The lookbehind matters: without it, `LOAD-BEARING` matches as
# `D-BEARING` and `READ-ONLY` as `D-ONLY`, which is how a first pass over the
# docs produced 2006 "deferral ids" — 54 of them the word "only". A predicate
# that matches noise is not a scope, it is a random sample.
ID = re.compile(r"(?<![A-Za-z0-9])D-[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+")

# THE HOLE IN `ID`, AND HOW IT IS CLOSED RATHER THAN CONFESSED.
# `ID` requires TWO segments after `D-`, because relaxing to one lets prose in
# (measured: `D-F`, `D-Q1`, `D-Q6` appear in the game handoff as false hits). But
# single-segment ids DO exist on the platform track — `D-START`, `D-TEAM` — and a
# scope that silently cannot see them is the NV-3 shape: the check never reaches
# its subject, and reports OK for it.
#
# So the shape is ENFORCED instead of hoped for. Any backticked `D-…` token
# inside a marked block that `ID` cannot parse FAILS the gate, with instructions
# to rename. A one-segment id is then impossible to add unnoticed — the hole is
# closed by making the unparseable case loud, not by widening the pattern until
# it matches noise.
BACKTICKED = re.compile(r"`(D-[A-Za-z0-9][A-Za-z0-9_-]*)`")

# Line-comment prefixes by extension.
#
# LINE COMMENTS ARE NOT ENOUGH, AND THE PROOF IS IN THIS REPO.
# The first version stripped only line comments and declared that block comments
# were "a known limit". Bite-testing it immediately produced two FALSE MECHANISED
# verdicts: `D-PUBLISHER-SMOKE-NOT-IN-CI` and `D-META-LIVE-SMOKE-NOT-IN-CI` were
# reported as carrying a mechanism when their only non-`#` mention in the whole
# tree is the **module docstring of `gate-wiring-gate.py`** — a triple-quoted
# string, which no line-based stripper touches, containing pure prose.
#
# That is the gate's one job, failed: it would have certified two prose-only
# deferrals as mechanised, which is worse than not checking, because it reports
# coverage. So docstrings and block comments are stripped too (`_strip`).
COMMENT = {
    ".rs": "//", ".go": "//", ".ts": "//", ".tsx": "//", ".js": "//",
    ".py": "#", ".yaml": "#", ".yml": "#", ".sh": "#", ".toml": "#",
    ".sql": "--",
}


def _registry_files() -> list[Path]:
    """Handoffs + the AMAW deferral registry, found by SHAPE.

    A new track's handoff is in scope the day it is created, without anyone
    adding it to a list — the same reason `gate-wiring-gate` keys on filename
    shape rather than an enumeration.
    """
    out = list(REPO.glob("docs/**/SESSION_HANDOFF.md"))
    out += sorted((REPO / "docs" / "deferred").glob("*.md"))
    return sorted(set(out))


def marked_ids(path: Path) -> set[str]:
    """Ids inside `deferral-registry:begin/end` blocks.

    The markers exist because *open* is not inferable from a 7,869-line
    historical document: the game handoff mentions closed ids, quoted ids, and
    ids inside `<details>` history blocks. Guessing at open-vs-closed from prose
    would make every verdict unreliable, and an unreliable gate gets ignored —
    which is the failure this whole file is about. The markers make `open`
    machine-readable at the cost of one HTML comment.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    found: set[str] = set()
    depth = 0
    for line in text.splitlines():
        if BEGIN in line:
            depth += 1
            continue
        if END in line:
            depth = max(0, depth - 1)
            continue
        if depth:
            found.update(ID.findall(line))
    return found


def unparseable_ids(path: Path) -> set[str]:
    """Backticked `D-…` tokens inside a block that `ID` cannot see. See BACKTICKED."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    bad: set[str] = set()
    depth = 0
    for line in text.splitlines():
        if BEGIN in line:
            depth += 1
            continue
        if END in line:
            depth = max(0, depth - 1)
            continue
        if depth:
            for tok in BACKTICKED.findall(line):
                if not ID.fullmatch(tok):
                    bad.add(tok)
    return bad


def _source_files() -> list[str]:
    # `--others --exclude-standard` is load-bearing, and it was a real bug: the
    # first run of this gate reported `D-Q0B-EMIT-PATH` as prose-only while the
    # asserted trigger that mechanises it sat in the working tree UNTRACKED.
    # A gate that cannot see a mechanism added in the same commit as its row
    # punishes exactly the workflow it is trying to encourage — and it fails
    # toward "no mechanism", so the author's fix is to weaken the row rather
    # than notice the gate is blind.
    r = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                       cwd=REPO, capture_output=True, text=True)
    # THIS FILE IS EXCLUDED, and the bug it fixes is the funniest one here: the
    # `PROSE_ONLY` keys below are string literals in a `.py` file, so on the very
    # first run every prose-only row was reported STALE — "the id is now named by
    # scripts/deferral-gate.py" — because declaring a row mechanised it. A
    # registry that satisfies its own requirement by existing is the purest form
    # of the vacuity this repo has a standard about.
    me = Path(__file__).name
    return [
        f for f in r.stdout.split()
        if not f.endswith(".md") and not f.startswith("docs/")
        and Path(f).suffix in COMMENT and Path(f).name != me
    ]


TRIPLE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')
BLOCK = re.compile(r"/\*[\s\S]*?\*/")


def _strip(body: str, prefix: str, suffix: str = ".py") -> str:
    """Remove line comments, block comments, and Python docstrings.

    Docstrings are removed WHOLESALE rather than only at module level, and yes
    that also removes legitimate triple-quoted string literals. That direction is
    chosen deliberately: it fails toward reporting a real mechanism as
    prose-only, which is LOUD (the author adds a PROSE_ONLY row, notices it is
    wrong, and moves the id into ordinary code). The other direction — counting a
    docstring as a mechanism — is SILENT, and it is the exact failure this
    function was rewritten to fix.
    """
    # Keyed on the LANGUAGE, not on the comment prefix. `"""` means nothing in
    # Go or YAML, and running the docstring regex over them could only ever
    # delete a real mechanism by accident — the direction that fails silently in
    # the *other* direction (a mechanism read as prose) is loud, but there is no
    # reason to accept even that when the language is known.
    if suffix == ".py":
        body = TRIPLE.sub("", body)
    if prefix == "//":
        body = BLOCK.sub("", body)
    return "\n".join(
        ln for ln in body.splitlines() if not ln.lstrip().startswith(prefix)
    )


def mechanisms() -> dict[str, list[str]]:
    """id -> files that name it in NON-COMMENT source.

    This is the whole discriminator. `git grep D-FOO` says yes for a TODO
    comment, and a TODO comment is exactly the thing that does not survive —
    it has no colour, nothing runs it, and it reads as coverage to the next
    person who greps. Stripping comments is what makes the answer mean
    *"something here changes state when the debt is paid."*
    """
    hits: dict[str, list[str]] = {}
    for rel in _source_files():
        prefix = COMMENT[Path(rel).suffix]
        try:
            body = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "D-" not in body:
            continue
        for i in set(ID.findall(_strip(body, prefix, Path(rel).suffix))):
            hits.setdefault(i, []).append(rel)
    return hits


# id -> what would wake it up. NOT a parking lot: the shrink rule below fails
# when a row's id leaves the registry OR becomes mechanised, so every row here
# is on a clock. A reason must say what the TRIGGER is, not restate the task.
PROSE_ONLY: dict[str, str] = {
    "D-POOL-PROBE-IS-NOT-A-QUERY": (
        "TRIGGER: the first commit that threads a retrieval call into the pool loop "
        "— the moment probe() output would actually be used as a search. Measured "
        "2026-08-01 against the real Fengshen corpus (2329 chunks, production "
        "chunker and cosine, BYOK embeddings): probe() returns the slot id and its "
        "consumers last path segments, which are English snake_case identifiers in "
        "the CONTRACT vocabulary, and the corpus is Ming-dynasty classical Chinese. "
        "Every slot scored at the noise floor and not one top-3 hit was on topic - "
        "instrument tag returned a lesson on playing the zither. Queries written by "
        "a model in the corpus own register scored about 0.09 higher and, far more "
        "importantly, returned the right material. No mechanism today because "
        "NOTHING CONSUMES probe() OUTPUT: it is computed, logged, and dropped, so a "
        "check on query quality would have no possible violation - the NV-2 shape. "
        "The fix changes the PlannerKind protocol and needs the retrieval seam "
        "threaded through the loop, which is a build, not an edit"),
    "D-POOL-EVIDENCE-N-UNDEFINED-ON-A-REAL-CORPUS": (
        "TRIGGER: the same commit - the first time retrieved spans replace the "
        "hand-written evidence block. The ABSTRACT criterion is m < n, and n came "
        "from a block the author wrote by hand: eleven bullet lines, so n=11. "
        "Retrieved spans do not arrive counted, and there is no defensible way to "
        "derive n from a chunk count because a chunk is not an object. Asking the "
        "MODEL for n hands it the denominator of its own gate, which is exactly the "
        "BLD-A4 failure this track already measured. The count has to come from an "
        "extraction step - where POC-1 interrogation stage and the citation matcher "
        "already live. No mechanism today because the evidence block is a literal "
        "in a git-ignored spike file, so nothing in the repo can disagree with it"),
    "D-POOL-REFUSAL-CHANNEL-HAS-TWO-MEANINGS": (
        "TRIGGER: the first consumer that READS the refusal channel — a router that "
        "turns a refusal into work for the named module, or a report that groups "
        "refusals by owner. BLD-A3 gave refusal its own channel with a single shape "
        "{what, why, owner}, and live runs showed the field carrying two unrelated "
        "meanings: for ABSTRACT and CLASSIFY_LINK owner means THIS BELONGS TO "
        "ANOTHER MODULE, but for PARTITION a refusal means THIS AXIS HAS NO LADDER "
        "and nothing is being routed at all — the model duly put the slot's own name "
        "in owner. Splitting it needs a decision about what a refusal IS, not an "
        "edit. No mechanism today because nothing consumes the channel: with no "
        "reader, a check on the field's meaning would have no possible violation"),
    "D-SPEC-CODE-ENUM-PARITY": (
        "TRIGGER: a layer-aware notion of enum identity, so DP ActorId and the "
        "feature-layer ActorId are different symbols rather than a name clash. "
        "design-lint count now checks spec-only enums against the declaration in "
        "the SAME FILE, which closed REC-98. It deliberately does NOT compare "
        "across documents, nor a corpus declaration against a real Rust enum. Both "
        "are real drift surfaces and both were CUT AT DESIGN REVIEW WITH EVIDENCE: "
        "three docs declare pub enum ActorId and two are legitimately different "
        "types (the data planes {Player, Npc} vs the feature layers {Pc, Npc, "
        "Synthetic, Admin, Locus}), so a cross-doc arity check would have "
        "false-positived on its first run. This checks own recorded history is that "
        "a lint which cries wolf gets switched off - it spent its first life "
        "INFO-only for exactly that reason. Shipping it noisy would cost more than "
        "the coverage buys. No mechanism today because the missing piece is a "
        "DESIGN decision about symbol identity, not code"),
    "D-WORLD-BASELINE-RETENTION": (
        "TRIGGER: the first commit adding a PRUNER or retention job to the world "
        "baseline store or the generator-version store. WDS-A5 says the baseline blob "
        "is never pruned while referenced; WDS-A6 says a generator version may not be "
        "deleted while a reality pins it. Both are load-bearing — deleting either "
        "silently makes a live reality unreproducible, and WDS-A7 already establishes "
        "that the bytes are the SSOT because f32 regeneration is unproven "
        "cross-platform. No mechanism today for the NV-2 reason: THE SUBJECT DOES NOT "
        "EXIST. There is no WorldBaselineStore, no pruner and no generator_version "
        "column, so a retention check would have no possible violation and would "
        "report coverage it does not have. The bite test is stated in advance so it "
        "is not designed after the fact: prune a digest a live reality still pins, "
        "and the job must REFUSE. RulesetStore is the precedent to copy — its put "
        "refuses to overwrite and its get refuses on digest mismatch, and retention "
        "is the one property it does not enforce either"),
    "D-RETIRED-IDENT-CODE-SCOPE": (
        "TRIGGER: the first commit that lands `MapKind` in Rust. amendment-rot-gate "
        "check D reads *.md under the design track only, so a retired identifier "
        "reappearing in crates/ or services/ is uncovered. Named by /review-impl "
        "immediately after the SAME check was found to be silently excluding "
        "_boundaries/ - one scope hole further out, and the second instance of NV-3 "
        "in one check. No mechanism today because the SUBJECT CANNOT OCCUR: MapKind "
        "is unimplemented, so no Rust file can reference ChannelTier and a code-side "
        "check would have no possible violation (the NV-2 shape). Widening also needs "
        "a language-aware notion of citing a retirement in code (a // comment naming "
        "the amendment row), which is a bigger change than the docs case. This row "
        "exists so the boundary is re-read when MapKind lands, not re-discovered"),
    "D-WORLD-PAYLOAD-DERIVABLE": (
        "TRIGGER: the first commit in which world-payload SIZE or wire BANDWIDTH is "
        "measured as a constraint. Measured 2026-07-30 (WDS-A8): 67.6% of the "
        "generated world payload is derivable and need not be stored — 50.1% is "
        "`vertex_polygon`, 7.9% `center`, the rest `neighbors` + `is_coast`. mesh.rs "
        "says why: the lattice is `fibonacci(n)` and its own test asserts the "
        "seed-driven rotation is 'the ONLY source of seed dependence here', so the "
        "whole mesh reconstructs from one integer and a quaternion; adjacency is "
        "Quickhull over the centres. Packed, the irreducible part is ~20 B/cell — "
        "~320 KB at Megaplanet against ~15 MB stored, a 46x difference. PO chose "
        "STORE-EVERYTHING (WDS-D3) for simplicity, which is a legitimate call at "
        "this scale: 15 MB per world constrains nothing today. No mechanism because "
        "there is no threshold to assert against — a check would have no possible "
        "violation (the NV-2 shape), and inventing a budget nobody has measured is "
        "how a gate becomes noise. Stripping is also NOT free: it needs Quickhull on "
        "the read path, where WDS-A7's f32 cross-platform problem is WORSE than on "
        "the write path. This row's job is to keep the 67.6% measurement findable "
        "the day someone profiles the payload, so it is re-derived from a number "
        "rather than re-discovered from scratch"),
    "D-LEDGER-BEFORE-BALANCE": (
        "TRIGGER: the first commit that BALANCES content against the economy — a "
        "price table, a drop table, a production/consumption rate, a reward curve. "
        "This is the only row in the registry with a DEADLINE rather than a "
        "priority, and the deadline is one-way: WSA-R14 states that the ledger "
        "becomes impossible to retrofit once content is balanced against a leaky "
        "economy, BECAUSE AT THAT POINT THE LEAKS ARE THE BALANCE — removing them "
        "later breaks every number an author tuned. Today EXC-F2 is true: the "
        "engine has the TRANSACTION but not the LEDGER, so nothing asserts "
        "conservation and a source-less 10 coins is silently legal. No mechanism "
        "yet because the subject does not exist — there is no ledger to assert "
        "against, so a check would have no possible violation (the NV-2 shape). "
        "What makes it mechanisable is the ledger itself: the bite test named in "
        "WSA-R14 is that a source-less 10 coins goes RED. Until then this row's "
        "job is to be printed on every run so the deadline cannot pass quietly"),
    "D-META-ALLOWLIST-NO-DRIFT-GATE": (
        "TRIGGER: the next meta table added. The Rust and Go allowlists are "
        "hand-mirrored and already drifted once — the Rust side silently dropped "
        "`xreality_topic` because serde ignores unknown fields while Go reads it. "
        "No mechanism today because the drift test wants a shared SoT that does "
        "not exist yet; adding a table is what makes writing it cheap"),
    "D-EMPTY-PORTABLE-SIDE": (
        "TRIGGER: F2 giving the portable side a required field. Today the only "
        "mention is a `///` doc comment on `Actor` — prose that happens to live "
        "in a .rs file, which is precisely what this gate refuses to count. There "
        "is nothing to assert yet: an empty portable side is currently LEGAL, so "
        "a check would have no possible violation (the NV-2 shape). The first "
        "required field is what gives it a subject"),
    "D-WIRE-DIGEST-ZERO": (
        "TRIGGER: `zero-digest-gate` growing a shrink rule, or the binding "
        "reaching the transport. The `// zero-digest-gate: ok — D-WIRE-DIGEST-ZERO` "
        "pragma in ChannelRoom.ts is an EXEMPTION, not a mechanism: it SILENCES a "
        "finding and would keep silencing it after the digest became real. It can "
        "only become a mechanism when the gate reds on a pragma that is no longer "
        "needed — the same shrink rule `gate-wiring-gate` applies to KNOWN_RED"),
    # These three were the gate's first real catch, and it caught its own author.
    # The handoff table shipped in the same commit claimed all three as
    # "guarded"/"named in gates.yml". Every one turned out to be a JSDoc block,
    # a `#` yaml comment, or a module docstring — prose in a source file.
    "D-GAME-WS-EDGE-CONTROLS": (
        "TRIGGER: the PRR-20 edge-control parity test. The three `ws/` files name "
        "this id ONLY in their JSDoc headers (`* … (077 / D-GAME-WS-EDGE-CONTROLS)`), "
        "which is provenance, not a check — nothing reds if the second public entry "
        "point stops inheriting the gateway's auth/rate-limit/audit controls. The "
        "mechanism is a test asserting that parity, and it needs both transports up"),
    "D-META-LIVE-SMOKE-NOT-IN-CI": (
        "TRIGGER: `gate-wiring-gate.is_gate()` widening to `-smoke`, which needs a "
        "stack-up CI job to exist first. Today the id appears only in that gate's "
        "docstring, where it is stated as a scope LIMIT — the smokes are explicitly "
        "out of its predicate. Documenting a hole is not covering it"),
    "D-PUBLISHER-SMOKE-NOT-IN-CI": (
        "TRIGGER: the same stack-up CI job. Same shape, same docstring, same "
        "distinction — `.github/workflows/gates.yml` names it in a `#` comment "
        "explaining why the smoke is absent, which is honesty about a gap rather "
        "than a mechanism that closes it"),
    "D-EPOCH-SIGNAL-FANOUT": (
        "TRIGGER: the first node hosting more than a handful of channels, or a "
        "measured PEL depth on `lw.meta.events`. Each channel writer takes its OWN "
        "consumer group on that deployment-wide stream (it must — a shared group "
        "SPLITS entries and a channel that missed one would never switch), so every "
        "meta write in the deployment is delivered N times for N channels. The "
        "signal bus also never calls `reclaim()`: a crash between fetch and ack "
        "leaves entries pending for that group forever. Neither is a CORRECTNESS "
        "problem — the reconcile reads the binding table, so a lost or unacked "
        "signal changes nothing — which is exactly why it needs a row: it will "
        "never announce itself as a bug, only as load"),
    "D-EPOCH-SMOKE-NOT-IN-CI": (
        "TRIGGER: the same stack-up CI job as the two rows above. "
        "`scripts/epoch-activation-live-smoke.sh` proves the Q0b B3 path against a "
        "real Postgres (binding -> island switch -> committed event) and runs only "
        "by hand, because `is_gate()` excludes `-smoke` and this one needs two "
        "throwaway databases plus the per-reality migration sequence. A third row "
        "rather than a footnote on an existing one: a reader asking 'is MY smoke in "
        "CI' must find the answer under its own name"),
    "D-S04-1": (
        "TRIGGER: the S04 provisioner track resuming. Nothing in this repo can "
        "red on it — the subject is an unbuilt service, so there is no file for a "
        "check to hold. Genuinely prose-only until S04 has code"),
    "D-DEFERRAL-GATE-PLATFORM-SCOPE": (
        "TRIGGER: the platform handoff gaining a `deferral-registry:begin` marker. "
        "This gate governs the game tier only; ~360 ids in docs/sessions/ and "
        "docs/deferred/ are out of obligation scope and are printed as a hole on "
        "every run. Widening is a decision about which of those are still OPEN — "
        "a triage, not a code change, which is exactly why it cannot be mechanised "
        "in advance"),
}


def audit() -> tuple[dict[str, list[str]], list[str], list[Path]]:
    """(mechanised, prose, unmarked_files) over the marked registries."""
    mech_all = mechanisms()
    marked: set[str] = set()
    unmarked: list[Path] = []
    for f in _registry_files():
        ids = marked_ids(f)
        if ids:
            marked |= ids
        else:
            unmarked.append(f)
    mechanised = {i: mech_all[i] for i in sorted(marked) if i in mech_all}
    prose = [i for i in sorted(marked) if i not in mech_all]
    return mechanised, prose, unmarked


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--audit", action="store_true",
                    help="classify every tracked deferral without judging it")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    mechanised, prose, unmarked = audit()

    if args.audit:
        for i, files in mechanised.items():
            print(f"  MECHANISED  {i:<42} {', '.join(files[:3])}")
        for i in prose:
            tag = "declared" if i in PROSE_ONLY else "UNDECLARED"
            print(f"  prose-only  {i:<42} {tag}")
        print(f"\n{len(mechanised)} mechanised, {len(prose)} prose-only "
              f"({len(mechanised) + len(prose)} tracked)")
        return 0

    fails: list[str] = []

    for f in _registry_files():
        for tok in sorted(unparseable_ids(f)):
            fails.append(
                f"{f.relative_to(REPO).as_posix()}: `{tok}` is inside a registry block "
                "but does not match the id shape, so the gate CANNOT SEE IT and would "
                "report OK for a deferral it never checked. Rename it to the "
                "`D-<WORD>-<WORD>` convention (at least two segments, upper-case).")

    undeclared = [i for i in prose if i not in PROSE_ONLY]
    if undeclared:
        fails.append(
            "deferral(s) with NO mechanism and no declared reason:\n"
            + "".join(f"      {i}\n" for i in undeclared)
            + "    Write the check that reds when it is due — an asserted trigger, a "
              "KNOWN_RED row, a test named for it — or add a PROSE_ONLY row saying "
              "what would wake it up. A row in a handoff and nothing else is the "
              "shape that has already been forgotten four times this week.")

    # THE SHRINK RULE, both arms.
    marked_now: set[str] = set(mechanised) | set(prose)
    for i in sorted(PROSE_ONLY):
        if i in mechanised:
            fails.append(
                f"{i}: PROSE_ONLY row is STALE — the id is now named by "
                f"{', '.join(mechanised[i][:3])}. Delete the row; it is claiming the "
                "debt has no mechanism while the mechanism exists.")
        elif i not in marked_now:
            fails.append(
                f"{i}: PROSE_ONLY row for an id that is no longer in any registry "
                "block. Either the deferral closed (delete the row) or it fell out "
                "of the block by accident (put it back) — an acknowledgement list "
                "that outlives its subjects stops being an acknowledgement.")

    for i, why in PROSE_ONLY.items():
        if "TRIGGER:" not in why:
            fails.append(f"{i}: PROSE_ONLY reason does not name a TRIGGER. 'Later' "
                         "is not a trigger; the row must say what wakes it up.")
        if len(why) < 80:
            fails.append(f"{i}: PROSE_ONLY reason is too thin to act on.")

    if unmarked:
        # PRINTED, NEVER SILENT — and not a failure. These are real registries
        # this gate does not govern; saying so on every run is what keeps the
        # scope honest. Tracked as D-DEFERRAL-GATE-PLATFORM-SCOPE.
        print("deferral-gate: OUT OF SCOPE (no deferral-registry marker) —")
        for f in unmarked:
            rel = f.relative_to(REPO).as_posix()
            n = len(set(ID.findall(f.read_text(encoding="utf-8", errors="replace"))))
            print(f"  {rel:<52} {n:>4} ids, ungoverned")
        print("  Tracked: D-DEFERRAL-GATE-PLATFORM-SCOPE\n")

    if fails:
        print(f"deferral-gate: {len(fails)} problem(s)\n")
        for f in fails:
            print(f"  - {f}")
        return 1

    print(f"deferral-gate: OK — {len(mechanised)} of {len(mechanised) + len(prose)} "
          f"tracked deferrals carry a mechanism that changes colour by itself; the "
          f"remaining {len(prose)} each declare what would wake them up.")
    return 0


def self_test() -> int:
    fails = []

    # BITE 1 — the id predicate must not match hyphenated prose. This is not
    # hypothetical: the naive version reported `D-ONLY` 54 times (from
    # `READ-ONLY`) and `D-BEARING` 45 (from `LOAD-BEARING`).
    if ID.findall("this is LOAD-BEARING and READ-ONLY"):
        fails.append("ID matches inside hyphenated words — the scope is noise")
    if ID.findall("see D-GATE-ROT-RAW-SQL now") != ["D-GATE-ROT-RAW-SQL"]:
        fails.append("ID fails to match a real deferral id")

    # BITE 1b — the ENFORCED-SHAPE arm, which is what stops the two-segment
    # requirement from being a silent hole. A one-segment id inside a block must
    # FAIL LOUDLY rather than be skipped.
    with __import__("tempfile").TemporaryDirectory() as d:
        p = Path(d) / "SESSION_HANDOFF.md"
        p.write_text(f"{BEGIN} -->\n| `D-START` | 1 | x | y |\n{END} -->\n",
                     encoding="utf-8")
        if unparseable_ids(p) != {"D-START"}:
            fails.append("a one-segment id inside a block is neither parsed NOR "
                         "reported — the scope silently fails to reach it (NV-3)")
        p.write_text(f"{BEGIN} -->\n| `D-GATE-ROT-RAW-SQL` | 1 | x | y |\n{END} -->\n",
                     encoding="utf-8")
        if unparseable_ids(p):
            fails.append("a WELL-FORMED id is reported unparseable — the shape arm "
                         "would fail every registry and get switched off")

    # BITE 2 — the comment stripper is the whole discriminator, so prove it bites
    # BOTH ways: a comment must not count, and code on the same id must.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.rs"
        p.write_text("// TODO(D-BITE-TEST): fix later\nfn f() {}\n", encoding="utf-8")
        code = "\n".join(
            ln for ln in p.read_text(encoding="utf-8").splitlines()
            if not ln.lstrip().startswith("//"))
        if "D-BITE-TEST" in code:
            fails.append("comment stripper let a `// TODO(D-…)` through — every row "
                         "could then satisfy the gate by being mentioned")
        if "D-BITE-TEST" in _strip(p.read_text(encoding="utf-8"), "//"):
            fails.append("comment stripper let a `// TODO(D-…)` through — every row "
                         "could then satisfy the gate by being mentioned")
        p.write_text('const R: &str = "D-BITE-TEST";\n', encoding="utf-8")
        if "D-BITE-TEST" not in _strip(p.read_text(encoding="utf-8"), "//"):
            fails.append("comment stripper ate a real string literal — it would "
                         "report mechanised rows as prose-only, failing open")

    # BITE 2b — THE DOCSTRING ARM, and the reason it exists: the first version of
    # this gate stripped only LINE comments and certified two prose-only deferrals
    # as mechanised, because their sole mention in the tree was the module
    # docstring of `gate-wiring-gate.py`. A gate that reports coverage it does not
    # have is worse than no gate, so this arm is not optional.
    if "D-BITE-TEST" in _strip('"""prose about D-BITE-TEST"""\nx = 1\n', "#"):
        fails.append("a PYTHON DOCSTRING still counts as a mechanism — this is the "
                     "exact false-MECHANISED bug the stripper was rewritten to fix")
    if "D-BITE-TEST" in _strip("/**\n * JSDoc naming D-BITE-TEST\n */\nlet x;\n", "//"):
        fails.append("a JSDoc BLOCK still counts as a mechanism — three ws/ files "
                     "name their deferral exactly this way and none of them checks "
                     "anything")
    if "D-BITE-TEST" not in _strip('KNOWN = {"D-BITE-TEST": 1}\n', "#"):
        fails.append("the stripper ate a dict key — a real KNOWN_RED-style mechanism "
                     "would read as prose-only")

    # BITE 3 — the marker parser must actually bound the block. Without this the
    # gate would claim the whole 7,869-line handoff as its scope and drown.
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "SESSION_HANDOFF.md"
        p.write_text(f"D-OUTSIDE-ONE\n{BEGIN} -->\nD-INSIDE-ONE\n{END} -->\n"
                     "D-OUTSIDE-TWO\n", encoding="utf-8")
        got = marked_ids(p)
        if got != {"D-INSIDE-ONE"}:
            fails.append(f"marker parser returned {sorted(got)} — it is not bounding "
                         "the block, so `open` is unreliable and the gate is noise")

    # The scope must stay a walk. An enumerated file list is default-uncovered:
    # a track created tomorrow would be outside the gate and nobody would know.
    if len(_source_files()) < 100:
        fails.append(f"_source_files() returned {len(_source_files())} — the scope "
                     "has stopped reaching the tree")
    if not any(f.name == "SESSION_HANDOFF.md" for f in _registry_files()):
        fails.append("_registry_files() found no handoff — the registry scope is dead")

    # At least one marked block must exist, or the gate passes over an empty set
    # and reports OK forever. This is the NV-3 degenerate case: a check whose
    # scope never reaches anything is green by construction.
    mechanised, prose, _ = audit()
    if not (mechanised or prose):
        fails.append("no marked registry block found anywhere — the gate would "
                     "report OK over an empty scope, which is the vacuity it "
                     "exists to prevent")

    # This gate must itself be wired, or it is the thing it forbids.
    me = Path(__file__).name
    hook = (REPO / ".githooks" / "pre-commit").read_text(encoding="utf-8", errors="replace")
    ci = "\n".join(
        f.read_text(encoding="utf-8", errors="replace")
        for f in (REPO / ".github" / "workflows").glob("*.yml"))
    if me not in hook and me not in ci and "gate-wiring-gate.py --run-all" not in ci:
        fails.append(f"{me} runs nowhere")

    if fails:
        print("deferral-gate SELF-TEST FAILED:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("deferral-gate: self-test OK — the id predicate rejects hyphenated prose, "
          "the comment stripper bites both ways (a TODO is not a mechanism, a string "
          "literal is), the marker parser bounds the block, the scope is a walk, and "
          "the marked scope is non-empty.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
