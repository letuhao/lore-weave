"""A seed assertion is SQL written against a schema I did not read. Check it before spending 25 turns.

FOUND 2026-08-21, batch 32: the assertion said `WHERE id=` and knowledge_projects' primary key is
`project_id`. All 25 runs failed in PROVISIONING, the report read "0/5 called, 5 err" for five
tools, and nothing about any tool was measured. The batch looked like a five-tool catastrophe and
was one typo.

It is the third instance of the same class in one session, which is why it is worth a chokepoint
rather than more care:

  batch 29  a `book_parts` table that does not exist (parts are structure_node rows in a
            DIFFERENT database) — caught before running, by luck, while reading the schema
  batch 31  `label='Ironhold'` asserted ACCOUNT-WIDE, matching rows from earlier arms; 4 of 5
            runs lost
  batch 32  `WHERE id=` against a table whose key is `project_id`; 25 of 25 runs lost

THE CHECK IS DELIBERATELY SHALLOW. It substitutes a syntactically valid UUID for every
placeholder and executes each query once. So it catches a bad COLUMN, a bad TABLE, or bad SYNTAX
— the failures that make a scenario unable to measure anything — and it cannot catch a wrong
EXPECTATION, because the dummy id makes the result meaningless. That is the right split: the real
assertion still runs per-run against the real fixture, where a wrong expectation is supposed to
fail loudly. A preflight that tried to validate expectations would either need the fixture (which
does not exist yet) or would start lying about what it proved.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))
sys.path.insert(0, str(ROOT / "scripts"))
import live_stack  # noqa: E402

SCENARIOS = sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json"))


def _preflight():
    try:
        import fe_runner  # noqa: PLC0415
        return fe_runner.preflight_seed_asserts
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"fe_runner unavailable: {exc}")


# 🔴 "no database reachable" WAS CHECKED BY `if not bad`, AND AN UNREACHABLE DATABASE
# IS NOT SILENT. With no container the preflight returns a CONNECTIVITY problem rather than
# nothing:
#
#     synthetic: [loreweave_knowledge] db_query failed (loreweave_knowledge):
#     error response from daemon: no such container: infra-postgres-1
#
# That is non-empty, so the skip never fired, and the assertions then failed for looking for
# "column" in a message about docker. Guard on the probe instead of on the shape of an error
# string -- matching a wrapped error by substring is how this class of guard rots. The
# `if not bad` skips stay: they are the right answer for a database that IS reachable and
# reports nothing.
#
# Scoped to the two LIVE classes. `TestTheRunnerItselfStillRuns` below is static and must keep
# running where there is no stack, or this file goes green by absence.
@pytest.mark.skipif(not live_stack.up(), reason=live_stack.REASON)
class TestItCatchesTheFailuresThatCostBatches:
    def test_the_batch_32_typo(self):
        """`id` against a table keyed on `project_id` — 25 runs."""
        pf = _preflight()
        bad = pf([{"id": "synthetic", "seed_assert": [{
            "db": "loreweave_knowledge",
            "query": "SELECT count(*)::text FROM knowledge_projects WHERE id='{project_id}'"}]}])
        if not bad:
            pytest.skip("no database reachable — the preflight is a live check by design")
        assert "column" in bad[0].lower() or "does not exist" in bad[0].lower()

    def test_a_table_that_does_not_exist(self):
        """batch 29's `book_parts` — parts are structure_node rows in another database."""
        pf = _preflight()
        bad = pf([{"id": "synthetic", "seed_assert": [{
            "db": "loreweave_book",
            "query": "SELECT count(*)::text FROM book_parts WHERE book_id='{book_id}'"}]}])
        if not bad:
            pytest.skip("no database reachable")
        assert "book_parts" in bad[0] or "does not exist" in bad[0].lower()

    def test_a_valid_query_is_silent(self):
        pf = _preflight()
        ok = pf([{"id": "synthetic", "seed_assert": [{
            "db": "loreweave_book",
            "query": "SELECT count(*)::text FROM worlds WHERE id='{book_id}'"}]}])
        if ok and "reach" in ok[0].lower():
            pytest.skip("no database reachable")
        assert ok == []

    def test_it_reports_the_scenario_id(self):
        """A list of SQL errors with no scenario names is a puzzle, not a message."""
        pf = _preflight()
        bad = pf([{"id": "my-scenario-name", "seed_assert": [{
            "db": "loreweave_book",
            "query": "SELECT nope FROM nope_nope"}]}])
        if not bad:
            pytest.skip("no database reachable")
        assert bad[0].startswith("my-scenario-name:")


@pytest.mark.skipif(not live_stack.up(), reason=live_stack.REASON)
class TestEveryCommittedScenarioPasses:
    def test_no_scenario_file_has_a_broken_seed_assertion(self):
        """The whole corpus, so a past batch's assertion cannot rot unnoticed either."""
        pf = _preflight()
        problems = []
        for f in SCENARIOS:
            try:
                scns = json.loads(f.read_text(encoding="utf-8")).get("scenarios") or []
            except ValueError:
                continue
            for p in pf(scns):
                problems.append(f"{f.name} :: {p}")
        if problems and any("could not" in p.lower() or "connect" in p.lower() for p in problems):
            pytest.skip("no database reachable")
        assert not problems, "\n".join(problems[:20])


class TestTheRunnerItselfStillRuns:
    """🔴 GUARD THE CALL SITE, NOT THE HELPER.

    Adding the preflight spliced its body into the MIDDLE of `main()`, so everything after
    `return problems` became dead code inside the helper and `main()` returned None
    immediately. Syntactically valid, imports fine, and the helper's own tests all passed —
    because they called `preflight_seed_asserts` directly. Meanwhile every fe_runner
    invocation exited 0, printed nothing, wrote no evidence, and looked like a quiet success.
    Two arms were lost to it before the silence was noticed.

    So this exercises the CLI end to end rather than the function.
    """

    def test_the_cli_refuses_a_broken_assertion_end_to_end(self, tmp_path):
        import subprocess  # noqa: PLC0415

        scn = tmp_path / "scn.json"
        scn.write_text(json.dumps({"scenarios": [{
            "id": "synthetic-bad", "tool_under_test": "x", "expect_tool": "x",
            "prompt": "p", "seed": [], "seed_assert": [{
                "db": "loreweave_knowledge",
                "query": "SELECT count(*)::text FROM knowledge_projects WHERE id='{project_id}'"}],
            "falsifier": "n/a", "ship_audit": {}}]}), encoding="utf-8")

        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "toolloop" / "fe_runner.py"), str(scn),
             "--repeats", "1"],
            capture_output=True, text=True, timeout=300, cwd=str(ROOT))

        if "could not" in (r.stderr or "").lower() or "connect" in (r.stderr or "").lower():
            pytest.skip("no database reachable")
        assert r.returncode == 2, (
            f"the CLI exited {r.returncode} on a broken seed assertion. Exit 0 with no output is "
            f"how a dead main() looks.\nstdout={r.stdout[:400]}\nstderr={r.stderr[:400]}")
        assert "REFUSING to run" in r.stderr

    def test_main_is_not_a_no_op(self):
        """The shape of the bug: main() must still contain the code that runs the batch."""
        src = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
        body = src[src.index("\ndef main("):]
        for needed in ("ApprovalState", "main_async", "emit_batch"):
            assert needed in body, (
                f"main() no longer references {needed} — its body was swallowed by an edit and "
                f"every run would exit 0 having done nothing")
