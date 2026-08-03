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
SCOPES: tuple[tuple[str, str, str], ...] = (
    (HANDOFF, "## ▶ GAME TIER", "\n---\n"),
    (RUN_STATE, "> # ▶▶ NEXT SESSION STARTS HERE", "\n---\n"),
    # The SLICE BOARD's own summary block. A stop-audit found it STALE at
    # round seven -- "81 findings over five rounds" when the count was 123 over
    # seven -- because the check covered the header and the handoff and not the
    # board two screens below them. **A figure outside a checker's scope is a
    # figure nobody is reading**, which is `_index.md`'s defect one file along.
    (RUN_STATE, "### 6-BUILD", "| # | Slice |"),
    (INDEX, "# Actor Hub", "\n## Read this to REUSE"),
)


class Unmeasurable(Exception):
    """A figure that cannot be measured HERE — never a reason to block a commit."""


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
    out = (run or (lambda a: subprocess.run(
        ["cargo", "test", *a], cwd=REPO, capture_output=True, text=True)))(args)
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
    (r"`dp-kernel --lib` \*\*(\d+)\*\*", "dp_kernel_lib_tests", "dp-kernel lib tests"),
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
    # An info string may not contain the fence character (CommonMark), so a line
    # carrying a second run of backticks is an INLINE code span, not a fence.
    if m.group("mark")[0] in m.group("info"):
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


def _fence_state(prefix: str) -> str | None:
    """True when `prefix` ends INSIDE a fenced block.

    `>` is stripped first: this project writes whole headers as blockquotes, and
    the gate's own docstring says so, yet the marker test was `lstrip()` only --
    so a `> ```-fenced example of the header line was not recognised as a fence
    at all and was reported as a live claim. Cry-wolf, in the exact region the
    scope was drawn around.
    """
    open_mark: str | None = None
    for line in prefix.split("\n"):
        open_mark, _ = _advance(open_mark, line)
    return open_mark


def _claimable(block: str, quotes: bool = True, in_fence: str | None = None) -> str:
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
    out, in_comment, open_mark = [], False, in_fence
    for line in lines:
        stripped = line.lstrip()
        # **The comment state is tested FIRST.** It was tested second, so a fence
        # marker inside an HTML comment both flipped the fence parity AND stopped
        # `-->` from ever clearing the comment -- both flags stuck, and the rest
        # of the block went permanently blind. Two states, each correct alone,
        # the ORDER between them defeating both.
        if in_comment:
            out.append(" " * len(line))
            if "-->" in line:
                in_comment = False
            continue
        open_mark, is_mark = _advance(open_mark, line)
        if is_mark or open_mark is not None:
            out.append(" " * len(line))
            continue
        # An HTML comment spans lines. `startswith("<!--")` blanked only the
        # OPENING line, so the figures inside a multi-line comment stayed live
        # claims -- and an INLINE `<!-- ... -->` mid-line was not blanked at all.
        if in_comment:
            out.append(" " * len(line))
            if "-->" in line:
                in_comment = False
            continue
        # Inline `<!-- ... -->` spans first, so what remains is either no
        # comment at all or an OPENING with no close on this line -- which is how
        # a comment that starts mid-line (`superseded <!--`) gets caught. Testing
        # `stripped.startswith("<!--")` missed exactly that, one line after the
        # multi-line fix went in.
        line = COMMENT_RE.sub(lambda mo: " " * len(mo.group(0)), line)
        if "<!--" in line:
            in_comment = True
            out.append(" " * len(line))
            continue
        del stripped
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


