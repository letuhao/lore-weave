#!/usr/bin/env python3
"""Mutate each gate's production rules and require its `--self-test` to go RED.

WHY THIS EXISTS
---------------
A self-test's own claim — *"every rule bites"* — is a claim like any other, and
the only proof is a mutation that turns it red. `D-376` recorded twelve such
mutations as *"verified by a script that runs them"*. **The script existed only
in a session scratchpad.** A cold-start review looked for it, did not find it,
and pointed out that `D-380`'s own thesis — a check nobody runs is not a check —
applies to the artefact certifying `D-376`.

So it lives here, and it runs a mutation per PRODUCTION RULE, not per file.

IT NEVER TOUCHES THE REAL FILE
------------------------------
An earlier hand-run of this idea edited the gate in place and was killed
mid-run, leaving two `if False:` mutations in the working tree — caught by
running the self-test before committing, which is luck, not a mechanism. So the
harness mutates a COPY placed beside the original (same directory, so `REPO`
still resolves) and deletes it in a `finally`. The original is opened read-only.

    python scripts/gate-bite-harness.py             # every gate with a table
    python scripts/gate-bite-harness.py --gate citation-gate
    python scripts/gate-bite-harness.py --self-test
"""

from __future__ import annotations

import argparse
import os
import shutil
import re
import subprocess
import sys
from pathlib import Path

# A hanging self-test must not wedge a commit or burn a CI job to its cap.
CHILD_TIMEOUT_S = 300

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"


def _read(path: Path) -> str:
    """Text with `\n` newlines, for MATCHING. Never used to restore.

    Two requirements pull opposite ways and both are load-bearing:

      * **Restoring must be byte-exact.** `Path.read_text` + `Path.write_text`
        silently rewrites every line ending on Windows -- `write_text` opens in
        text mode, so `\n` becomes `\r\n`. A clean, fully-green `--rust` run
        left three Rust source files modified end to end: **the harness
        committing the very incident its module docstring says it was shaped
        by**, on the SUCCESS path rather than the interrupted one.
      * **Matching must be newline-agnostic.** The first fix made both sides
        byte-exact, and four `\n`-written anchors immediately stopped matching
        the CRLF crate files -- reported as drift, which is the harness telling
        the truth about a defect the fix had just introduced.

    So: match on normalised text, restore from the original BYTES.
    """
    return _raw(path).decode("utf-8").replace("\r\n", "\n")


def _raw(path: Path) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _write(path: Path, text: str, like: bytes | None = None) -> None:
    """Write `text`, re-applying the newline convention of `like` if given."""
    data = text.encode("utf-8")
    if like is not None and b"\r\n" in like:
        data = text.replace("\n", "\r\n").encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)

