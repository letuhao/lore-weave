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
         '    (RUN_STATE, "### 6-BUILD", "| # | Slice |"),', ""),
        ("the _index.md scope row deleted",
         '    (INDEX, "# Actor Hub", "\\n## Read this to REUSE"),', ""),
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
         "        block = _claimable(block, in_fence=opens_fenced)", "        block = block"),
        # The prefix state must be PASSED, not merely computed. The first fix
        # defined `_fence_state`, added the parameter, and never wired it -- and
        # its case passed anyway, because the correct code and the unwired
        # version report the SAME NUMBER of findings about DIFFERENT lines.
        ("the prefix fence state computed and not passed",
         "        block = _claimable(block, in_fence=opens_fenced)",
         "        block = _claimable(block)"),
        ("the fence state is GUESSED instead of taken from the prefix",
         "    out, in_comment, open_mark = [], False, in_fence",
         "    out, in_comment, open_mark = [], False, None"),
        # REMOVED: `is_mark or ...` vs `...` is an EQUIVALENT mutant once a
        # closer is required to carry no info string. The two differ only on the
        # CLOSING line -- an opener leaves `open_mark` set, so it is blanked
        # either way -- and a valid closer is a bare run of backticks with
        # nothing on it to be live. Deleting the row rather than contriving a
        # case, for the same reason the test-result regex row went.
        ("the prefix fence scan returns nothing",
         "        open_mark, _ = _advance(open_mark, line)\n    return open_mark",
         "        open_mark, _ = _advance(open_mark, line)\n    return None"),
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
         '    if m.group("mark")[0] in m.group("info"):\n        return None',
         "    if False:\n        return None"),
        # ...and the ORDER of the two states. Testing the fence first left both
        # flags stuck true on a fence marker inside a comment.
        ("the comment state is tested AFTER the fence again",
         "        if in_comment:\n            out.append(\" \" * len(line))\n"
         "            if \"-->\" in line:\n                in_comment = False\n"
         "            continue\n        open_mark, is_mark = _advance(open_mark, line)",
         "        open_mark, is_mark = _advance(open_mark, line)"),
        # M2 -- a missing END marker silently widened the window to the whole
        # file: mass cry-wolf for the figures, total blindness for the escape
        # rule, and nothing reported.
        ("a missing end marker widens the scope to the whole file",
         "    return None if j < 0 else (i, j)",
         "    return (i, j if j > 0 else len(text))"),
        ("the empty-block rule removed",
         "        if doc in checked and not checked[doc]:", "        if False:"),
        # M1 -- the escape rule read only the three files with a current-state
        # block. Eight more carried the range and stayed green, two of them files
        # this same gate already opens.
        ("the escape rule reads only the SCOPES documents",
         "    docs = sorted({d for d, _, _ in scopes} | "
         "(set(ESCAPE_DOCS) if scopes is SCOPES else set()))",
         "    docs = sorted({d for d, _, _ in scopes})"),
        ("the multi-line comment state dropped",
         '        if "<!--" in line:\n            in_comment = True',
         '        if False:\n            in_comment = True'),
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
         'rf"`{prefix}-{first}`\\s*\\n?>?\\s*\\.\\.\\s*\\n?>?\\s*`{prefix}-(\\d+)`"',
         'rf"`{prefix}-{first}`\\.\\.`{prefix}-(\\d+)`"'),
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


def run_rust(only: str | None = None, run=None) -> tuple[int, str | None]:
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
            _write(path, src.replace(find, repl, 1), like=raws[rel])
            runner = run or (lambda t: subprocess.run(
                ["cargo", "test", "-p", "actor-hub", "--test", "fold_survivors",
                 t, "--", "--exact"], cwd=REPO, capture_output=True, text=True,
                timeout=CHILD_TIMEOUT_S))
            try:
                out = runner(test)
            finally:
                # The ORIGINAL BYTES, not a re-encoding of the text: exact even
                # for a file with mixed line endings, which no normalisation
                # round trip can promise.
                path.write_bytes(raws[rel])
            red = out.returncode != 0
            print(f"  {'RED ' if red else 'GREEN'}  {label:52} -> {test}")
            green += 0 if red else 1
    finally:
        for rel in originals:
            (REPO / rel).write_bytes(raws[rel])
    return green, None


def _mutate_and_run(gate: str, find: str, repl: str, run=None,
                    no_cargo: bool = False) -> tuple[bool, str]:
    """(went_red, note). The ORIGINAL is opened read-only; a copy is mutated."""
    src = SCRIPTS / f"{gate}.py"
    raw = _raw(src)
    text = _read(src)
    if text.count(find) != 1:
        return False, f"anchor occurs {text.count(find)}x — the table has drifted"
    # Beside the original so `REPO = Path(__file__).parent.parent` still resolves.
    copy = SCRIPTS / f".bite-{gate}.py"
    try:
        _write(copy, text.replace(find, repl, 1), like=raw)
        # **The mutation must actually be a mutation.** Nothing checked that the
        # copy differed from the original, so a harness that had silently stopped
        # mutating would report every rule RED-free and look like success.
        if _read(copy) == text:
            return False, "the copy is identical to the original — nothing was mutated"
        runner = run or (lambda p: subprocess.run(
            [sys.executable, str(p), "--self-test"], cwd=REPO,
            capture_output=True, text=True, timeout=CHILD_TIMEOUT_S,
            env=_child_env(no_cargo)))
        out = runner(copy)
    finally:
        copy.unlink(missing_ok=True)
    if out.returncode != 0:
        return True, ""
    return False, "self-test stayed GREEN"


