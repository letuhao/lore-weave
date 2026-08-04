#!/usr/bin/env python3
"""actor-hub-figures — every number the actor-hub docs claim, MEASURED.

WHY THIS EXISTS
---------------
The stale-figure defect recurred **five times** in one round, each time inside
the commit that recorded the previous recurrence:

  D-343  the handoff block shipped in the feature commit carried four numbers
         that same commit superseded.
  D-350  the fix advanced 270 -> 279 while its own VERIFY line said 281.
  D-351  the next fix advanced 279 -> 281 while its own VERIFY line said 283.
  D-353  the row declaring the remedy *"every number is now derived by a script
         that reads the artifacts"* was written while **no such script existed**.
  D-359  the first version of THIS script then refused its own commit: the
         handoff said `D-353` while the run-state had reached `D-358`.

WHAT A REVIEW THEN FOUND IN THIS SCRIPT, AND WHAT CHANGED
---------------------------------------------------------
The first version measured **six** quantities and compared **two**, while the
documents claimed *"every figure in this block is emitted by this script, which
`--check`s them"*. **That is `D-353`'s defect one level up — a mechanism claimed
rather than verified — inside the mechanism written to end it.** It also:

  * crashed with a raw ``FileNotFoundError`` when ``cargo`` was absent, in a hook
    triggered by the **repo-wide** ``SESSION_HANDOFF.md`` — so a frontend or
    Python contributor on any of 47 services could not commit a handoff update;
  * passed **silently** when a marker string moved, reporting *"the docs agree"*
    against zero subjects;
  * had a RUN-STATE arm whose window contained **no** matching claim at all;
  * missed ``_index.md``, the file with the worst record for this exact defect
    (stale twice, `D-347` and `D-350`);
  * counted a FAILING ``cargo test`` as zero passes and then told the developer
    to rewrite the doc to match a broken build;
  * had no ``--self-test`` of its own, unlike both sibling gates;
  * and was named ``actor-hub-figures.py`` -- **which `gate-wiring-gate`'s
    filename predicate does not recognise**, so `--run-all` never executed it and
    the degradation message's promise *"CI checks it"* was FALSE. Renamed to
    ``-gate.py``, which is the shape that predicate keys on. A promise about
    another mechanism is a claim like any other.

Every one of those is fixed below, and each has a case in ``--self-test``.

    python scripts/actor-hub-figures-gate.py            # measure + check (the default)
    python scripts/actor-hub-figures-gate.py --print    # measurements only, never fails
    python scripts/actor-hub-figures-gate.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CRATES = ["actor-hub", "entity-existence", "ruleset-core", "game-rules", "ruleset-loader"]
# (path, measurement key). Keyed, not positional -- see `measure`.
CONTRACTS = [
    ("docs/specs/2026-08-02-actor-hub/2026-08-02-actor-hub.md", "contract_hub_lines"),
    ("docs/specs/2026-08-02-actor-hub/2026-08-02-engine-substrate.md", "contract_substrate_lines"),
    ("docs/specs/2026-08-02-actor-hub/2026-08-02-seams-and-triggers.md", "contract_seams_lines"),
]
SEAMS = "docs/specs/2026-08-02-actor-hub/2026-08-02-seams-and-triggers.md"

# Every document the LIVE-RANGE rule reads. A directory would be better still,
# but `docs/` is 2 000 files and this round's registers are the only ones whose
# head this gate can measure -- so the list is the set of documents that cite
# THIS round's decision record, and `--self-test` asserts none is missing by
# re-deriving it from the tree.
ESCAPE_DOCS = (
    "docs/specs/2026-08-02-actor-hub/2026-08-02-actor-hub.md",
    "docs/specs/2026-08-02-actor-hub/2026-08-02-engine-substrate.md",
    "docs/specs/2026-08-02-actor-hub/2026-08-02-seams-and-triggers.md",
    "docs/specs/2026-08-02-actor-hub/analysis/2026-08-02-actor-data-structure.md",
    "docs/specs/2026-08-02-actor-hub/analysis/2026-08-02-actor-dataflow.md",
    "docs/specs/2026-08-02-actor-hub/analysis/2026-08-02-feature-notes.md",
    "docs/specs/2026-08-02-actor-hub/analysis/2026-08-02-value-model-analysis.md",
    "docs/specs/2026-08-02-item-data-structure.md",
    "docs/specs/2026-08-02-item-dataflow.md",
    "docs/plans/2026-08-02-item-substrate-RUN-STATE.md",
)
RUN_STATE = "docs/plans/2026-08-02-actor-substrate-RUN-STATE.md"
HANDOFF = "docs/sessions/SESSION_HANDOFF.md"
INDEX = "docs/specs/2026-08-02-actor-hub/_index.md"

# The blocks whose figures are CURRENT-STATE claims. A decision record is
# supposed to contain the numbers that were true when it was written, so the
# scan is bounded to the block a session rewrites — see `D-358`, which is what
# the first version of this check got wrong in the other direction.
#
# `end` is a marker, not a character count. A fixed 4000-char window put the
# RUN-STATE arm's subjects OUTSIDE it, so half the check had nothing to compare.
# The END is an EXPLICIT SENTINEL, not the first horizontal rule.
#
# `\n---\n` was a boundary the documents did not know they had. Inserting a rule
# anywhere inside a block -- an utterly ordinary markdown edit -- silently
# truncated the scope, and the "resolved but empty" rule only caught TOTAL
# collapse: measured, a `---` in the middle of the handoff block left one claim
# behind, so `checked` stayed true and **three governed figures went silently
# ungoverned**. That is the worked example the rule was written from, still
# passing after the rule was written.
#
# A sentinel is deletable too -- but deleting it fails the both-markers check
# LOUDLY, which is the whole difference.
def END(block: str) -> str:
    """The end sentinel for one block, NAMED.

    A single shared sentinel made "exactly once in the file" meaningless the
    moment a second block wanted one: three legitimate markers, and the rule
    that exists to catch a stray duplicate fired on all three. Naming each
    block's marker keeps the rule file-wide and exact, and makes the message say
    WHICH block a stray copy belongs to.
    """
    return f"<!-- actor-hub-figures:end {block} -->"

# `must_claim` is what closes the LAST route to a silently shortened scope.
#
# The empty-block rule catches TOTAL collapse; moving the sentinel up by one
# paragraph leaves a claim behind, so `checked` stays true and everything below
# goes quietly ungoverned -- which is the defect the sentinel replaced, reached
# by a third road after the duplicate road and the incidental-`---` road were
# closed. Naming the figures a block MUST carry closes it by construction: the
# question stops being "did anything match" and becomes "did THESE match".
#
# It is an enumeration, and that is the point: adding a governed figure to a
# block means saying so here. Forgetting is a MISS, and the coverage arm still
# catches a shape claimed by no document anywhere.
SCOPES: tuple[tuple[str, str, str, frozenset[str]], ...] = (
    (HANDOFF, "## ▶ GAME TIER", END("game-tier"),
     frozenset({"rust_tests", "dp_kernel_lib_tests", "max_decision_id",
                "max_seam_id", "hook_gate_scripts"})),
    (RUN_STATE, "> # ▶▶ NEXT SESSION STARTS HERE", END("next-session"),
     frozenset({"rust_tests", "dp_kernel_lib_tests", "max_seam_id",
                "hook_gate_scripts", "contract_hub_lines",
                "contract_substrate_lines"})),
    # The SLICE BOARD's own summary block. A stop-audit found it STALE at
    # round seven -- "81 findings over five rounds" when the count was 123 over
    # seven -- because the check covered the header and the handoff and not the
    # board two screens below them. **A figure outside a checker's scope is a
    # figure nobody is reading**, which is `_index.md`'s defect one file along.
    (RUN_STATE, "### 6-BUILD", END("slice-board"),
     frozenset({"rust_tests", "dp_kernel_lib_tests"})),
    (INDEX, "# Actor Hub", END("index"),
     frozenset({"max_decision_id", "max_seam_id", "contract_hub_lines",
                "contract_substrate_lines", "contract_seams_lines",
                "contract_total_lines"})),
)


class Unmeasurable(Exception):
    """A figure that cannot be measured HERE — never a reason to block a commit."""


# A cold `cargo test` legitimately runs minutes; this is the hang bound, not a
# performance budget.
CARGO_TIMEOUT_S = 900


def _cargo_passed(args: list[str], run=None, which=None) -> int:
    """Passing tests, or `Unmeasurable` if the toolchain is absent or the build is red.

    **Never raises a bare OSError, and never reports 0 for a broken build.** The
    first version did both: no `cargo` gave a raw traceback inside a pre-commit
    hook that fires on the repo-wide handoff, and a failing suite summed to 0,
    after which the script told the developer *"do not advance the number"* —
    i.e. to rewrite the doc to match a broken build.
    """
    if (which or shutil.which)("cargo") is None:
        raise Unmeasurable("cargo is not on PATH")
    try:
        out = (run or (lambda a: subprocess.run(
            ["cargo", "test", *a], cwd=REPO, capture_output=True, text=True,
            timeout=CARGO_TIMEOUT_S)))(args)
    except subprocess.TimeoutExpired:
        # Unmeasurable, not a refusal: this hook fires on the repo-wide handoff
        # for all 47 services, and a cold cargo build that runs long must not
        # block a commit that never touched Rust.
        raise Unmeasurable(f"the test run did not finish within {CARGO_TIMEOUT_S}s")
    if "test result: FAILED" in out.stdout or out.returncode != 0:
        raise Unmeasurable("the test run is not green, so its count means nothing")
    return sum(int(m) for m in re.findall(r"test result: ok\. (\d+) passed", out.stdout))


def _max_id(path: str, prefix: str, read=None) -> int:
    text = read(path) if read else (REPO / path).read_text(encoding="utf-8", errors="replace")
    ids = [int(x) for x in re.findall(rf"\*\*{prefix}-(\d+)\*\*", text)]
    if not ids:
        raise Unmeasurable(f"no bold {prefix}- id in {path}")
    return max(ids)


def _hook_gate_scripts(read=None) -> int:
    """Distinct `scripts/*.py|sh` the pre-commit hook invokes, comments excluded."""
    text = read() if read else (REPO / ".githooks/pre-commit").read_text(
        encoding="utf-8", errors="replace")
    body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    return len(set(re.findall(r"scripts/([A-Za-z0-9_-]+\.(?:py|sh))", body)))


def measure(cargo=None) -> dict[str, object]:
    """`cargo` is injectable so `--self-test` can assert WHICH ARGUMENTS the
    measurements ask for, on a machine with no toolchain.

    Three production rules were RED with cargo present and GREEN without it --
    the FAILED-count parse, the crate list, and `dp-kernel`'s `--lib`. The only
    automatic runner of the mutation harness is CI, which has no Rust, so those
    three were covered nowhere. A rule whose coverage depends on the developer's
    machine is not covered.
    """
    passed = cargo or _cargo_passed
    out: dict[str, object] = {}
    for name, fn in (
        ("rust_tests", lambda: passed(sum([["-p", c] for c in CRATES], []))),
        ("dp_kernel_lib_tests", lambda: passed(["-p", "dp-kernel", "--lib"])),
        ("max_decision_id", lambda: _max_id(RUN_STATE, "D")),
        ("max_seam_id", lambda: _max_id(SEAMS, "S")),
        ("hook_gate_scripts", _hook_gate_scripts),
    ):
        try:
            out[name] = fn()
        except Unmeasurable as e:
            out[name] = {"unmeasurable": str(e)}
    # **Each contract measured under its OWN name.** The first version unpacked
    # a positional pair -- `hub, substrate = lines` -- OUTSIDE the try, so adding
    # a third contract raised `ValueError: too many values to unpack` as a raw
    # traceback inside a hook that fires on the repo-wide `SESSION_HANDOFF`:
    # `D-364`'s cargo crash again, one line along. The dict `contract_lines` was
    # also emitted and compared by nothing, which is `F5`'s defect surviving its
    # own fix.
    for path, key in CONTRACTS:
        try:
            # `errors="replace"`, and `Exception` rather than `OSError`: a
            # `UnicodeDecodeError` is a `ValueError`, so it escaped as a raw
            # traceback from a hook that fires on the repo-wide handoff -- the
            # third time this file has shipped that same class (the cargo crash,
            # the positional unpack, this).
            out[key] = len((REPO / path).read_text(
                encoding="utf-8", errors="replace").splitlines())
        except Exception as e:  # noqa: BLE001 - a measurement never blocks a commit
            out[key] = {"unmeasurable": f"{path}: {e}"}
    counts = [out[k] for _, k in CONTRACTS]
    out["contract_total_lines"] = (
        sum(counts) if all(isinstance(c, int) for c in counts)
        else {"unmeasurable": "a contract could not be read"})
    return out


# Every claim shape this script governs, and the measurement it must equal.
# **A claim shape with no subject anywhere is itself a finding** — see `_check`.
CLAIMS: tuple[tuple[str, str, str], ...] = (
    (r"\*\*(\d+) passed, 0 failed\*\*", "rust_tests", "passing tests"),
    # `(?: passed)?` because the slice board writes `**315 passed**` and the
    # header writes `**315**`. One word, and the figure was ungoverned in a
    # block whose headline says otherwise -- found by widening the bolded-figure
    # detector, not by reading.
    # The header block writes the Rust total as `**300 Rust tests**` and the
    # evidence lines write it as `**300 passed, 0 failed**`. Only the second
    # had a rule, so the first was ungoverned in a block whose headline says
    # otherwise -- found by widening the bolded-figure detector, not by
    # reading it.
    (r"\*\*(\d+) Rust tests\*\*", "rust_tests", "passing tests"),
    (r"`dp-kernel --lib` \*\*(\d+)(?: passed)?\*\*", "dp_kernel_lib_tests",
     "dp-kernel lib tests"),
    (r"`D-1`\.\.`D-(\d+)`", "max_decision_id", "the highest decision id"),
    # **`S-1`, not `S-11`.** The pattern used to require the SEGMENT this round
    # added -- `S-11`..`S-18` -- to equal the register's head, while `D-398`
    # certifies that same string as a fixed historical fact. Measured by seeding
    # `S-19`: two findings, on two sentences the decision record calls correct
    # and permanent. **Cry-wolf, armed and dated.** The register's own range is
    # first-id-anchored, so it tracks the head by construction, which is the
    # criterion -- and the two current-state blocks now state that instead.
    (r"`S-1`\.\.`S-(\d+)`", "max_seam_id", "the highest seam id"),
    # N3 -- a FIFTH stale figure inside `_index.md`'s governed block, on the row
    # this round rewrote: "ten measured seams" against 18, one column right of
    # the `66` that was corrected. It was spelled as a WORD, so no pattern could
    # reach it. `D-396`'s lesson repeating one cell over.
    (r"\*\*(\d+)\*\* measured seams", "max_seam_id", "the seam count, in the index table"),
    (r"the \*\*(\d+)\*\*\s*\n?gate scripts", "hook_gate_scripts", "hook gate scripts"),
    # There was a second, wider `\*\*(\d+)\*\* gate scripts` row here. It was
    # deletable with the suite green, and NOT because it lacked a case: its
    # pattern is a strict SUBSTRING of the row above, matching the same span of
    # the same sentence. The coverage arm cannot see an alias -- the pattern is
    # not dead, it is shadowed -- so the only remedy is not to write two rows
    # over one subject.
    # F5 — `contract_lines` was measured, printed as JSON and **never compared**,
    # while the block one line above it says "every figure above is emitted by
    # this script, which --checks them". Six measured, five compared, in the
    # commit whose message states the defect as "six measured, TWO compared".
    (r"the two contracts are \*\*(\d+)\*\* and", "contract_hub_lines", "the hub contract's lines"),
    # `>?` because the RUN-STATE header is written entirely as a blockquote, so
    # the wrap puts `> ` between "and" and the number. The coverage arm caught
    # this immediately: "NO DOCUMENT claims the substrate contract's lines".
    (r"and\s*\n?>?\s*\*\*(\d+)\*\*\s*\n?>?\s*lines", "contract_substrate_lines", "the substrate contract's lines"),
    # M1 -- the same three files, stated again as a TABLE inside `_index.md`'s
    # governed block, and every pattern above keys on PROSE. Measured: the block
    # said 172 / 142 / 50 and "364 lines total" while the files were 202 / 157 /
    # 66 -- **four stale figures inside the scope**, twenty lines from a prose
    # sentence stating two of the same numbers correctly, in the file this
    # script's own docstring calls "the file with the worst record for this exact
    # defect". A checker's scope is a claim; so is the SHAPE it recognises inside
    # that scope.
    (r"\(2026-08-02-actor-hub\.md\)\s*\|\s*(\d+)\s*\|", "contract_hub_lines",
     "the hub contract's lines, in the index table"),
    (r"\(2026-08-02-engine-substrate\.md\)\s*\|\s*(\d+)\s*\|", "contract_substrate_lines",
     "the substrate contract's lines, in the index table"),
    (r"\(2026-08-02-seams-and-triggers\.md\)\s*\|\s*(\d+)\s*\|", "contract_seams_lines",
     "the seams register's lines, in the index table"),
    (r"\*\*(\d+) lines total\.\*\*", "contract_total_lines", "the three contracts' total lines"),
)


# A bolded figure -- the shape this project states every measurement in.
# Anything matching it inside a governed block and read by no `CLAIMS` row is a
# figure nobody checks, which is the class three rounds found by hand.
#
# **The SHAPE was the shape of its own case.** The first version matched
# `**7**` and nothing else -- not `**7 widgets**`, not `**7.5**`, not
# `**7,000**` -- so narrowing it back to `\d+` survived every mutation. That is
# the same defect one level down: a checker's scope is a claim, and so is the
# shape it recognises inside that scope. Widened, it finds two ungoverned
# figures in the shipped blocks that the narrow form did not.
#
# A bolded YEAR (`**2026**`) is reported, deliberately. The block's own headline
# says every bolded figure in it is emitted by a checker; a bolded year is not,
# so the remedy is to unbold it. Exempting one would be an untested carve-out in
# the rule whose whole finding was an untested carve-out. A DATE
# (`**2026-08-03**`) does not match -- the hyphen ends the run.
#
# **And the WRAP tolerance its siblings already carry.** These documents wrap,
# and `contract_substrate_lines` in this same file carries `\s*\n?>?\s*` written
# for exactly that reason. Without it here, `**0\n> warnings**` -- the slice
# board's copy of the very claim a round-12 verifier measured FALSE, and which
# this round found and fixed one block over -- stayed invisible to the detector
# that had just been widened to catch it. Two decisions, each correct, the later
# one defeating the earlier: this file's own name for the class.
#
# **And it admitted ONE word.** `**315 passed**` matched; `**300 Rust tests**`
# did not -- a governed figure sitting in a governed block, invisible on BOTH
# arms, because the missing key is not compared and an unmatched shape is not
# surplus either.
#
# **And the bound was itself an enumeration.** `{0,3}` lasted one round: a
# planted `**999 Rust integration tests pass**` -- four words -- sat in the
# governed block with the gate silent and rc 0, which is `D-479`'s shape one
# word further along. Unbounded now, measured to add ZERO findings on all
# four shipped blocks. A bolded SENTENCE is excluded by SHAPE rather than by
# counting: any punctuation after the digits ends the run.
#
# **And the unbounded form was EXPONENTIAL.** Removing the bound left three
# star-quantified space runs inside one repeated group, so a run of words can
# be split many ways and every split is re-explored when the closing `**` never
# arrives. Measured: n=10 0.001s, n=20 0.89s on an unpaired `**`; 0.00s -> 6.64s
# on the real governed blocks; and this gate's whole `--self-test` at **189.5s**.
# It stayed GREEN throughout -- rc 0, every case passing -- because only the WALL
# CLOCK moved, and the one timing alarm the apparatus owns fires on the 300s hang
# bound. A 60x slowdown is invisible to a check that can only see a hang.
#
# THREE forms that LOOK unambiguous were measured and rejected. An alternation
# separator: still exponential -- a greedy `[ \t]+` gives its characters back.
# One disjoint character class per separator: still exponential -- an EMPTY
# separator lets `ab` be re-parsed as `a` + `b`. And a two-phase span/body split,
# whose SPAN half was **redundant** once the separator was mandatory -- measured,
# one regex is 0.9ms on a 5 000-word probe and finds the identical 94 figures in
# the whole run-state document. Its own bite test is what said so: the mutation
# restoring the old regex made the child exceed its 300s bound, and a HANG is not
# a failing case, so the half could not be guarded by anything meaningful. A
# comment here claimed *"linearity needs BOTH halves"* -- written, believed, and
# never measured, which is the finding directly above, one step later.
#
# So the whole repair is ONE token: the separator between two words is MANDATORY.
_FIGURE_WORD = r"[A-Za-z%][\w%-]*"
BOLD_INT_RE = re.compile(
    r"\*\*\d[\d,. \u00a0]*(?:[ \t\n>]*" + _FIGURE_WORD
    + r"(?:[ \t\n>]+" + _FIGURE_WORD + r")*)?\*\*")

# An italicised quotation, and an inline HTML comment. See `_claimable`.
QUOTE_RE = re.compile(r'\*"[^"]*"\*')
COMMENT_RE = re.compile(r"<!--.*?-->")


FENCE_RE = re.compile(r"^\s*(?:>\s*)*(?P<mark>`{3,}|~{3,})(?P<info>.*)$")


def _fence_mark(line: str) -> str | None:
    """The fence marker this line opens or closes with, or None.

    **A marker is not a toggle.** The first version counted every `` ``` `` as a
    flip, which broke five measured shapes -- and one of them is the standard
    markdown idiom for DOCUMENTING a fence, so it exposed the contents of a
    four-backtick block as live claims. That is the cry-wolf direction, in a gate
    wired to the repo-wide handoff.
    """
    m = FENCE_RE.match(line)
    if not m:
        return None
    # A BACKTICK fence's info string may not contain a backtick (CommonMark),
    # so a line carrying a second run of them is an INLINE code span, not a
    # fence. A TILDE fence has no such restriction -- applying the rule to both
    # meant `~~~ ~diagram~` was not recognised as a fence and its contents were
    # reported as live claims. Cry-wolf, on a shape the spec allows.
    if m.group("mark")[0] == "`" and "`" in m.group("info"):
        return None
    return m.group("mark")


def _advance(open_mark: str | None, line: str) -> tuple[str | None, bool]:
    """(fence state after `line`, whether `line` IS a fence marker).

    **One copy.** The open/close rule was written out twice -- once in
    `_fence_state` and once in `_claimable` -- so mutating either left the other
    satisfying every case. A duplicated rule is a rule with half a test, and the
    mutation harness found it the round after the duplication was introduced.
    """
    mark = _fence_mark(line)
    if mark is None:
        return open_mark, False
    if open_mark is None:
        return mark, True
    # A fence closes only on the SAME character, at least as long. A `~~~` inside
    # a ``` block is content, not a closer.
    # A CLOSER carries no info string (CommonMark). ```` **281 passed**` inside a
    # fenced block is CONTENT that happens to start with backticks, not a
    # closer -- and treating it as one exposed the rest of the block.
    if (mark[0] == open_mark[0] and len(mark) >= len(open_mark)
            and not (FENCE_RE.match(line).group("info") or "").strip()):
        return None, True
    return open_mark, True


