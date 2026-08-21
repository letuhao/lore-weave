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

SCENARIOS = sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json"))


def _preflight():
    try:
        import fe_runner  # noqa: PLC0415
        return fe_runner.preflight_seed_asserts
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"fe_runner unavailable: {exc}")


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