def run_gate(gate: str, run=None, only: str | None = None, no_cargo: bool = False) -> int:
    rows = [r for r in MUTATIONS[gate] if only is None or only.lower() in r[0].lower()]
    print(f"\n{gate}" + (f"  ({len(rows)}/{len(MUTATIONS[gate])} matching {only!r})" if only else ""))
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
        text = (SCRIPTS / f"{gate}.py").read_text(encoding="utf-8")
        for label, find, _ in rows:
            if text.count(find) != 1:
                failures += 1
                print(f"  FAIL {gate}: anchor for '{label}' occurs {text.count(find)}x")
    # ...and the Rust table, which mutates in place and so must not drift silently.
    for label, rel, find, _, _ in RUST_MUTATIONS:
        text = _read(REPO / rel)
        if text.count(find) != 1:
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
    leftover = list(SCRIPTS.glob(".bite-*.py"))
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
    same, note = _mutate_and_run(gate, find, find)
    if same or "nothing was mutated" not in note:
        failures += 1
        print(f"  FAIL a no-op replacement must be reported, not run: {note!r}")
    else:
        print("  ok  a replacement that changes nothing is reported, not run")

    if quietly(lambda: run_gate(gate, run=lambda _: _R(0), only="the pragma")) == 0:
        failures += 1
        print("  FAIL run_gate did not count a surviving mutation")
    else:
        print("  ok  run_gate counts survivors")
    if quietly(lambda: run_gate(gate, run=lambda _: _R(1), only="the pragma")) != 0:
        failures += 1
        print("  FAIL run_gate counted a reddened mutation as a survivor")
    else:
        print("  ok  run_gate does not count a reddened mutation")
    if quietly(lambda: run_gate(gate, run=lambda _: _R(1), only="@@ MATCHES NOTHING @@")) != 0:
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

    survivors, refusal = quietly(lambda: run_rust(run=_rust_run(1)))
    if survivors or refusal or not rust_calls:
        failures += 1
        print(f"  FAIL a reddened Rust mutation must not count: {survivors}, {refusal}")
    else:
        print(f"  ok  a reddened Rust mutation is not a survivor ({len(rust_calls)} run)")

    rust_calls.clear()
    survivors, refusal = quietly(lambda: run_rust(run=_rust_run(0)))
    if survivors != len(RUST_MUTATIONS) or refusal:
        failures += 1
        print(f"  FAIL a GREEN Rust mutation must be a survivor: got {survivors} of "
              f"{len(RUST_MUTATIONS)}")
    else:
        print("  ok  a surviving Rust mutation is counted")

    # The restore is not optional: `--rust` mutates the real crate in place.
    before = {rel: _raw(REPO / rel) for _, rel, _, _, _ in RUST_MUTATIONS}
    quietly(lambda: run_rust(run=_rust_run(1)))
    after = {rel: _raw(REPO / rel) for rel in before}
    if after != before:
        failures += 1
        changed = [r for r in before if before[r] != after[r]]
        print(f"  FAIL --rust left the tree modified: {changed}")
    else:
        print(f"  ok  --rust restores all {len(before)} crate file(s) byte for byte")

    # **A refusal is not a survivor count.** The first version returned `2` as a
    # sentinel and `main` printed "2 Rust mutation(s) SURVIVED" for a run in
    # which nothing executed.
    survivors, refusal = run_rust(run=None, only="@@ NOTHING @@") if False else (0, None)
    fake_dirty = ["crates/actor-hub/src/fold.rs"]
    _real_dirty = globals()["_rust_dirty"]
    globals()["_rust_dirty"] = lambda: fake_dirty
    try:
        survivors, refusal = quietly(lambda: run_rust())
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

    # `--no-cargo` must reach the child. Nothing checked that the flag was
    # forwarded, so the whole control could be inert.
    seen_env: list[dict | None] = []
    _mutate_and_run("citation-gate", find, repl,
                    run=lambda p: seen_env.append(None) or _R(1), no_cargo=False)
    envs: list[dict | None] = []

    def _capture(p):
        envs.append(_child_env(True))
        return _R(1)

    _mutate_and_run("citation-gate", find, repl, run=_capture, no_cargo=True)
    stripped = envs[0]
    if stripped is None or shutil.which("cargo", path=stripped.get("PATH", "")) is not None:
        failures += 1
        print("  FAIL --no-cargo left cargo reachable on the child's PATH")
    else:
        print("  ok  --no-cargo removes every PATH entry carrying cargo")
    if _child_env(False) is not None:
        failures += 1
        print("  FAIL without --no-cargo the child must inherit the environment")
    else:
        print("  ok  without --no-cargo the environment is inherited unchanged")

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

    gates = [args.gate] if args.gate else sorted(MUTATIONS)
    unknown = [g for g in gates if g not in MUTATIONS]
    if unknown:
        print(f"gate-bite-harness: no mutation table for {unknown}", file=sys.stderr)
        return 2
    survivors = sum(run_gate(g, only=args.only, no_cargo=args.no_cargo) for g in gates)
    total = sum(len([r for r in MUTATIONS[g]
                     if args.only is None or args.only.lower() in r[0].lower()])
                for g in gates)
    if not total:
        print(f"gate-bite-harness: no mutation matched {args.only!r} — a filter that "
              "selects nothing must not report success", file=sys.stderr)
        return 2
    if survivors:
        print(f"\ngate-bite-harness: {survivors}/{total} mutations SURVIVED — those "
              "rules have no case and can be deleted with the suite green",
              file=sys.stderr)
        return 1
    print(f"\ngate-bite-harness: all {total} mutations reddened their self-test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