def _scope_span(text: str, start_marker: str, end_marker: str) -> tuple[int, int] | None:
    """Character span of the current-state block, or None if EITHER anchor moved.

    **The end marker used to be optional.** A missing one silently widened the
    window to the whole file -- mass cry-wolf for the figure check, and total
    blindness for the escape rule, whose exempt span then covered the entire
    document. Only the START marker was reported. A scope with one asserted end
    and one guessed end is half a scope.
    """
    i = text.find(start_marker)
    if i < 0:
        return None
    j = text.find(end_marker, i + len(start_marker))
    return None if j < 0 else (i, j)


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
    return None if span is None else text[span[0]:span[1]]


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
    return re.compile(rf"`{prefix}-{first}`\s*\n?>?\s*\.\.\s*\n?>?\s*`{prefix}-(\d+)`")


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
    docs = sorted({d for d, _, _ in scopes} | (set(ESCAPE_DOCS) if scopes is SCOPES else set()))
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
        spans = [sp for d, sm, em in scopes if d == doc
                 for sp in [_scope_span(text, sm, em)] if sp]
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
    checked: dict[str, bool] = {}
    scopes = scopes if scopes is not None else SCOPES

    for doc, start_marker, end_marker in scopes:
        block = _scope_text(doc, start_marker, end_marker, read=read)
        # The fence state at the window's start, read from everything before it.
        # The first version defined `_fence_state`, added the parameter, and
        # never passed it -- so the fix was inert and its case was satisfied by
        # a coincidence: the same NUMBER of findings, about different lines.
        full = _read_doc(doc, read=read)
        span = _scope_span(full, start_marker, end_marker) if full is not None else None
        opens_fenced = _fence_state(full[:span[0]]) if (full is not None and span) else False
        if block is None:
            # **A moved anchor is a FINDING, not a silent pass.** The first
            # version set the text to "" and reported "the docs agree" against
            # zero subjects — a check whose scope never reaches it (NV-3).
            problems.append(
                f"{doc}: the markers `{start_marker}` .. `{end_marker}` do not both "
                "resolve, so this document was NOT checked"
            )
            continue
        block = _claimable(block, in_fence=opens_fenced)
        checked[doc] = checked.get(doc, False)
        for pattern, key, label in CLAIMS:
            want = m.get(key)
            for claimed in re.findall(pattern, block):
                checked[doc] = True
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
    # Only for the REAL scopes. A probe block whose single figure is correctly
    # blanked -- a fenced example, a quotation -- is indistinguishable from a
    # collapsed scope by this test, so applying it to injected scopes would red
    # every cry-wolf case in the suite. The subject is the shipped documents.
    for doc, start_marker, _ in (scopes if scopes is SCOPES else ()):
        if doc in checked and not checked[doc]:
            problems.append(
                f"{doc}: the block at `{start_marker}` contains NO figure this "
                "script governs — its end marker has probably moved up, which "
                "silently shrinks the scope rather than reporting anything"
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
        problems, notes = _check(m, scopes=(("<probe>", "@@", "@@END"),),
                                 read=lambda _: f"@@\n{text}\n@@END")
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
    # A fence OPENED inside the block and never closed keeps running to the end
    # of the block, because that is what it does in the document. Reporting the
    # figure below it would be cry-wolf on a code sample.
    check_block("a fence opened and not closed covers the rest of the block",
                "```rust\nlet x = 1;\n\nthe count is **281 passed, 0 failed** today", 0)
    # ...and a block that BEGINS INSIDE a fence is the case neither guess could
    # express. The state comes from the prefix, so the probe has to carry one:
    # here the fence opens BEFORE the window's start marker, and its closer
    # inside the window ends it -- after which the figure is live again.
    problems, _ = _check(m, scopes=(("<probe>", "@@", "@@END"),),
                         read=lambda _: "```rust\nlet x = 1;\n@@\nstill fenced "
                                        "**281 passed, 0 failed**\n```\n"
                                        "`dp-kernel --lib` **300**\n@@END")
    real = [x for x in problems if not x.startswith("NO DOCUMENT")]
    # **The IDENTITY of the finding, not its count.** Both the correct code and
    # the unwired version report exactly ONE problem here -- the correct one
    # about the line AFTER the closer, the broken one about the line before it.
    # A case that counts findings cannot tell those apart, and the mutation that
    # unwired the prefix state survived because the first version counted.
    if len(real) != 1 or "dp-kernel" not in real[0]:
        failures += 1
        print(f"  FAIL a block beginning INSIDE a fence: want 1 problem about "
              f"dp-kernel, got {real}")
    else:
        print("  ok  a block that begins inside a fence stays blanked until the closer")
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
        problems, _ = _check(meas or m, scopes=(("<probe>", "@@", "@@END"),),
                             read=lambda _: doc)
        got = [x for x in problems if "LIVE range" in x]
        ok = len(got) == want
        failures += 0 if ok else 1
        print(f"  {'ok ' if ok else 'FAIL'} {name}: expected {want}, got {len(got)}")
        for g in got if not ok else []:
            print(f"        {g}")

    escape_case("the live range inside the current-state block is correct",
                "@@\n`D-1`..`D-372`\n@@END", 0)
    escape_case("the live range OUTSIDE the block is a finding",
                "@@\nnothing\n@@END\n\n| D-195 | it declares `D-1`..`D-372` |", 1)
    # **B1 — the case the substring test could not fail.** The document carries
    # the live range INSIDE its block, which is the design, AND an escaped copy
    # outside it. `if any(mo.group(0) in b for b in blocks)` exempted the second
    # because the identical string appeared in the first, so two of the three
    # governed documents were unguarded -- including the very line the mechanism
    # had just repaired.
    escape_case("an escape in a document that LEGITIMATELY carries the live range",
                "@@\n`D-1`..`D-372`\n@@END\n\n| D-195 | it declares `D-1`..`D-372` |", 1)
    # The wrap tolerance itself: these documents wrap, and the blockquote form
    # puts `> ` between the two halves. Without it a wrapped live range escapes
    # entirely -- an adjacent decision (how the docs are written) defeating the
    # rule, which is the shape the sibling contract-lines pattern already carries
    # a tolerance for.
    escape_case("a WRAPPED live range is still an escape",
                "@@\nnothing\n@@END\n\n> | D-195 | it declares `D-1`..\n> `D-372` |", 1)
    escape_case("a HISTORICAL range outside the block is correct, and stays",
                "@@\nnothing\n@@END\n\n| D-195 | it declares `D-1`..`D-109` |", 0)
    # ...and with no measurable head there is nothing to compare against, so the
    # rule must stay SILENT rather than guess. Cry-wolf here would fire on every
    # machine without the artifact.
    escape_case("a FENCED example of the header is not an escape",
                "@@\nnothing\n@@END\n\n```\n`D-1`..`D-372`\n```", 0)
    escape_case("a QUOTATION carrying the live head IS an escape, by design",
                '@@\nnothing\n@@END\n\n| D-195 | it declares *"`D-1`..`D-372`"* |', 1)
    escape_case("an unmeasurable head accuses nobody",
                "@@\nnothing\n@@END\n\n| D-195 | `D-1`..`D-372` |", 0,
                meas={**m, "max_decision_id": {"unmeasurable": "no bold D- id"}})

    # A missing END marker must be a FINDING. It used to widen the window to
    # the whole file: mass cry-wolf for the figure check, and total blindness for
    # the escape rule, whose exempt span then covered the entire document.
    problems, _ = _check(m, scopes=(("<probe>", "@@", "NO SUCH END"),),
                         read=lambda _: "@@\n**281 passed, 0 failed**\n@@END")
    if not any("do not both" in x for x in problems):
        failures += 1
        print(f"  FAIL a missing END marker must be a finding, got {problems}")
    else:
        print("  ok  a missing end marker is a finding, not a whole-file window")

    # A block that RESOLVES but carries no governed figure is the other half of
    # the same defect: inserting a `---` inside the handoff block truncates it
    # silently, and the gate then agrees with whatever survived. Driven against
    # the REAL scopes, because that is the only place the rule applies.
    def _truncated(doc: str) -> str:
        text = (REPO / doc).read_text(encoding="utf-8", errors="replace")
        if doc != HANDOFF:
            return text
        i = text.find("## \u25b6 GAME TIER")
        return text[:i] + "## \u25b6 GAME TIER\n\n---\n" + text[i:]

    problems, _ = _check(m, read=_truncated)
    if not any("contains NO figure" in x for x in problems):
        failures += 1
        print("  FAIL a block truncated to nothing did not produce a finding")
    else:
        print("  ok  a scope that shrank to nothing is a finding, not agreement")

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
    problems, notes = _check(unmeasurable, scopes=(("<probe>", "@@", "@@END"),),
                             read=lambda _: "@@\n**283 passed, 0 failed**\n@@END")
    real = [x for x in problems if not x.startswith("NO DOCUMENT")]
    if real or len(notes) != 1:
        failures += 1
        print(f"  FAIL an unmeasurable figure must be a NOTE, not a block: {real} / {notes}")
    else:
        print("  ok  an unmeasurable figure is a NOTE, not a block")

    # A moved anchor is a FINDING, not a silent pass.
    problems, _ = _check(m, scopes=(("<probe>", "NO SUCH MARKER", "@@END"),),
                         read=lambda _: "@@\n**281 passed, 0 failed**\n@@END")
    if not any("marker" in x for x in problems):
        failures += 1
        print("  FAIL a moved anchor did not produce a finding")
    else:
        print("  ok  a moved anchor is a finding, not a silent pass")

    # The coverage arm: a claim shape with no subject anywhere.
    problems, _ = _check(m, scopes=(("<probe>", "@@", "@@END"),),
                         read=lambda _: "@@\nnothing here\n@@END")
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
        nonlocal failures
        try:
            fn()
        except Unmeasurable as e:
            ok = want in str(e)
            failures += 0 if ok else 1
            print(f"  {'ok ' if ok else 'FAIL'} {name}: {e}")
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
    governed_escape = set(ESCAPE_DOCS) | {d for d, _, _ in SCOPES}
    missing_escape = []
    for pattern in ("docs/specs/2026-08-02-*", "docs/plans/2026-08-02-*"):
        for path in REPO.glob(pattern + "/**/*.md" if "specs" in pattern else pattern + ".md"):
            rel = path.relative_to(REPO).as_posix()
            if rel in governed_escape:
                continue
            if RANGE_RE.search(path.read_text(encoding="utf-8", errors="replace")):
                missing_escape.append(rel)
    if missing_escape:
        failures += 1
        print(f"  FAIL these cite a `D-1`..`D-N` range and no rule reads them: "
              f"{sorted(missing_escape)}")
    else:
        print(f"  ok  all {len(governed_escape)} documents citing the range are read")

    # Every document this script MUST govern is actually in SCOPES. Iterating
    # SCOPES alone cannot notice a deleted row -- it just iterates one fewer.
    governed = {d for d, _, _ in SCOPES}
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
    for doc, start_marker, end_marker in SCOPES:
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
        return self_test()

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