# A fence marker rewritten so `_fence_mark` no longer recognises it. Same
# length is not required -- these lines are blanked either way -- but keeping the
# text visible makes a debug dump readable.
_MASK_FENCE = "<!-- fence -->"


def _unpaired_opener(lines: list[str]) -> int | None:
    """Index of a fence opener with no closer, or None if every one is paired."""
    open_mark, at = None, None
    for i, line in enumerate(lines):
        after, is_mark = _advance(open_mark, line)
        if is_mark and open_mark is None:
            at = i
        open_mark = after
    return at if open_mark is not None else None


def _fence_state(prefix: str) -> tuple[str | None, bool]:
    """(open fence marker, inside an HTML comment) at the END of `prefix`.

    **It tracks comments too, and that is not decoration.** The previous version
    scanned fences only, so ONE ```` ``` ```` line inside an HTML comment anywhere
    above a block flipped it into a fence that never closed. Both directions were
    measured on the real documents: a silently BLINDED slice board, and -- worse
    -- a refusal on `SESSION_HANDOFF` whose markers are perfectly fine, from the
    pre-commit hook that fires on it for every one of 47 services.

    The comment-before-fence ordering was fixed in `_claimable` and not here, so
    the two scanners disagreed about the same input. **A rule written twice is a
    rule with half a test**, which is the finding one round earlier, in this same
    pair of functions.
    """
    open_mark, in_comment = None, False
    for line in prefix.split("\n"):
        open_mark, in_comment, _ = _scan_line(open_mark, in_comment, line)
    return open_mark, in_comment


def _scan_line(open_mark: str | None, in_comment: bool, line: str
               ) -> tuple[str | None, bool, bool]:
    """(fence, comment, whether the line is NOT live prose) after `line`.

    The single scanner. `_fence_state` runs it over a document prefix to learn
    where a window starts; `_claimable` runs it over the window to blank what is
    not a claim. They used to be two loops that had to agree by inspection.
    """
    if in_comment:
        return open_mark, "-->" not in line, True
    after, is_mark = _advance(open_mark, line)
    if is_mark or after is not None:
        return after, False, True
    # An HTML comment that OPENS here and does not close on this line. Inline
    # `<!-- ... -->` spans are removed first, so what is left is either no
    # comment or an unterminated opening -- which is how a comment starting
    # mid-line is caught. The blanking of those inline spans is `_claimable`'s
    # job; the STATE is this function's, and it used to live only in
    # `_claimable`, so the prefix scan walked straight past an open comment.
    if "<!--" in COMMENT_RE.sub("", line):
        return after, True, True
    return after, False, False


def _claimable(block: str, quotes: bool = True, in_fence: str | None = None,
               in_comment: bool = False, comments: bool = True) -> str:
    """The block with everything that is NOT a live claim blanked out.

    **F6 — a quoted historical figure, a fenced example and an HTML comment each
    refused a commit.** These blocks are precisely where this project writes
    *"the handoff said X at round seven"*, and the board block does exactly that
    today. Blanking preserves offsets so nothing else shifts.

    **An UNQUOTED historical figure is treated as a live claim, deliberately.**
    Nothing distinguishes *"the handoff said 281"* from *"the count is 281"*
    except the quotation marks, so the gate requires them rather than guessing.
    Writing a past figure as `*"..."*` is what this project already does.

    Blockquote lines (`>`) are NOT blanked: the RUN-STATE header is written
    entirely as a blockquote, so blanking them would empty the scope — which the
    coverage assertion would then catch, but by making the gate useless rather
    than correct.
    """
    lines = block.split("\n")

    # **Fence state comes from the CALLER, computed over the document prefix.**
    #
    # `_scope_text` cuts its window at a marker, so a fence can straddle the
    # boundary and the window alone cannot say which side of one it starts on.
    # Two versions guessed, and both were measurably wrong:
    #
    #   * TOGGLING from False blanked EVERY REMAINING LINE after an unmatched
    #     opener -- a check whose scope stops reaching its subject halfway down.
    #   * PAIRING markers 0-1, 2-3 was worse in the closer/opener/closer shape:
    #     it blanks real prose AND exposes a genuine code block, where toggling
    #     did neither.
    #
    # There is nothing to guess. The prefix says what the state is; `_fence_state`
    # reads it, and inside the window a plain toggle is then exactly right --
    # including for a fence that genuinely continues past the window's end.
    # **An UNPAIRED opener inside the block is literal text.**
    #
    # `_marker_hits` already falls back to raw text when blanking hides every
    # marker; the same input hitting the CONTENT blanking had no such fallback,
    # so an unterminated fence blanked the rest of the block, `must_claim` fired,
    # and the commit was refused with a diagnosis naming a cause that was not the
    # cause -- "its end sentinel has probably moved UP" about a sentinel nobody
    # touched. The fix was applied to one of the two consumers of the same rule,
    # which is the defect this round exists to stop repeating.
    #
    # Not blanking a broken code sample can at worst report a figure inside it;
    # blanking refuses the commit. Cry-wolf is the severe direction.
    # **The scope is the OPENER ONWARD, not the whole text.** The first version
    # asked "is there an unpaired opener anywhere" and then masked EVERY fence
    # marker in the text, so one unterminated fence at the bottom of
    # `SESSION_HANDOFF` turned every correctly-paired code block above it into
    # live prose -- in all three consumers of this function at once. Measured:
    # three separate refusals on the shipped documents, one of them the very
    # "the end sentinel has probably moved UP" misdiagnosis this masking was
    # written to eliminate. A predicate about the document, an action about one
    # fence: the two-scopes defect, inside the fix for it.
    #
    # Lines BEFORE the opener are fully paired by construction -- that is what
    # makes the opener unpaired -- so they keep their fence semantics.
    unpaired_at = None if in_fence is not None else _unpaired_opener(lines)
    if unpaired_at is not None:
        lines = lines[:unpaired_at] + [
            _MASK_FENCE if _fence_mark(l) is not None else l
            for l in lines[unpaired_at:]]

    out, open_mark = [], in_fence
    for line in lines:
        stripped = line.lstrip()
        # **The comment state is tested FIRST**, inside `_scan_line`. It was
        # tested second, so a fence marker inside an HTML comment both flipped
        # the fence parity AND stopped `-->` from ever clearing the comment --
        # both flags stuck, and the rest of the block went permanently blind.
        # Two states, each correct alone, the ORDER between them defeating both.
        open_mark, in_comment, opaque = _scan_line(open_mark, in_comment, line)
        # `comments=False` keeps HTML comments visible: the scope SENTINEL is one,
        # so the marker search must still see it while fenced regions are blanked.
        if opaque and (comments or open_mark is not None or _fence_mark(line)):
            out.append(" " * len(line))
            continue
        # An HTML comment spans lines. `startswith("<!--")` blanked only the
        # OPENING line, so the figures inside a multi-line comment stayed live
        # claims -- and an INLINE `<!-- ... -->` mid-line was not blanked at all.
        # The inline `<!-- ... -->` spans, blanked in place. Whether the line
        # OPENS a multi-line comment is `_scan_line`'s answer, above.
        #
        # `comments=False` leaves them alone, because the scope SENTINEL is an
        # inline comment: the marker search needs fences blanked and comments
        # visible, and blanking both erased the very thing it was looking for.
        if comments:
            line = COMMENT_RE.sub(lambda mo: " " * len(mo.group(0)), line)
        # An ITALICISED QUOTATION -- *"..."* -- is this repo's syntax for text
        # written elsewhere, so a figure inside one is a historical record and
        # not a live claim.
        #
        # **A SYNTAX rule, not a content one.** The first version matched the
        # literal strings `said **` and `read it (*` -- the two phrasings that
        # happened to be in the corpus that afternoon. That blanks a REAL claim
        # the day someone writes "the spec said **283 passed**" and misses a
        # quotation the day they write "reported". Offsets are preserved either
        # way, so line numbers stay valid.
        out.append(QUOTE_RE.sub(lambda mo: " " * len(mo.group(0)), line) if quotes else line)
    return "\n".join(out)


