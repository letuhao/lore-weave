"""D-ARCHIVE-FABRICATES-SUCCESS — archiving an id that does not exist reported success.

MEASURED 2026-08-14 against the live MCP surface with a UUID invented on the spot:

    composition_arc_template_edit(op="archive", arc_id="d0a602e9-…")
      -> {"id": "d0a602e9-…", "archived": true,
          "_meta": {"undo_hint": {"tool": "composition_arc_template_restore", …}}}
    SELECT count(*) FROM arc_template WHERE id='d0a602e9-…'  ->  0

The tool reported archiving a row that was never there and handed back an undo hint for it. A
model told "archived: true" tells the author their library changed. Nothing had changed.

🔴 IT WAS DELIBERATE, AND THE CONTROL IS WHY IT STILL HAD TO GO. The description called it "a
uniform no-op (returns archived:true — no existence oracle)", which is an honest intent. But the
anti-oracle is already defeated by this tool's OWN siblings — measured, same tool, same
nonexistent arc_id:

    op=archive  -> success
    op=restore  -> "not found or not accessible"
    op=update   -> "not found or not accessible"

Anyone probing whether an id exists calls op=update. The silence bought no protection and cost
the author the truth about their own library, so archive now matches the two ops beside it.

WHAT IS DELIBERATELY KEPT: idempotency. Archiving a row you own that is ALREADY archived is still
a success — the end state is the one you asked for. Only a row that is not yours refuses. That
distinction is the reason the repo returns three values instead of a bool.
"""
from __future__ import annotations

import pathlib
import re

SRC_REPO = (pathlib.Path(__file__).resolve().parents[1]
            / "app" / "db" / "repositories" / "arc_template_repo.py").read_text(encoding="utf-8")
SRC_MCP = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "mcp" / "server.py").read_text(encoding="utf-8")


class TestTheRepoReportsWhatItDid:
    """THE FALSIFIER for the repo half: it used to return None and discard the UPDATE tag."""

    def test_archive_is_not_typed_as_returning_none(self):
        m = re.search(r"async def archive\(\s*self,[^)]*\)\s*->\s*(\w+)", SRC_REPO, re.S)
        assert m, "ArcTemplateRepo.archive signature not found"
        assert m.group(1) == "str", (
            f"archive returns {m.group(1)} — a bare None cannot distinguish UPDATE 0 from UPDATE 1, "
            "which is the whole defect")

    def test_it_reads_the_update_tag(self):
        i = SRC_REPO.index("async def archive(")
        body = SRC_REPO[i:i + 4200]
        assert "tag = await c.execute(" in body, "the UPDATE's status string is discarded again"
        assert 'rsplit(" ", 1)[-1] != "0"' in body, "the row count is not being read"

    def test_all_three_outcomes_exist(self):
        i = SRC_REPO.index("async def archive(")
        body = SRC_REPO[i:i + 4200]
        for outcome in ('"archived"', '"already_archived"', '"not_found"'):
            assert outcome in body, f"archive can no longer report {outcome}"

    def test_the_zero_row_case_disambiguates_with_a_select(self):
        """already_archived and not_found are BOTH `UPDATE 0` — only a SELECT separates them, and
        conflating them would either break idempotency or restore the fabricated success."""
        i = SRC_REPO.index("async def archive(")
        body = SRC_REPO[i:i + 4200]
        assert "fetchval(" in body and "SELECT 1 FROM arc_template" in body


class TestTheHandlerRefusesAMissingRow:
    """CALL-SITE GUARD. The repo change is inert if the handler keeps returning archived:True
    unconditionally — which is exactly the shape the defect had."""

    def test_it_refuses_not_found(self):
        i = SRC_MCP.index("async def composition_arc_template_archive(")
        body = SRC_MCP[i:i + 2600]
        assert 'outcome == "not_found"' in body
        assert "raise uniform_not_accessible()" in body

    def test_it_keeps_idempotency_a_success(self):
        i = SRC_MCP.index("async def composition_arc_template_archive(")
        body = SRC_MCP[i:i + 2600]
        assert '"archived": True' in body, "an owned row must still report success"
        assert 'already_archived' in body, (
            "the caller cannot tell a fresh archive from a repeat, which is the fact that makes "
            "the success honest rather than merely true")

    def test_the_outcome_is_not_discarded(self):
        i = SRC_MCP.index("async def composition_arc_template_archive(")
        body = SRC_MCP[i:i + 2600]
        assert re.search(r"outcome\s*=\s*await ArcTemplateRepo\(get_pool\(\)\)\.archive\(", body), (
            "the repo's result is thrown away again — the original defect exactly")


class TestTheDescriptionNoLongerClaimsAnAntiOracleItDoesNotHave:
    def test_it_does_not_promise_no_existence_oracle(self):
        i = SRC_MCP.index('name="composition_arc_template_archive"')
        desc = SRC_MCP[i:i + 900]
        assert "no existence oracle" not in desc, (
            "the claim is false while op=update and op=restore both refuse on a missing id")

    def test_it_states_the_refusal(self):
        i = SRC_MCP.index('name="composition_arc_template_archive"')
        desc = SRC_MCP[i:i + 900]
        assert "not found or not accessible" in desc