# gate -> [(label, find, replace)]. `find` must occur EXACTLY once: an anchor
# that has drifted is reported as a failure, not silently skipped, or the table
# rots into a list of no-ops that all pass.
MUTATIONS: dict[str, list[tuple[str, str, str]]] = {
    "actor-hub-figures-gate": [
        ("a stale figure is never reported",
         "                elif int(claimed) != want:", "                elif False:"),
        ("a moved anchor downgraded to a note",
         '            problems.append(\n                f"{doc}: the marker',
         '            notes.append(\n                f"{doc}: the marker'),
        ("the coverage arm disabled",
         "        if pattern not in seen:", "        if False:"),
        ("the unmeasurable branch skipped",
         "                if isinstance(want, dict):", "                if False:"),
        ("the live-range escape rule disabled",
         "    problems += _escaped_live_range(m, scopes=scopes, read=read)",
         "    problems += []"),
        ("the escape rule stops excluding the governed block",
         "                if any(a <= mo.start() < b for a, b in spans):",
         "                if False:"),
        # B1 -- the SPAN test degraded back to the substring test it replaced.
        # That version was defeated by the two documents that legitimately carry
        # the live range, so it exempted every other occurrence in those files.
        ("block membership degraded from a span to a substring",
         "                if any(a <= mo.start() < b for a, b in spans):",
         "                if any(mo.group(0) in text[a:b] for a, b in spans):"),
        # Both LINES of the tuple: deleting the first left the continuation
        # dangling, so the child died in the parser and no case ran -- the very
        # question `D-467` asks of the Rust half, never asked of this one.
        ("the 6-BUILD scope row deleted",
         '    (RUN_STATE, "### 6-BUILD", END("slice-board"),\n'
         '     frozenset({"rust_tests", "dp_kernel_lib_tests"})),', ""),
        # **`D-470` fixed the row above and not this one, in the same
        # table.** Deleting only the first line of a two-line tuple left
        # `(\n frozenset({...})),` -- a 1-tuple holding a frozenset -- so the
        # child reached 62 cases, raised `TypeError`, printed ZERO `FAIL` lines
        # and was still reported RED. The instance fixed, the class left, and
        # the very next row of the same table the counter-example.
        ("the _index.md scope row deleted",
         '    (INDEX, "# Actor Hub", END("index"),\n'
         '     frozenset({"max_decision_id", "max_seam_id", "contract_hub_lines",\n'
         '                "contract_substrate_lines", "contract_seams_lines",\n'
         '                "contract_total_lines"})),', ""),
        ("the red-build guard removed",
         '    if "test result: FAILED" in out.stdout or out.returncode != 0:',
         "    if False:"),
        # --- the reality-layer widening (2026-08-11) ------------------------
        # The second track this gate governs. Its rules had a self-test and no
        # MUTATION rows, which is half a proof: a case asserts the rule works
        # TODAY, a mutation asserts the case would notice if it stopped.
        ("the reality-layer scope row deleted",
         '    (REALITY_RUN_STATE, "## 1 · MEASURED STATE", END("reality-measured-state"),\n'
         '     frozenset({"rl_realities", "rl_reality_tables", "rl_reality_migrations",\n'
         '                "rl_meta_tables", "rl_meta_migrations", "rl_shards",\n'
         '                "rl_world_service_bins", "rl_admin_registries",\n'
         '                "rl_compose_game_tier", "rl_pg_login_roles"})),', ""),
        ("the psql-absent guard removed",
         '    if (which or shutil.which)("psql") is None:', "    if False:"),
        ("the psql error branch removed",
         "    if out.returncode != 0:", "    if False:"),
        # `int("t")` is a raw ValueError out of a pre-commit hook -- this file's
        # oldest failure shape, three helpers along.
        ("the non-count scalar guard removed",
         '    if not re.fullmatch(r"\\d+", scalar):', "    if False:"),
        # THE REACH FAMILY. A glob whose directory moved matches nothing, and a
        # walk that reaches nothing is byte-identical to a clean tree.
        ("the empty-glob reach guard removed",
         "    hits = sorted(REPO.glob(pattern))\n    if not hits:",
         "    hits = sorted(REPO.glob(pattern))\n    if False:"),
        # A port or password PINNED here instead of read from compose is a
        # second SSOT that rots -- the exact defect the widening exists to
        # catch, committed inside the mechanism.
        ("the dev DSN pinned instead of read from compose",
         '    return ("localhost",',
         '    return ("localhost", "5555", "loreweave", "loreweave_dev")\n'
         '    return ("localhost",'),
        # WHICH database is the document's claim; how many tables it holds is
        # Postgres's. Pinning the name measures a different subject from the
        # sentence the day the exemplar changes.
        ("the exemplar reality database pinned instead of read",
         "    return names[0]", '    return "lw_reality_cd0747d24b94"'),
        ("the cargo-absent guard removed",
         '    if (which or shutil.which)("cargo") is None:', "    if False:"),
        ("the empty-id guard removed", "    if not ids:", "    if False:"),
        ("the hook scan counts commented invocations",
         '    body = "\\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))',
         "    body = text"),
        ("main() stops failing",
         '    if problems:\n        print(f"\\nactor-hub-figures: {len(problems)} disagreement(s)',
         '    if False:\n        print(f"\\nactor-hub-figures: {len(problems)} disagreement(s)'),
        ("--print starts failing", "    if args.print_only:\n        return 0",
         "    if False:\n        return 0"),
        ("fence/comment/quote blanking removed (cry wolf)",
         "        block = _claimable(block, in_fence=opens_fenced, in_comment=opens_commented)",
         "        block = block"),
        # The prefix state must be PASSED, not merely computed. The first fix
        # defined `_fence_state`, added the parameter, and never wired it -- and
        # its case passed anyway, because the correct code and the unwired
        # version report the SAME NUMBER of findings about DIFFERENT lines.
        ("the prefix fence state computed and not passed",
         "        block = _claimable(block, in_fence=opens_fenced, in_comment=opens_commented)",
         "        block = _claimable(block)"),
        ("the fence state is GUESSED instead of taken from the prefix",
         "    out, open_mark = [], in_fence",
         "    out, open_mark = [], None"),
        # REMOVED: `is_mark or ...` vs `...` is an EQUIVALENT mutant once a
        # closer is required to carry no info string. The two differ only on the
        # CLOSING line -- an opener leaves `open_mark` set, so it is blanked
        # either way -- and a valid closer is a bare run of backticks with
        # nothing on it to be live. Deleting the row rather than contriving a
        # case, for the same reason the test-result regex row went.
        ("the prefix fence scan returns nothing",
         "        open_mark, in_comment, _ = _scan_line(open_mark, in_comment, line)\n"
         "    return open_mark, in_comment",
         "        open_mark, in_comment, _ = _scan_line(open_mark, in_comment, line)\n"
         "    return None, in_comment"),
        # M2 -- the prefix scan had no comment tracking at all, so ONE fence
        # marker inside an HTML comment above a block flipped it into a fence
        # that never closed: a blinded slice board one way, and a refusal on a
        # perfectly correct handoff the other, from the repo-wide hook.
        ("the prefix comment state is dropped",
         "        open_mark, in_comment, _ = _scan_line(open_mark, in_comment, line)\n"
         "    return open_mark, in_comment",
         "        open_mark, in_comment, _ = _scan_line(open_mark, in_comment, line)\n"
         "    return open_mark, False"),
        ("the scanner stops opening multi-line comments",
         '    if "<!--" in COMMENT_RE.sub("", line):\n        return after, True, True',
         "    if False:\n        return after, True, True"),
        ("a BLOCKQUOTE fence stops being a fence",
         'FENCE_RE = re.compile(r"^\\s*(?:>\\s*)*(?P<mark>`{3,}|~{3,})(?P<info>.*)$")',
         'FENCE_RE = re.compile(r"^\\s*(?P<mark>`{3,}|~{3,})(?P<info>.*)$")'),
        # M9 -- a marker is not a toggle. Counting every one flipped the state on
        # a longer outer fence (the idiom for DOCUMENTING a fence) and exposed
        # its contents as live claims: cry-wolf, the severe direction.
        ("a fence closes on ANY marker, not the same one",
         "    if (mark[0] == open_mark[0] and len(mark) >= len(open_mark)",
         "    if (True or (mark[0] == open_mark[0] and len(mark) >= len(open_mark))"),
        # ...and the CommonMark rule that a CLOSER carries no info string. A
        # backtick line WITH text is fence content; treating it as a closer
        # exposed everything after it as live claims.
        ("a closer may carry an info string again",
         '            and not (FENCE_RE.match(line).group("info") or "").strip()):',
         "            and True):"),
        ("an inline code span counts as a fence opener",
         '    if m.group("mark")[0] == "`" and "`" in m.group("info"):\n        return None',
         "    if False:\n        return None"),
        # minor 6 -- the rule applied to BOTH fence characters, but CommonMark
        # forbids backticks only in a BACKTICK fence's info string. `~~~ ~x~`
        # was therefore not a fence at all and its contents were reported as
        # live claims: cry-wolf on a shape the spec allows.
        ("the info-string rule applies to tildes too",
         '    if m.group("mark")[0] == "`" and "`" in m.group("info"):',
         '    if m.group("mark")[0] in m.group("info"):'),
        # ...and the ORDER of the two states. Testing the fence first left both
        # flags stuck true on a fence marker inside a comment.
        ("the comment state is tested AFTER the fence again",
         '    if in_comment:\n        return open_mark, "-->" not in line, True\n'
         "    after, is_mark = _advance(open_mark, line)",
         "    after, is_mark = _advance(open_mark, line)"),
        # M2 -- a missing END marker silently widened the window to the whole
        # file: mass cry-wolf for the figures, total blindness for the escape
        # rule, and nothing reported.
        ("a missing end marker widens the scope to the whole file",
         "    if not hits:\n        return None",
         "    if False:\n        return None"),
        # B1 -- deletion was never the defect; PREMATURE TERMINATION was, and a
        # SECOND marker does it exactly as the first incidental `---` did.
        ("a second end marker silently shortens the block",
         "    if len(hits) > 1:", "    if False:"),
        # ...and a marker MENTIONED in prose or an inline code span -- which is
        # what documenting it looks like -- must not terminate anything.
        ("a marker mentioned mid-line terminates the block",
         "        hits = tuple(k for k in _all_occurrences(haystack, needle, start)\n"
         "                     if _at_line_start(haystack, k, needle))",
         "        hits = tuple(_all_occurrences(haystack, needle, start))"),
        # B2 -- the END marker was hardened and the START marker had a raw
        # `find`, so documenting it inline moved the block 260 lines up and the
        # message blamed the wrong marker.
        ("the start marker goes back to a raw find",
         "    starts = _marker_hits(text, start_marker, 0)",
         "    starts = [text.find(start_marker)] if start_marker in text else []"),
        ("a duplicated START marker is accepted",
         "    if len(starts) > 1:", "    if False:"),
        # M2 -- a fenced EXAMPLE of a marker must not terminate anything, or the
        # record documenting this gate cannot show its own markers.
        ("a fenced example of a marker terminates the block",
         "    for haystack in (_indented_blanked(_claimable(text, quotes=False, comments=False)),\n"
         "                     text):",
         "    for haystack in (text,):"),
        # O-R15-6 -- markdown has TWO literal forms and this file handled one, so
        # showing the sentinel INDENTED reported it as a duplicate and refused.
        ("an indented example of a marker terminates the block",
         "    return chr(10).join(\n"
         '        " " * len(l) if INDENT_CODE.match(l) else l for l in text.split(chr(10)))',
         "    return text"),
        # O-R15-1 -- the raw fallback reached the marker search and not the
        # CONTENT blanking, so an unterminated fence refused the commit while
        # naming a cause that was not the cause.
        ("an unpaired fence opener blankets the rest of the block again",
         "    unpaired_at = None if in_fence is not None else _unpaired_opener(lines)",
         "    unpaired_at = None"),
        # R16/B1 -- the predicate asked about the DOCUMENT and the action masked
        # every fence in it, so one unterminated fence un-fenced every correctly
        # paired block above: three measured refusals on the shipped documents.
        ("the unpaired mask covers the whole text again",
         "        lines = lines[:unpaired_at] + [",
         "        lines = lines[:0] + ["),
        ("the unpaired scan stops seeing tilde fences",
         "    open_mark, at = None, None", "    open_mark, at = '~~~', None"),
        ("the caller's fence state stops suppressing the mask",
         "    unpaired_at = None if in_fence is not None else _unpaired_opener(lines)",
         "    unpaired_at = _unpaired_opener(lines)"),
        # R16/M8 -- markdown's two indent forms, one cased and its twin not, in
        # the round whose headline is exactly that.
        ("the tab half of the indent rule",
         'INDENT_CODE = re.compile(r"^(?: {4}|\\t)")',
         'INDENT_CODE = re.compile(r"^(?: {4})")'),
        ("the tab half of the blockquote prefix",
         'QUOTE_PREFIX = re.compile(r"^[ \\t>]*")',
         'QUOTE_PREFIX = re.compile(r"^[ >]*")'),
        # R16/M9 -- "every scope ends on a NAMED sentinel" was made true by
        # editing data, with nothing asserting the shape.
        ("a scope end reverts to a heading",
         '    (INDEX, "# Actor Hub", END("index"),',
         '    (INDEX, "# Actor Hub", "\\n## Read this to REUSE",'),
        # R16/M5 -- the `must_claim` surplus was recorded as closing the
        # sentinel-moved-up hole and does not: it is keyed by measurement KEY,
        # so a SECOND occurrence of a key already named is not surplus.
        ("the orphaned tail is never scanned",
         "    for (doc, start_marker), (tail, opens, commented) in tails.items():",
         "    for (doc, start_marker), (tail, opens, commented) in []:"),
        # R17/M2 -- the scan took `_fence_state(...)[0]` and dropped the comment
        # half, two lines below the call that passes both for the block.
        ("the tail loses the prefix state entirely",
         "            tails[(doc, start_marker)] = (full[a:b], *_fence_state(full[:a]))",
         "            tails[(doc, start_marker)] = (full[a:b], None, False)"),
        # RETIRED: "the tail keeps the fence half and drops the comment half".
        # A round-18 measurement proved the comment half CANNOT VARY while every
        # scope ends on a sentinel -- 0 of 11 prefix shapes -- so the row and its
        # case were certifying coverage that does not exist. The disclosure lives
        # beside the code. The FENCE half keeps its row, above.
        # R17/m3 -- the sentinel assertion could be weakened to accept any HTML
        # comment, because its only case reverted the DATA to a heading.
        ("the sentinel shape accepts any HTML comment",
         'SENTINEL_RE = re.compile(r"^<!-- actor-hub-figures:end [a-z0-9-]+ -->$")',
         'SENTINEL_RE = re.compile(r"^<!--")'),
        ("the tail terminator loses its blockquote prefix",
         'TAIL_END_RE = re.compile(r"^[ \\t>]*(?:#{1,6}[ \\t]|\\|)")',
         'TAIL_END_RE = re.compile(r"^(?:#{1,6}[ \\t]|\\|)")'),
        ("the tail runs to the next heading only",
         'TAIL_END_RE = re.compile(r"^[ \\t>]*(?:#{1,6}[ \\t]|\\|)")',
         'TAIL_END_RE = re.compile(r"^[ \\t>]*(?:#{1,6}[ \\t])")'),
        # R16/minor 1 -- the detector's SHAPE was its own case's shape.
        # R16 -- the widened shape STILL missed `**0\n> warnings**`, the
        # slice board's copy of a claim measured FALSE at round 12 and corrected
        # in the header block only. The sibling `contract_substrate_lines` pattern
        # in that same file has carried the wrap tolerance from the start.
        # R21 -- the two CACHES. A cache cannot make a check fail; it can only
        # make it answer from the wrong place, which is why it needs a witness
        # rather than a code review. A third cache (file reads, keyed on
        # path+mtime+size) was REMOVED instead of cased: nothing could tell it
        # apart, because the documents do not change while the process runs, and
        # measured best-of-three it was worth 0.04s of 2.94s.
        # **The anchor carries its `key =` line, and that is not decoration.**
        # `_psql` (2026-08-11) copied this bypass verbatim, so the one-line
        # anchor started matching TWICE and the harness reported table drift.
        # It reported rather than guessed, which is the whole design — but the
        # lesson is the older one this file keeps relearning: **a rule written
        # twice is a rule with half a test**, so the copy gets its own row below
        # instead of sharing this one.
        ("the cargo memo forgets that an injected runner is not the real one",
         "    cacheable = run is None and which is None\n    key = tuple(args)",
         "    cacheable = True\n    key = tuple(args)"),
        ("the psql memo forgets that an injected runner is not the real one",
         "    cacheable = run is None and which is None\n    key = (db, sql)",
         "    cacheable = True\n    key = (db, sql)"),
        ("the blanking cache drops an argument from its key",
         "@functools.lru_cache(maxsize=4096)\ndef _claimable(",
         "@functools.lru_cache(maxsize=4096)\n"
         "def _claimable_keyed(block, quotes=True, in_fence=None, in_comment=False,\n"
         "                     comments=True):\n"
         "    return _claimable_real(block, quotes, in_fence, in_comment, comments)\n"
         "\n"
         "\ndef _claimable(block, quotes=True, in_fence=None, in_comment=False,\n"
         "               comments=True):\n"
         "    return _claimable_keyed(block)\n"
         "\n"
         "\ndef _claimable_real("),
        ("the bolded-figure shape loses its wrap tolerance",
         '    r"\\*\\*\\d[\\d,. \\u00a0]*(?:[ \\t\\n>]*"',
         '    r"\\*\\*\\d[\\d,. \\u00a0]*(?:[ \\t]*"'),
        # R19/M3 -- the word bound was an ENUMERATION, and a four-word
        # figure walked through it in the governed block ONE ROUND after it
        # was set. Measured: unbounded adds zero findings on all four blocks.
        ("the bolded-figure shape re-bounds the word run",
         '    + r"(?:[ \\t\\n>]+" + _FIGURE_WORD + r")*)?\\*\\*")',
         '    + r"(?:[ \\t\\n>]+" + _FIGURE_WORD + r"){0,3})?\\*\\*")'),
        ("the bolded-figure shape narrows to a bare integer",
         'BOLD_INT_RE = re.compile(\n'
         '    r"\\*\\*\\d[\\d,. \\u00a0]*(?:[ \\t\\n>]*" + _FIGURE_WORD\n'
         '    + r"(?:[ \\t\\n>]+" + _FIGURE_WORD + r")*)?\\*\\*")',
         'BOLD_INT_RE = re.compile(r"\\*\\*\\d+\\*\\*")'),
        # R20/1 -- LINEARITY. The shipped shape was exponential and every case
        # still passed, so the only witness is the wall clock. One token: with
        # an OPTIONAL separator a single word can be re-parsed as two, and that
        # ambiguity alone is worth ~4s on the 24-word probe against a 0.5s
        # budget. A two-phase span/body split was tried here too and removed --
        # its span half was redundant, and the mutation restoring the old regex
        # HUNG the child rather than failing a case, so nothing could guard it.
        ("the bolded-figure word separator becomes optional",
         '    + r"(?:[ \\t\\n>]+"',
         '    + r"(?:[ \\t\\n>]*"'),
        ("the dp-kernel rule stops reading the slice board's phrasing",
         r'    (r"`dp-kernel --lib` \*\*(\d+)(?: passed)?\*\*", "dp_kernel_lib_tests",',
         r'    (r"`dp-kernel --lib` \*\*(\d+)\*\*", "dp_kernel_lib_tests",'),
        ("the unpaired-opener scan never finds one",
         "    return at if open_mark is not None else None", "    return None"),
        # O-R15-3 -- `must_claim` was a lower bound while its sibling
        # enumeration is re-derived from the tree.
        ("the must_claim surplus is not reported",
         "        surplus = sorted(present.get((doc, start_marker), set()) - want)",
         "        surplus = []"),
        # O-R15-4 -- no detector for a bolded figure inside a governed block
        # that no rule reads; three rounds found one by hand.
        ("an ungoverned bolded figure is not reported",
         "        for mo in BOLD_INT_RE.finditer(text):", "        for mo in []:"),
        ("the claim spans are never recorded",
         "                claim_spans[(doc, start_marker)].append(mo.span())",
         "                pass"),
        # M1 -- the last route to a silently shortened scope: MOVING the one
        # sentinel up leaves a claim behind, so the empty-block rule stays quiet.
        ("the required-figures rule removed",
         "        missing = sorted((rest[0] if rest else frozenset()) - "
         "present.get((doc, start_marker), set()))",
         "        missing = []"),
        # The empty-block rule is gone -- `must_claim` supersedes it -- so this
        # row now targets the rule that replaced it.
        ("the required-figures rule stops reporting",
         "        if missing:", "        if False:"),
        # B1 -- the block end was the first incidental `---`, so an ordinary
        # markdown edit silently ungoverned everything below it, and the
        # empty-block rule caught only TOTAL collapse.
        ("the block end goes back to the first horizontal rule",
         '    return f"<!-- actor-hub-figures:end {block} -->"',
         '    return "\\n---\\n"'),
        # Each block's sentinel is NAMED, or "exactly once in the file" stops
        # meaning anything the moment a second block wants one: three
        # legitimate markers, and the duplicate rule fires on all three.
        ("the end sentinels stop being named per block",
         '    return f"<!-- actor-hub-figures:end {block} -->"',
         '    return "<!-- actor-hub-figures:end -->"'),
        # M1 -- `RUN_STATE` appears twice in SCOPES, so a per-document key let
        # one block vouch for the other. `checked` is gone (superseded by
        # `must_claim`); the key that matters now is `present`.
        ("the required-figures key drops the start marker",
         "                present[(doc, start_marker)].add(key)",
         '                present[(doc, "")] = present.get((doc, ""), set()) | {key}'),
        # M1 -- the escape rule read only the three files with a current-state
        # block. Eight more carried the range and stayed green, two of them files
        # this same gate already opens.
        ("the escape rule reads only the SCOPES documents",
         "    docs = sorted({sc[0] for sc in scopes} | "
         "(set(ESCAPE_DOCS) if scopes is SCOPES else set()))",
         "    docs = sorted({sc[0] for sc in scopes})"),
        ("the inline comment span not blanked",
         '        line = COMMENT_RE.sub(lambda mo: " " * len(mo.group(0)), line)',
         "        line = line"),
        ("the escape scan stops blanking fences (cry wolf on an example)",
         "        scan = _claimable(text, quotes=False)", "        scan = text"),
        ("the escape scan starts exempting quotations",
         "        scan = _claimable(text, quotes=False)", "        scan = _claimable(text)"),
        # M1 -- the index TABLE rows, which no pattern reached while four figures
        # inside a governed block were stale.
        ("the index table's hub-lines row deleted",
         '    (r"\\(2026-08-02-actor-hub\\.md\\)\\s*\\|\\s*(\\d+)\\s*\\|", "contract_hub_lines",\n'
         '     "the hub contract\'s lines, in the index table"),',
         ""),
        ("the contracts' TOTAL row deleted",
         '    (r"\\*\\*(\\d+) lines total\\.\\*\\*", "contract_total_lines", "the three contracts\' total lines"),',
         ""),
        ("the total stops being a sum",
         "        sum(counts) if all(isinstance(c, int) for c in counts)",
         "        0 if all(isinstance(c, int) for c in counts)"),
        # M6 -- the three rules that were covered only on a machine with cargo.
        ("the crate list truncated to one crate",
         'CRATES = ["actor-hub", "entity-existence", "ruleset-core", "game-rules", "ruleset-loader"]',
         'CRATES = ["actor-hub"]'),
        ("dp-kernel measured WITHOUT --lib",
         '("dp_kernel_lib_tests", lambda: passed(["-p", "dp-kernel", "--lib"])),',
         '("dp_kernel_lib_tests", lambda: passed(["-p", "dp-kernel"])),'),
        # REMOVED: widening the result regex from `ok\\.` to `\\S+` is an
        # EQUIVALENT mutant, because the red-build guard three lines above it
        # rejects any output containing `test result: FAILED` before the regex
        # runs -- and `ok` and `FAILED` are the only two summary forms cargo
        # emits. A review measured it RED with a real toolchain and GREEN
        # without; the difference is not the toolchain, it is that no input
        # reaching this line can distinguish the two patterns. **Recorded rather
        # than papered over with a case that would have to be contrived**: an
        # adjacent decision making a mutation equivalent is a fact about the
        # design, and the honest response is to delete the row.
        # m4 -- the wrap tolerance the sibling pattern already carried.
        ("the range pattern loses its line-wrap tolerance",
         'r"\\s*\\n?>?\\s*\\.\\.\\s*\\n?>?\\s*"',
         'r"\\.\\."'),
        # minor 1 -- the backticks were REQUIRED, so the un-backticked form (seven
        # occurrences in the RUN-STATE alone) was invisible to the rule and to the
        # coverage assertion, which shares the regex.
        ("the range pattern requires backticks again",
         '    t = "`?"', '    t = "`"'),
        # M3 -- the derivation must ask the question the RULE asks. Asking "does
        # this cite A range" reported ten documents belonging to other rounds'
        # own `D-` registers; asking "does it cite THE LIVE one" is the rule.
        ("the escape derivation stops matching the head",
         "        if any(int(m) == head for m in RANGE_RE.findall(text)):",
         "        if RANGE_RE.search(text):"),
        ("the escape derivation walks only the docs root",
         '    return sorted(REPO.glob("docs/**/*.md"))',
         '    return sorted(REPO.glob("docs/*.md"))'),
        # REMOVED: the degrade-safety assertion is a CASE, not a production
        # rule, and mutating a case cannot red the suite it belongs to -- the
        # same mis-target as the discovery floor two rounds ago. The production
        # behaviour it guards (an unmeasurable figure is a NOTE, never a block)
        # is covered by "the unmeasurable branch skipped", which reds.
        ("the substrate contract row deleted",
         '    (r"and\\s*\\n?>?\\s*\\*\\*(\\d+)\\*\\*\\s*\\n?>?\\s*lines", "contract_substrate_lines", "the substrate contract\'s lines"),',
         ""),
    ],
    "gate-self-tests": [
        ("a red gate no longer fails the run", "    if failed:", "    if False:"),
        # R16/M4 -- ONE hanging gate aborted THIS driver, the one the pre-commit
        # hook runs, with a raw traceback; the gates after it were reported by
        # nothing. The mutation harness carries the guard and its comment
        # describes this exact failure, about itself. Never written here.
        ("the driver's timeout handler removed",
         "        except subprocess.TimeoutExpired:\n"
         "            ms = int((time.time() - t0) * 1000)",
         "        except ValueError:\n"
         "            ms = int((time.time() - t0) * 1000)"),
        ("a hanging gate stops failing the run",
         '            print(f"  SLOW {p.name:<44} {ms:>6}ms -> no verdict in '
         '{CHILD_TIMEOUT_S}s")\n            failed.append(p.name)',
         '            print(f"  SLOW {p.name:<44} {ms:>6}ms -> no verdict in '
         '{CHILD_TIMEOUT_S}s")',
         ),
        ("the failing child's reason is swallowed",
         "            for line in (out.stdout + out.stderr).splitlines():",
         "            for line in []:"),
        ("discovery stops excluding this driver and scratch copies",
         '        if p.name == SELF or p.name.startswith("."):\n            continue',
         "        if False:\n            continue"),
        ("the discovery predicate matches everything",
         '            if advertised_flag(p.read_text(encoding="utf-8", errors="replace")):',
         "            if True:"),
        # M8 -- the predicate counted a MENTION of the flag as having one. A gate
        # in this tree names it in two comments, has no self-test, was invoked,
        # ignored the flag, exited 0, and was counted green.
        # The anchor is inside `advertised_flag` now, not at the call site: the
        # predicate moved there when the driver learned the second spelling
        # (2026-08-07). Both anchors went stale in that edit and THIS HARNESS is
        # what said so -- "occurs 0x outside the tables" -- which is the mutation
        # equivalent of BDR-30: a mutation whose target no longer exists applies
        # nowhere and reports green.
        ("the predicate counts prose as code again",
         "    m = FLAG_RE.search(_code_only(src))",
         "    m = FLAG_RE.search(src)"),
        ("the routing to self_test() removed",
         '    mode = _route(args)\n    if mode == "self-test":',
         '    mode = _route(args)\n    if False:'),
        ("discovery stops being recursive",
         '    for p in sorted(root.rglob("*.py")):',
         '    for p in sorted(root.glob("*.py")):'),
        # Targeted at `main`'s floor, not at the assertion inside `self_test`.
        # Mutating a CASE cannot red the suite it belongs to, so the first
        # version of this row surveyed nothing and reported GREEN — which is how
        # the production floor turned out to have no case at all.
        ("the discovery floor removed from main()",
         '    if len(found) < MIN_EXPECTED:\n        print(f"gate-self-tests: discovery found only',
         '    if False:\n        print(f"gate-self-tests: discovery found only'),
        ("the discovery injection ignored", "    found = (discover_fn or discover)()",
         "    found = discover()"),
    ],
    # **This file mutates ITSELF.** Round 12 measured 19 of 19 mutations of its
    # own new code surviving, because `--self-test` drives every helper with an
    # injected runner and so cannot reach the rules about the real invocation.
    # A harness that verifies other code and not itself is the regress it says
    # it stops at, pointed the wrong way.
    "gate-bite-harness": [
        # B1 -- the harness never ran an unmutated BASELINE, so it could not
        # tell "every rule bites" from "the suite is already broken": CI's
        # `--no-cargo` job reported 47 of 47 red while three NULL mutations were
        # also red, and the defect was found by a human doing it by hand.
        ("the baseline is never run",
         "    reason = baseline_is_green(gate, run=run, no_cargo=no_cargo)",
         "    reason = None"),
        ("a red baseline is reported as surviving rules",
         "        return -(len(rows) or 1)", "        return len(rows) or 1"),
        # M5 -- `CHILD_TIMEOUT_S` was configured and never caught, so a slow
        # child aborted the run with a raw traceback.
        ("the timeout handler removed",
         "        except subprocess.TimeoutExpired:\n"
         "            # A timeout is a FINDING about that mutation, not the end of the",
         "        except ValueError:\n"
         "            # A timeout is a FINDING about that mutation, not the end of the"),
        # M6 -- D-428's own fix was unguarded: without the exclusion every row of
        # this table goes red for a reason unrelated to the rule.
        # B2 -- `baseline_is_green` got two rows and three cases this round; its
        # TWIN, written in the same commit for the same reason, got none. A
        # seeded red `fold_survivors` proved it: rc 2 with the guard, rc 0 and
        # "every Rust mutation reddened its test" without.
        ("the RUST baseline is never checked",
         "        probe = baseline()", "        probe = None"),
        ("the RUST baseline probe's verdict is discarded",
         "    if probe is not None and probe.returncode != 0:",
         "    if probe is not None and False:"),
        # B3 -- the negative sentinel was guarded at its PRODUCER and not at its
        # CONSUMER, so a red baseline could cancel a real survivor into rc 0.
        ("the negative-baseline sentinel is ignored by main",
         "    if any(v < 0 for v in results):", "    if False:"),
        # M5 -- the forwarding to the MUTATION child got a sentinel case this
        # round; the forwarding to the BASELINE child got none, so a baseline
        # could pass in an environment the mutations never run in.
        ("the baseline child runs in a different environment",
         "        text=True, timeout=CHILD_TIMEOUT_S, env=_child_env(no_cargo)))",
         "        text=True, timeout=CHILD_TIMEOUT_S))"),
        # M6 -- the gate half counts a drifted anchor and a timeout as survivors
        # and has cases for both; the Rust half counted them and had neither.
        ("a drifted RUST anchor is not counted",
         '                print(f"  DRIFT  {label:52} anchor occurs {src.count(find)}x")\n'
         "                green += 1",
         '                print(f"  DRIFT  {label:52} anchor occurs {src.count(find)}x")\n'
         "                green += 0"),
        ("a timed-out RUST child is not counted",
         '                print(f"  SLOW   {label:52} -> no verdict in {CHILD_TIMEOUT_S}s")\n'
         "                green += 1",
         '                print(f"  SLOW   {label:52} -> no verdict in {CHILD_TIMEOUT_S}s")\n'
         "                green += 0"),
        ("the leftover check stops excluding this file's copy",
         "    leftover = [q for q in SCRIPTS.glob(\".bite-*.py\") "
         "if q.name != Path(__file__).name]",
         "    leftover = list(SCRIPTS.glob(\".bite-*.py\"))"),
        # M4 -- `--self-test` drives `run_rust` three times and the pre-commit
        # hook runs `--self-test`, so an uninjectable writer meant 30 in-place
        # writes to the shipped crate sources on every commit.
        ("the rust writer stops being injectable",
         "            (write or _write)(path, mutated, like=raws[rel])",
         "            _write(path, mutated, like=raws[rel])"),
        # B2 -- `--rust --only <nothing>` executed zero mutations and printed
        # "every Rust mutation reddened its test" with exit 0: the sole signal
        # of the CI job that mode exists for, reporting success having done
        # nothing. One guard now, mode-aware, ahead of any work.
        ("the empty-filter guard stops seeing the rust table",
         "    rows_for = (lambda: RUST_MUTATIONS) if args.rust else (",
         "    rows_for = (lambda: []) if args.rust else ("),
        # R16/M2 -- the parity table demanded a row aimed at EACH half and had
        # one `any` across both, so three of its four properties were rowed on
        # one side only. These four close the gap it was hiding.
        ("the gate anchor search stops excluding the tables",
         '    at = _find_one(text, find)\n    if at < 0:',
         '    at = text.find(find)\n    if at < 0:'),
        ("the gate null-mutation check removed",
         '        if _read(copy) == text:', "        if False:"),
        ("the RUST anchor search stops excluding the tables",
         "            at = _find_one(src, find)", "            at = src.find(find)"),
        ("the gate no-verdict guard removed",
         "    if out.returncode != 0 and not bit:", "    if False:"),
        ("a reached case counts as a failing one again",
         '    bit = sum(1 for l in lines if l.lstrip().startswith("FAIL"))',
         '    bit = sum(1 for l in lines if l.lstrip().startswith(("ok ", "FAIL")))'),


        ("the RUST named-test guard removed",
         "            if red and not named_failed:", "            if False:"),
        ("the RUST named-test check reads any failure",
         '            named_failed = f"test {test} ... FAILED" in (out.stdout or "")',
         '            named_failed = "FAILED" in (out.stdout or "")'),
        ("the RUST null-mutation check removed",
         "            if mutated == src:", "            if False:"),
        ("the label rule stops checking dotted tokens",
         "            if len(parts) > 1:\n"
         "                if not any(all(q in line for q in parts) "
         "for line in body.split(chr(10))):",
         "            if len(parts) > 1:\n                if False:"),
        ("the label rule stops checking plain tokens",
         "            elif tok not in body and tok not in scope:",
         "            elif False:"),
        ("the label rule covers no row",
         "    bad = mislabelled_rows(all_rows + [canary])", "    bad = []"),
        ("the label rule's stray filter passes everything",
         '    strays = [b for b in bad if "canary" not in b]', "    strays = []"),
        ("the label rule stops requiring its canary",
         "    if len(bad) != expect:", "    if False:"),
        ("the label rule treats every token as a filename",
         "            if tok.endswith(LABEL_FILE_EXT):",
         "            if True:"),
        ("the duplicate-row check is never consulted",
         '    dupes = [f"{k[0]} | {k[1]}" for k, n in rowset.items() if n > 1]',
         "    dupes = []"),
        ("the sibling rule stops requiring the label to name its token",
         "                if not (_label_words(t) & _label_words(lab)):",
         "                if False:"),
        ("the sibling rule accepts a lower-case difference too",
         '            if not (x[:1].isupper() and y[:1].isupper()):',
         "            if False:"),
        ("the sibling rule covers no row",
         "    swappable = interchangeable_rows(sibs + canaries)", "    swappable = []"),
        ("the sibling rule stops expecting a PAIR",
         "    sib_verdict = canary_verdict(swappable, expect=2)",
         "    sib_verdict = canary_verdict(swappable, expect=0)"),
        ("the label rule's anchor search stops excluding the tables",
         '        at = _find_one(text, find)\n        scope = _enclosing_def(text, at)',
         '        at = text.find(find)\n        scope = _enclosing_def(text, at)'),
        ("the unbounded-child sweep stops looking at the timeout",
         '                     if not any(k.arg == "timeout" for k in n.keywords)]',
         "                     if False]"),
        ("the unbounded-child sweep stops looking for a handler",
         "        elif not handles:", "        elif False:"),
        ("the unbounded-child sweep covers no gate",
         "    guarded = sorted(set(MUTATIONS) | {\"gate-self-tests\"})",
         "    guarded = []"),
        ("the child environment is not forwarded",
         "            env=child_env))", "            env=None))"),
        ("the dirty-tree refusal removed",
         "    if dirty and run is None:", "    if False:"),
        ("a refused run reports survivors again",
         "        if refusal:\n            print(f\"gate-bite-harness: {refusal}\", "
         "file=sys.stderr)\n            return 2",
         "        if False:\n            print(f\"gate-bite-harness: {refusal}\", "
         "file=sys.stderr)\n            return 2"),
    ],
    "citation-gate": [
        ("the pragma stops exempting", "        if _pragma_covers(lines, i):", "        if False:"),
        ("URLs are no longer blanked",
         "        scan_line = URL_RE.sub(lambda m: \" \" * len(m.group(0)), line)",
         "        scan_line = line"),
        ("a no-line-number citation is checked again (the cry-wolf revert)",
         "            # A dead branch is not a record of a decision; this comment is.\n"
         "            if start is None:",
         "            # A dead branch is not a record of a decision; this comment is.\n"
         "            if False:"),
    ],
    # A-1, the vocabulary leak detector. One row per production rule, plus the
    # two structural decisions the rules stand on: the accessor key (a name key
    # let the gate's OWN bite test walk through it with a one-letter binding)
    # and brace-counted test-block exclusion (cutting at the first occurrence
    # makes every line below a mid-file `mod tests` default-uncovered).
    # `D-2`, the ENGINE side of the same leak `hub-vocabulary-gate` guards
    # from the hub side. One row per structural decision the gate stands on:
    # the vocabulary being READ from the presets rather than listed (a list
    # here would be a second declaration and would drift from the first), the
    # word boundary (a substring match cries wolf on `breathe`), both blanking
    # passes, and the pragma's block window.
    "engine-vocabulary-gate": [
        ('the vocabulary is hardcoded instead of read from the presets',
         '    out: dict[str, list[str]] = {}\n    tree = REPO / PRESET_TREE',
         '    return {}\n    out: dict[str, list[str]] = {}\n    tree = REPO / PRESET_TREE'),
        ('the word boundary is dropped, so a substring cries wolf',
         'pattern = re.compile(r"\\b(" + "|".join(sorted(map(re.escape, vocab))) + r")\\b")',
         'pattern = re.compile(r"(" + "|".join(sorted(map(re.escape, vocab))) + r")")'),
        ('comments stop being blanked, so an EXPLANATION reads as a leak',
         '    body = strip_comments(blank_rust_test_items(src), keep_strings=True)',
         '    body = blank_rust_test_items(src)'),
        ('test items stop being blanked, so a fixture reads as a leak',
         '    body = strip_comments(blank_rust_test_items(src), keep_strings=True)',
         '    body = strip_comments(src, keep_strings=True)'),
        ('the pragma stops exempting',
         '    if PRAGMA in raw[line_no - 1]:\n        return True',
         '    if False:\n        return True'),
        # Added after a cold-start reviewer measured three of this gate's own
        # claims as untested: the derived scope, both branches of the file
        # walk, and `main()`'s empty-vocabulary refusal. A gate whose scope
        # logic is unchecked is the shape it exists to refuse, one tier up.
        ("the scope reverts to a HAND-WRITTEN list -- the defect the gate's own header condemns",
         '    man = _manifests()\n    reaching = {c for c in ROOT_CRATES if c in man}',
         '    return ["crates/actor-hub/src"]\n    man = _manifests()\n    reaching = {c for c in ROOT_CRATES if c in man}'),
        ('the transitive closure stops, so only the root crates are guarded',
         '            if name not in reaching and deps & reaching:',
         '            if False:'),
        ('the wire trees leave the full scan, and the gate is Rust-only again',
         '        for t, suffix in NON_RUST_TREES:',
         '        for t, suffix in ():'),
        ("main()'s empty-vocabulary refusal becomes a pass",
         '    if not vocab:\n        print(',
         '    if False:\n        print('),
        ("the pragma's block window becomes unbounded, silencing a whole file",
         '    while j >= 0 and raw[j].lstrip().startswith(("//", "///", "//!", "#[", "*")):',
         '    while j >= 0:'),
    ],
    "hub-vocabulary-gate": [
        ("the construction rule stops seeing a literal address",
         'rf"\\b{ADDRESS}(?:::new)?\\(\\s*\\d"',
         'rf"\\b{ADDRESS}(?:::new)?\\(\\s*ZZ"'),
        ("the comparison rule stops seeing the accessor",
         'rf"{ACCESSOR}(?:\\s+as\\s+\\w+)?\\s*(?:==|!=|<=|>=|<|>)\\s*-?\\d"',
         'rf"{ACCESSOR}(?:\\s+as\\s+\\w+)?\\s*(?:==|!=|<=|>=|<|>)\\s*ZZ"'),
        ("the mirrored comparison stops being read",
         'rf"-?\\d+\\s*(?:==|!=|<=|>=|<|>)\\s*[\\w.]*{ACCESSOR}"',
         'rf"ZZ\\s*(?:==|!=|<=|>=|<|>)\\s*[\\w.]*{ACCESSOR}"'),
        ("the accessor key reverts to a NAME key — the defect its own bite found",
         'ACCESSOR = r"\\.(?:get|index)\\(\\)"',
         'ACCESSOR = r"(?:fold_layer|layer|ordinal)\\w*(?:\\.get\\(\\))?"'),
        ("test blocks are cut at the first occurrence instead of brace-counted",
         "    out = list(src)\n    for m in re.finditer(r\"#\\[cfg\\(test\\)\\]\", src):",
         "    cut = src.find(\"#[cfg(test)]\")\n"
         "    if cut >= 0:\n"
         "        return src[:cut] + \"\\n\" * src[cut:].count(\"\\n\")\n"
         "    out = list(src)\n    for m in re.finditer(r\"#\\[cfg\\(test\\)\\]\", src):"),
        ("the pragma stops exempting",
         "    if PRAGMA in raw[idx]:\n        return True",
         "    if False:\n        return True"),
        ("the pragma's comment block becomes a fixed one-line window",
         "        if not stripped.startswith((\"//\", \"/*\", \"*\")):\n            return False",
         "        if k < idx - 1:\n            return False\n"
         "        if not stripped.startswith((\"//\", \"/*\", \"*\")):\n            return False"),
        # **This row mutates a RULE, not the arm that reads it.** The first
        # version deleted the cry-wolf arm's own `if shipped:` and stayed GREEN
        # — necessarily so: an arm whose subject is clean can always be deleted
        # with the suite green, which makes it a check of the CHECK rather than
        # of the rule. What gives that arm its subject is a rule that
        # OVER-matches, so that is what is mutated here: dropping the literal
        # requirement makes rule 1 report every mention of an address type,
        # including every type in every signature, and the shipped tree lights
        # up. The arm is the only thing that sees it.
        ("the construction rule stops requiring a literal (cry wolf)",
         'rf"\\b{ADDRESS}(?:::new)?\\(\\s*\\d"', 'rf"\\b{ADDRESS}"'),
    ],
    # A-2, the source-citation gate. `D-512` is the row that matters: the two
    # obvious checks were measured against the actual defect and both MISS it.
    "source-citation-gate": [
        # **A MENTION counting as a definition** is the check `D-512` proved
        # insufficient, so that is the mutation. The first attempt added `use` to
        # the KINDS list, which changed nothing at all: in `pub use x::{GoneState}`
        # the symbol sits inside braces and never follows the keyword, so the row
        # was GREEN because the mutant and the original behave identically.
        ("a mention starts counting as a definition",
         "    kinds = r\"(?:enum|struct|trait|type|const|fn|static|mod|union)\"",
         "    kinds = r\"(?:enum|struct|trait|type|const|fn|static|mod|union)\"\n"
         "    return sym in text"),
        ("a longer name starts counting as the symbol",
         'rf"\\bpub(?:\\([^)]*\\))?\\s+{kinds}\\s+{esc}\\b"',
         'rf"\\bpub(?:\\([^)]*\\))?\\s+{kinds}\\s+{esc}"'),
        # A definition that lives only in a COMMENT is the shape a verifier used
        # to make `D-512` pass: one ordinary sentence in the re-exporting file.
        ("the definition search stops stripping comments",
         "    body = strip_comments(text, False)", "    body = text"),
        ("resolution stops trying the crate-relative root",
         '    for cand in (REPO / path, REPO / "crates" / path):',
         "    for cand in (REPO / path,):"),
        ("a trailing comment stops carrying a citation",
         '            at = line.find("//")', '            at = -1  #'),
        # The pragma has TWO branches and the rows must reach both. Every case
        # put the pragma in the block ABOVE, so the same-line branch could be
        # deleted with the suite green until a case for it existed.
        ("the pragma stops exempting on the line itself",
         "    if PRAGMA in raw[idx]:\n        return True",
         "    if False:\n        return True"),
        ("the pragma's comment block becomes a fixed one-line window",
         "        if not stripped.startswith((\"//\", \"/*\", \"*\")):\n            return False",
         "        if k < idx - 1:\n            return False\n"
         "        if not stripped.startswith((\"//\", \"/*\", \"*\")):\n            return False"),
        # NOT a row on the subject arm. `D-517`: an arm whose subject is
        # non-empty can be deleted with the suite green, so what gives that arm
        # its meaning is a rule mutation that EMPTIES the subject.
        ("the citation pattern stops matching a symbol at all",
         r'CITE_RE = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.rs)#(?P<sym>[A-Za-z_][A-Za-z0-9_]*)")',
         r'CITE_RE = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.rs)##(?P<sym>[A-Za-z_][A-Za-z0-9_]*)")'),
    ],
}