def _unpaired_note(text: str) -> str:
    """The clause naming an unterminated fence, or "" when there is none.

    A marker finding produced in a document carrying an unterminated fence is
    almost never about the marker: the fence changes what is literal below it,
    so the sentinel the reader is being sent to look at is fine. Naming the real
    cause is the difference between an actionable refusal and one that points at
    the wrong file -- which is the whole complaint against the version of the
    masking this replaces.
    """
    at = _unpaired_opener(text.split(chr(10)))
    if at is None:
        return ""
    return (f" — NOTE: an unterminated code fence opens at line {at + 1} of this "
            "document; everything below it is literal text, which is the likely "
            "cause here rather than the marker")


def _scope_span(text: str, start_marker: str, end_marker: str
                ) -> tuple[int, int] | str | None:
    """The block's span, `None` if an anchor is missing, or a REASON string.

    **A sentinel fixed the wrong half of the problem.** Deleting the end marker
    was never the defect -- terminating EARLY was, and a second marker does that
    exactly as the first incidental `---` did. Measured on the shipped handoff:
    one extra sentinel mid-block takes the scope from **5 governed figures to 1**,
    and four seeded-stale figures below it produce **zero** findings where the
    control produces four.

    Two rules, because there were two ways in:

      * the end marker must occur **exactly once** after the start -- a second
        one is a finding, not a shorter block;
      * it is only a terminator on a line **of its own**. `_scope_span` reads raw
        text, so writing the marker inside a fenced example or an inline code
        span -- the normal way to DOCUMENT a marker, and what this gate's own
        decision record does -- silently truncated the scope.
    """
    # **The START marker gets the same two rules.** It had NEITHER: a raw
    # `find`, so documenting `### 6-BUILD` in an inline code span moved the block
    # 260 lines up, and the contributor was then told the END marker was
    # duplicated -- cry-wolf and a misdiagnosis pointing at the wrong file. The
    # end marker was hardened and the start marker was not, which is this round's
    # whole shape in one line.
    starts = _marker_hits(text, start_marker, 0)
    if not starts:
        return None
    if len(starts) > 1:
        lines = [text.count(chr(10), 0, k) + 1 for k in starts]
        return (f"the start marker `{start_marker.strip()}` occurs {len(starts)} "
                f"times (lines {lines}) — the FIRST one wins, so the block may "
                "not be the one you are looking at" + _unpaired_note(text))
    i = starts[0]
    # The marker is matched on its own line, so a leading newline in the literal
    # is noise -- it would put the match at the END of the previous line and the
    # standalone test would compare against that line instead.
    # **Fenced examples do not count.** `_claimable` blanks fenced regions and
    # preserves offsets, so searching its output means the decision record can
    # SHOW a marker in a code block without terminating anything -- which it
    # must, because this gate's own record documents these markers. Comments are
    # deliberately left intact: the sentinel IS one.
    hits = _marker_hits(text, end_marker, i + len(start_marker))
    if not hits:
        return None
    if len(hits) > 1:
        lines = [text.count("\n", 0, k) + 1 for k in hits]
        return (f"the end marker `{end_marker.strip()}` occurs {len(hits)} times after "
                f"`{start_marker}` (lines {lines}) — the FIRST one wins, so every "
                "figure below it is silently ungoverned" + _unpaired_note(text))
    return (i, hits[0])


def _escape_corpus() -> list[Path]:
    """Every markdown file the escape derivation examines."""
    return sorted(REPO.glob("docs/**/*.md"))


def _escape_derivation(governed: set[str], head: int, corpus=None) -> list[str]:
    """Documents citing `D-1`..`D-<head>` that no rule reads.

    **It asks the question the RULE asks.** An earlier version asked whether a
    document cited *a* range at all, and other rounds keep their own `D-`
    registers, so it reported ten documents whose numbering has nothing to do
    with this one. The rule fires only on numeric EQUALITY with this document's
    head, so the completeness check must use the same test.

    `corpus` is injectable because in a pristine tree the answer is the empty
    list, so an assertion on it alone is default-satisfied -- which is how both
    narrowing the glob and deleting the report survived.
    """
    out = []
    for path in (corpus or _escape_corpus)():
        try:
            rel = path.relative_to(REPO).as_posix()
        except ValueError:
            rel = path.name
        if rel in governed:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(int(m) == head for m in RANGE_RE.findall(text)):
            out.append(rel)
    return out


INDENT_CODE = re.compile(r"^(?: {4}|\t)")


def _indented_blanked(text: str) -> str:
    """`text` with 4-space/tab indented lines blanked, offsets preserved.

    Markdown has two literal forms and this file handled one. A marker shown in
    an indented block is a MENTION exactly as a fenced one is; treating it as a
    terminator refused a commit for documenting the marker.

    A line inside a list item is also indented, so this is deliberately narrow:
    it only ever REMOVES candidate markers, and `_marker_hits` falls back to raw
    text when that removes them all.
    """
    return chr(10).join(
        " " * len(l) if INDENT_CODE.match(l) else l for l in text.split(chr(10)))


def _marker_hits(text: str, marker: str, start: int) -> list[int]:
    """Offsets where `marker` is a real marker, not a mention.

    Two filters and a fallback:

      * **fence-blanked first**, so the decision record can SHOW a marker in a
        code block without terminating anything -- which it must, since this
        gate's own record documents these markers;
      * **line-start**, so a marker written in prose or an inline code span is a
        mention;
      * **and a RAW fallback when blanking finds none.** An UNTERMINATED fence
        inside a block blanks everything after it including the end marker, and
        the block then stops resolving -- a refusal on malformed-but-harmless
        markdown, which is the cry-wolf direction. Falling back means the worst
        case is the behaviour that existed before fences were considered.
    """
    needle = marker.strip(chr(10))
    # An INDENTED (4-space) code block is markdown's OTHER literal form. Fenced
    # examples were excluded and indented ones were not, so showing the sentinel
    # indented -- which is how a plain-text example is written -- reported it as
    # a duplicate and refused the commit. One literal form handled, its twin not.
    for haystack in (_indented_blanked(_claimable(text, quotes=False, comments=False)),
                     text):
        hits = [k for k in _all_occurrences(haystack, needle, start)
                if _at_line_start(haystack, k, needle)]
        if hits:
            return hits
    return []


def _all_occurrences(text: str, needle: str, start: int) -> list[int]:
    out, at = [], start
    while True:
        at = text.find(needle, at)
        if at < 0:
            return out
        out.append(at)
        at += 1


QUOTE_PREFIX = re.compile(r"^[ \t>]*")


def _at_line_start(text: str, at: int, needle: str) -> bool:
    r"""True when `needle` BEGINS its line, past any blockquote/indent prefix.

    **One rule, applied to BOTH markers.** The end marker had it and the start
    marker had a raw `find`, so documenting `### 6-BUILD` in an inline code span
    moved the block 260 lines up -- and the message then blamed the END marker,
    pointing the reader at the wrong file. Hardening one and not the other is
    this round's shape in a single line.

    **Line-start, not whole-line**: two markers are structural PREFIXES -- a
    heading carries its title (`## GAME TIER — feature #1 is BUILT`) and a table
    header continues -- so requiring the line to hold nothing else refuses every
    real document, which is the cry-wolf direction.

    **`>` is not whitespace**, and the RUN-STATE's governed block is a blockquote
    from end to end, so the sentinel written where it belongs -- inside the quote
    -- was not recognised. `FENCE_RE` in this same file already tolerates
    `(?:>\s*)*`; this did not, and nothing had tried it yet.

    A marker shown inside a FENCED example is handled by the caller, which
    searches fence-blanked text rather than by a rule here.
    """
    bol = text.rfind(chr(10), 0, at) + 1
    return not QUOTE_PREFIX.sub("", text[bol:at]).strip()


HEADING_RE = re.compile(r"^[ \t>]*#{1,6}[ \t]")
# A table row STARTS A REGISTER. This project writes current state in prose and
# history in a table -- the slice board below `### 6-BUILD`'s sentinel records
# what each slice measured at ITS close -- so a figure in a table below the
# sentinel is a historical record, not an orphan. Ending the tail at the heading
# alone reported two of them, which is cry-wolf on the correct document.
TAIL_END_RE = re.compile(r"^[ \t>]*(?:#{1,6}[ \t]|\|)")


def _orphaned_tail(text: str, span: tuple[int, int], end_marker: str) -> tuple[int, int]:
    """The span between the end sentinel and the next heading.

    **The `must_claim` surplus could not close this and the record said it did.**
    That check is keyed by measurement KEY: a SECOND occurrence of a key the set
    already names produces no surplus, and the missing-arm is satisfied by the
    first occurrence — so moving the sentinel above a repeated figure was still
    zero findings, for every key in every block, because every key is already in
    its set. Measured as a reproduction of the finding it was recorded closing.

    So the rule is positional instead. A sentinel closes a stretch of prose; the
    next heading starts the next one. Text in between is inside a governed
    section with nothing reading it, which is the shape a sentinel move creates
    and the only shape it creates. Any heading level ends it — using
    same-or-shallower would make `# Actor Hub`'s tail the rest of the file.
    """
    eol = text.find(chr(10), span[1] + len(end_marker.strip(chr(10))))
    if eol < 0:
        return (len(text), len(text))
    start = at = eol + 1
    for line in text[start:].split(chr(10)):
        if TAIL_END_RE.match(line):
            break
        at += len(line) + 1
    return (start, min(at, len(text)))


SENTINEL_RE = re.compile(r"^<!-- actor-hub-figures:end [a-z0-9-]+ -->$")


def _unsentinelled(scopes) -> list[str]:
    """Scopes whose end anchor is not a NAMED `:end <block>` sentinel.

    Extracted from the assertion so a case can drive it with a scope that
    violates it. Inline, the assertion could be weakened to `startswith("<!--")`
    -- which accepts any HTML comment, and "NAMED" is the whole point -- with
    the suite green, because the only case reverted the DATA to a heading and a
    heading fails either form. A rule tested only through data it happens to
    have is a rule with half a test.
    """
    return [f"{sc[0]} @ {sc[1]}" for sc in scopes if not SENTINEL_RE.match(sc[2])]


def _read_doc(doc: str, read=None) -> str | None:
    try:
        return read(doc) if read else (REPO / doc).read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return None


def _scope_text(doc: str, start_marker: str, end_marker: str, read=None) -> str | None:
    """The current-state block, or None if its anchor has moved.

    `read` is injectable so `--self-test` can drive this and `_check` for real
    instead of reimplementing their logic — the defect that let twelve
    production rules be deleted with the self-test green.
    """
    text = _read_doc(doc, read=read)
    if text is None:
        return None
    span = _scope_span(text, start_marker, end_marker)
    return None if not isinstance(span, tuple) else text[span[0]:span[1]]


# `\s*\n?>?\s*` because these documents WRAP, and the sibling
# `contract_substrate_lines` pattern already carries that tolerance for exactly
# this reason -- a live range split over a line break escaped the first version
# entirely. Two decisions, each correct, the later one defeating the earlier.
#
# **WHY ONLY THE `D-` RANGE, stated as a criterion rather than an instinct.**
# The first version said "not generalised to the other claim shapes on purpose"
# and argued only about `**283 passed**` -- which a review correctly called the
# wrong argument, because `S-11`..`S-N` looks exactly like a moving pointer too.
#
# It is not, and the distinguishing property is the FIRST id. `D-1`..`D-N` runs
# from the record's first entry, so it names the WHOLE record and therefore
# tracks its head by construction. `S-11`..`S-18` runs from an interior id: it
# names a SEGMENT -- the seams THIS ROUND added -- which is a fixed historical
# fact that stays true when `S-19` lands.
#
# Measured, not argued: adding `S-11`..`S-N` to this table produces exactly ONE
# finding across the three governed documents, and it is `B10`'s slice row
# recording what that slice produced. **Cry-wolf on a correct statement** -- the
# failure mode this gate has committed four times. So the rule is: a range
# anchored at the record's FIRST id.
def _range_re(prefix: str, first: int) -> "re.Pattern[str]":
    # **The backticks are OPTIONAL.** This project writes the range both ways,
    # and the un-backticked form occurs seven times in the RUN-STATE alone --
    # every one invisible to the rule AND to the coverage assertion, which
    # shares this regex and so could never report a form the rule misses. A
    # checker and its own completeness check keyed on one pattern are one
    # claim wearing two hats.
    t = "`?"
    return re.compile(
        rf"{t}{prefix}-{first}{t}" + r"\s*\n?>?\s*\.\.\s*\n?>?\s*"
        + rf"{t}{prefix}-" + r"(\d+)" + rf"{t}")


RANGE_RE = _range_re("D", 1)
RANGES = (("`D-1`..`D-N`", RANGE_RE, "max_decision_id"),)


