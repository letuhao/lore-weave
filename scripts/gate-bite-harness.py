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
        ("the 6-BUILD scope row deleted",
         '    (RUN_STATE, "### 6-BUILD", END("slice-board"), frozenset({"rust_tests"})),',
         ""),
        ("the _index.md scope row deleted",
         '    (INDEX, "# Actor Hub", "\\n## Read this to REUSE",', "        ("),
        ("the red-build guard removed",
         '    if "test result: FAILED" in out.stdout or out.returncode != 0:',
         "    if False:"),
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
         "        hits = [k for k in _all_occurrences(haystack, needle, start)\n"
         "                if _at_line_start(haystack, k, needle)]",
         "        hits = [k for k in _all_occurrences(haystack, needle, start)]"),
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
         "    for haystack in (_claimable(text, quotes=False, comments=False), text):",
         "    for haystack in (text,):"),
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
        ("discovery stops excluding this driver and scratch copies",
         '        if p.name == SELF or p.name.startswith("."):\n            continue',
         "        if False:\n            continue"),
        ("the discovery predicate matches everything",
         '            if FLAG in _code_only(p.read_text(encoding="utf-8", errors="replace")):',
         "            if True:"),
        # M8 -- the predicate counted a MENTION of the flag as having one. A gate
        # in this tree names it in two comments, has no self-test, was invoked,
        # ignored the flag, exited 0, and was counted green.
        ("the predicate counts prose as code again",
         "            if FLAG in _code_only(p.read_text(encoding=\"utf-8\", errors=\"replace\")):",
         "            if FLAG in p.read_text(encoding=\"utf-8\", errors=\"replace\"):"),
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
        ("the leftover check stops excluding this file's copy",
         "    leftover = [q for q in SCRIPTS.glob(\".bite-*.py\") "
         "if q.name != Path(__file__).name]",
         "    leftover = list(SCRIPTS.glob(\".bite-*.py\"))"),
        # M4 -- `--self-test` drives `run_rust` three times and the pre-commit
        # hook runs `--self-test`, so an uninjectable writer meant 30 in-place
        # writes to the shipped crate sources on every commit.
        ("the rust writer stops being injectable",
         "            (write or _write)(path, src.replace(find, repl, 1), like=raws[rel])",
         "            _write(path, src.replace(find, repl, 1), like=raws[rel])"),
        # B2 -- `--rust --only <nothing>` executed zero mutations and printed
        # "every Rust mutation reddened its test" with exit 0: the sole signal
        # of the CI job that mode exists for, reporting success having done
        # nothing. One guard now, mode-aware, ahead of any work.
        ("the empty-filter guard stops seeing the rust table",
         "    rows_for = (lambda: RUST_MUTATIONS) if args.rust else (",
         "    rows_for = (lambda: []) if args.rust else ("),
        ("the child environment is not forwarded",
         "            env=_child_env(no_cargo)))", "            env=None))"),
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
     "a_derivation_on_an_undeclared_fold_layer_is_refused"),
    ("the zero-divisor refusal removed",
     "crates/actor-hub/src/registry.rs",
     "        if row.divisor == 0 {\n            return Err(RowRefusal::ZeroDivisor);\n        }",
     "        if false {\n            return Err(RowRefusal::ZeroDivisor);\n        }",
     "a_zero_divisor_and_a_contradictory_bound_are_refused"),
    ("Accumulator.wanted reports the EMITTED value",
     "crates/actor-hub/src/fold.rs",
     "        capped.push(Capped { quantity: q, site: CapSite::Emit, wanted: r.value, emitted: out });",
     "        capped.push(Capped { quantity: q, site: CapSite::Emit, wanted: out as i64, emitted: out });",
     "the_accumulator_record_carries_the_exact_wanted_total"),
    ("pre_emit collapses onto value",
     "crates/actor-hub/src/fold.rs",
     "            pre_emit,\n            value,",
     "            pre_emit: value as i64,\n            value,",
     "pre_emit_differs_from_value_when_the_emit_clamps"),
    ("a bound that raises reports nothing",
     "crates/actor-hub/src/rows.rs",
     "        let site = if bounded != clamped {",
     "        let site = if bounded < clamped {",
     "a_bound_whose_floor_bites_is_reported"),
    ("division floors instead of truncating",
     "crates/actor-hub/src/rows.rs",
     "            (source_value as i64).saturating_mul(self.factor_milli as i64) / (self.divisor as i64)",
     "            (source_value as i64).saturating_mul(self.factor_milli as i64).div_euclid(self.divisor as i64)",
     "a_negative_derivation_truncates_toward_zero"),
    # M10 -- `order_key`'s middle component is the submitting plugin. Layer and
    # index each had a case; the plugin did not, so a constant survived the whole
    # 293-test suite. One plugin cannot show a key that sorts by plugin.
    ("order_key stops sorting by submitting plugin",
     "crates/actor-hub/src/fold.rs",
     "    (c.fold_layer.get(), c.source.get(), idx)",
     "    (c.fold_layer.get(), 0, idx)",
     "contributions_at_one_layer_are_ordered_by_submitting_plugin"),
    ("an exact bound min==max wrongly refused",
     "crates/actor-hub/src/registry.rs",
     "            && b.min > b.max",
     "            && b.min >= b.max",
     "an_exact_bound_is_legal_and_pins_the_contribution"),
    ("the table-length boundary weakened to >",
     "crates/actor-hub/src/registry.rs",
     "                if q.ordinal.index() >= table.len() {",
     "                if q.ordinal.index() > table.len() {",
     "an_ordinal_exactly_at_the_table_length_is_refused"),
]