def _child_env(no_cargo: bool) -> dict[str, str] | None:
    """The child's environment, with `cargo` removed from PATH when asked.

    **This is a CONTROL, not an assumption.** The first version was wired into CI
    with the comment *"this runner has no Rust toolchain"* and a timing claim
    resting on it -- an assertion about somebody else's machine image, verified
    by nothing, and `ubuntu-latest` ships rustup. Either the timing justification
    was void or the gate's own *"CI checks it"* NOTE was false; both are defects,
    and neither is decidable from here. So the harness decides.
    """
    if not no_cargo:
        return None
    env = dict(os.environ)
    # **Every** entry, not the first one `shutil.which` happened to return. A
    # GitHub runner carries cargo on two (`~/.cargo/bin` and a toolchain dir), so
    # removing one left the child finding it anyway -- a control that did not
    # control, with nothing checking the result.
    kept = [d for d in env.get("PATH", "").split(os.pathsep)
            if d and shutil.which("cargo", path=d) is None]
    env["PATH"] = os.pathsep.join(kept)
    return env


# ── the Rust half ────────────────────────────────────────────────────────────
#
# (label, file, find, replace, the test that must go RED). A round-10 review ran
# 113 mutations against `crates/actor-hub` and found NINE actionable survivors --
# in a crate nine rounds had called untouched. The shape repeats: the existing
# tests asserted the interesting half of a rule and left the boring half -- the
# other row kind, the other sign, the boundary itself, the exact value rather
# than its direction -- to be inferred, and a mutation lives in the inferred half.
#
# Unlike the Python half this MUTATES IN PLACE: cargo compiles the crate, so a
# copy beside the original would not be the code under test. It restores in a
# `finally` and refuses to start if any file it would touch is already dirty --
# so an interrupted run is detectable rather than silently mixed into a diff.
RUST_MUTATIONS: list[tuple[str, str, str, str, str]] = [
    # ── actor.rs / plugin_set.rs / ordinal.rs / report.rs ────────────────
    # A cold-start verifier measured that the 21 rows here touched ONLY
    # fold.rs, registry.rs and rows.rs -- so identity, existence, attachment
    # and the report surface were entirely unmutated, and D-521's fixed point
    # ("every witness has a mutation row") was false as written. These six
    # close the four files that had none.
    ("the hub ADJUDICATES existence instead of carrying it",
     "crates/actor-hub/src/actor.rs",
     "        self.existence = state;",
     "        self.existence = entity_existence::higher(self.existence, state);",
     "actor::tests::existence_is_platform_state_and_is_carried_not_adjudicated",
     "--lib"),
    # A row for `owner_of(q) == Some(p)` was written here, MEASURED, and
    # REMOVED: it survived, and correctly so. `actor.rs` says the guard is not
    # observable until a feature can move a quantity after attach, so
    # re-initialising an already-attached plugin's quantity writes the value
    # that is already there. A row that cannot red makes "N survivors"
    # permanently non-zero, which trains everyone to stop reading the number --
    # the cry-wolf failure of mutation testing. Its trigger is `S-15`'s: the
    # first feature that defines how its own quantity moves.
    ("detach clears the wrong bit",
     "crates/actor-hub/src/plugin_set.rs",
     "        Self(self.0 & !p.bit())",
     "        Self(self.0)",
     "plugin_set::tests::detach_removes_only_its_own_bit", "--lib"),
    ("membership answers from the whole mask, not the plugin's bit",
     "crates/actor-hub/src/plugin_set.rs",
     "        self.0 & p.bit() != 0",
     "        self.0 != 0",
     "plugin_set::tests::attach_then_contains", "--lib"),
    ("the quantity width bound is off by one",
     "crates/actor-hub/src/ordinal.rs",
     "        if (raw as usize) < MAX_DECLARED_QUANTITIES {",
     "        if (raw as usize) <= MAX_DECLARED_QUANTITIES {",
     "ordinal::tests::quantity_ordinal_refuses_past_the_declared_width", "--lib"),
    ("an ABSENT quantity reads as zero through the report",
     "crates/actor-hub/src/report.rs",
     "        self.values[q.index()]",
     "        Some(self.values[q.index()].unwrap_or(0))",
     "an_absent_quantity_is_none_not_zero", "fold"),
    ("a refused derivation is dropped, not recorded",
     "crates/actor-hub/src/fold.rs",
     "            Err(reason) => refused.push(Refused { row: RowRef::Derivation(i), reason }),",
     "            Err(_reason) => {}",
     "a_refused_derivation_is_recorded_with_its_row_index"),
    ("derivations refused BEFORE modifiers",
     "crates/actor-hub/src/fold.rs",
     """    let mut accepted_mods: Vec<(usize, &ModifierRow)> = Vec::new();
    for (i, row) in modifiers.iter().enumerate() {
        match registry.check_modifier(attached, row) {
            Ok(()) => accepted_mods.push((i, row)),
            Err(reason) => refused.push(Refused { row: RowRef::Modifier(i), reason }),
        }
    }
    let mut accepted_derivs: Vec<(usize, &DerivationRow)> = Vec::new();
    for (i, row) in derivations.iter().enumerate() {
        match registry.check_derivation(attached, row) {
            Ok(()) => accepted_derivs.push((i, row)),
            Err(reason) => refused.push(Refused { row: RowRef::Derivation(i), reason }),
        }
    }""",
     """    let mut accepted_derivs: Vec<(usize, &DerivationRow)> = Vec::new();
    for (i, row) in derivations.iter().enumerate() {
        match registry.check_derivation(attached, row) {
            Ok(()) => accepted_derivs.push((i, row)),
            Err(reason) => refused.push(Refused { row: RowRef::Derivation(i), reason }),
        }
    }
    let mut accepted_mods: Vec<(usize, &ModifierRow)> = Vec::new();
    for (i, row) in modifiers.iter().enumerate() {
        match registry.check_modifier(attached, row) {
            Ok(()) => accepted_mods.push((i, row)),
            Err(reason) => refused.push(Refused { row: RowRef::Modifier(i), reason }),
        }
    }""",
     "refusals_are_modifiers_then_derivations_each_in_submission_order"),
    ("check_derivation stops checking the fold layer",
     "crates/actor-hub/src/registry.rs",
     "        self.check_layer(row.fold_layer)?;\n        if row.divisor == 0 {",
     "        let _ = self.check_layer(row.fold_layer);\n        if row.divisor == 0 {",
     "registry::a_derivation_on_an_undeclared_fold_layer_is_refused"),
    ("the zero-divisor refusal removed",
     "crates/actor-hub/src/registry.rs",
     "        if row.divisor == 0 {\n            return Err(RowRefusal::ZeroDivisor);\n        }",
     "        if false {\n            return Err(RowRefusal::ZeroDivisor);\n        }",
     "registry::a_zero_divisor_and_a_contradictory_bound_are_refused"),
    # **The label said `Accumulator` and the anchor mutated the EMIT push.**
    # Renamed to what it touches, and the accumulator half -- which the label
    # had been standing in for, and which nothing pinned -- gets its own row.
    ("the Emit record's wanted reports the EMITTED value",
     "crates/actor-hub/src/fold.rs",
     "        capped.push(Capped { quantity: q, site: CapSite::Emit, wanted: r.value, emitted: out });",
     "        capped.push(Capped { quantity: q, site: CapSite::Emit, wanted: out as i64, emitted: out });",
     "capping::the_accumulator_record_carries_the_exact_wanted_total"),
    ("the Accumulator record's wanted reports the EMITTED value",
     "crates/actor-hub/src/fold.rs",
     "        capped.push(Capped { quantity: q, site: CapSite::Accumulator,"
     " wanted: r.value, emitted: out });",
     "        capped.push(Capped { quantity: q, site: CapSite::Accumulator,"
     " wanted: out as i64, emitted: out });",
     "capping::the_accumulator_record_carries_the_saturated_total_not_the_emitted_value"),
    ("pre_emit collapses onto value",
     "crates/actor-hub/src/fold.rs",
     "            pre_emit,\n            value,",
     "            pre_emit: value as i64,\n            value,",
     "capping::pre_emit_differs_from_value_when_the_emit_clamps"),
    ("a bound that raises reports nothing",
     "crates/actor-hub/src/rows.rs",
     "        let site = if bounded != clamped {",
     "        let site = if bounded < clamped {",
     "capping::a_bound_whose_floor_bites_is_reported"),
    ("division floors instead of truncating",
     "crates/actor-hub/src/rows.rs",
     "            (source_value as i64).saturating_mul(self.factor_milli as i64) / (self.divisor as i64)",
     "            (source_value as i64).saturating_mul(self.factor_milli as i64).div_euclid(self.divisor as i64)",
     "a_negative_derivation_truncates_toward_zero"),
    # M10 -- `order_key`'s middle component is the submitting plugin. The LAYER
    # half had a case and the plugin did not, so a constant survived the whole
    # 293-test suite. One plugin cannot show a key that sorts by plugin.
    #
    # **The row used to say the index half was cased too. It was not** -- a
    # round-16 sweep proved `usize::MAX / 2 + i` -> `- i` a survivor, so the row
    # asserting the coverage was itself the miss. Both halves are cased now.
    ("order_key stops sorting by submitting plugin",
     "crates/actor-hub/src/fold.rs",
     "    (c.fold_layer.get(), c.source.get(), idx)",
     "    (c.fold_layer.get(), 0, idx)",
     "contributions_at_one_layer_are_ordered_by_submitting_plugin"),
    ("order_key reverses two derivations at one layer",
     "crates/actor-hub/src/fold.rs",
     "        RowRef::Derivation(i) => usize::MAX / 2 + i,",
     "        RowRef::Derivation(i) => usize::MAX / 2 - i,",
     "two_derivations_from_one_plugin_at_one_layer_keep_submission_order"),
    # R16/minor 5 -- the SOURCE-before-TARGET precedence in this same function
    # has a case; the LAYER-before-DIVISOR pair had none, so swapping them
    # reported `ZeroDivisor` where the contract reports `UndeclaredFoldLayer`.
    # A refusal REASON is the whole product of substrate §7.
    ("the layer check moves after the divisor check",
     "crates/actor-hub/src/registry.rs",
     "        self.check_layer(row.fold_layer)?;\n"
     "        if row.divisor == 0 {\n"
     "            return Err(RowRefusal::ZeroDivisor);\n"
     "        }",
     "        if row.divisor == 0 {\n"
     "            return Err(RowRefusal::ZeroDivisor);\n"
     "        }\n"
     "        self.check_layer(row.fold_layer)?;",
     "registry::an_undeclared_layer_is_reported_before_a_zero_divisor"),
    # R17/B1 -- `D-459` cased ONE of `check_derivation`'s five adjacent
    # precedence pairs and its row claimed a second that was false: the
    # source-before-target case is on `check_modifier`, which writes the same two
    # lines again. Three were survivors. That is `D-458`'s defect -- a row
    # asserting coverage it does not have -- one row later, same commit.
    ('check_derivation reports the TARGET before the SOURCE',
     'crates/actor-hub/src/registry.rs',
     '        self.check_source(attached, row.source)?;\n        self.check_target(attached, row.target)?;\n        if !self.is_present(attached, row.source_quantity) {',
     '        self.check_target(attached, row.target)?;\n        self.check_source(attached, row.source)?;\n        if !self.is_present(attached, row.source_quantity) {',
     'registry::a_derivations_refusal_chain_reports_the_first_violation_at_every_step'),
    ('check_derivation reports the LAYER before the SOURCE QUANTITY',
     'crates/actor-hub/src/registry.rs',
     '        if !self.is_present(attached, row.source_quantity) {\n            return Err(RowRefusal::UndeclaredSource { ordinal: row.source_quantity.get() });\n        }\n        self.check_layer(row.fold_layer)?;',
     '        self.check_layer(row.fold_layer)?;\n        if !self.is_present(attached, row.source_quantity) {\n            return Err(RowRefusal::UndeclaredSource { ordinal: row.source_quantity.get() });\n        }',
     'registry::a_derivations_refusal_chain_reports_the_first_violation_at_every_step'),
    ('check_derivation reports the BOUND before the DIVISOR',
     'crates/actor-hub/src/registry.rs',
     '        if row.divisor == 0 {\n            return Err(RowRefusal::ZeroDivisor);\n        }\n        if let Some(b) = row.bound',
     '        if let Some(b) = row.bound\n            && b.min > b.max\n        {\n            return Err(RowRefusal::ContradictoryBound { min: b.min, max: b.max });\n        }\n        if row.divisor == 0 {\n            return Err(RowRefusal::ZeroDivisor);\n        }\n        if let Some(b) = row.bound',
     'registry::a_derivations_refusal_chain_reports_the_first_violation_at_every_step'),
    ('check_modifier reports the TARGET before the SOURCE',
     'crates/actor-hub/src/registry.rs',
     '        self.check_source(attached, row.source)?;\n        self.check_target(attached, row.target)?;\n        self.check_layer(row.fold_layer)',
     '        self.check_target(attached, row.target)?;\n        self.check_source(attached, row.source)?;\n        self.check_layer(row.fold_layer)',
     'registry::a_modifiers_refusal_chain_reports_the_first_violation_at_every_step'),
    # R17/m1 -- the negative direction separated truncation from flooring and
    # the ceiling direction was caught; HALF-ROUNDING is neither, and both data
    # points of the divisor case are invariant under it.
    ('raw_amount rounds half-up instead of truncating',
     'crates/actor-hub/src/rows.rs',
     '            (source_value as i64).saturating_mul(self.factor_milli as i64) / (self.divisor as i64)',
     '            ((source_value as i64).saturating_mul(self.factor_milli as i64)\n                + (self.divisor as i64) / 2)\n                / (self.divisor as i64)',
     'a_positive_derivation_truncates_rather_than_rounding_half_up'),
    # R17/m2 -- `FoldReport.capped` is public output and `emit` writes the two
    # records deliberately; their sequence was asserted by nothing.
    ('the Accumulator record is pushed AFTER the Emit record',
     'crates/actor-hub/src/fold.rs',
     '    if r.saturated {\n        capped.push(Capped { quantity: q, site: CapSite::Accumulator, wanted: r.value, emitted: out });\n    }\n    if out as i64 != r.value {',
     '    if out as i64 != r.value {\n        capped.push(Capped { quantity: q, site: CapSite::Emit, wanted: r.value, emitted: out });\n    }\n    if r.saturated {\n        capped.push(Capped { quantity: q, site: CapSite::Accumulator, wanted: r.value, emitted: out });\n    }\n    if out as i64 != r.value {',
     'capping::the_accumulator_record_precedes_the_emit_record_for_one_quantity'),
    # R19/m5 -- the FLOOR-WINS degradation is documented at length in the code
    # and enforced by that paragraph alone: ceiling-wins survived all 301 tests.
    ("a contradictory bound lets the CEILING win",
     "crates/actor-hub/src/rows.rs",
     "            Some(b) => clamped.clamp(b.min, b.max.max(b.min)),",
     "            Some(b) => clamped.clamp(b.min.min(b.max), b.max),",
     "capping::a_contradictory_bound_lets_the_floor_win"),
    ("an exact bound min==max wrongly refused",
     "crates/actor-hub/src/registry.rs",
     "            && b.min > b.max",
     "            && b.min >= b.max",
     "registry::an_exact_bound_is_legal_and_pins_the_contribution"),
    ("the table-length boundary weakened to >",
     "crates/actor-hub/src/registry.rs",
     "                if q.ordinal.index() >= table.len() {",
     "                if q.ordinal.index() > table.len() {",
     "registry::an_ordinal_exactly_at_the_table_length_is_refused"),
]