def _escaped_live_range(m: dict[str, object], scopes=None, read=None) -> list[str]:
    """`D-1`..`D-<head>` written OUTSIDE a current-state block.

    **This is the one defect four rounds of this gate could not see, because it
    lives in exactly the region the gate was scoped OUT of.** `D-358` bounded the
    figure check to the two current-state blocks so that a decision row could
    keep the number that was true when it was written. Correct — and it left the
    rest of the document unguarded, so a blanket find-and-replace of
    `` `D-1`..`D-N` `` rewrote **six** historical statements to the live head:

      * `D-195` quotes another document — the item RUN-STATE — which says
        `D-109` in every commit it has ever had. The replace made this document
        attribute a sentence to it that it does not contain.
      * `D-196`'s next clause is *"The 85 it has not seen"*, and 194-109 = 85.
        The replace moved the number and left the arithmetic behind.
      * `D-358`'s worked EXAMPLE — inside the row whose entire subject is this
        gate crying wolf on correct historical statements.

    The range is a moving pointer at this document's own head, so a row that
    states it is stale the moment the next decision lands. Two places may hold
    the live value: the header and the handoff, both of which a session rewrites.
    Everywhere else, write the range that was TRUE.

    Not generalised to the other claim shapes on purpose. `**283 passed**` in a
    historical row is a coincidence of value, not a pointer — and `D-351` says
    *"its own VERIFY line said 283"* about a different day.
    """
    scopes = SCOPES if scopes is None else scopes
    problems: list[str] = []
    # **Every governed document, not the three with a current-state block.**
    #
    # The span fix was correct and its REACH was not: the rule read only the
    # three files in `SCOPES`. Replaying the original blanket replace file by
    # file across `docs/` measured eight more that carry the range and stayed
    # GREEN -- among them `2026-08-02-actor-hub.md` and
    # `2026-08-02-seams-and-triggers.md`, **files this same gate already opens**
    # to measure `contract_hub_lines` and `max_seam_id`. Three was not the
    # universe; it was an enumerated list, which is NV-3.
    #
    # The docstring's own sentence is repo-wide -- *"Everywhere else, write the
    # range that was TRUE"* -- so the scope now matches the rule. Cry-wolf risk
    # is near zero by construction: it fires only on numeric EQUALITY with this
    # document's head, and no other register in the tree is near it.
    docs = sorted({sc[0] for sc in scopes} | (set(ESCAPE_DOCS) if scopes is SCOPES else set()))
    for doc in docs:
        text = _read_doc(doc, read=read)
        if text is None:
            continue
        # **SPANS, not substrings.** The first version asked whether the matched
        # text appeared ANYWHERE inside a current-state block:
        #
        #     if any(mo.group(0) in b for b in blocks): continue
        #
        # Two of the three governed documents legitimately carry the live range
        # inside their block -- which is the design -- so that string test
        # exempted every OTHER occurrence in those same files. Measured: replaying
        # the original blanket replace against `_index.md` alone, including the
        # very line this mechanism was written to repair, left the gate GREEN.
        # A guard defeated by the thing it is guarding.
        spans = [sp for sc in scopes if sc[0] == doc
                 for sp in [_scope_span(text, sc[1], sc[2])] if isinstance(sp, tuple)]
        # Fenced examples and HTML comments are blanked -- a code block
        # SHOWING the header line is not a claim, and reporting it would be the
        # cry-wolf failure this gate has hit four times.
        #
        # **Quotations are NOT blanked, and that is deliberate.** Everywhere else
        # in this file `*"..."*` marks a historical record; here it is the exact
        # costume the defect wore. `D-195` presented the live head inside what
        # read as a quotation of another document, and that is *why* nobody
        # checked the number -- a quotation is supposed to be frozen. A quotation
        # containing this document's own moving head is either fabricated or
        # already stale.
        scan = _claimable(text, quotes=False)
        for label, pattern, key in RANGES:
            head = m.get(key)
            # A dict never equals an int, so this is not a guard that changes an
            # outcome -- it is the early exit that says so. Without a measurable
            # head there is nothing to compare against.
            if not isinstance(head, int):
                continue
            for mo in pattern.finditer(scan):
                if int(mo.group(1)) != head:
                    continue
                if any(a <= mo.start() < b for a, b in spans):
                    continue
                line = scan.count("\n", 0, mo.start()) + 1
                problems.append(
                    f"{doc}:{line}: {label} is the LIVE range, written outside "
                    "every current-state block. A row states the range that was "
                    "true WHEN IT WAS WRITTEN; only the header and the handoff "
                    "track the head. If this is a quotation, quote what the "
                    "other document says."
                )
    return problems


def _check(m: dict[str, object], scopes=None, read=None) -> tuple[list[str], list[str]]:
    """(blocking problems, non-blocking notes)."""
    problems: list[str] = []
    notes: list[str] = []
    seen: set[str] = set()
    # Keyed by (document, START MARKER), because `RUN_STATE` appears twice.
    # A per-document key let the header block vouch for the slice board, so
    # collapsing the board -- the block added *because* a stop-audit found a
    # stale figure outside every checker's scope -- was invisible.
    present: dict[tuple[str, str], set[str]] = {}
    claim_spans: dict[tuple[str, str], list[tuple[int, int]]] = {}
    # **NV-1 DISCLOSURE — the comment half cannot vary today.** `_unsentinelled`
    # requires every scope to end on a line matching `SENTINEL_RE`, which ends
    # ` -->`, and `_scan_line` closes any open comment on a line containing
    # `-->`. So `full[:a]` -- which always ends on the end-marker line -- can
    # never leave a comment open, on any conforming document. Measured: 0 of 11
    # prefix shapes. **Two individually-correct decisions, the first defeating
    # the second**, which is this file's own name for the class.
    #
    # It is kept, and its mutation row is NOT, because a row would certify
    # coverage that does not exist -- the defect four rounds running. The fence
    # half IS live and IS cased. If the sentinel rule ever changes, this is
    # already correct rather than a second bug to find.
    #
    # (text, open fence, open comment) -- **BOTH halves of the prefix state.**
    # The first version took `_fence_state(...)[0]` and dropped the comment,
    # two lines below the call that passes both for the block. An HTML comment
    # opening in the block and closing in the tail therefore left the tail
    # reading as live prose, and a figure inside it refused the commit: the
    # cry-wolf direction, from the hook that fires repo-wide, in the rule added
    # to close a hole. One half carried, its twin dropped.
    tails: dict[tuple[str, str], tuple[str, str | None, bool]] = {}
    blanks: dict[tuple[str, str], str] = {}
    scopes = scopes if scopes is not None else SCOPES

    for doc, start_marker, end_marker, *rest in scopes:
        block = _scope_text(doc, start_marker, end_marker, read=read)
        # The fence state at the window's start, read from everything before it.
        # The first version defined `_fence_state`, added the parameter, and
        # never passed it -- so the fix was inert and its case was satisfied by
        # a coincidence: the same NUMBER of findings, about different lines.
        full = _read_doc(doc, read=read)
        span = _scope_span(full, start_marker, end_marker) if full is not None else None
        if isinstance(span, str):
            problems.append(f"{doc}: {span}")
            span = None
        opens_fenced, opens_commented = (
            _fence_state(full[:span[0]]) if (full is not None and span) else (None, False))
        # `(None, False)`, not `(False, False)`: the fence half is a marker
        # string, and a bool would raise `TypeError: 'bool' object is not
        # subscriptable` inside a pre-commit hook the first time it was reached.
        if block is None:
            # **A moved anchor is a FINDING, not a silent pass.** The first
            # version set the text to "" and reported "the docs agree" against
            # zero subjects — a check whose scope never reaches it (NV-3).
            problems.append(
                f"{doc}: the markers `{start_marker}` .. `{end_marker}` do not both "
                "resolve, so this document was NOT checked"
            )
            continue
        if span:
            a, b = _orphaned_tail(full, span, end_marker)
            tails[(doc, start_marker)] = (full[a:b], *_fence_state(full[:a]))
        block = _claimable(block, in_fence=opens_fenced, in_comment=opens_commented)
        present[(doc, start_marker)] = set()
        claim_spans[(doc, start_marker)] = []
        blanks[(doc, start_marker)] = block
        for pattern, key, label in CLAIMS:
            want = m.get(key)
            for mo in re.finditer(pattern, block):
                claim_spans[(doc, start_marker)].append(mo.span())
            for claimed in re.findall(pattern, block):
                present[(doc, start_marker)].add(key)
                # Keyed on the PATTERN, not the key: two rows share
                # `hook_gate_scripts`, so a dead pattern with a live sibling was
                # invisible to the coverage arm written to catch exactly that.
                seen.add(pattern)
                if isinstance(want, dict):
                    # **A figure this MACHINE cannot measure is a SKIP, not a
                    # block.** The hook fires on the repo-wide `SESSION_HANDOFF`,
                    # which this project's SESSION phase mandates updating on
                    # essentially every commit across 47 services — so refusing
                    # a commit because the contributor has no Rust toolchain is
                    # the cry-wolf failure this round spent four rounds learning,
                    # aimed at people who never touched the actor hub.
                    #
                    # CI has the toolchain and enforces there. Every sibling gate
                    # in this repo degrades the same way, with a printed reason.
                    notes.append(
                        f"{doc}: claims {claimed} for {label} — NOT CHECKED here "
                        f"({want['unmeasurable']}); CI checks it"
                    )
                elif int(claimed) != want:
                    problems.append(
                        f"{doc}: claims {claimed} for {label}, measured {want}"
                    )

    # **A block that resolves but carries no governed claim is a finding.**
    # The end marker is the first `\n---\n`; inserting a horizontal rule inside
    # the block silently truncates it, and the gate then reports "every governed
    # figure agrees" against whatever survived. Measured: a stale figure with a
    # `---` above it produced ZERO findings. `--self-test` asserted this for the
    # real documents; production did not, so it held only at the moment someone
    # ran the self-test.
    # **The set must be EXACT, not a lower bound.** `must_claim` is an
    # enumeration and its sibling enumeration in this same file (`ESCAPE_DOCS`)
    # is re-derived from the tree; this one was not, so emptying any scope's set
    # left the suite green -- and a governed figure ADDED to a block was never
    # named, which is what leaves a block's tail unprotected when the sentinel
    # later moves above it. Reporting the surplus closes both: the day a figure
    # appears, the set is told to grow.
    for doc, start_marker, _e, *rest in (scopes if scopes is SCOPES else ()):
        want = rest[0] if rest else frozenset()
        surplus = sorted(present.get((doc, start_marker), set()) - want)
        if surplus:
            problems.append(
                f"{doc}: the block at `{start_marker}` now states {surplus}, which "
                "its `must_claim` set does not name — add them, or a later sentinel "
                "move will orphan them silently"
            )

    # **The figures each block MUST carry.** Moving the sentinel up by one
    # paragraph leaves a claim behind, so the empty-block rule -- which catches
    # only TOTAL collapse -- stays silent while everything below goes ungoverned.
    # Asking "did THESE match" instead of "did anything match" closes that.
    for doc, start_marker, _e, *rest in (scopes if scopes is SCOPES else ()):
        missing = sorted((rest[0] if rest else frozenset()) - present.get((doc, start_marker), set()))
        if missing:
            problems.append(
                f"{doc}: the block at `{start_marker}` no longer states {missing} — "
                "its end sentinel has probably moved UP, which shortens the scope "
                "silently instead of reporting anything"
            )

    # REMOVED: a "the block contains no governed figure at all" rule. Every real
    # scope now declares the figures it MUST state, and `must_claim` reports the
    # missing ones by name -- so the older rule could no longer produce a finding
    # the new one does not, and a mutation deleting it stayed green. Superseded,
    # not forgotten: the message it used to print is strictly less informative
    # than "no longer states ['dp_kernel_lib_tests', ...]".

    # **The prose between the sentinel and the next heading.** See
    # `_orphaned_tail`: it is the region a sentinel move creates, and the only
    # region it creates, so it is where a moved sentinel's orphans land.
    for (doc, start_marker), (tail, opens, commented) in tails.items():
        for pattern, key, label in CLAIMS:
            for mo in re.finditer(
                    pattern, _claimable(tail, in_fence=opens, in_comment=commented)):
                line = tail.count(chr(10), 0, mo.start()) + 1
                problems.append(
                    f"{doc}: `{mo.group(0)[:40]}` states {label} BELOW the end "
                    f"sentinel of the block at `{start_marker}` (line {line} of the "
                    "tail) and above the next heading or table — the sentinel "
                    "closes its "
                    "prose, so either move it down or move the figure in"
                )

    # **A bolded integer inside a governed block that NO rule reads.** Three
    # separate rounds found one of these by hand -- the last was fixed by
    # DELETING the figures, which is an instance fix with no detector. The block
    # is `_claimable`-blanked first, so a quoted or fenced number is not a claim.
    for (doc, start_marker), spans in claim_spans.items():
        text = blanks.get((doc, start_marker), "")
        for mo in BOLD_INT_RE.finditer(text):
            if any(a <= mo.start() < b for a, b in spans):
                continue
            line = text.count(chr(10), 0, mo.start()) + 1
            problems.append(
                f"{doc}: `{mo.group(0)}` inside the block at `{start_marker}` "
                f"(line {line} of the block) is read by no rule here — govern it "
                "or stop stating it, because this block claims every figure in it "
                "is checked"
            )

    problems += _escaped_live_range(m, scopes=scopes, read=read)

    # A claim shape that matches NOTHING anywhere is a rule with no subject.
    # Half of the first version's check was exactly this and nobody noticed,
    # because a vacuous arm and a passing arm look identical from outside.
    for pattern, key, label in CLAIMS:
        # No measurability guard. `seen` records what the DOCUMENTS contain, and
        # whether this machine has a Rust toolchain has nothing to do with
        # whether a document makes the claim. The guard it replaces could only
        # fire when a claim was BOTH absent from every document AND unmeasurable
        # here -- and in that case the coverage gap is real and worth reporting.
        # It was deletable with the suite green because it had no subject.
        if pattern not in seen:
            problems.append(
                f"NO DOCUMENT claims {label}: this arm of the check has no subject "
                "and proves nothing (docs/standards/non-vacuity.md, NV-3)"
            )
    return problems, notes