def _rust_dirty() -> list[str]:
    """Files this harness would mutate that already carry uncommitted changes."""
    files = sorted({rel for _, rel, _, _, _ in RUST_MUTATIONS})
    out = subprocess.run(["git", "status", "--porcelain", "--", *files],
                         cwd=REPO, capture_output=True, text=True)
    return [l[3:].strip() for l in out.stdout.splitlines() if l.strip()]


def run_rust(only: str | None = None, run=None, write=None) -> tuple[int, str | None]:
    """(survivors, refusal). **Two separate answers, because they were one.**

    The first version returned `2` as a refusal sentinel and `main` read the
    return value as a survivor count, so a refused run -- nothing executed, no
    mutations applied -- printed *"2 Rust mutation(s) SURVIVED"*. A count that
    doubles as an error code reports a defect that does not exist, which is the
    same class as a check reporting coverage it does not have.
    """
    rows = [r for r in RUST_MUTATIONS if only is None or only.lower() in r[0].lower()]
    dirty = _rust_dirty()
    if dirty and run is None:
        return 0, ("refusing to mutate files that are already modified: "
                   f"{dirty}. Commit or stash them first.")
    print(f"\ncrates/actor-hub  ({len(rows)} Rust mutation(s))")
    # The Rust half needs the same guard: a crate whose suite is already red
    # reddens every mutation for free.
    if run is None:
        if shutil.which("cargo") is None:
            # **No toolchain is a SKIP, not a crash.** The baseline probe added
            # with this guard called cargo unconditionally and raised
            # `FileNotFoundError` on every machine without Rust -- including the
            # one CI runs the gate half on, which is exactly the population the
            # degrade-safety rule exists for. A guard that cannot run without
            # the thing it guards is not degrade-safe.
            return 0, "cargo is not on PATH, so the Rust mutations were not run"
        try:
            probe = subprocess.run(
                ["cargo", "test", "-p", "actor-hub", "--test", "fold_survivors"],
                cwd=REPO, capture_output=True, text=True, timeout=CHILD_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired) as e:
            return 0, f"the unmutated fold_survivors suite could not be run: {e}"
        if probe.returncode != 0:
            return len(rows) or 1, ("the UNMUTATED fold_survivors suite already fails "
                                    "— every mutation below would be red for that reason")
    originals: dict[str, str] = {}
    raws: dict[str, bytes] = {}
    green = 0
    try:
        for label, rel, find, repl, test in rows:
            path = REPO / rel
            raws.setdefault(rel, _raw(path))
            src = originals.setdefault(rel, _read(path))
            if src.count(find) != 1:
                print(f"  DRIFT  {label:52} anchor occurs {src.count(find)}x")
                green += 1
                continue
            # `write` is injectable because `--self-test` drives this function
            # three times, and the pre-commit hook runs `--self-test`: the first
            # version therefore performed **30 in-place writes to the shipped
            # crate sources on every commit across 47 services**. The incident
            # the Python half mutates a copy to avoid -- a killed run leaving a
            # mutation on disk -- was on the automatic path.
            (write or _write)(path, src.replace(find, repl, 1), like=raws[rel])
            runner = run or (lambda t: subprocess.run(
                ["cargo", "test", "-p", "actor-hub", "--test", "fold_survivors",
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
            red = out.returncode != 0
            print(f"  {'RED ' if red else 'GREEN'}  {label:52} -> {test}")
            green += 0 if red else 1
    finally:
        for rel in originals:
            if _raw(REPO / rel) != raws[rel]:
                (REPO / rel).write_bytes(raws[rel])
    return green, None


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
    for node in tree.body:
        names = []
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        if not any(n.endswith("MUTATIONS") for n in names):
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
                    no_cargo: bool = False) -> tuple[bool, str]:
    """(went_red, note). The ORIGINAL is opened read-only; a copy is mutated."""
    src = SCRIPTS / f"{gate}.py"
    raw = _raw(src)
    text = _read(src)
    at = _find_one(text, find)
    if at < 0:
        return False, (f"anchor occurs {text.count(find)}x outside the tables "
                       "— the table has drifted")
    # Beside the original so `REPO = Path(__file__).parent.parent` still resolves.
    copy = SCRIPTS / f".bite-{gate}.py"
    try:
        _write(copy, text[:at] + repl + text[at + len(find):], like=raw)
        # **The mutation must actually be a mutation.** Nothing checked that the
        # copy differed from the original, so a harness that had silently stopped
        # mutating would report every rule RED-free and look like success.
        if _read(copy) == text:
            return False, "the copy is identical to the original — nothing was mutated"
        runner = run or (lambda p: subprocess.run(
            [sys.executable, str(p), "--self-test"], cwd=REPO,
            capture_output=True, text=True, timeout=CHILD_TIMEOUT_S,
            env=_child_env(no_cargo)))
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
        red, note = _mutate_and_run(gate, find, repl, run=run, no_cargo=no_cargo)
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
            if _find_one(text, find) < 0:
                failures += 1
                print(f"  FAIL {gate}: anchor for '{label}' occurs "
                      f"{text.count(find)}x outside the tables")
    # ...and the Rust table, which mutates in place and so must not drift silently.
    for label, rel, find, _, _ in RUST_MUTATIONS:
        text = _read(REPO / rel)
        if _find_one(text, find) < 0:
            failures += 1
            print(f"  FAIL {rel}: anchor for '{label}' occurs {text.count(find)}x")
    if not failures:
        total = sum(len(v) for v in MUTATIONS.values())
        print(f"  ok  all {total} mutation anchors resolve exactly once")

    # A mutation that leaves the self-test GREEN must be reported as GREEN, and
    # one that reddens it as RED. Driven through the real `_mutate_and_run`.
    class _R:
        def __init__(self, rc):
            self.returncode, self.stdout, self.stderr = rc, "", ""

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

    red, note = _mutate_and_run(gate, find, repl, run=_times_out)
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
    rust_calls: list[str] = []

    class _RustR:
        def __init__(self, rc):
            self.returncode, self.stdout, self.stderr = rc, "", ""

    def _rust_run(rc):
        def go(test):
            rust_calls.append(test)
            return _RustR(rc)
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

    # The restore is not optional: `--rust` mutates the real crate in place.
    # **The write/restore round trip, proved on a TEMP file.** The previous
    # version kept the real writer on one real crate file, so `--self-test` --
    # which the pre-commit hook runs on every staged `scripts/*.py` -- still
    # wrote `fold.rs` twice, bypassing the dirty-tree refusal because that call
    # site passes `run=`. Proving a round trip does not require touching the
    # shipped sources, and it covers a case the crate files cannot: **CRLF**,
    # whose re-application in `_write` has never had one.
    import tempfile
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
    if forwarded is not marker:
        failures += 1
        print(f"  FAIL --no-cargo's environment did not reach the child: {forwarded}")
    else:
        print("  ok  --no-cargo's environment reaches the child (sentinel observed)")
    if not_forwarded is not None:
        failures += 1
        print("  FAIL without --no-cargo the child must inherit the environment")
    else:
        print("  ok  without --no-cargo the environment is inherited unchanged")
    # ...and the helper itself removes every entry carrying cargo.
    stripped_env = real_child_env(True)
    if stripped_env is None or shutil.which("cargo", path=stripped_env.get("PATH", "")):
        failures += 1
        print("  FAIL _child_env left cargo reachable")
    else:
        print("  ok  _child_env removes every PATH entry carrying cargo")

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
    try:
        quietly(lambda: run_rust(only="a refused derivation", write=lambda *a, **k: None))
    finally:
        _sp.run = real_run
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

    if failures:
        print(f"\ngate-bite-harness --self-test: {failures} rule(s) did not behave")
        return 1
    print("\ngate-bite-harness --self-test: every rule bites, and none cries wolf")
    return 0


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
        return self_test()

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