def _rust_dirty() -> list[str]:
    """Files this harness would mutate that already carry uncommitted changes."""
    files = sorted({r[1] for r in RUST_MUTATIONS})
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--", *files],
                             cwd=REPO, capture_output=True, text=True,
                             timeout=CHILD_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        # Refusing is the safe direction: this answers "may I mutate the crate
        # in place", and an unanswered question must not read as yes.
        return ["<git status did not answer within "
                f"{CHILD_TIMEOUT_S}s — refusing to mutate>"]
    return [l[3:].strip() for l in out.stdout.splitlines() if l.strip()]


def run_rust(only: str | None = None, run=None, write=None,
             baseline=None, rows=None, root=None) -> tuple[int, str | None]:
    """(survivors, refusal). **Two separate answers, because they were one.**

    The first version returned `2` as a refusal sentinel and `main` read the
    return value as a survivor count, so a refused run -- nothing executed, no
    mutations applied -- printed *"2 Rust mutation(s) SURVIVED"*. A count that
    doubles as an error code reports a defect that does not exist, which is the
    same class as a check reporting coverage it does not have.
    """
    # `rows=`/`root=` are injectable for the same reason `run=`/`write=` are:
    # this half read the real crate through `REPO / rel`, so the two guards
    # added to it could not be DRIVEN by a case at all -- and a guard that
    # cannot be driven is how this half came to lack three its twin has.
    rows = [r for r in (RUST_MUTATIONS if rows is None else rows)
            if only is None or only.lower() in r[0].lower()]
    root = root or REPO
    dirty = _rust_dirty()
    if dirty and run is None:
        return 0, ("refusing to mutate files that are already modified: "
                   f"{dirty}. Commit or stash them first.")
    # The Rust half needs the same guard: a crate whose suite is already red
    # reddens every mutation for free.
    # **One decision, reached by both paths.** With the injected baseline and the
    # real probe each carrying their own `if`, a case drives one branch and a
    # mutation targets the other -- so the guard had a row AND a case and still
    # survived. The two paths now only decide WHETHER the baseline is red; what
    # to do about it is written once.
    # `baseline` injects the PROBE, not its verdict: injecting the verdict left
    # `probe.returncode != 0` reachable only by seeding a red crate suite, so it
    # kept a mutation row and a case and survived both. One extraction, one path.
    if baseline is not None:
        probe = baseline()
    elif run is not None:
        probe = None
    elif shutil.which("cargo") is None:
        # No toolchain is a SKIP, not a crash. The probe added with this guard
        # called cargo unconditionally and raised `FileNotFoundError` on every
        # machine without Rust -- a degrade-safety defect inside the
        # degrade-safety guard.
        return 0, "cargo is not on PATH, so the Rust mutations were not run"
    else:
        try:
            probe = subprocess.run(
                ["cargo", "test", "-p", "actor-hub", "--test", "fold_survivors"],
                cwd=REPO, capture_output=True, text=True, timeout=CHILD_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired) as e:
            return 0, f"the unmutated fold_survivors suite could not be run: {e}"

    if probe is not None and probe.returncode != 0:
        return len(rows) or 1, ("the UNMUTATED fold_survivors suite already fails "
                                "— every mutation below would be red for that reason")

    print(f"\ncrates/actor-hub  ({len(rows)} Rust mutation(s))")
    originals: dict[str, str] = {}
    raws: dict[str, bytes] = {}
    green = 0
    try:
        for row in rows:
            # **The target is per ROW, not hardcoded.** It was `--test
            # fold_survivors` for every row, so a row naming a test that lives
            # anywhere else would run a cargo command that matches NOTHING and
            # read as GREEN -- the mutation surviving because its witness was
            # never executed. A verifier measured that the 21 rows here touched
            # only three files; closing the other four needs `--lib` and
            # `--test fold`, so the enumeration had to go.
            label, rel, find, repl, test = row[:5]
            target = row[5] if len(row) > 5 else "fold_survivors"
            path = root / rel
            raws.setdefault(rel, _raw(path))
            src = originals.setdefault(rel, _read(path))
            # `_find_one`, not a raw count: the twin has used the table-aware
            # form since a self-mutating file found its own anchors twice, and
            # this side kept counting raw. Rust sources carry no Python tables,
            # so the two agree today -- which is exactly why the asymmetry
            # survived, and exactly why it must not be left to luck.
            at = _find_one(src, find)
            if at < 0:
                print(f"  DRIFT  {label:52} anchor occurs {src.count(find)}x")
                green += 1
                continue
            # `write` is injectable because `--self-test` drives this function
            # three times, and the pre-commit hook runs `--self-test`: the first
            # version therefore performed **30 in-place writes to the shipped
            # crate sources on every commit across 47 services**. The incident
            # the Python half mutates a copy to avoid -- a killed run leaving a
            # mutation on disk -- was on the automatic path.
            mutated = src[:at] + repl + src[at + len(find):]
            # **The mutation must actually BE a mutation.** The twin checks this
            # and this half did not, so a harness that had silently stopped
            # mutating would have reported every Rust row red and looked like
            # success -- the same false-green the check next to it exists for.
            if mutated == src:
                print(f"  NULL   {label:52} the replacement changes nothing")
                green += 1
                continue
            (write or _write)(path, mutated, like=raws[rel])
            sel = ["--lib"] if target == "--lib" else ["--test", target]
            runner = run or (lambda t, sel=sel: subprocess.run(
                ["cargo", "test", "-p", "actor-hub", *sel,
                 t, "--", "--exact"], cwd=REPO, capture_output=True, text=True,
                timeout=CHILD_TIMEOUT_S))
            try:
                out = runner(test)
            except subprocess.TimeoutExpired:
                print(f"  SLOW   {label:52} -> no verdict in {CHILD_TIMEOUT_S}s")
                green += 1
                continue
            finally:
                # The ORIGINAL BYTES, not a re-encoding of the text: exact even
                # for a file with mixed line endings, which no normalisation
                # round trip can promise.
                #
                # Restore when the file DIFFERS, never when the writer was
                # injected: keying the restore on `write is None` meant a
                # mutation of the injection itself wrote the file and then
                # skipped putting it back -- which left `fold.rs` modified after
                # a fully-green sweep, the exact class this whole mode exists to
                # avoid, reintroduced by its own fix one round later.
                if _raw(path) != raws[rel]:
                    path.write_bytes(raws[rel])
            # **The NAMED TEST must have FAILED**, which `rc != 0` does not
            # say: a mutant that breaks an unrelated test, or a `--exact` name
            # that no longer matches anything, both move the return code. The
            # gate half asks the same question one line down; this is its twin.
            named_failed = f"test {test} ... FAILED" in (out.stdout or "")
            # **A run that selected NO TEST is not a verdict.** `--exact` with a
            # bare name matches nothing under `--lib`, where the printed name is
            # `actor::tests::<name>` -- so five rows added to close four empty
            # files ran `0 passed; 0 failed; 27 filtered out`, and every one read
            # as the mutation SURVIVING. It survived nothing: its witness never
            # executed. This is `D-478` on the Rust side -- a bite is a FAILING
            # CASE, and no case at all is neither red nor green.
            if "0 passed; 0 failed" in (out.stdout or ""):
                print(f"  NOTEST {label:52} -> `{test}` selected nothing")
                green += 1
                continue
            red = out.returncode != 0
            # REMOVED: a `BROKE` guard reading `error[E` / `could not compile`
            # from stderr. **`named_failed` is strictly stronger** -- a mutant
            # that does not build cannot print `test <name> ... FAILED`, so
            # every input the compile guard would catch is caught one line
            # above it. Written this morning, measured unreachable this
            # afternoon, and a check that cannot fail is worse than no check.
            # The property it defended is not lost; it moved to a stronger
            # question. Its two rows and two cases went with it.
            if red and not named_failed:
                print(f"  WRONG  {label:52} -> {test} did not fail")
                green += 1
                continue
            print(f"  {'RED ' if red else 'GREEN'}  {label:52} -> {test}")
            green += 0 if red else 1
    finally:
        for rel in originals:
            if _raw(root / rel) != raws[rel]:
                (root / rel).write_bytes(raws[rel])
    return green, None