def self_test() -> int:
    """Every rule against input that violates it AND input that must not trip it.

    **It drives `_check` and `main` — the REAL functions.** The first version
    reimplemented the matching loop inline, so it tested a copy of the code: a
    review deleted twelve production rules one at a time, `main()`'s
    `if problems:` among them, and this self-test stayed **green for all twelve**.
    A self-test that does not call the thing it tests is the purest form of the
    defect this whole file exists to prevent.
    """
    failures = 0
    m = {"rust_tests": 283, "dp_kernel_lib_tests": 315, "max_decision_id": 372,
         "max_seam_id": 18, "hook_gate_scripts": 38,
         "contract_hub_lines": 202, "contract_substrate_lines": 157,
         "contract_seams_lines": 66, "contract_total_lines": 425}

    def check_block(name: str, text: str, expect_problems: int, expect_notes: int = 0) -> None:
        """Drive the REAL `_check` over one synthetic document."""
        nonlocal failures
        try:
            problems, notes = _check(m, scopes=(("<probe>", "@@START", "@@END"),),
                                     read=lambda _: f"@@START\n{text}\n@@END")
        except Exception as e:  # noqa: BLE001 - see `guard`
            failures += 1
            print(f"  FAIL {name}: _check raised {type(e).__name__}: {e}")
            return
        # The coverage arm reports every claim shape with no subject anywhere;
        # a single-block probe cannot carry them all, so they are filtered out
        # and covered by their own case below.
        real = [x for x in problems if not x.startswith("NO DOCUMENT")]
        ok = len(real) == expect_problems and len(notes) == expect_notes
        failures += 0 if ok else 1
        detail = f"expected {expect_problems}p/{expect_notes}n, got {len(real)}p/{len(notes)}n"
        print(f"  {'ok ' if ok else 'FAIL'} {name}: {detail}")
        if not ok:
            for x in real + notes:
                print(f"        {x}")

    def check_doc(name: str, doc: str, expect_problems: int) -> None:
        """Drive `_check` over a whole synthetic DOCUMENT, tail included."""
        nonlocal failures
        try:
            problems, _notes = _check(m, scopes=(("<probe>", "@@START", "@@END"),),
                                      read=lambda _: doc)
        except Exception as e:  # noqa: BLE001 - see `guard`
            failures += 1
            print(f"  FAIL {name}: _check raised {type(e).__name__}: {e}")
            return
        real = [x for x in problems if not x.startswith("NO DOCUMENT")]
        ok = len(real) == expect_problems
        failures += 0 if ok else 1
        print(f"  {'ok ' if ok else 'FAIL'} {name}: expected {expect_problems}, "
              f"got {len(real)}")
        if not ok:
            for x in real:
                print(f"        {x}")

    # **The prose BELOW the sentinel and above the next heading.** The
    # `must_claim` surplus was recorded as closing this and does not: it is keyed
    # by measurement KEY, so a SECOND occurrence of a key the set already names
    # is not surplus and the missing-arm is already satisfied by the first. Every
    # key in every block is in its set, so the hole was open for all of them --
    # measured as an exact reproduction of the finding it was recorded closing.
    check_doc("a stale figure below the sentinel is caught",
              "@@START\n**283 passed, 0 failed**\n@@END\n"
              "the suite ran **11 passed, 0 failed** today\n\n## Next", 1)
    check_doc("...a CORRECT one below it is caught too — it is ungoverned either way",
              "@@START\n**283 passed, 0 failed**\n@@END\n"
              "the suite ran **283 passed, 0 failed** today\n\n## Next", 1)
    # The two stops, each measured on the shipped documents before it was added.
    # A TABLE starts a register: the slice board below `### 6-BUILD`'s sentinel
    # records what each slice measured AT ITS CLOSE, and ending the tail at the
    # heading alone reported two of those as orphans -- cry-wolf on the correct
    # document, from the pre-commit hook.
    # m1 -- the `[ \t>]*` prefix had no subject: every probe wrote its table and
    # its heading at column 0, while the slice-board block is a BLOCKQUOTE from
    # end to end, so the form its own tail would need was the untested one.
    # Third occurrence of "two literal forms and only one had a subject".
    check_doc("a BLOCKQUOTED table row below the sentinel stops the tail",
              "@@START\n**283 passed, 0 failed**\n@@END\n"
              "> | slice | evidence |\n> |---|---|\n> | B1 | **11 passed, 0 failed** |", 0)
    check_doc("a BLOCKQUOTED heading below the sentinel stops the tail",
              "@@START\n**283 passed, 0 failed**\n@@END\n"
              ">  ### Next\n**11 passed, 0 failed**", 0)

    check_doc("a figure in a TABLE below the sentinel is a register, not an orphan",
              "@@START\n**283 passed, 0 failed**\n@@END\n"
              "| slice | evidence |\n|---|---|\n| B1 | **11 passed, 0 failed** |", 0)
    check_doc("a figure below the next HEADING is out of the tail",
              "@@START\n**283 passed, 0 failed**\n@@END\n\n## Next\n"
              "the suite ran **11 passed, 0 failed** today", 0)
    check_doc("a QUOTED historical figure in the tail is not an orphan",
              "@@START\n**283 passed, 0 failed**\n@@END\n"
              'round 5 said *"**11 passed, 0 failed**"*\n\n## Next', 0)
    # **BOTH halves of the prefix state reach the tail.** The first version
    # carried the fence and dropped the comment, two lines below the call that
    # passes both for the block -- so a comment opening in the block and closing
    # in the tail left the tail reading as live prose and a figure inside it
    # refused the commit. The half that WAS carried had no case either: the
    # whole expression could be replaced by `None` and the suite stayed green.
    check_doc("a FENCE opening in the block and closing in the tail is not live",
              "@@START\n**283 passed, 0 failed**\n```\n@@END\n"
              "**11 passed, 0 failed**\n```\n\n## Next", 0)
    check_doc("a COMMENT opening in the block and closing in the tail is not live",
              "@@START\n**283 passed, 0 failed**\n<!--\n@@END\n"
              "**11 passed, 0 failed**\n-->\n\n## Next", 0)
    # ...and once each closes, the tail below it IS live again, so neither case
    # passes by blanking the whole tail.
    check_doc("...and the tail below the fence's closer is live again",
              "@@START\n**283 passed, 0 failed**\n```\n@@END\n"
              "```\n**11 passed, 0 failed**\n\n## Next", 1)
    check_doc("...and the tail below the comment's closer is live again",
              "@@START\n**283 passed, 0 failed**\n<!--\n@@END\n"
              "-->\n**11 passed, 0 failed**\n\n## Next", 1)

    # m2 -- the scan's REACH was uncased in two directions: restricting it to
    # the first block was green (three of four real tails carry no figure), and
    # restricting `CLAIMS` to its first row was green (one of thirteen shapes was
    # exercised there). A scope is a claim; so is the set of shapes inside it.
    two_blocks = (("<probe>", "@@START", "@@END"),
                  ("<probe>", "%%START", "%%END"))
    doc2 = ("@@START\n**283 passed, 0 failed**\n@@END\nprose\n\n## A\n"
            "%%START\n`D-1`..`D-372`\n%%END\n"
            "the seams run `S-1`..`S-15` today\n\n## B")
    problems, _ = _check(m, scopes=two_blocks, read=lambda _: doc2)
    real = [x for x in problems if not x.startswith("NO DOCUMENT")]
    if len(real) != 1 or "S-1" not in real[0]:
        failures += 1
        print(f"  FAIL the tail of the SECOND block, on a NON-first claim shape: {real}")
    else:
        print("  ok  the scan reaches every block's tail and every claim shape")

    check_doc("a tail with no figure at all is silent",
              "@@START\n**283 passed, 0 failed**\n@@END\nprose\n\n## Next", 0)

    check_block("a correct test count passes", "**283 passed, 0 failed**", 0)
    check_block("a stale test count is caught", "**281 passed, 0 failed**", 1)
    check_block("a correct decision range passes", "`D-1`..`D-372`", 0)
    check_block("a stale decision range is caught", "`D-1`..`D-353`", 1)
    check_block("a stale dp-kernel count is caught", "`dp-kernel --lib` **300**", 1)
    check_block("a stale seam range is caught", "`S-1`..`S-15`", 1)
    check_block("a correct seam range passes", "`S-1`..`S-18`", 0)
    check_block("a stale seam COUNT in the index table is caught",
                "| x | 66 | **10** measured seams to features", 1)
    check_block("a stale gate-script count is caught", "the **37**\ngate scripts", 1)
    check_block("a stale contract line count is caught", "the two contracts are **200** and **157** lines", 1)
    check_block("correct contract line counts pass", "the two contracts are **202** and **157** lines", 0)
    # Both halves of that sentence are governed by DIFFERENT rows, and only the
    # first had a case: deleting the substrate row left the suite green and 157
    # silently ungoverned. One case per ROW, not one per sentence.
    check_block("a stale substrate line count is caught",
                "the two contracts are **202** and **150** lines", 1)
    # M1 -- the TABLE form, which no pattern reached while four figures inside a
    # governed block were stale. One case per row, and the passing direction too.
    check_block("the index table's line counts pass when correct",
                "| [x](2026-08-02-actor-hub.md) | 202 | ...\n"
                "| [x](2026-08-02-engine-substrate.md) | 157 | ...\n"
                "| [x](2026-08-02-seams-and-triggers.md) | 66 | ...\n"
                "**425 lines total.**", 0)
    check_block("a stale hub count in the index TABLE is caught",
                "| [x](2026-08-02-actor-hub.md) | 172 | ...", 1)
    check_block("a stale substrate count in the index TABLE is caught",
                "| [x](2026-08-02-engine-substrate.md) | 142 | ...", 1)
    check_block("a stale seams count in the index TABLE is caught",
                "| [x](2026-08-02-seams-and-triggers.md) | 50 | ...", 1)
    check_block("a stale TOTAL is caught", "**364 lines total.**", 1)

    # F6 — a QUOTED historical figure must not block. These blocks are exactly
    # where this project writes "it said X at round seven".
    check_block("a quoted historical figure is not a claim",
                '> Round 5 said *"**281 passed, 0 failed**"*, superseded at round 6.', 0)
    # ...and an UNQUOTED historical figure IS a claim, deliberately. There is no
    # syntax that distinguishes "the handoff said 281" from "the count is 281",
    # so the gate requires the quotation marks rather than guessing -- which is
    # what the two content heuristics it replaced were doing.
    check_block("an UNQUOTED historical figure is treated as a claim, by design",
                "> Round 5's handoff said **281 passed, 0 failed**.", 1)
    check_block("a fenced example is not a claim",
                "```\nAt the seal the log ran `D-1`..`D-353`.\n```", 0)
    check_block("an HTML comment is not a claim",
                "<!-- was: **281 passed, 0 failed** -->", 0)
    check_block("a MULTI-LINE HTML comment is not a claim",
                "<!--\nwas: **281 passed, 0 failed**\n-->", 0)
    check_block("an INLINE HTML comment is not a claim",
                "the count is fine <!-- was **281 passed, 0 failed** --> today", 0)
    # ...and the line AFTER it is live. Not blanking the inline span leaves
    # `in_comment` set -- the `-->` was consumed on the previous line -- so every
    # following line goes blind. Counting findings on the comment line alone
    # cannot see that: the whole line is blanked either way.
    check_block("an inline comment does not blind the lines after it",
                "fine <!-- was **281 passed, 0 failed** --> today\n"
                "`dp-kernel --lib` **300**", 1)
    # **An UNPAIRED opener is LITERAL TEXT, and the reasoning is a comparison
    # of two cry-wolves rather than a preference.** Blanking the tail refuses
    # the commit through `must_claim` with a diagnosis naming a cause that is
    # not the cause -- "the sentinel has moved UP" about a sentinel nobody
    # touched, which points at the wrong file and implies a wrong remedy. Not
    # blanking reports "claims 281, measured 294" about a figure that IS in
    # the document and DOES disagree: an accurate statement the author can act
    # on, by fixing the figure or by closing the fence. An earlier version of
    # this case asserted the opposite, before the refusal path existed to
    # compare it against.
    check_block("an unpaired fence opener is literal text, not a blanket",
                "```rust\nlet x = 1;\n\nthe count is **281 passed, 0 failed** today", 1)
    # **...and it reaches only from the OPENER DOWN.** The predicate asks about
    # the document and the first version's action masked every fence marker in
    # it, so one unterminated fence at the bottom un-fenced every correctly
    # paired block above -- three measured refusals on the shipped documents,
    # one of them the misdiagnosis this masking exists to prevent. A CLOSED
    # block above the opener keeps its fence semantics.
    check_block("a CLOSED fence above an unpaired opener is still a fence",
                "```\nthe count was **281 passed, 0 failed**\n```\n"
                "prose\n```rust\nlet x = 1;", 0)
    check_block("...and the text below that opener is still literal",
                "```\nthe count was **281 passed, 0 failed**\n```\n"
                "```rust\nlet x = 1;\nthe count is **281 passed, 0 failed**", 1)
    # A `~~~` opener is an opener. `_unpaired_opener` delegates to `_advance`,
    # which handles both characters -- but nothing asserted the tilde half, so
    # narrowing the scan to backticks survived.
    check_block("an unpaired ~~~ opener is literal text too",
                "~~~\nthe count is **281 passed, 0 failed** today", 1)
    # A block that BEGINS INSIDE a fence is no longer expressible: a marker in a
    # fenced region is a MENTION by design, so the scope cannot start there. The
    # property that case was reaching for -- prefix fence state carried into the
    # window -- is asserted directly on `_fence_state` and `_claimable` below.
    # A blockquote fence is a fence. This project writes whole headers as
    # blockquotes and the gate's own docstring says so, yet the marker test was
    # `lstrip()` only -- so this was reported as a live claim.
    # M9 -- five fence shapes a review measured, one of them CRY-WOLF: the
    # standard markdown idiom for DOCUMENTING a fence is a longer outer fence,
    # and counting every marker as a toggle exposed its contents as live claims.
    check_block("a 4-backtick fence documenting a 3-backtick one is not a claim",
                "````\n```\nthe count was **281 passed, 0 failed**\n```\n````", 0)
    # A line that STARTS with the fence character but carries text is content,
    # not a closer -- so the block stays blanked and the figure on it is not a
    # live claim. Treating it as a closer exposed everything after it.
    check_block("a backtick line with text does not close a fence",
                "```\n``` shell output follows\nthe count was **281 passed, 0 failed**\n```", 0)
    # minor 6 -- a TILDE fence may carry tildes in its info string; CommonMark
    # forbids backticks only in a backtick fence's. Applying the rule to both
    # meant this was not a fence at all and its contents were live claims.
    check_block("a ~~~ fence whose info contains a tilde is still a fence",
                "~~~ ~diagram~\nthe count was **281 passed, 0 failed**\n~~~", 0)
    check_block("a ~~~ line inside a ``` fence does not close it",
                "```\n~~~\nthe count was **281 passed, 0 failed**\n~~~\n```", 0)
    # ...and a fence marker inside an HTML COMMENT must not flip the fence at
    # all. Testing the fence before the comment left BOTH flags stuck true and
    # blinded the rest of the block permanently.
    check_block("a fence marker inside a comment does not blind the block",
                "<!--\n```\n-->\n`dp-kernel --lib` **300**", 1)
    # An INLINE code span at the start of a line is not a fence opener: a fence
    # info string may not contain the fence character.
    check_block("an inline ```code``` span is not a fence",
                "```rustfmt``` says `dp-kernel --lib` **300**", 1)
    check_block("a BLOCKQUOTE fence is a fence",
                "> ```\n> the count was **281 passed, 0 failed**\n> ```", 0)
    # A comment that OPENS mid-line, one line after the multi-line fix.
    # M2 -- a comment must stay open until `-->`, and its OPENING line must be
    # opaque. Both rules were deletable green because every case used a one-line
    # body and put no figure on the opening line.
    check_block("a MULTI-line comment body stays closed to the end",
                "<!--\nsuperseded, was `dp-kernel --lib` **300**\n"
                "and also **281 passed, 0 failed**\n-->", 0)
    check_block("a figure on the comment's OPENING line is not a claim",
                "<!-- superseded: `dp-kernel --lib` **300**\nstill inside\n-->", 0)
    check_block("a comment opening MID-LINE is not a claim",
                "superseded <!--\n**281 passed, 0 failed**\n-->", 0)
    check_block("an italicised QUOTATION is a historical record, not a claim",
                'the header read it (*"**281 passed, 0 failed**"* at round six)', 0)
    # ...and the same figure OUTSIDE a quotation is still a live claim, so the
    # rule is syntax and not a licence.
    check_block("the same figure outside a quotation is still a claim",
                "the header says **281 passed, 0 failed** today", 1)

    # The live range escaping its block -- F1's mechanism, both directions.
    def escape_case(name: str, doc: str, want: int, meas=None) -> None:
        """Driven through `_check`, NOT through `_escaped_live_range` directly.

        The first version called the rule directly, so deleting its call site in
        `_check` left the whole suite green -- the rule tested, its WIRING not.
        That is the same defect as a self-test reimplementing the loop it tests,
        one call deep, and the mutation harness found it on its first run.
        """
        nonlocal failures
        problems, _ = _check(meas or m, scopes=(("<probe>", "@@START", "@@END"),),
                             read=lambda _: doc)
        got = [x for x in problems if "LIVE range" in x]
        ok = len(got) == want
        failures += 0 if ok else 1
        print(f"  {'ok ' if ok else 'FAIL'} {name}: expected {want}, got {len(got)}")
        for g in got if not ok else []:
            print(f"        {g}")

    escape_case("the live range inside the current-state block is correct",
                "@@START\n`D-1`..`D-372`\n@@END", 0)
    escape_case("the live range OUTSIDE the block is a finding",
                "@@START\nnothing\n@@END\n\n| D-195 | it declares `D-1`..`D-372` |", 1)
    # **B1 — the case the substring test could not fail.** The document carries
    # the live range INSIDE its block, which is the design, AND an escaped copy
    # outside it. `if any(mo.group(0) in b for b in blocks)` exempted the second
    # because the identical string appeared in the first, so two of the three
    # governed documents were unguarded -- including the very line the mechanism
    # had just repaired.
    escape_case("an escape in a document that LEGITIMATELY carries the live range",
                "@@START\n`D-1`..`D-372`\n@@END\n\n| D-195 | it declares `D-1`..`D-372` |", 1)
    # The wrap tolerance itself: these documents wrap, and the blockquote form
    # puts `> ` between the two halves. Without it a wrapped live range escapes
    # entirely -- an adjacent decision (how the docs are written) defeating the
    # rule, which is the shape the sibling contract-lines pattern already carries
    # a tolerance for.
    escape_case("a WRAPPED live range is still an escape",
                "@@START\nnothing\n@@END\n\n> | D-195 | it declares `D-1`..\n> `D-372` |", 1)
    escape_case("a HISTORICAL range outside the block is correct, and stays",
                "@@START\nnothing\n@@END\n\n| D-195 | it declares `D-1`..`D-109` |", 0)
    # ...and with no measurable head there is nothing to compare against, so the
    # rule must stay SILENT rather than guess. Cry-wolf here would fire on every
    # machine without the artifact.
    escape_case("a FENCED example of the header is not an escape",
                "@@START\nnothing\n@@END\n\n```\n`D-1`..`D-372`\n```", 0)
    escape_case("a QUOTATION carrying the live head IS an escape, by design",
                '@@\nnothing\n@@END\n\n| D-195 | it declares *"`D-1`..`D-372`"* |', 1)
    escape_case("an unmeasurable head accuses nobody",
                "@@START\nnothing\n@@END\n\n| D-195 | `D-1`..`D-372` |", 0,
                meas={**m, "max_decision_id": {"unmeasurable": "no bold D- id"}})

    # **`_claimable` preserves OFFSETS**, which is load-bearing and had no case:
    # `_escaped_live_range` compares `mo.start()` in the BLANKED text against
    # spans computed on the ORIGINAL, so blanking to `""` silently exempts every
    # escape after the first blanked character.
    for probe in ("plain\n```\nfenced\n```\ntail",
                  "<!--\ncomment\n-->\ntail",
                  'a *"quoted **281 passed, 0 failed**"* b',
                  "crlf\r\nlines\r\nhere"):
        if len(_claimable(probe)) != len(probe):
            failures += 1
            print(f"  FAIL _claimable changed the length of {probe!r}")
            break
    else:
        print("  ok  _claimable preserves offsets, so span exclusion stays valid")

    # **The prefix state must REACH the window**, and the only route left is a
    # comment: a marker inside a fence is no longer a marker, so the fence
    # version of this case became inexpressible and the rule lost its driver.
    # `_marker_hits` keeps comments visible precisely so the sentinel is found,
    # which leaves an unterminated comment above a block both possible and
    # load-bearing.
    problems, _ = _check(
        m, scopes=(("<probe>", "@@START", "@@END"),),
        read=lambda _: "<!--\nsuperseded\n@@START\n**281 passed, 0 failed**\n@@END")
    real = [x for x in problems if not x.startswith("NO DOCUMENT")]
    if real:
        failures += 1
        print(f"  FAIL a block opening inside a comment must be blanked: {real}")
    else:
        print("  ok  the prefix comment state reaches the window and blanks it")

    # ...and the FENCE half, asserted directly: a marker inside a fence is no
    # longer a marker, so there is no document shape that can carry this through
    # `_check`. The parameter still has to work.
    if _claimable("**281 passed, 0 failed**", in_fence="```").strip():
        failures += 1
        print("  FAIL a window opening inside a fence was not blanked")
    else:
        print("  ok  the prefix fence state reaches the window and blanks it")

    # A missing END marker must be a FINDING. It used to widen the window to
    # the whole file: mass cry-wolf for the figure check, and total blindness for
    # the escape rule, whose exempt span then covered the entire document.
    # **This case OWNS its exception.** Deleting the guard makes `_scope_span`
    # index an empty list, so the call below RAISES rather than disagreeing --
    # the run died here, the crash wrapper reported it, and the harness read
    # that as the rule biting. The case existed for eighteen rounds and never
    # once disagreed with anything.
    try:
        problems, _ = _check(m, scopes=(("<probe>", "@@START", "NO SUCH END"),),
                             read=lambda _: "@@START\n**281 passed, 0 failed**\n@@END")
    except Exception as e:  # noqa: BLE001 - the crash IS the finding
        problems = [f"raised {type(e).__name__}: {e}"]
    if not any("do not both" in x for x in problems):
        failures += 1
        print(f"  FAIL a missing END marker must be a finding, got {problems}")
    else:
        print("  ok  a missing end marker is a finding, not a whole-file window")

    # A block that RESOLVES but carries no governed figure is the other half of
    # the same defect: inserting a `---` inside the handoff block truncates it
    # silently, and the gate then agrees with whatever survived. Driven against
    # the REAL scopes, because that is the only place the rule applies.
    # These cases read the REAL documents, so they need the REAL measurement:
    # `m` above is a synthetic probe (283/372/38) and comparing live documents
    # against it reports disagreements that have nothing to do with the rule.
    # **`measure()` must never raise.** Every figure it cannot obtain is an
    # `Unmeasurable`, which is the whole degrade-safety design -- so a raw
    # exception here is a finding, and for nineteen rounds it was instead the
    # EVIDENCE for the cargo-absent guard: delete that guard, this line raises,
    # and the harness read the traceback as the rule biting.
    try:
        real_m = measure()
    except Exception as e:  # noqa: BLE001 - the crash IS the finding
        failures += 1
        print(f"  FAIL measure() raised {type(e).__name__}: {e} — every figure "
              "it cannot obtain must be an Unmeasurable, never a crash")
        real_m = {k: {"unmeasurable": "measure() raised"} for k in
                  ("rust_tests", "dp_kernel_lib_tests", "max_decision_id",
                   "max_seam_id", "hook_gate_scripts", "contract_hub_lines",
                   "contract_substrate_lines", "contract_seams_lines",
                   "contract_total_lines")}

    def _seed_handoff(mutate):
        def read(doc: str) -> str:
            text = (REPO / doc).read_text(encoding="utf-8", errors="replace")
            return mutate(text) if doc == HANDOFF else text
        return read

    # The sentinel moved UP to just after the heading: the block resolves and
    # contains nothing.
    def _collapse(text: str) -> str:
        # MOVED, not duplicated: two markers is a different finding with its own
        # message, so adding one here would assert the wrong rule.
        text = text.replace(END("game-tier") + "\n", "", 1)
        i = text.find("## \u25b6 GAME TIER")
        return text[:i] + "## \u25b6 GAME TIER\n\n" + END("game-tier") + "\n" + text[i:]

    problems, _ = _check(real_m, read=_seed_handoff(_collapse))
    # Either message is a correct answer: `must_claim` names WHICH figures went
    # missing, the empty-block rule says the block holds none at all. A total
    # collapse trips both, and the more informative one wins the race.
    if not any(("contains NO figure" in x) or ("no longer states" in x) for x in problems):
        failures += 1
        print(f"  FAIL a block truncated to nothing did not produce a finding: {problems[:2]}")
    else:
        print("  ok  a scope that shrank to nothing is a finding, not agreement")

    # **And a horizontal rule INSIDE the block is now a non-event.** It used to
    # be the block's end, so an ordinary markdown edit silently ungoverned
    # everything below it -- measured: three of the five figures in the handoff
    # block went invisible, with the gate reporting agreement. Counting findings
    # on the collapse alone could not see that, because one claim survived.
    def _rule_midway(text: str) -> str:
        i = text.find("## \u25b6 GAME TIER")
        j = text.find("**Evidence:**", i)
        return text[:j] + "\n---\n\n" + text[j:]

    problems, _ = _check(real_m, read=_seed_handoff(_rule_midway))
    if problems:
        failures += 1
        print(f"  FAIL a `---` inside a block must not change anything: {problems}")
    else:
        print("  ok  a horizontal rule inside a block is not a scope boundary")

    # ...and the figures BELOW that rule are still governed, which is the half
    # that was actually broken.
    def _rule_and_stale(text: str) -> str:
        # **A figure measurable with NO toolchain.** Seeding a Rust test count
        # made this case fail on any machine without cargo -- so the gate refused
        # commits from exactly the contributors its own docstring says it must
        # never block, and CI's `--no-cargo` mutation job went vacuous because
        # every row was red before any mutation was applied.
        text = _rule_midway(text)
        return text.replace("the **39**", "the **11**", 1)

    problems, _ = _check(real_m, read=_seed_handoff(_rule_and_stale))
    if not any("claims 11" in x for x in problems):
        failures += 1
        print("  FAIL a stale figure below a `---` was not caught")
    else:
        print("  ok  a figure below a horizontal rule is still governed")

    # A SECOND end marker must be a finding, not a shorter block. Deletion was
    # never the defect; premature termination was, and the sentinel that replaced
    # the incidental `---` inherited it exactly.
    def _second_sentinel(text: str) -> str:
        j = text.find("**Evidence:**", text.find("## \u25b6 GAME TIER"))
        return text[:j] + END("game-tier") + "\n\n" + text[j:]

    problems, _ = _check(real_m, read=_seed_handoff(_second_sentinel))
    if not any("occurs 2 times" in x for x in problems):
        failures += 1
        print(f"  FAIL a duplicated end marker was not reported: {problems[:2]}")
    else:
        print("  ok  a second end marker is a finding, not a shorter block")

    # ...and a marker MENTIONED in an inline code span is not a terminator, which
    # is what documenting it looks like.
    def _mentioned(text: str) -> str:
        j = text.find("**Evidence:**", text.find("## \u25b6 GAME TIER"))
        return text[:j] + "the marker is `" + END("game-tier") + "` here\n\n" + text[j:]

    problems, _ = _check(real_m, read=_seed_handoff(_mentioned))
    if problems:
        failures += 1
        print(f"  FAIL a marker mentioned inline must not terminate: {problems[:2]}")
    else:
        print("  ok  a marker mentioned inside a line is not a terminator")

    # The range is written BOTH ways in this project; requiring backticks made
    # the un-backticked form invisible to the rule and to its own coverage check.
    escape_case("an UN-BACKTICKED live range is still an escape",
                "@@START\nnothing\n@@END\n\n| D-195 | it declares D-1..D-372 |", 1)

    # The corpus is RECURSIVE. Narrowing it to `docs/*.md` left the derivation
    # unable to see any of the documents it exists to police.
    corpus = {p.relative_to(REPO).as_posix() for p in _escape_corpus()}
    if RUN_STATE not in corpus or INDEX not in corpus:
        failures += 1
        print("  FAIL the escape corpus does not reach nested documents")
    else:
        print(f"  ok  the escape corpus walks {len(corpus)} documents, nested included")

    # The `>` tolerance had NO SUBJECT: every shipped marker is at column 0, so
    # dropping `>` from `QUOTE_PREFIX` left all four scopes byte-identical and
    # the suite green -- NV-1, in the round that cites NV-1. The RUN-STATE's
    # governed block IS a blockquote, so a marker written inside it is the shape
    # the tolerance exists for.
    quoted = "> # \u25b6\u25b6 NEXT SESSION STARTS HERE"
    if not _at_line_start("prefix\n" + quoted, len("prefix\n") + 2, quoted):
        failures += 1
        print("  FAIL a blockquote-prefixed marker was not recognised")
    else:
        print("  ok  a marker inside a blockquote is still at the start of its line")
    if _at_line_start("prefix\nsee " + quoted, len("prefix\nsee "), quoted):
        failures += 1
        print("  FAIL a marker after prose was treated as line-start")
    else:
        print("  ok  a marker after prose on the same line is not at line-start")

    # **The mask must NOT apply when the CALLER already knows the fence state.**
    # A window that BEGINS inside a fence has a genuine open marker above it, so
    # the first marker inside the window is a CLOSER, not an unpaired opener --
    # and masking it leaves the whole window fenced, hiding a live claim below.
    # Dropping the `in_fence is None` conjunct survived every other case.
    resumed = _claimable("was **281 passed, 0 failed**\n```\nis **281 passed, 0 failed**",
                         in_fence="```")
    if "is **281 passed, 0 failed**" not in resumed or "was **281" in resumed:
        failures += 1
        print("  FAIL a window resuming inside a fence lost the live claim below its closer")
    else:
        print("  ok  a window resuming inside a fence keeps the claim below its closer")

    # **The TAB half of both indent rules.** `INDENT_CODE` and `QUOTE_PREFIX`
    # each accept two literal forms and only the space form had a subject, so
    # dropping `\t` from either left the suite green -- one literal form cased
    # and its twin not, in the round whose headline is exactly that.
    if _indented_blanked("\tsee <!-- x -->").strip():
        failures += 1
        print("  FAIL a TAB-indented line was not treated as a code block")
    else:
        print("  ok  a TAB-indented line is markdown's other literal form")
    if not _at_line_start("prefix\n\t> mark", len("prefix\n\t> "), "mark"):
        failures += 1
        print("  FAIL a TAB before a blockquote marker was not tolerated")
    else:
        print("  ok  a TAB in the blockquote prefix is still line-start")

    # **Every scope ENDS on a named sentinel.** `_index.md`'s scope was moved
    # onto one and nothing asserted the shape, so reverting it to a heading --
    # which is what made the block silently re-terminable by a second heading of
    # the same text -- left the whole suite green. The property was made true by
    # editing data, with no check to keep it true.
    unsentinelled = _unsentinelled(SCOPES)
    # ...and the predicate must REJECT the shapes it exists to reject, each of
    # which is an HTML comment, so a `startswith("<!--")` weakening accepts all
    # three while the shipped scopes stay green.
    # **Each shape must fail for its OWN reason.** The first version's
    # "an `:end` with no block name" was `<!-- actor-hub-figures:end -->`, which
    # fails on the missing SPACE rather than the missing name -- so the `+`
    # quantifier the row is about stayed unpinned, and so did the `$` anchor.
    # A rule tested only through data it happens to have is a rule with half a
    # test, which is the sentence that row is written around.
    rejects = _unsentinelled((("d", "s", "<!-- not a sentinel -->"),
                              ("d", "s", "<!-- actor-hub-figures:end  -->"),
                              ("d", "s", "<!-- actor-hub-figures:end x --> junk"),
                              ("d", "s", "## a heading")))
    if len(rejects) != 4:
        failures += 1
        print(f"  FAIL the sentinel predicate accepted {4 - len(rejects)} non-sentinel(s)")
    else:
        print("  ok  an EMPTY name, a trailing tail and a bare comment are not sentinels")
    if unsentinelled:
        failures += 1
        print(f"  FAIL these scopes do not end on a named sentinel: {unsentinelled}")
    else:
        print(f"  ok  all {len(SCOPES)} scopes end on a named `:end <block>` sentinel")

    def expect(name: str, fn, want) -> None:
        """Assert `fn()` == `want`, attributing an exception to THIS case.

        Without the attribution the exception escapes, kills the run, and the
        crash wrapper reports it -- which the mutation harness then reads as a
        rule that bit. Every rule whose removal RAISES rather than disagrees
        needs its case to own that exception, or the rule has no case at all.
        """
        nonlocal failures
        try:
            got = fn()
        except Exception as e:  # noqa: BLE001 - the crash IS the finding
            failures += 1
            print(f"  FAIL {name}: raised {type(e).__name__}: {e}")
            return
        if got != want:
            failures += 1
            print(f"  FAIL {name}: got {got!r}, want {want!r}")
        else:
            print(f"  ok  {name}")

    # ── the marker rules, both markers, every route to a wrong block ─────────
    #
    # Written as a TABLE over (which marker, how it appears, what must happen),
    # because the recurring defect in this run is hardening one marker and not
    # the other, or closing one route to premature termination and not the next.
    def _append(doc: str, extra: str):
        def read(d: str) -> str:
            text = (REPO / d).read_text(encoding="utf-8", errors="replace")
            return text + "\n" + extra + "\n" if d == doc else text
        return read

    marker_cases = (
        ("a STRAY duplicate end sentinel is loud",
         HANDOFF, END("game-tier"), "occurs 2 times"),
        ("a STRAY duplicate start marker is loud",
         RUN_STATE, "### 6-BUILD", "occurs 2"),
        ("an end sentinel shown INDENTED is a mention",
         HANDOFF, "    " + END("game-tier"), None),
        ("a start marker shown INDENTED is a mention",
         RUN_STATE, "    ### 6-BUILD", None),
        ("an end sentinel shown in a FENCE is a mention",
         RUN_STATE, "```\n" + END("next-session") + "\n```", None),
        ("a start marker shown in a FENCE is a mention",
         RUN_STATE, "```\n### 6-BUILD\n```", None),
        ("an end sentinel MENTIONED inline is a mention",
         HANDOFF, "the marker is `" + END("game-tier") + "` here", None),
        ("a start marker MENTIONED inline is a mention",
         RUN_STATE, "| D-9 | the block starts at `### 6-BUILD` |", None),
        ("a repeating structural row is no longer an end marker",
         RUN_STATE, "| # | Slice | Done when |", None),
    )
    for name, doc, extra, want in marker_cases:
        got = [x for x in _check(real_m, read=_append(doc, extra))[0] if doc in x]
        ok = (want is None and not got) or (want is not None and any(want in x for x in got))
        failures += 0 if ok else 1
        print(f"  {'ok ' if ok else 'FAIL'} {name}" + ("" if ok else f": {got[:1]}"))

    # ...and the LAST route to a silently shortened scope: MOVING the one
    # sentinel up. The block still holds a claim, so the empty-block rule stays
    # quiet; naming the figures each block must carry is what catches it.
    def _move_up(text: str) -> str:
        sentinel = END("game-tier")
        text = text.replace(sentinel + "\n", "", 1)
        j = text.find("**Evidence:**", text.find("## \u25b6 GAME TIER"))
        return text[:j] + sentinel + "\n\n" + text[j:]

    problems, _ = _check(real_m, read=_seed_handoff(_move_up))
    if not any("no longer states" in x for x in problems):
        failures += 1
        print(f"  FAIL a MOVED sentinel left the scope short and silent: {problems[:2]}")
    else:
        print("  ok  a moved sentinel is caught by the figures the block must state")

    # **An UNTERMINATED fence must not refuse the commit**, and must not do it
    # with a diagnosis naming a cause that is not the cause. The marker search
    # got a raw fallback and the CONTENT blanking did not, so this input
    # resolved its markers, blanked the block anyway, tripped `must_claim` and
    # reported "its end sentinel has probably moved UP" about a sentinel nobody
    # had touched.
    def _unterminated_inside(text: str) -> str:
        j = text.find("**Evidence:**", text.find("## ▶ GAME TIER"))
        return text[:j] + "```rust\nlet x = 1;\n\n" + text[j:]

    problems, _ = _check(real_m, read=_seed_handoff(_unterminated_inside))
    if problems:
        failures += 1
        print(f"  FAIL an unterminated fence inside a block refused the commit: {problems[:2]}")
    else:
        print("  ok  an unterminated fence inside a block changes nothing")

    # ...and a figure BELOW it is still governed, which is the half that must not
    # be traded away for the half above.
    def _unterminated_and_stale(text: str) -> str:
        return _unterminated_inside(text).replace("the **39**", "the **11**", 1)

    problems, _ = _check(real_m, read=_seed_handoff(_unterminated_and_stale))
    if not any("claims 11" in x for x in problems):
        failures += 1
        print(f"  FAIL a stale figure below an unterminated fence was missed: {problems[:2]}")
    else:
        print("  ok  a figure below an unterminated fence is still governed")

    # O-R15-4 -- a bolded figure inside a governed block that no rule reads.
    # Three rounds found one of these by hand; the last was fixed by DELETING
    # the figures, which is an instance fix with no detector.
    def _ungoverned_bold(text: str) -> str:
        j = text.find("**Evidence:**", text.find("## ▶ GAME TIER"))
        return text[:j] + "and **7** brand new widgets\n\n" + text[j:]

    problems, _ = _check(real_m, read=_seed_handoff(_ungoverned_bold))
    if not any("read by no rule" in x for x in problems):
        failures += 1
        print(f"  FAIL a bolded figure nothing governs was not reported: {problems[:2]}")
    else:
        print("  ok  a bolded figure inside a governed block that no rule reads is reported")

    # **The SHAPE the detector recognises is a claim too.** It matched `**7**`
    # and nothing else -- the exact shape of the case above -- so narrowing it
    # back to `\d+` survived. Every form here is one this project writes, and
    # widening to them found two ungoverned figures in the shipped blocks.
    for shape, want in (("**7 widgets**", True), ("**7.5**", True),
                        # TWO and THREE words. The shape admitted ONE, so
                        # `**301 Rust tests**` sat in a governed block invisible
                        # on both arms -- not compared, and not surplus either.
                        ("**301 Rust tests**", True),
                        ("**7 brand new widgets**", True),
                        # FOUR words and more: the `{0,3}` bound was an
                        # enumeration and a four-word figure walked through it
                        # in the governed block, one round after it was set.
                        ("**7 one two three four**", True),
                        ("**999 Rust integration tests pass**", True),
                        # TWELVE words. A four-word case only reds a bound of
                        # three, and `D-496`'s whole point is that ANY bound is
                        # an enumeration — so the case has to outrun the numbers
                        # a mutation would plausibly pick, not just the last one.
                        ("**7 one two three four five six seven eight nine ten eleven**", True),
                        # ...and a bolded SENTENCE is still not a figure: any
                        # punctuation after the digits ends the run.
                        ("**7 widgets, and then some**", False),
                        ("**7 widgets. Also this**", False),
                        ("**7,000**", True), ("**7 000**", True),
                        ("**2026**", True), ("**2026-08-03**", False),
                        # ...and the WRAP tolerance its siblings carry. The
                        # slice board writes this one across a line break inside
                        # a blockquote, and the widened shape still missed it.
                        ("**0" + chr(10) + "> warnings**", True),
                        ("**0" + chr(10) + "warnings**", True),
                        ("**ok**", False), ("**passed**", False)):
        got = bool(BOLD_INT_RE.fullmatch(shape))
        if got != want:
            failures += 1
            print(f"  FAIL the bolded-figure shape {shape!r}: matched={got}, want={want}")
        else:
            print(f"  ok  the bolded-figure shape {shape!r} -> {'reported' if want else 'ignored'}")

    # **A rule that still passes, 60x slower, is a defect this apparatus
    # cannot see.** The bolded-figure matcher went exponential and NOTHING
    # noticed: rc stayed 0, every shape case above still passed, `--check`
    # still agreed with the artifacts, and the one timing alarm here fires
    # on a 300s HANG -- so 189.5s sat below it. A budget is what separates
    # slow from hung, so these two probes carry one.
    #
    # TWO probes, because linearity has two independent halves and one probe
    # would leave the other unguarded. The first needs the SPAN to stop at
    # the next `*`; the second needs the BODY separator to be MANDATORY.
    # Each reds under exactly one of the two mutations that restore them.
    for probe, budget_s, what in (
            # TWENTY-FOUR words. The count is chosen from the MEASURED growth of
            # the mutation this case exists to catch -- about fourfold per two
            # words, so 24 costs the mutant ~4s against a 0.5s budget, while 28
            # would cost it a minute and 40 would HANG the child. A hang is not a
            # failing case (`D-478`), so a probe that is too strong is as useless
            # here as one that is too weak.
            ("**1 " + " ".join(["ab"] * 24),
             0.5, "an unpaired `**` and 24 words"),
            ("**1 " + " ".join(["ab"] * 24) + ", x**",
             0.5, "a 24-word figure that fails at a comma")):
        started = time.monotonic()
        BOLD_INT_RE.findall(probe)
        took = time.monotonic() - started
        if took > budget_s:
            failures += 1
            print(f"  FAIL the bolded-figure matcher took {took:.2f}s on "
                  f"{what} (budget {budget_s}s) — it is backtracking, and a "
                  "rule this slow still reads GREEN everywhere else")
        else:
            print(f"  ok  the bolded-figure matcher stays linear on {what} "
                  f"({took * 1000:.1f}ms)")

    # `dp-kernel --lib` **315 passed** -- the slice board's phrasing, one word
    # past the pattern the header's phrasing fits, so the figure sat inside a
    # governed block reading as checked and was not.
    both = [t for t in ("`dp-kernel --lib` **315**", "`dp-kernel --lib` **315 passed**")
            if not any(re.findall(pat, t) for pat, k, _l in CLAIMS
                       if k == "dp_kernel_lib_tests")]
    if both:
        failures += 1
        print(f"  FAIL the dp-kernel rule does not read these phrasings: {both}")
    else:
        print("  ok  the dp-kernel rule reads both the header's and the board's phrasing")

    # O-R15-3 -- `must_claim` must be EXACT. Its sibling enumeration is
    # re-derived from the tree; this one was a lower bound, so emptying any
    # scope's set left the suite green and a figure ADDED to a block was never
    # named -- which is what leaves the block's tail unprotected later.
    thin = tuple((sc[0], sc[1], sc[2], frozenset()) if sc[1] == "### 6-BUILD" else sc
                 for sc in SCOPES)
    real_scopes = globals()["SCOPES"]
    globals()["SCOPES"] = thin
    try:
        problems, _ = _check(real_m, scopes=thin)
    finally:
        globals()["SCOPES"] = real_scopes
    if not any("does not name" in x for x in problems):
        failures += 1
        print(f"  FAIL an emptied must_claim set was not reported: {problems[:2]}")
    else:
        print("  ok  a must_claim set that no longer names what its block states is reported")

    # **DEGRADE-SAFE, asserted.** With every figure unmeasurable -- a machine
    # with no Rust toolchain, which is most of them -- the check must be SILENT
    # on the real documents. A case that seeds a cargo-dependent figure breaks
    # this and turns the pre-commit hook into a refusal for every contributor
    # without cargo; it also makes CI's `--no-cargo` mutation run vacuous,
    # because every mutation is red before it is applied.
    blind = {k: {"unmeasurable": "no toolchain"} for k in real_m}
    problems, notes = _check(blind)
    if problems:
        failures += 1
        print(f"  FAIL with nothing measurable the check must be silent: {problems[:2]}")
    elif not notes:
        failures += 1
        print("  FAIL an unmeasurable run produced no NOTE either — it checked nothing quietly")
    else:
        print(f"  ok  with no toolchain the check degrades to {len(notes)} note(s), zero refusals")


    # M2 -- a fence marker inside an HTML COMMENT in the document PREFIX. One
    # such line above a block used to flip the prefix scan into a fence that
    # never closed: a silently blinded slice board in one direction, and a
    # refusal on a perfectly correct handoff in the other -- from the hook that
    # fires on it for all 47 services.
    def _commented_fence(text: str) -> str:
        i = text.find("## ▶ GAME TIER")
        return text[:i] + "<!--\n```\n-->\n\n" + text[i:]

    problems, _ = _check(real_m, read=_seed_handoff(_commented_fence))
    if problems:
        failures += 1
        print(f"  FAIL a commented-out fence above a block must change nothing: {problems}")
    else:
        print("  ok  a fence marker inside a comment does not blind the prefix scan")

    # ...and the state it DOES carry still reaches the window: a genuinely open
    # fence above the block still blanks it.
    marker, commented = _fence_state("<!--\n```\n-->\n")
    if marker is not None or commented:
        failures += 1
        print(f"  FAIL a closed comment left state behind: {marker!r}, {commented}")
    else:
        print("  ok  a comment containing a fence marker leaves no state behind")
    # ...and an UNTERMINATED comment in the prefix carries into the window: the
    # scanner returns both halves of the state, and dropping the comment half
    # left every figure below an open comment live.
    marker, commented = _fence_state("<!--" + chr(10) + "superseded" + chr(10))
    if commented is not True:
        failures += 1
        print(f"  FAIL an unterminated comment in the prefix was lost: {commented}")
    else:
        print("  ok  an unterminated comment in the prefix reaches the window")
    blanked = _claimable("**281 passed, 0 failed**", in_comment=True)
    if blanked.strip():
        failures += 1
        print("  FAIL a window opening inside a comment was not blanked")
    else:
        print("  ok  a window opening inside a comment is blanked")

    marker, commented = _fence_state("```rust\nlet x = 1;\n")
    if marker != "```":
        failures += 1
        print(f"  FAIL an open fence in the prefix was lost: {marker!r}")
    else:
        print("  ok  an open fence in the prefix reaches the window")


    # The escape rule must READ every document on its list, not only the three
    # with a current-state block. Eight files carried the range and were blind.
    other = ESCAPE_DOCS[0]

    def _seeded(doc: str) -> str:
        if doc == other:
            return f"| D-1 | it declares `D-1`..`D-{m['max_decision_id']}` |"
        return (REPO / doc).read_text(encoding="utf-8", errors="replace")

    problems, _ = _check(m, read=_seeded)
    if not any(other in x and "LIVE range" in x for x in problems):
        failures += 1
        print(f"  FAIL {other} is on the escape list and was not read")
    else:
        print(f"  ok  the escape rule reads all {len(ESCAPE_DOCS)} listed documents")

    # An unmeasurable figure is a NOTE, not a block -- production behaviour, which
    # the inline copy asserted the OPPOSITE of and nothing noticed.
    unmeasurable = {**m, "rust_tests": {"unmeasurable": "cargo is not on PATH"}}
    problems, notes = _check(unmeasurable, scopes=(("<probe>", "@@START", "@@END"),),
                             read=lambda _: "@@START\n**283 passed, 0 failed**\n@@END")
    real = [x for x in problems if not x.startswith("NO DOCUMENT")]
    if real or len(notes) != 1:
        failures += 1
        print(f"  FAIL an unmeasurable figure must be a NOTE, not a block: {real} / {notes}")
    else:
        print("  ok  an unmeasurable figure is a NOTE, not a block")

    # A moved anchor is a FINDING, not a silent pass.
    problems, _ = _check(m, scopes=(("<probe>", "NO SUCH MARKER", "@@END"),),
                         read=lambda _: "@@START\n**281 passed, 0 failed**\n@@END")
    if not any("marker" in x for x in problems):
        failures += 1
        print("  FAIL a moved anchor did not produce a finding")
    else:
        print("  ok  a moved anchor is a finding, not a silent pass")

    # The coverage arm: a claim shape with no subject anywhere.
    problems, _ = _check(m, scopes=(("<probe>", "@@START", "@@END"),),
                         read=lambda _: "@@START\nnothing here\n@@END")
    if not any(x.startswith("NO DOCUMENT") for x in problems):
        failures += 1
        print("  FAIL the coverage arm did not fire on a block with no claims")
    else:
        print("  ok  a claim shape with no subject anywhere is a finding")

    # `main()` must actually FAIL on a problem. Driven for real with a seeded
    # stale measurement -- the first version short-circuited before the
    # `if problems:` branch, so deleting that branch left the suite green.
    import contextlib
    import io as _io
    stale = {**m, "rust_tests": 1}
    with contextlib.redirect_stdout(_io.StringIO()), contextlib.redirect_stderr(_io.StringIO()):
        rc = main(argv=[], measure_fn=lambda: stale)
    if rc == 0:
        failures += 1
        print("  FAIL main() returned 0 with a seeded stale measurement")
    else:
        print("  ok  main() returns non-zero when a figure disagrees")
    # ...and zero when they agree. **The reason is PRINTED on failure.** The
    # first version redirected both streams into a bin and reported only
    # "returned non-zero on the real, agreeing documents" -- a message that
    # ASSERTS the thing that just turned out to be false, names "rules" rather
    # than the document, and throws away the list that says which figure is
    # stale. Reproduced by seeding one stale number in the handoff: the run was
    # red with an empty stderr and no way to find out why.
    real_out, real_err = _io.StringIO(), _io.StringIO()
    with contextlib.redirect_stdout(real_out), contextlib.redirect_stderr(real_err):
        rc_ok = main(argv=[], measure_fn=measure)
    if rc_ok != 0:
        failures += 1
        print("  FAIL a governed document carries a STALE figure. `main()` said:")
        for line in real_err.getvalue().splitlines():
            if line.strip():
                print(f"        {line}")
    else:
        print("  ok  main() returns zero when everything agrees")

    # `--print` must NEVER fail, whatever the documents say: it is the "show me
    # the measurements" mode a developer runs to FIX a stale figure. Deleting
    # `if args.print_only: return 0` left the suite green.
    with contextlib.redirect_stdout(_io.StringIO()), contextlib.redirect_stderr(_io.StringIO()):
        rc_print = main(argv=["--print"], measure_fn=lambda: stale)
    if rc_print != 0:
        failures += 1
        print("  FAIL --print returned non-zero; it must never fail")
    else:
        print("  ok  --print never fails, even with a stale figure")

    # The measurement helpers' guards, each driven directly.
    def guard(name: str, fn, want: str) -> None:
        """Assert `fn` degrades with an `Unmeasurable`, never a crash."""
        nonlocal failures
        try:
            fn()
        except Unmeasurable as e:
            ok = want in str(e)
            failures += 0 if ok else 1
            print(f"  {'ok ' if ok else 'FAIL'} {name}: {e}")
            return
        except Exception as e:  # noqa: BLE001 - the crash IS what this asserts against
            # **An exception inside a case is a failure OF THAT CASE.** Deleting
            # the guard this case defends makes the call raise a DIFFERENT
            # exception, which used to escape here, kill the run, and be counted
            # as a bite by the crash wrapper -- so the rule read RED for
            # eighteen rounds while this case never disagreed with anything.
            # Attributing it is the same argument the mutation harness makes
            # about a timeout: a finding about ONE case, not the end of the run.
            failures += 1
            print(f"  FAIL {name}: raised {type(e).__name__}: {e} — the whole "
                  "point is that it degrades instead")
            return
        failures += 1
        print(f"  FAIL {name}: no Unmeasurable raised")

    guard("an absent cargo is Unmeasurable, never a crash",
          lambda: _cargo_passed([], which=lambda _: None), "not on PATH")

    class _Red:
        returncode = 101
        stdout = "test result: FAILED. 3 passed; 1 failed"

    guard("a RED build is Unmeasurable, never a count of zero",
          lambda: _cargo_passed([], which=lambda _: "cargo", run=lambda _: _Red()), "not green")
    guard("a document with no bold id is Unmeasurable",
          lambda: _max_id("x", "D", read=lambda _: "no ids here"), "no bold D- id")

    # M6 -- the three rules that were RED with cargo and GREEN without. CI is the
    # only automatic runner of the mutation harness and has no Rust toolchain, so
    # these must be assertable with none.
    class _Green:
        returncode = 0
        stdout = ("test result: ok. 5 passed; 0 failed\n"
                  "test result: ok. 3 passed; 0 failed\n")

    total = _cargo_passed([], which=lambda _: "cargo", run=lambda _: _Green())
    if total != 8:
        failures += 1
        print(f"  FAIL passing counts must SUM across test binaries: got {total}, want 8")
    else:
        print("  ok  passing counts sum across every test binary")

    class _Mixed:
        returncode = 0
        stdout = ("test result: ok. 5 passed; 0 failed\n"
                  "test result: FAILED. 40 passed; 1 failed\n")

    try:
        _cargo_passed([], which=lambda _: "cargo", run=lambda _: _Mixed())
        failures += 1
        print("  FAIL a FAILED line among green ones must not be counted as passes")
    except Unmeasurable:
        print("  ok  a FAILED line among green ones is Unmeasurable, not 45")

    calls: list[list[str]] = []
    measure(cargo=lambda a: calls.append(list(a)) or 1)
    # **Written out, not derived from `CRATES`.** The first version built the
    # expectation with `sum([["-p", c] for c in CRATES], [])`, so truncating
    # `CRATES` to one crate moved BOTH sides of the comparison and the case
    # could not fail -- the subject-cannot-vary shape, in the file whose whole
    # subject is that shape.
    want_crates = ["-p", "actor-hub", "-p", "entity-existence", "-p", "ruleset-core",
                   "-p", "game-rules", "-p", "ruleset-loader"]
    if not calls or calls[0] != want_crates:
        failures += 1
        print(f"  FAIL the crate list is not what was measured: {calls[:1]}")
    elif len(calls) < 2 or calls[1] != ["-p", "dp-kernel", "--lib"]:
        failures += 1
        print(f"  FAIL dp-kernel must be measured with --lib, got {calls[1:2]}")
    else:
        print(f"  ok  cargo is asked for all {len(CRATES)} crates, and dp-kernel with --lib")

    # The hook scan must ignore COMMENTED invocations, or a documented-but-
    # disabled gate would be counted as wired.
    live = _hook_gate_scripts(read=lambda: '"$PY" "$ROOT/scripts/a-gate.py"\n# scripts/b-gate.py\n')
    if live != 1:
        failures += 1
        print(f"  FAIL the hook scan counted a commented invocation: got {live}, want 1")
    else:
        print("  ok  the hook scan ignores commented invocations")

    # **The escape list is re-derived from the tree, not trusted.** An
    # enumerated list is default-uncovered; this asserts that no document under
    # `docs/specs/2026-08-02-*` or `docs/plans/2026-08-02-*` cites a `D-1`..`D-N`
    # range without being on it. That is the mechanism the list itself is not.
    governed_escape = set(ESCAPE_DOCS) | {sc[0] for sc in SCOPES}
    # **Every markdown file under `docs/`.** The first version globbed
    # `docs/specs/2026-08-02-*` and `docs/plans/2026-08-02-*`, and the ternary
    # made the specs branch directory-only -- so `2026-08-02-item-data-structure.md`
    # and `2026-08-02-item-dataflow.md`, **two of its own ten entries**, were
    # unreachable by the assertion meant to police the list. A probe file one
    # directory over, or dated a day later, was default-uncovered too. A pair of
    # date-prefixed globs is an enumeration wearing a wildcard.
    missing_escape = _escape_derivation(governed_escape, real_m['max_decision_id'])
    if missing_escape:
        failures += 1
        print(f"  FAIL these cite a `D-1`..`D-N` range and no rule reads them: "
              f"{sorted(missing_escape)}")
    else:
        print(f"  ok  no document outside the {len(governed_escape)} governed ones "
              "cites the live range")

    # **And the walk is driven with a seeded probe**, because in a pristine tree
    # nothing is missing and the assertion above is DEFAULT-SATISFIED: narrowing
    # the glob back to `docs/*.md`, or deleting the report entirely, both left it
    # green. NV-1 inside the fix for NV-3.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        probe = Path(d) / "seeded-probe.md"
        probe.write_text(f"| x | it declares `D-1`..`D-{real_m['max_decision_id']}` |",
                         encoding="utf-8")
        seeded = _escape_derivation(governed_escape, real_m['max_decision_id'],
                                    corpus=lambda: [probe])
        if not seeded:
            failures += 1
            print("  FAIL a seeded document citing the live range was not reported")
        else:
            print("  ok  a document citing the live range and read by nothing is reported")

    # Every document this script MUST govern is actually in SCOPES. Iterating
    # SCOPES alone cannot notice a deleted row -- it just iterates one fewer.
    governed = {sc[0] for sc in SCOPES}
    for required in (HANDOFF, RUN_STATE, INDEX):
        if required not in governed:
            failures += 1
            print(f"  FAIL {required} is not in SCOPES, so nothing checks its figures")
    if len(SCOPES) < 4:
        failures += 1
        print(f"  FAIL SCOPES has {len(SCOPES)} entries; the slice board block is one of four")
    if governed >= {HANDOFF, RUN_STATE, INDEX} and len(SCOPES) >= 4:
        print(f"  ok  all {len(SCOPES)} required blocks are in scope")

    # And the REAL documents must each carry at least one governed claim.
    for doc, start_marker, end_marker, *_ in SCOPES:
        block = _scope_text(doc, start_marker, end_marker)
        if block is None:
            failures += 1
            print(f"  FAIL {doc}: its own marker does not resolve")
            continue
        subjects = sum(len(re.findall(pat, _claimable(block))) for pat, _, _ in CLAIMS)
        if subjects == 0:
            failures += 1
            print(f"  FAIL {doc}: its block contains NO claim this script governs")
        else:
            print(f"  ok  {doc}: {subjects} claim(s) in scope")

    if failures:
        print(f"\nactor-hub-figures --self-test: {failures} rule(s) did not behave")
        return 1
    print("\nactor-hub-figures --self-test: every rule bites, and none cries wolf")
    return 0