def unbounded_children(text: str) -> list[str]:
    """Functions in `text` that spawn a child nothing can interrupt.

    **The DERIVED half of the parity mechanism.** The table beside it names four
    properties by hand, so it cannot detect a new one-sided guard -- and the
    round that added it shipped a driver with no timeout handler at all, which
    is the same property, on a third file, going unnoticed for exactly that
    reason. This asks the tree instead, so a function written tomorrow is
    covered by construction.

    Two ways to hang a pre-commit hook, and both are findings:

      * a `subprocess.run` with no `timeout=` — nothing ever interrupts it;
      * a function that spawns and has no `except subprocess.TimeoutExpired` —
        the bound exists and its expiry is an uncaught traceback, which is worse
        than no bound: the run dies mid-sweep and the rest is reported by
        nothing.

    Measured when it was written: FOUR such functions across the four scripts
    this harness is responsible for, including `_rust_dirty` in this very file.
    """
    import ast
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ["<unparseable>"]
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        spawns = [n for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "run"
                  and getattr(n.func.value, "id", "") == "subprocess"]
        if not spawns:
            continue
        # A nested function carries its own guard; attributing its spawns to the
        # enclosing one would report a parent that is perfectly bounded.
        inner = {id(n) for d in ast.walk(fn)
                 if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d is not fn
                 for n in ast.walk(d)}
        spawns = [n for n in spawns if id(n) not in inner] or spawns
        unbounded = [n.lineno for n in spawns
                     if not any(k.arg == "timeout" for k in n.keywords)]
        handles = any(isinstance(h, ast.ExceptHandler) and h.type is not None
                      and "TimeoutExpired" in ast.dump(h.type)
                      for h in ast.walk(fn))
        if unbounded:
            out.append(f"{fn.name} spawns with no timeout= at line(s) {unbounded}")
        elif not handles:
            out.append(f"{fn.name} spawns with a timeout nothing catches")
    return out


# A CODE-SHAPED token: a `.`/`::` path, a `snake_case` name, or a `CamelCase`
# one. An English word carries none of those, so the rule cannot fire on prose.
LABEL_CODE_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:(?:\.|::)[A-Za-z_][A-Za-z0-9_]*)+"
    r"|[a-z][a-z0-9]*(?:_[a-z0-9]+)+"
    r"|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+")
# `_index.md` is a FILENAME, not a member access. Measured: without this the
# rule reports it, which is the cry-wolf direction on a correct row.
LABEL_FILE_EXT = (".md", ".py", ".rs", ".sh", ".json", ".yaml", ".yml", ".toml",
                  ".jsonl")
DEF_LINE_RE = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:fn|def|class|impl)\s")


def _enclosing_def(text: str, at: int) -> str:
    """The definition `at` sits in — back to its `fn`/`def`, on to the next."""
    lines = text.split(chr(10))
    seen, line_of = 0, 0
    for i, l in enumerate(lines):
        if seen + len(l) + 1 > at:
            line_of = i
            break
        seen += len(l) + 1
    start = next((k for k in range(line_of, -1, -1) if DEF_LINE_RE.match(lines[k])), 0)
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for k in range(start + 1, len(lines)):
        if DEF_LINE_RE.match(lines[k]) and (len(lines[k]) - len(lines[k].lstrip())) <= indent:
            end = k
            break
    return chr(10).join(lines[start:end])


def mislabelled_rows(rows) -> list[str]:
    """Rows whose LABEL names a symbol their ANCHOR does not touch.

    **The class fix four rounds have failed to make.** Every blocking finding
    since round 15 has been a row asserting coverage of something ADJACENT to
    what it mutates -- a sibling function, a sibling record, the other half of a
    two-line tuple -- and each round's remedy was to write a better row. Writing
    is the thing that keeps failing, so this reads the row instead.

    Two questions, because a label names things two ways:

      * a **dotted** token (`Accumulator.wanted`) names a member OF a thing, so
        both halves must meet on ONE line of the anchor. The row that produced
        this rule is labelled `Accumulator.wanted` and mutates the **Emit**
        push, where `wanted` appears and `Accumulator` does not;
      * a **plain** token (`check_derivation`, `order_key`) names the subject,
        which the anchor need not contain literally -- an anchor inside a
        function rarely repeats its own name -- so it may appear in the
        anchor or in the **enclosing definition**.

    Measured across all 132 shipped rows before wiring: 1 finding, and it was
    the defect. `rows` is `(label, path, find, repl)`, injectable so a case can
    drive it with a row built to violate it.
    """
    out = []
    for label, rel, find, repl in rows:
        body = find + chr(10) + repl
        try:
            text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            out.append(f"{label!r}: its file {rel} cannot be read")
            continue
        text = text.replace(chr(13) + chr(10), chr(10))
        # `_find_one`, not `text.find`: this file mutates ITSELF, so a raw
        # find lands on the TABLE ROW naming the rule instead of the rule, and
        # the "enclosing definition" then spans the whole table. Same defect,
        # same file, as the one `_find_one` was written for.
        at = _find_one(text, find)
        scope = _enclosing_def(text, at) if at >= 0 else ""
        for tok in LABEL_CODE_RE.findall(label):
            if tok.endswith(LABEL_FILE_EXT):
                continue
            parts = re.split(r"\.|::", tok)
            if len(parts) > 1:
                if not any(all(q in line for q in parts) for line in body.split(chr(10))):
                    out.append(
                        f"{label!r}: `{tok}` names a member, but its two halves "
                        "never meet on one line of the anchor — the row is "
                        "aimed at a sibling")
            elif tok not in body and tok not in scope:
                out.append(
                    f"{label!r}: `{tok}` appears neither in the anchor nor in "
                    "the definition around it")
    return out


def canary_verdict(bad: list[str], expect: int = 1) -> list[str]:
    """What to report, given the subject set always carries ONE known-bad row.

    Two clauses, and the second is the one that matters: an EMPTY result means
    the rule examined nothing, which is precisely what `bad = []` produced and
    what a floor on the row COUNT walked straight past. Extracted because that
    clause is unreachable while the rule works, so only an injected input can
    drive it -- the same reason `run_rust` gained `rows=`/`root=`.
    """
    strays = [b for b in bad if "canary" not in b]
    if strays:
        return strays
    if len(bad) != expect:
        return [f"the canary was not reported (got {len(bad)}, want {expect}) — "
                "the rule examined nothing, so its verdict is about no rows at all"]
    return []