def _self_test_guarded(fn, name: str) -> int:
    """Run a self-test, reporting an ESCAPING EXCEPTION as a CRASH.

    **A self-test that dies has failed, and it must say so in its own
    vocabulary.** Four rules in this repo read RED for eighteen rounds purely
    because deleting them made the child raise: the harness saw a non-zero exit
    and called it a bite, while not one case had disagreed. `run_rust`'s
    compile-failure guard was written for exactly this on the Rust side; the
    Python side had nothing.
    """
    try:
        return fn()
    except BaseException as e:  # noqa: BLE001 - a crash IS the finding here
        # **`CRASH`, not `FAIL`, and the difference is load-bearing.** The first
        # version printed `FAIL`, which is exactly the token the mutation
        # harness counts as a case disagreeing -- so a child that DIED read as a
        # rule that BIT, which is the artifact the failing-case rule was written
        # in the same commit to end. Two decisions, each correct alone, the
        # later one defeating the earlier.
        #
        # The exit code is still non-zero, so a human and `gate-self-tests`
        # both see a red gate; only the harness's "did a case disagree"
        # question gets the honest answer, which is no.
        print(f"  CRASH {name} raised before finishing: {type(e).__name__}: {e}")
        print(f"{chr(10)}{name}: 1 rule(s) did not behave")
        return 1


def main(argv: list[str] | None = None, measure_fn=None) -> int:
    """`measure_fn` is injectable so `--self-test` can drive THIS function with a
    seeded stale measurement. The first version short-circuited before the
    `if problems:` branch, so deleting that branch left the suite green."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--print", action="store_true", dest="print_only",
                    help="measurements only; never fails")
    ap.add_argument("--check", action="store_true",
                    help="accepted for compatibility; checking is the default")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test_guarded(self_test, "actor-hub-figures --self-test")

    m = (measure_fn or measure)()
    print(json.dumps(m, indent=2, default=str))
    if args.print_only:
        return 0

    problems, notes = _check(m)
    for n in notes:
        print(f"actor-hub-figures: NOTE — {n}")
    if problems:
        print(f"\nactor-hub-figures: {len(problems)} disagreement(s)\n", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        print(
            "\nA figure that disagrees with this script is wrong by construction. "
            "READ the measurement above; do not advance the number.",
            file=sys.stderr,
        )
        return 1

    print("\nactor-hub-figures: every governed figure agrees with the artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