def _label_words(text: str) -> set[str]:
    """The lower-cased words of an identifier or a label — humps and `_` split."""
    return {w.lower() for w in
            re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", text) if len(w) > 2}


def interchangeable_rows(rows) -> list[str]:
    """Sibling rows a swap of their anchors would leave indistinguishable.

    **The shape `mislabelled_rows` cannot reach, and the shape `D-476` was.**
    Two `Capped` pushes differ by exactly one token — `CapSite::Emit` against
    `CapSite::Accumulator` — and a label sat on the wrong one. Round 18 fixed
    that by RENAMING the label, which deleted the dot the token rule keys on and
    moved BOTH rows out of its scope: the remedy removed its own subject.

    So this asks a question no token regex can. If two rows in one file have
    anchors differing in exactly one CAPITALISED token, each label must name its
    own token — otherwise the rows are interchangeable and swapping them is
    silent. Capitalised, because the alternative was measured: lower-case
    differences are incidental variable names (`hits`/`starts`, `text`/`src`)
    and requiring those produced three findings on three correct rows, which is
    the cry-wolf direction.

    Measured before wiring: 2 sibling pairs shipped, 0 findings; swapping the
    two `Capped` anchors while keeping the shipped labels reports both halves.
    """
    tok = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    out = []
    for i, (label_a, rel_a, find_a) in enumerate(rows):
        for label_b, rel_b, find_b in rows[i + 1:]:
            if rel_a != rel_b:
                continue
            ta, tb = tok.findall(find_a), tok.findall(find_b)
            if len(ta) != len(tb):
                continue
            diff = [(x, y) for x, y in zip(ta, tb) if x != y]
            if len(diff) != 1:
                continue
            x, y = diff[0]
            if not (x[:1].isupper() and y[:1].isupper()):
                continue
            for lab, t in ((label_a, x), (label_b, y)):
                if not (_label_words(t) & _label_words(lab)):
                    out.append(
                        f"{lab!r}: its anchor differs from a sibling row's only "
                        f"by `{t}`, which the label does not name — swap the two "
                        "anchors and nothing here would notice")
    return out


def _outside_tables(text: str) -> list[tuple[int, int]]:
    """Character spans of `text` that are NOT a `*MUTATIONS` table literal.

    **A file that mutates itself finds every anchor twice** -- once in the rule
    and once in the table row naming it -- so `count(find) != 1` reported drift
    on rules that had not moved. The tables are DATA: mutating a row changes no
    behaviour, and excluding them is what makes self-mutation mean anything.
    """
    import ast
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [(0, len(text))]
    offsets = [0]
    for line in text.split("\n"):
        offsets.append(offsets[-1] + len(line) + 1)
    starts, ends = [0], []
    # **Every WITNESS TABLE, wherever it is defined.** The first version walked
    # `tree.body` only, so the `parity` table -- a local inside `self_test`,
    # added to catch guards present in one half and not the other -- was treated
    # as code, and every anchor it names counted twice. A table is data whether
    # it sits at module level or inside a function.
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        if not any(n.endswith("MUTATIONS") or n == "parity" for n in names):
            continue
        ends.append(offsets[node.lineno - 1])
        starts.append(offsets[min(node.end_lineno, len(offsets) - 1)])
    ends.append(len(text))
    return list(zip(starts, ends))


def _find_one(text: str, find: str) -> int:
    """The offset of `find` outside every table literal, or -1 if not exactly one."""
    hits = []
    for a, b in _outside_tables(text):
        start = a
        while True:
            i = text.find(find, start, b)
            if i < 0:
                break
            hits.append(i)
            start = i + 1
    return hits[0] if len(hits) == 1 else -1


def _mutate_and_run(gate: str, find: str, repl: str, run=None,
                    no_cargo: bool = False, label_hint: str = "",
                    root=None) -> tuple[bool, str]:
    """(went_red, note). The ORIGINAL is opened read-only; a copy is mutated.

    `root` is injectable so a case can point this at a file built to exercise
    the anchor search. Without it the search could be reverted to a raw
    `text.find` -- mutating the TABLE ROW that names a rule instead of the rule
    -- and the whole suite stayed green: the sole survivor of a 101-row sweep.
    """
    root = root or SCRIPTS
    src = root / f"{gate}.py"
    raw = _raw(src)
    text = _read(src)
    at = _find_one(text, find)
    if at < 0:
        return False, (f"anchor occurs {text.count(find)}x outside the tables "
                       "— the table has drifted")
    # Beside the original so `REPO = Path(__file__).parent.parent` still resolves.
    copy = root / f".bite-{gate}.py"
    try:
        _write(copy, text[:at] + repl + text[at + len(find):], like=raw)
        # **The mutation must actually be a mutation.** Nothing checked that the
        # copy differed from the original, so a harness that had silently stopped
        # mutating would report every rule RED-free and look like success.
        if _read(copy) == text:
            return False, "the copy is identical to the original — nothing was mutated"
        # The child is told WHICH ROW is under test, so its own drift check can
        # skip the anchor this mutation just removed.
        child_env = dict(_child_env(no_cargo) or os.environ)
        child_env["GATE_BITE_MUTATING"] = label_hint
        runner = run or (lambda p: subprocess.run(
            [sys.executable, str(p), "--self-test"], cwd=REPO,
            capture_output=True, text=True, timeout=CHILD_TIMEOUT_S,
            env=child_env))
        try:
            out = runner(copy)
        except subprocess.TimeoutExpired:
            # A timeout is a FINDING about that mutation, not the end of the
            # run. The timeout was configured and never caught, so the
            # documented local invocation aborted at mutation 11 of 42 with a
            # raw traceback -- and the 47 that never executed were reported by
            # nothing at all.
            return False, f"the self-test did not finish within {CHILD_TIMEOUT_S}s"
    finally:
        copy.unlink(missing_ok=True)
    # **RED for the RIGHT REASON, asked of THIS half too.** `D-467` added the
    # question to `run_rust` and not to its twin, and one row of the shipped
    # table was already answering it wrongly: deleting one line of a two-line
    # tuple left the child unparseable, so python's parser reddened it and not
    # one case ran. A mutant that cannot execute proves nothing about the rule
    # it aims at, exactly as a mutant that cannot compile does.
    #
    # **A bite is a FAILING CASE, not a non-zero exit.** The first version asked
    # whether the child REACHED a case, and the very next row of the same table
    # was the counter-example: a mangled tuple let the child reach 62 cases,
    # raise `TypeError`, print ZERO `FAIL` lines, and be reported RED. Reaching
    # a case is not answering; a self-test prints one `ok`/`FAIL` line per case,
    # so the question is whether one of them said FAIL.
    #
    # The failure direction is safe: a child that reds without printing a FAIL
    # line is counted as a SURVIVOR, so the harness under-claims rather than
    # over-claims. It is deliberately not a list of exception names, which would
    # be the enumeration this file keeps being caught by.
    lines = (out.stdout or "").splitlines()
    ran = sum(1 for l in lines if l.lstrip().startswith(("ok ", "FAIL")))
    bit = sum(1 for l in lines if l.lstrip().startswith("FAIL"))
    if out.returncode != 0 and not bit:
        first = next((l.strip() for l in reversed((out.stderr or "").splitlines())
                      if l.strip()), "no output at all")
        return False, (f"the child exited non-zero with NO failing case "
                       f"(reached {ran}) — {first}")
    if out.returncode != 0:
        return True, ""
    return False, "self-test stayed GREEN"


def baseline_is_green(gate: str, run=None, no_cargo: bool = False) -> str | None:
    """None when the gate's UNMUTATED self-test passes; the reason otherwise.

    **A mutation run against a red baseline reports total success.** Every row
    goes RED whatever the mutation does -- including a mutation that changes
    nothing -- so "all N mutations reddened their self-test" becomes a statement
    about the suite being broken rather than about the rules biting.

    This is not hypothetical and it is not a near miss. A previous round shipped
    a case that failed on any machine without a Rust toolchain; CI runs this
    harness with `--no-cargo`, which is exactly such a machine; and the harness
    reported **47 of 47 red** while three semantically NULL mutations were also
    red. The defect was found by a human running those null mutations by hand,
    and nothing replaced the human -- so the fix closed the instance and left the
    class with no detector at all.

    Running the baseline is that detector, and it costs one child per gate.
    """
    src = SCRIPTS / f"{gate}.py"
    runner = run or (lambda p: subprocess.run(
        [sys.executable, str(p), "--self-test"], cwd=REPO, capture_output=True,
        text=True, timeout=CHILD_TIMEOUT_S, env=_child_env(no_cargo)))
    try:
        out = runner(src)
    except subprocess.TimeoutExpired:
        return f"the unmutated self-test did not finish within {CHILD_TIMEOUT_S}s"
    if out.returncode != 0:
        first = next((l.strip() for l in (out.stdout or "").splitlines()
                      if l.strip().startswith("FAIL")), "")
        return (f"the UNMUTATED self-test already fails (rc={out.returncode})"
                + (f": {first}" if first else "")
                + " — every mutation below would be red for that reason")
    return None


def run_gate(gate: str, run=None, only: str | None = None, no_cargo: bool = False) -> int:
    rows = [r for r in MUTATIONS[gate] if only is None or only.lower() in r[0].lower()]
    print(f"\n{gate}" + (f"  ({len(rows)}/{len(MUTATIONS[gate])} matching {only!r})" if only else ""))
    reason = baseline_is_green(gate, run=run, no_cargo=no_cargo)
    if reason:
        # NEGATIVE, so the summary can say what actually happened. Reporting a
        # red baseline as "those rules have no case and can be deleted with the
        # suite green" is a false statement about the rules, and it points the
        # reader at the wrong file.
        print(f"  BASELINE  {reason}")
        return -(len(rows) or 1)
    green = 0
    for label, find, repl in rows:
        red, note = _mutate_and_run(gate, find, repl, run=run, no_cargo=no_cargo,
                                    label_hint=label)
        print(f"  {'RED ' if red else 'GREEN'}  {label}{'  <- ' + note if note else ''}")
        green += 0 if red else 1
    return green


def self_test() -> int:
    """The harness's own rules. It cannot verify itself by mutation — that is
    the regress this file stops at — so its cases are direct."""
    import contextlib
    import io as _io

    def quietly(fn):
        with contextlib.redirect_stdout(_io.StringIO()), contextlib.redirect_stderr(_io.StringIO()):
            return fn()

    failures = 0

    # Every table entry's anchor must still occur exactly once. A drifted anchor
    # silently mutates nothing, and a table of no-ops passes every time.
    for gate, rows in MUTATIONS.items():
        text = _read(SCRIPTS / f"{gate}.py")
        for label, find, _ in rows:
            if label and label == os.environ.get("GATE_BITE_MUTATING"):
                # **The row being mutated right now.** When this file mutates
                # ITSELF the mutation removes its own anchor, so this check reds
                # -- and the parent records RED while the RULE was never
                # exercised. Red for the wrong reason reads exactly like red for
                # the right one, which is the defect this whole file rejects.
                continue
            if _find_one(text, find) < 0:
                failures += 1
                print(f"  FAIL {gate}: anchor for '{label}' occurs "
                      f"{text.count(find)}x outside the tables")
    # ...and the Rust table, which mutates in place and so must not drift silently.
    for label, rel, find in ((r[0], r[1], r[2]) for r in RUST_MUTATIONS):
        text = _read(REPO / rel)
        if _find_one(text, find) < 0:
            failures += 1
            print(f"  FAIL {rel}: anchor for '{label}' occurs {text.count(find)}x")
    if not failures:
        total = sum(len(v) for v in MUTATIONS.values())
        print(f"  ok  all {total} mutation anchors resolve exactly once")

    # **A child that never reached a case did not answer.** One shipped row
    # deleted the first line of a two-line tuple and left the continuation
    # dangling, so python's parser reddened the child and not one case ran --
    # counted RED, so `106/106` was 105 verdicts and one artifact. `D-467` asked
    # this of the RUST half in the same commit and not of this one.
    class _Unparseable:
        returncode, stdout = 1, ""
        stderr = "  File \"x.py\", line 147\nIndentationError: unexpected indent"

    # ...and the shape that made the FIRST version of this guard useless: a
    # child that REACHES many cases, passes them all, then raises. It exits
    # non-zero having proven nothing, and "did it reach a case" says yes.
    class _CrashedLate:
        returncode = 1
        stdout = "  ok  rule one\n  ok  rule two\n"
        stderr = "TypeError: unsupported operand type(s) for -: 'set' and 'str'"

    # ...and the shape a wrapper introduced in the SAME commit as this
    # guard: a self-test that dies is now caught and reported, and the
    # first version reported it with the word `FAIL` -- precisely the
    # token counted as a case disagreeing. `CRASH` is a different event.
    class _CaughtCrash:
        returncode = 1
        stdout = ("  ok  rule one\n"
                  "  CRASH some-gate --self-test raised before finishing: "
                  "ValueError: max() iterable argument is empty\n")
        stderr = ""

    gate0, (_, find0, repl0) = "citation-gate", MUTATIONS["citation-gate"][0]
    red, note = _mutate_and_run(gate0, find0, repl0, run=lambda _: _Unparseable())
    if red or "NO failing case" not in note:
        failures += 1
        print(f"  FAIL a child that printed no case was counted as a bite: {red}, {note!r}")
    else:
        print("  ok  a mutant whose child never reached a case is not a bite")

    red, note = _mutate_and_run(gate0, find0, repl0, run=lambda _: _CrashedLate())
    if red or "NO failing case" not in note:
        failures += 1
        print(f"  FAIL a child that passed every case and then crashed was a bite: {note!r}")
    else:
        print("  ok  a child that reaches cases, passes them, then raises is not a bite")

    red, note = _mutate_and_run(gate0, find0, repl0, run=lambda _: _CaughtCrash())
    if red or "NO failing case" not in note:
        failures += 1
        print(f"  FAIL a CAUGHT crash was counted as a case disagreeing: {note!r}")
    else:
        print("  ok  a crash the gate CAUGHT and reported is still not a bite")

    # A mutation that leaves the self-test GREEN must be reported as GREEN, and
    # one that reddens it as RED. Driven through the real `_mutate_and_run`.
    # A self-test child PRINTS a case line. These stand-ins must too, or they
    # are children that never reached a case -- which the guard below reports,
    # correctly, and which would make every one of these cases pass for the
    # wrong reason.
    # A RED self-test child prints a FAIL line; a GREEN one prints only `ok`.
    # A stand-in that reds with no FAIL line is a child that crashed, which the
    # guard below now reports as a survivor -- so these must agree, or every
    # case here passes for a reason unrelated to the rule under test.
    class _R:
        def __init__(self, rc, stdout=None):
            self.returncode = rc
            self.stdout = stdout if stdout is not None else (
                "  FAIL some rule did not bite\n" if rc else "  ok  some rule bit\n")
            self.stderr = ""

    gate, (_, find, repl) = "citation-gate", MUTATIONS["citation-gate"][0]
    red, _ = _mutate_and_run(gate, find, repl, run=lambda _: _R(1))
    if not red:
        failures += 1
        print("  FAIL a reddened self-test was not reported as RED")
    else:
        print("  ok  a reddened self-test is reported RED")
    red, note = _mutate_and_run(gate, find, repl, run=lambda _: _R(0))
    if red or "GREEN" not in note:
        failures += 1
        print("  FAIL a surviving mutation was not reported as GREEN")
    else:
        print("  ok  a surviving mutation is reported GREEN")

    # ...and the copy must be gone whatever happened, or a killed run leaves a
    # mutated file on disk — which is the incident this harness is shaped by.
    def _boom(_):
        raise RuntimeError("killed mid-run")

    try:
        _mutate_and_run(gate, find, repl, run=_boom)
    except RuntimeError:
        pass
    # **Excluding this file's own copy.** When the harness mutates ITSELF the
    # child runs as `.bite-gate-bite-harness.py`, and a bare glob finds it --
    # so an UNMUTATED exact copy already failed this check, and all five rows of
    # the self-mutation table were RED for a reason that had nothing to do with
    # the rule under test. A control the table itself could not distinguish from
    # success.
    leftover = [q for q in SCRIPTS.glob(".bite-*.py") if q.name != Path(__file__).name]
    if leftover:
        failures += 1
        print(f"  FAIL a crashed run left {[p.name for p in leftover]} on disk")
    else:
        print("  ok  a crashed run leaves no mutated copy behind")

    # The anchor guard must FIRE on an anchor that does not exist -- otherwise
    # the drift check above is the only thing standing, and it lives here too.
    red, note = _mutate_and_run(gate, "@@ NOT IN ANY FILE @@", "x")
    if red or "drifted" not in note:
        failures += 1
        print(f"  FAIL a missing anchor was not reported as drift: {note!r}")
    else:
        print("  ok  a missing anchor is reported as drift, not skipped")

    # m7 -- the reporting path. Every one of these was deletable with the suite
    # green, including "the mutation is never applied at all": a harness that had
    # stopped mutating reported every rule fine and looked like success.
    # **A TIMEOUT is a finding about that mutation, not the end of the run.**
    # `CHILD_TIMEOUT_S` was configured and never caught, so the documented local
    # invocation aborted at mutation 11 of 42 with a raw traceback and 47
    # mutations never executed -- reported by nothing.
    def _times_out(_):
        raise subprocess.TimeoutExpired(cmd="probe", timeout=CHILD_TIMEOUT_S)

    # **This case OWNS the exception.** Deleting the handler it defends makes
    # the call RAISE, which escaped, killed the run, and was read as the rule
    # biting -- so the case never once disagreed with anything.
    try:
        red, note = _mutate_and_run(gate, find, repl, run=_times_out)
    except BaseException as e:  # noqa: BLE001 - the escape IS the finding
        red, note = True, f"escaped as {type(e).__name__}"
    if red or "did not finish" not in note:
        failures += 1
        print(f"  FAIL a timed-out child must be a finding, not a crash: {note!r}")
    else:
        print("  ok  a timed-out child is reported, and the run continues")

    same, note = _mutate_and_run(gate, find, find)
    if same or "nothing was mutated" not in note:
        failures += 1
        print(f"  FAIL a no-op replacement must be reported, not run: {note!r}")
    else:
        print("  ok  a replacement that changes nothing is reported, not run")

    # The injected runner answers by PATH: the unmutated original is green and
    # only the `.bite-` copy carries the verdict under test. A runner that
    # answered the same for both would fail the baseline and never reach the
    # rows -- which is the guard working, not the case.
    def _by_path(rc):
        return lambda path: _R(rc if Path(path).name.startswith(".bite-") else 0)

    if quietly(lambda: run_gate(gate, run=_by_path(0), only="the pragma")) == 0:
        failures += 1
        print("  FAIL run_gate did not count a surviving mutation")
    else:
        print("  ok  run_gate counts survivors")
    if quietly(lambda: run_gate(gate, run=_by_path(1), only="the pragma")) != 0:
        failures += 1
        print("  FAIL run_gate counted a reddened mutation as a survivor")
    else:
        print("  ok  run_gate does not count a reddened mutation")
    if quietly(lambda: run_gate(gate, run=_by_path(1), only="@@ MATCHES NOTHING @@")) != 0:
        failures += 1
        print("  FAIL an empty filter must select nothing, not report success")
    else:
        print("  ok  an empty filter selects nothing")
    if quietly(lambda: main(argv=["--only", "@@ MATCHES NOTHING @@"])) != 2:
        failures += 1
        print("  FAIL main() must refuse a filter that matched no mutation")
    else:
        print("  ok  main() refuses a filter that matched no mutation")

    # ── M3: round 10 added `--no-cargo`, `--rust`, the dirty refusal, the
    # timeout and the applied-mutation check, and gave a case to ONE of them.
    # Thirteen of fifteen mutations of that new code survived. The sharpest was
    # `red = True` in `run_rust`: **the harness could report every Rust mutation
    # RED unconditionally and its own self-test stayed green**, which makes "all
    # 9 red" unfalsifiable by the mechanism that produced it.
    import tempfile
    rust_calls: list[str] = []

    class _RustR:
        def __init__(self, rc):
            self.returncode, self.stdout, self.stderr = rc, "", ""

    def _rust_run(rc):
        def go(test):
            rust_calls.append(test)
            r = _RustR(rc)
            # A real `cargo test --exact <name>` that reds prints this line. A
            # stand-in that reds without it is a run whose NAMED test did not
            # fail, which the guard now counts as a survivor.
            r.stdout = f"test {test} ... FAILED" if rc else f"test {test} ... ok"
            return r
        return go

    # **`write=` on every call that does not need real bytes.** The first
    # version injected it on ONE of four, so `--self-test` -- which the
    # pre-commit hook runs -- still performed 30 in-place writes to the shipped
    # crate sources, the exact number the commit message states as the defect it
    # fixed. The certifying case could not see it: it compares CONTENT, which
    # the content-keyed restore guarantees by construction.
    nowrite = lambda *a, **k: None
    survivors, refusal = quietly(lambda: run_rust(run=_rust_run(1), write=nowrite))
    if survivors or refusal or not rust_calls:
        failures += 1
        print(f"  FAIL a reddened Rust mutation must not count: {survivors}, {refusal}")
    else:
        print(f"  ok  a reddened Rust mutation is not a survivor ({len(rust_calls)} run)")

    rust_calls.clear()
    survivors, refusal = quietly(lambda: run_rust(run=_rust_run(0), write=nowrite))
    if survivors != len(RUST_MUTATIONS) or refusal:
        failures += 1
        print(f"  FAIL a GREEN Rust mutation must be a survivor: got {survivors} of "
              f"{len(RUST_MUTATIONS)}")
    else:
        print("  ok  a surviving Rust mutation is counted")

    # **The two guards the Rust half did not have.** Both are driven over a
    # temp tree through the `rows=`/`root=` injection added with them -- this
    # half read the real crate unconditionally, so neither could be cased, and
    # a guard that cannot be driven is how the asymmetry survived.
    with tempfile.TemporaryDirectory() as d:
        probe = Path(d) / "probe.rs"
        probe.write_text("let a = 1;\nlet a = 1;\nlet b = 2;\n", encoding="utf-8")
        twice = [("anchor twice", "probe.rs", "let a = 1;", "let z = 9;", "t")]
        survivors, refusal = quietly(lambda: run_rust(
            run=_rust_run(1), write=nowrite, rows=twice, root=Path(d)))
        if survivors != 1 or refusal:
            failures += 1
            print(f"  FAIL a Rust anchor occurring twice must not be mutated: {survivors}")
        else:
            print("  ok  a Rust anchor occurring twice is drift, not a silent first-hit")

        # **A mutant is a bite only when the NAMED TEST fails.** Three
        # shapes, each of which `rc != 0` alone calls a bite:
        #   * a mutant that does not build -- no test line at all;
        #   * a mutant that breaks a DIFFERENT test;
        #   * a `--exact` name that no longer matches anything.
        # This replaces a `BROKE` guard that read compiler noise from stderr:
        # measured unreachable once this question was asked, because a mutant
        # that does not build cannot print `test <name> ... FAILED`.
        class _NoTestLine:
            returncode, stdout = 101, ""
            stderr = "error[E0308]: mismatched types"

        class _OtherFailed:
            returncode = 101
            stdout = "test some_other_test ... FAILED"
            stderr = ""

        # **The probe must carry the anchor ONCE.** The previous case left it
        # on two lines, so `_find_one` reported DRIFT and both the shipped code
        # and the mutant returned the same count -- two cases passing for a
        # reason unrelated to the guard they were written to prove.
        probe.write_text("let a = 1;" + chr(10) + "let b = 2;" + chr(10),
                         encoding="utf-8")
        one = [("compiles not", "probe.rs", "let a = 1;", "let a = ();", "t")]
        for name, fake in (("does not build", _NoTestLine),
                           ("breaks a DIFFERENT test", _OtherFailed)):
            survivors, refusal = quietly(lambda: run_rust(
                run=lambda _t: fake(), write=nowrite, rows=one, root=Path(d)))
            if survivors != 1 or refusal:
                failures += 1
                print(f"  FAIL a mutant that {name} must not read as a bite: {survivors}")
            else:
                print(f"  ok  a Rust mutant that {name} is not counted as red")

        null = [("changes nothing", "probe.rs", "let b = 2;", "let b = 2;", "t")]
        probe.write_text("let a = 1;" + chr(10) + "let b = 2;" + chr(10), encoding="utf-8")
        survivors, refusal = quietly(lambda: run_rust(
            run=_rust_run(1), write=nowrite, rows=null, root=Path(d)))
        if survivors != 1 or refusal:
            failures += 1
            print(f"  FAIL a NULL Rust mutation must not read as red: {survivors}")
        else:
            print("  ok  a Rust mutation that changes nothing is refused, not counted red")

    # The restore is not optional: `--rust` mutates the real crate in place.
    # **The write/restore round trip, proved on a TEMP file.** The previous
    # version kept the real writer on one real crate file, so `--self-test` --
    # which the pre-commit hook runs on every staged `scripts/*.py` -- still
    # wrote `fold.rs` twice, bypassing the dirty-tree refusal because that call
    # site passes `run=`. Proving a round trip does not require touching the
    # shipped sources, and it covers a case the crate files cannot: **CRLF**,
    # whose re-application in `_write` has never had one.
    with tempfile.TemporaryDirectory() as d:
        for label, raw in (("LF", b"line one\nline TWO\n"),
                           ("CRLF", b"line one\r\nline TWO\r\n")):
            f = Path(d) / f"probe-{label}.txt"
            f.write_bytes(raw)
            original = _raw(f)
            _write(f, _read(f).replace("TWO", "THREE", 1), like=original)
            mutated = _raw(f)
            f.write_bytes(original)
            if mutated == original:
                failures += 1
                print(f"  FAIL {label}: the mutation did not change the file")
            elif label == "CRLF" and b"\r\n" not in mutated:
                failures += 1
                print("  FAIL CRLF: the newline convention was not re-applied")
            elif _raw(f) != original:
                failures += 1
                print(f"  FAIL {label}: the restore was not byte-exact")
            else:
                print(f"  ok  {label}: mutate and restore is byte-exact")

    # ...and NOTHING under `crates/` is written by a self-test run.
    crate_writes: list[str] = []
    real_write = globals()["_write"]
    real_bytes = Path.write_bytes

    def _spy_write(path, text, like=None):
        crate_writes.append(str(path))
        return real_write(path, text, like=like)

    def _spy_bytes(self, data):
        crate_writes.append(str(self))
        return real_bytes(self, data)

    globals()["_write"] = _spy_write
    Path.write_bytes = _spy_bytes
    try:
        quietly(lambda: run_rust(run=_rust_run(1), write=nowrite))
    finally:
        globals()["_write"] = real_write
        Path.write_bytes = real_bytes
    into_crates = [w for w in crate_writes if "actor-hub" in w and "src" in w]
    if into_crates:
        failures += 1
        print(f"  FAIL a self-test run wrote {len(into_crates)} crate file(s)")
    else:
        print("  ok  a self-test run writes no crate source, by any route")

    # **A refusal is not a survivor count.** The first version returned `2` as a
    # sentinel and `main` printed "2 Rust mutation(s) SURVIVED" for a run in
    # which nothing executed.
    fake_dirty = ["crates/actor-hub/src/fold.rs"]
    _real_dirty = globals()["_rust_dirty"]
    globals()["_rust_dirty"] = lambda: fake_dirty
    try:
        survivors, refusal = quietly(lambda: run_rust(write=nowrite))
        rc = quietly(lambda: main(argv=["--rust"]))
    finally:
        globals()["_rust_dirty"] = _real_dirty
    if survivors != 0 or not refusal or "refusing" not in refusal:
        failures += 1
        print(f"  FAIL a dirty tree must refuse with ZERO survivors: {survivors}, {refusal}")
    elif rc != 2:
        failures += 1
        print(f"  FAIL a refused --rust must exit 2, not report survivors: rc={rc}")
    else:
        print("  ok  a dirty tree refuses, with no survivors invented")

    # **`--no-cargo` must REACH the child, observed at the call the child is
    # actually made with.** The first version called `_child_env(True)` inside
    # its own fake runner and asserted on that -- so it tested the helper and
    # not the forwarding, and all three plumbing mutations survived while the
    # comment above it claimed otherwise. Measured non-equivalence: 0.37 s with
    # the flag, 38 s without.
    calls: list[dict] = []

    def _spy(cmd, **kw):
        # rc=0 for the BASELINE child (the unmutated original), rc=1 for the
        # mutated copy. A spy that fails everything fails the baseline, so
        # `run_gate` returns before launching the child this case observes --
        # and `calls[-1]` is then the baseline's own call site, which forwards
        # correctly, so the case passes while proving nothing.
        calls.append(kw)
        return _R(0 if not any(".bite-" in str(a) for a in cmd) else 1)

    import subprocess as _sp
    real_run = _sp.run
    _sp.run = _spy
    try:
        quietly(lambda: run_gate(gate, only="the pragma", no_cargo=True))
        with_flag = calls[-1].get("env")
        quietly(lambda: run_gate(gate, only="the pragma", no_cargo=False))
        without = calls[-1].get("env")
        quietly(lambda: main(argv=["--gate", gate, "--only", "the pragma", "--no-cargo"]))
        via_main = calls[-1].get("env")
    finally:
        _sp.run = real_run

    # **Assert the FORWARDING, not cargo's absence.** Checking that the child's
    # PATH has no cargo is vacuous on a machine that has none -- which is
    # precisely the machine CI runs this on, so in the only automatic runner the
    # assertion could not fail. A sentinel proves the value travelled.
    marker = {"PATH": "", "LOREWEAVE_CHILD_ENV_MARKER": "1"}
    real_child_env = globals()["_child_env"]
    globals()["_child_env"] = lambda flag: marker if flag else None
    calls.clear()
    _sp.run = _spy
    try:
        quietly(lambda: run_gate(gate, only="the pragma", no_cargo=True))
        forwarded = calls[-1].get("env") if calls else "no child was launched"
        quietly(lambda: run_gate(gate, only="the pragma", no_cargo=False))
        not_forwarded = calls[-1].get("env") if calls else "no child was launched"
    finally:
        _sp.run = real_run
        globals()["_child_env"] = real_child_env
    # The child's env is a COPY -- it carries the row hint -- so the assertion
    # is that the sentinel's CONTENT travelled, not that the object did.
    if not isinstance(forwarded, dict) or "LOREWEAVE_CHILD_ENV_MARKER" not in forwarded:
        failures += 1
        print(f"  FAIL --no-cargo's environment did not reach the child: {forwarded}")
    else:
        print("  ok  --no-cargo's environment reaches the child (sentinel observed)")
    if not isinstance(not_forwarded, dict) or "LOREWEAVE_CHILD_ENV_MARKER" in not_forwarded:
        failures += 1
        print(f"  FAIL without --no-cargo the child must inherit the environment: "
              f"{type(not_forwarded).__name__}")
    else:
        print("  ok  without --no-cargo the environment is inherited unchanged")
    # ...and the helper itself removes every entry carrying cargo -- asserted
    # against a SYNTHETIC PATH, because asserting cargo's absence is vacuous on
    # a machine that has none, and that is precisely the machine CI runs this
    # on. The assertion three lines above was fixed for exactly this reason and
    # this one was left; one token substituted, in the fix for one-token
    # substitution.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        one, two = Path(d) / "a", Path(d) / "b"
        for slot in (one, two):
            slot.mkdir()
            exe = slot / ("cargo.exe" if os.name == "nt" else "cargo")
            exe.write_text("", encoding="utf-8")
            exe.chmod(0o755)
        keep = Path(d) / "keep"
        keep.mkdir()
        real_path = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join(str(x) for x in (one, keep, two))
        try:
            stripped = real_child_env(True)
            left = [x for x in stripped["PATH"].split(os.pathsep) if x]
        finally:
            os.environ["PATH"] = real_path
    if left != [str(keep)]:
        failures += 1
        print(f"  FAIL _child_env kept {left}, want only the cargo-free entry")
    else:
        print("  ok  _child_env removes EVERY entry carrying cargo, keeping the rest")

    # ...and the child is invoked with the arguments the mode needs. Nothing
    # asserted the cargo command shape, so dropping `-p actor-hub`, `--exact` or
    # the test name were all survivors.
    argv_seen: list[list[str]] = []

    def _spy_argv(cmd, **kw):
        # `_rust_dirty` shells out to `git status` first, so only the cargo
        # invocation is the subject here.
        # The MUTATION invocation, not the baseline probe that now precedes it.
        if list(cmd)[:1] == ["cargo"] and "--exact" in list(cmd):
            argv_seen.append(list(cmd))
            return _R(1)
        return real_run(cmd, **kw)

    _sp.run = _spy_argv
    # **The tree is reported CLEAN for the duration of this case**, because
    # `run_rust` refuses on a dirty one — and the tree is ALWAYS dirty at the
    # moment that matters, since the pre-commit hook runs this with the change
    # staged. Without the swap the case observes nothing, reports `[]`, and
    # fails on the first commit that stages a file `RUST_MUTATIONS` touches:
    # the SUBJECT would be the developer's git state rather than the argv.
    _real_dirty_here = globals()["_rust_dirty"]
    globals()["_rust_dirty"] = lambda: []
    _sp.run = _spy_argv
    try:
        quietly(lambda: run_rust(only="a refused derivation", write=lambda *a, **k: None))
    finally:
        _sp.run = real_run
        globals()["_rust_dirty"] = _real_dirty_here
    want = ["cargo", "test", "-p", "actor-hub", "--test", "fold_survivors",
            "a_refused_derivation_is_recorded_with_its_row_index", "--", "--exact"]
    if shutil.which("cargo") is None:
        # No toolchain: `run_rust` refuses before invoking anything, which is
        # the degrade-safe answer and leaves this case nothing to observe.
        print("  ok  --rust's cargo argv: not observable without a toolchain (skipped)")
    elif not argv_seen or argv_seen[0] != want:
        failures += 1
        print(f"  FAIL the cargo command is not what --rust needs: {argv_seen[:1]}")
    else:
        print("  ok  --rust invokes cargo with the crate, the test and --exact")

    # B2 -- a filter that selects no Rust mutation must not report success. The
    # gate branch had this guard and two cases; the `--rust` branch had neither,
    # and it is the only signal of the CI job it exists for.
    if quietly(lambda: main(argv=["--rust", "--only", "@@ MATCHES NOTHING @@"])) != 2:
        failures += 1
        print("  FAIL --rust with a filter matching nothing did not refuse")
    else:
        print("  ok  --rust refuses a filter that selects nothing")

    # ...and a filter that DOES match must not be refused. Without this the
    # guard could simply never see the Rust table and both directions would look
    # identical, because "matched nothing" and "cannot see the table" produce the
    # same answer for a filter that matches nothing.
    err = _io.StringIO()
    with contextlib.redirect_stdout(_io.StringIO()), contextlib.redirect_stderr(err):
        main(argv=["--rust", "--only", "a refused derivation"])
    if "no mutation matched" in err.getvalue():
        failures += 1
        print("  FAIL a --rust filter that MATCHES was refused as empty")
    else:
        print("  ok  a --rust filter that matches is not refused")


    # **The baseline guard**, both directions. Without it the harness cannot
    # distinguish "every rule bites" from "the suite is already broken", and CI's
    # `--no-cargo` job is the only automatic runner -- so a red baseline there
    # reported 47 of 47 red while three NULL mutations were also red.
    if baseline_is_green(gate, run=lambda _: _R(0)) is not None:
        failures += 1
        print("  FAIL a green baseline was reported as red")
    else:
        print("  ok  a green baseline lets the mutations speak")
    why = baseline_is_green(gate, run=lambda _: _R(1))
    if not why or "UNMUTATED" not in why:
        failures += 1
        print(f"  FAIL a red baseline was not reported: {why!r}")
    else:
        print("  ok  a red baseline is reported instead of 47 free reds")
    if quietly(lambda: run_gate(gate, run=lambda _: _R(1), only="the pragma")) >= 0:
        failures += 1
        print("  FAIL a red baseline must not be counted as surviving rules")
    else:
        print("  ok  a red baseline is not reported as rules without cases")

    # The RUST baseline, both directions.
    survivors, refusal = quietly(lambda: run_rust(run=_rust_run(1), write=nowrite,
                                                  baseline=lambda: _RustR(1)))
    # BOTH halves of the answer: the refusal text AND the survivor count. The
    # count is what `main` acts on, and asserting only the text let a mutation
    # that discards the baseline's verdict keep the message while returning zero.
    if not refusal or "already fails" not in refusal or survivors != len(RUST_MUTATIONS):
        failures += 1
        print(f"  FAIL a red Rust baseline was not reported: {refusal!r}, "
              f"survivors={survivors} of {len(RUST_MUTATIONS)}")
    else:
        print("  ok  a red Rust baseline is reported instead of N free reds")
    survivors, refusal = quietly(lambda: run_rust(run=_rust_run(1), write=nowrite,
                                                  baseline=lambda: _RustR(0)))
    if refusal or survivors:
        failures += 1
        print(f"  FAIL a green Rust baseline blocked the run: {refusal!r}")
    else:
        print("  ok  a green Rust baseline lets the Rust mutations speak")

    # A drifted anchor and a timed-out child must each COUNT on the Rust side,
    # exactly as they do on the gate side. Both were `green += 1` with no case.
    def _boom_timeout(_):
        raise subprocess.TimeoutExpired(cmd="cargo", timeout=CHILD_TIMEOUT_S)

    slow, _ = quietly(lambda: run_rust(run=_boom_timeout, write=nowrite,
                                       baseline=lambda: _RustR(0)))
    if slow < 1:
        failures += 1
        print("  FAIL a timed-out Rust child was not counted as a non-verdict")
    else:
        print("  ok  a timed-out Rust child counts, and does not read as success")

    real_rows = RUST_MUTATIONS[:]
    globals()["RUST_MUTATIONS"] = [("drift probe", real_rows[0][1], "@@ NOT PRESENT @@",
                                    "x", real_rows[0][4])]
    try:
        drift, _ = quietly(lambda: run_rust(run=_rust_run(1), write=nowrite,
                                            baseline=lambda: _RustR(0)))
    finally:
        globals()["RUST_MUTATIONS"] = real_rows
    if drift < 1:
        failures += 1
        print("  FAIL a drifted Rust anchor was not counted as a non-verdict")
    else:
        print("  ok  a drifted Rust anchor counts, and does not read as success")

    # `main` must ACT on the negative sentinel: a red baseline cancelling a real
    # survivor into rc 0 is the failure the sentinel exists to prevent.
    real_run_gate = globals()["run_gate"]
    for verdicts, want, why in (([-1], 1, "a red baseline alone"),
                                ([-1, 1], 1, "a red baseline cancelling a survivor"),
                                ([0, 0], 0, "two clean gates")):
        # Padded: `main` iterates every gate table, so a short sequence
        # runs out before the loop does.
        seq = list(verdicts) + [0] * len(MUTATIONS)
        globals()["run_gate"] = lambda *a, **k: seq.pop(0)
        err = _io.StringIO()
        try:
            with contextlib.redirect_stdout(_io.StringIO()), contextlib.redirect_stderr(err):
                rc = main(argv=["--no-cargo"])
        finally:
            globals()["run_gate"] = real_run_gate
        if rc != want:
            failures += 1
            print(f"  FAIL {why}: rc={rc}, want {want}")
        elif verdicts[0] < 0 and "proves NOTHING" not in err.getvalue():
            failures += 1
            print(f"  FAIL {why}: the summary did not say the run proves nothing")
        else:
            print(f"  ok  main acts on {why}")

    # `baseline_is_green` must run its child in the SAME environment as the
    # mutations, or a baseline can pass where the mutations never run.
    seen_env: list[dict | None] = []
    globals()["_child_env"] = lambda flag: marker if flag else None
    _sp.run = lambda cmd, **kw: (seen_env.append(kw.get("env")), _R(0))[1]
    try:
        baseline_is_green(gate, no_cargo=True)
    finally:
        _sp.run = real_run
        globals()["_child_env"] = real_child_env
    if not seen_env or not isinstance(seen_env[0], dict) \
            or "LOREWEAVE_CHILD_ENV_MARKER" not in seen_env[0]:
        failures += 1
        print(f"  FAIL the baseline child did not get the --no-cargo environment")
    else:
        print("  ok  the baseline child runs in the same environment as the mutations")

    # ── PARITY: this file has two halves, and every round hardens one ────────
    #
    # **The anchor search excludes the tables at the CALL SITE too.** Reverting
    # it to a raw `text.find` mutates the TABLE ROW naming a rule instead of the
    # rule -- so the child runs unmutated code, stays green, and the row reads as
    # a surviving rule. It was the sole survivor of a 101-row sweep.
    with tempfile.TemporaryDirectory() as d:
        probe = Path(d) / "probe-gate.py"
        probe.write_text(
            'MUTATIONS = {"probe-gate": [("row", "guard = 1", "guard = 0")]}\n'
            "def rule():\n"
            "    guard = 1\n"
            "    return guard\n", encoding="utf-8")
        seen_text: list[str] = []

        class _R0:
            returncode, stdout, stderr = 0, "  ok  some rule bit\n", ""


        _mutate_and_run("probe-gate", "guard = 1", "guard = 9",
                        run=lambda q: (seen_text.append(_read(q)), _R0())[1],
                        root=Path(d))
        body = seen_text[0] if seen_text else ""
        if "guard = 9" not in body or '("row", "guard = 1"' not in body:
            failures += 1
            print("  FAIL the anchor search mutated the TABLE ROW, not the rule")
        else:
            print("  ok  the anchor search skips the table row that names the rule")

    # **A row's LABEL must name what its ANCHOR touches.** Four rounds
    # running, the blocking finding was a row asserting coverage of something
    # adjacent to what it mutates, and each round's remedy was to write a better
    # row. Reading the row instead: measured over all 132 shipped rows before it
    # was wired, ONE finding, and it was the defect.
    all_rows = [(r[0], f"scripts/{g}.py", r[1], r[2])
                for g, v in MUTATIONS.items() for r in v]
    all_rows += [(r[0], r[1], r[2], r[3]) for r in RUST_MUTATIONS]
    # **A CANARY row, so the check can never be vacuous.** The shipped rows are
    # clean, so `bad = mislabelled_rows(all_rows)` -> `bad = []` changed nothing
    # and survived: a rule reporting "all N rows are fine" about a set it never
    # examined. The subject set therefore always carries ONE known-bad row, and
    # the check is "exactly the canary" rather than "nothing" -- NV-3 closed by
    # construction rather than by a floor, which the same mutation walked past.
    canary = ("Accumulator.wanted is the canary", "crates/actor-hub/src/fold.rs",
              "        capped.push(Capped { quantity: q, site: CapSite::Emit,"
              " wanted: r.value, emitted: out });", "")
    bad = mislabelled_rows(all_rows + [canary])
    if len(all_rows) < 100:
        failures += 1
        print(f"  FAIL the label rule saw only {len(all_rows)} rows")
    # **ASSERTED PRESENT, not forgiven.** Forgiving the canary and then asking
    # `if bad:` let an EMPTY result pass, so `bad = []` survived the very rule
    # the canary was added to make non-vacuous. The check is now "exactly one
    # finding, and it is the canary" -- which no empty answer satisfies.
    verdict = canary_verdict(bad)
    if verdict:
        failures += 1
        for b in verdict:
            print(f"  FAIL a row aimed at a sibling — {b}")
    else:
        print(f"  ok  all {len(all_rows)} rows' labels name what their anchors "
              "touch, and the canary is reported")

    # ...and BOTH clauses of that verdict, driven directly, because the
    # empty-result clause is unreachable while the rule works -- which is how
    # `strays or len(bad) != 1` -> `strays` survived a whole sweep.
    for name, given, expect, want in (
            ("an empty result", [], 1, True),
            ("the canary alone", ["'x': canary"], 1, False),
            ("the canary plus a stray", ["'x': canary", "'y': real"], 1, True),
            ("a stray alone", ["'y': real"], 1, True),
            # ...and the PAIR form the sibling rule uses. Without it the
            # `expect` parameter has no subject at anything but its default,
            # which is the shape that let `len(...) != 2` survive.
            ("one canary where two are due", ["'x': canary"], 2, True),
            ("both canaries", ["'x': canary", "'y': canary"], 2, False)):
        if bool(canary_verdict(given, expect=expect)) != want:
            failures += 1
            print(f"  FAIL the canary verdict on {name}: "
                  f"{canary_verdict(given, expect=expect)}")
        else:
            print(f"  ok  the canary verdict on {name} -> "
                  f"{'reported' if want else 'silent'}")

    # ...and the rule must SEE each shape. Both probes are the real defects it
    # was built from: a label naming a member whose halves live on different
    # lines, and a label naming a function the anchor's neighbourhood does not
    # contain.
    probes = (
        ("a member named across two records",
         ("Accumulator.wanted reports the EMITTED value", "crates/actor-hub/src/fold.rs",
          "        capped.push(Capped { quantity: q, site: CapSite::Emit,"
          " wanted: r.value, emitted: out });", "")),
        ("a function the anchor's neighbourhood never mentions",
         ("check_derivation stops checking the layer", "crates/actor-hub/src/fold.rs",
          "    let out = r.value.clamp(i32::MIN as i64, i32::MAX as i64) as i32;", "")),
    )
    for name, row in probes:
        if len(mislabelled_rows([row])) != 1:
            failures += 1
            print(f"  FAIL the label rule missed {name}")
        else:
            print(f"  ok  the label rule reports {name}")
    # **The anchor search must EXCLUDE the tables**, and only a row whose
    # anchor also appears in a table row can tell the two apart: with a raw
    # `find` the "enclosing definition" becomes the whole table, which contains
    # every token any label could name, so nothing is ever reported. This file
    # mutates itself, so its own table is exactly that situation.
    # The anchor is SPLIT so this line is not itself a second occurrence --
    # which the first version was, putting the anchor outside the tables after
    # all and making the case pass for the wrong reason.
    only_in_table = '        ("the sibling rule ' + 'covers no row",'
    # The label names `must_claim`, which appears in the TABLE region and
    # nowhere near the rule -- so a raw `find` puts it in scope and reports
    # nothing, while the table-aware search reports it. That difference is the
    # whole point of `_find_one`, and only a token with this placement can see it.
    table_row = ("the must_claim surplus is not reported",
                 "scripts/gate-bite-harness.py", only_in_table, "")
    if len(mislabelled_rows([table_row])) != 1:
        failures += 1
        print("  FAIL an anchor inside a TABLE was not searched outside it")
    else:
        print("  ok  the anchor search excludes the tables, so the scope is the rule")

    # ...and stays silent on a filename, which LOOKS dotted and is not a member.
    ok_row = ("the _index.md scope row deleted", "scripts/actor-hub-figures-gate.py",
              '    (INDEX, "# Actor Hub", END("index"),', "")
    if mislabelled_rows([ok_row]):
        failures += 1
        print("  FAIL the label rule read a FILENAME as a member access")
    else:
        print("  ok  a filename in a label is not read as a member access")

    # **One mutation per PRODUCTION RULE**, which the governed handoff block
    # asserts and nothing checked: a byte-identical row shipped TWICE, so the
    # total counted 120 rules where there were 119. `--only` matched both.
    rowset: dict[tuple, int] = {}
    for gate_name, table in MUTATIONS.items():
        for r in table:
            rowset[(gate_name, r[0], r[1], r[2])] = rowset.get(
                (gate_name, r[0], r[1], r[2]), 0) + 1
    for r in RUST_MUTATIONS:
        rowset[(r[1], r[0], r[2], r[3])] = rowset.get((r[1], r[0], r[2], r[3]), 0) + 1
    # A CANARY in the subject set, so `if dupes:` cannot be deleted: the table
    # is clean, so an empty result passed either way. The same NV-3 the label
    # and sibling rules each needed, on the third rule beside them.
    rowset[("<canary>", "the duplicate canary", "a", "b")] = 2
    dupes = [f"{k[0]} | {k[1]}" for k, n in rowset.items() if n > 1]
    dupe_verdict = canary_verdict(dupes, expect=1)
    if dupe_verdict:
        failures += 1
        for d in dupe_verdict:
            print(f"  FAIL a row is written twice — {d}")
    else:
        print(f"  ok  all {len(rowset) - 1} rows are distinct, and the canary is not")

    # **...and the shape a token regex cannot reach.** See
    # `interchangeable_rows`: two anchors differing by one capitalised token,
    # with labels that do not name their own. That IS `D-476`, and round 18's
    # remedy — renaming the label — moved both rows out of the token rule's
    # scope, so the rule built for the defect no longer examines it.
    sibs = [(r[0], f"scripts/{g}.py", r[1]) for g, v in MUTATIONS.items() for r in v]
    sibs += [(r[0], r[1], r[2]) for r in RUST_MUTATIONS]
    # **Two CANARY rows, so this call can never be vacuous.** `swappable = []`
    # survived otherwise: a clean report about a set the rule never examined --
    # the same NV-3 the label rule's canary closed one commit earlier, in the
    # rule written beside it.
    # A file of their own, so they pair with each other and not with the real
    # rows that share those anchors -- which produced four findings, two of
    # them about correct rows.
    canaries = [("the FIRST canary", "<canary>", "let x = CapSite::Emit;"),
                ("the SECOND canary", "<canary>", "let x = CapSite::Accumulator;")]
    swappable = interchangeable_rows(sibs + canaries)
    # The SAME verdict helper as the label rule's. Re-deriving it produced the
    # identical unreachable-clause defect twice in two commits.
    sib_verdict = canary_verdict(swappable, expect=2)
    if sib_verdict:
        failures += 1
        for w in sib_verdict:
            print(f"  FAIL two rows are interchangeable — {w}")
    else:
        print(f"  ok  no two of the {len(sibs)} rows are interchangeable, and the "
              "canary pair is")

    # ...and the rule must SEE the defect it was built from: swap the two
    # `Capped` anchors, keep the shipped labels, and BOTH halves must report.
    swapped = []
    for lab, rel, find in sibs:
        if "CapSite::Emit, wanted: r.value" in find and "Emit record" in lab:
            find = find.replace("CapSite::Emit", "CapSite::Accumulator")
        elif "CapSite::Accumulator, wanted: r.value" in find and "Accumulator record" in lab:
            find = find.replace("CapSite::Accumulator", "CapSite::Emit")
        swapped.append((lab, rel, find))
    if len(interchangeable_rows(swapped)) != 2:
        failures += 1
        print("  FAIL swapping the two Capped anchors was not reported "
              f"({len(interchangeable_rows(swapped))} finding(s))")
    else:
        print("  ok  swapping two sibling anchors reports BOTH labels")

    # **The derived half: no gate this harness drives may spawn a child that
    # nothing can interrupt.** The table below is four hand-written rows and so
    # detects no NEW one-sided guard; this asks the tree, over every script the
    # harness has a table for plus the driver that runs them all. It found four
    # when it was written, one of them in this file.
    guarded = sorted(set(MUTATIONS) | {"gate-self-tests"})
    hangs = [f"{g}.py: {w}" for g in guarded
             for w in unbounded_children(_read(SCRIPTS / f"{g}.py"))]
    if hangs:
        failures += 1
        for w in hangs:
            print(f"  FAIL a child nothing can interrupt — {w}")
    elif len(guarded) < 4 or "gate-bite-harness" not in guarded:
        # **The subject set needs a FLOOR.** Emptying it left the sweep silent
        # and printing "none of the 0 gates" -- a clean report about nothing,
        # which is NV-3 in the rule written to close an NV-3 finding.
        failures += 1
        print(f"  FAIL the unbounded-child sweep covers only {guarded}")
    else:
        print(f"  ok  none of the {len(guarded)} gates spawn an uninterruptible child")

    # ...and the sweep must SEE each shape SEPARATELY. One planted probe missing
    # both a timeout and a handler is answered by either arm, so deleting either
    # left it reported by the other and both mutations survived. Two probes, one
    # per arm, each carrying the guard the other lacks.
    probes = (
        ("no timeout, but a handler",
         "import subprocess\n"
         "def spawns():\n"
         "    try:\n"
         "        return subprocess.run(['x'], capture_output=True)\n"
         "    except subprocess.TimeoutExpired:\n"
         "        return None\n"),
        ("a timeout, but no handler",
         "import subprocess\n"
         "def spawns():\n"
         "    return subprocess.run(['x'], capture_output=True, timeout=1)\n"),
    )
    for label, probe in probes:
        if len(unbounded_children(probe)) != 1:
            failures += 1
            print(f"  FAIL the unbounded-child sweep missed a planted one ({label})")
        else:
            print(f"  ok  the unbounded-child sweep reports a planted one ({label})")
    # ...and a function carrying BOTH guards is silent, or the rule is a blanket.
    clean = ("import subprocess\n"
             "def spawns():\n"
             "    try:\n"
             "        return subprocess.run(['x'], capture_output=True, timeout=1)\n"
             "    except subprocess.TimeoutExpired:\n"
             "        return None\n")
    if unbounded_children(clean):
        failures += 1
        print("  FAIL a fully guarded spawn was reported")
    else:
        print("  ok  a spawn with both a timeout and a handler is silent")

    # Measured across rounds 10-15, six BLOCKING/MAJOR findings in one commit
    # were the same object: a guard added to the gate half and not the Rust
    # half, a sentinel cased at its producer and not its consumer, an
    # environment asserted for one child and not the other. **Noticing that by
    # reading is what has failed fifteen times**, so it is a check.
    #
    # Each row names a property both halves must have and the substring that
    # witnesses it. A new guard on one side with no twin fails here, by name.
    # **`__file__`, not the name.** This read the ORIGINAL while the child
    # under test IS the mutated copy beside it, so every witness below was
    # searched in unmutated bytes -- the parity table could not see the mutation
    # aimed at it, and `GATE_BITE_MUTATING` (whose whole job is to let the child
    # skip the anchor its own mutation removed) was inert for the same reason.
    own_full = _read(Path(__file__))
    # **...and only the CODE, not the tables.** This file contains the parity
    # table and the mutation rows, so every single-line witness was present
    # whether or not the guard existed: seven of the eight survived deleting the
    # guard they witness. `_outside_tables` already answers this question for
    # anchors, and was not used by the check that needed it most.
    own = "\n".join(own_full[a:b] for a, b in _outside_tables(own_full))
    # Each row: the property, then (witness, mutation-row token) for each half.
    # **The row token is separate from the witness.** Deriving it by cutting the
    # witness at its first `(` matched neither half reliably -- the Rust
    # baseline HAS two rows and the derived token found neither, so the check
    # reported a pass for a reason unrelated to whether the row exists.
    parity = (
        ("a baseline before mutating",
         ("reason = baseline_is_green(", "reason = baseline_is_green("),
         ("probe = baseline()", "probe = baseline()")),
        ("a caught timeout",
         ("except subprocess.TimeoutExpired:\n            # A timeout is a FINDING",
          "# A timeout is a FINDING about that mutation"),
         ("            except subprocess.TimeoutExpired:", "SLOW   {label:52} -> no verdict")),
        ("a drifted anchor counted, not skipped",
         ("anchor occurs {text.count(find)}x outside the tables", "at = _find_one(text, find)"),
         ("            at = _find_one(src, find)", "at = _find_one(src, find)")),
        ("the child environment forwarded",
         ("capture_output=True, text=True, timeout=CHILD_TIMEOUT_S,\n            env=child_env))",
          "env=child_env))"),
         ("timeout=CHILD_TIMEOUT_S, env=_child_env(no_cargo)))",
          "env=_child_env(no_cargo)))")),
        ("a mutant that never ran is not a bite",
         ("with NO failing case", "    if out.returncode != 0 and not bit:"),
         ("if red and not named_failed", "            if red and not named_failed:")),
        ("a null mutation refused",
         ("the copy is identical to the original", "if _read(copy) == text:"),
         ("            if mutated == src:", "if mutated == src:")),
    )
    # **`all`, per half, not `any` across both.** The row check was `any(tok in
    # rows for tok in (gate_tok, rust_tok))`, so one row covered both halves and
    # three of the four properties passed on one half only.
    rows = "\n".join(r[1] + r[2] for r in MUTATIONS.get("gate-bite-harness", []))
    rows += "\n".join(r[2] + r[3] for r in RUST_MUTATIONS)
    for prop, gate_side, rust_side in parity:
        for name, (witness, token) in (("the gate half", gate_side),
                                       ("the Rust half", rust_side)):
            if witness not in own:
                failures += 1
                print(f"  FAIL {prop}: absent from {name}")
            elif token not in rows:
                failures += 1
                print(f"  FAIL {prop}: {name} has no mutation row aimed at it")
    if not failures:
        print(f"  ok  both halves carry all {len(parity)} guards, each with its own "
              "mutation row")

    if failures:
        print(f"\ngate-bite-harness --self-test: {failures} rule(s) did not behave")
        return 1
    print("\ngate-bite-harness --self-test: every rule bites, and none cries wolf")
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate", help="one gate name (default: all with a table)")
    ap.add_argument("--only", help="substring filter on the mutation label")
    ap.add_argument("--no-cargo", action="store_true", dest="no_cargo",
                    help="strip cargo from the child's PATH (see `_child_env`)")
    ap.add_argument("--rust", action="store_true",
                    help="the crates/actor-hub mutations instead of the gate ones")
    ap.add_argument("--self-test", action="store_true", dest="self_test")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test_guarded(self_test, "gate-bite-harness --self-test")

    gates = [args.gate] if args.gate else sorted(MUTATIONS)
    unknown = [g for g in gates if g not in MUTATIONS]
    if unknown:
        print(f"gate-bite-harness: no mutation table for {unknown}", file=sys.stderr)
        return 2
    # **The empty-filter guard runs FIRST.** Running the gates and then noticing
    # that nothing was selected spends a baseline child per gate to answer a
    # question that needed no work at all -- and reports the wrong exit code.
    rows_for = (lambda: RUST_MUTATIONS) if args.rust else (
        lambda: [r for g in gates for r in MUTATIONS[g]])
    total = len([r for r in rows_for()
                 if args.only is None or args.only.lower() in r[0].lower()])
    if not total:
        print(f"gate-bite-harness: no mutation matched {args.only!r} — a filter that "
              "selects nothing must not report success", file=sys.stderr)
        return 2

    if args.rust:
        survivors, refusal = run_rust(only=args.only)
        if refusal:
            print(f"gate-bite-harness: {refusal}", file=sys.stderr)
            return 2
        if survivors:
            print(f"\ngate-bite-harness: {survivors} Rust mutation(s) SURVIVED",
                  file=sys.stderr)
            return 1
        print("\ngate-bite-harness: every Rust mutation reddened its test")
        return 0

    results = [run_gate(g, only=args.only, no_cargo=args.no_cargo) for g in gates]
    if any(v < 0 for v in results):
        print("\ngate-bite-harness: a gate's UNMUTATED self-test is already red, so "
              "this run proves NOTHING about whether its rules bite. Fix the suite "
              "first.", file=sys.stderr)
        return 1
    survivors = sum(results)
    if survivors:
        print(f"\ngate-bite-harness: {survivors}/{total} mutations SURVIVED — those "
              "rules have no case and can be deleted with the suite green",
              file=sys.stderr)
        return 1
    print(f"\ngate-bite-harness: all {total} mutations reddened their self-test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
