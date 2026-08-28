"""D-RESTORE-WITH-NO-WAY-TO-SEE-WHAT-IS-RESTORABLE — the structure-template family's live proof
left its own debris, and this is the guard that stops it recurring.

THE DEFECT. `composition_structure_template_edit`'s op=list dropped `include_archived` at the
call site even though the repo has always supported it (`list_for_user(user_id,
include_archived=...)`, already wired through the FE's own canon.py router). Same shape as
composition_list_canon_rules, already fixed on this row. Fixed by adding `include_archived` to
`_StructTemplateEditArgs` and passing it through — no new tool, no new op, one optional argument
on a tool that already ships.

🔴 THE FIRST LIVE BATCH MEASURED THE FIX AND ALSO MEASURED ITS OWN DEBRIS. Batch c-structrestore4,
K=5: the seeded archived template was ALWAYS present in the tool's response (verified from the
raw tool result, not the model's prose) — the invariant this row is about, proven. But
`composition_structure_template_edit`'s seed is USER-scoped (owner_user_id), not book-scoped, so
none of this harness's throwaway-book teardown ever reaches it. The batch surfaced 32 OTHER
archived templates dated back to 2026-07-30 — names like `E2E Struct 1784308909624`, `i223 my
copy`, `B21 Seed Smoke` — every prior loop that ever touched this tool family, still sitting
there. `sweep_archived_structure_templates` closes that the way
`sweep_phantom_job_projections` closed the equivalent translation-job leak hours earlier the
same day: SELECT before DML, harness account only, called unconditionally from the runner.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
PROVISION = (ROOT / "scripts" / "toolloop" / "provision.py").read_text(encoding="utf-8")


def _fn(name: str) -> ast.FunctionDef:
    tree = ast.parse(PROVISION)
    return next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == name)


def test_the_sweep_exists_and_touches_structure_template():
    assert "sweep_archived_structure_templates" in PROVISION
    fn = _fn("sweep_archived_structure_templates")
    body = ast.get_source_segment(PROVISION, fn) or ""
    assert "structure_template" in body, "the sweep does not touch the leaking table"


def test_the_sweep_is_SELECT_before_DML():
    fn = _fn("sweep_archived_structure_templates")
    stmts = fn.body[1:] if ast.get_docstring(fn) else fn.body
    code = "\n".join(ast.get_source_segment(PROVISION, st) or "" for st in stmts)
    assert code.upper().index("SELECT") < code.upper().index("DELETE"), "SELECT before DML"


def test_the_sweep_is_scoped_to_the_HARNESS_ACCOUNT_and_ARCHIVED_rows_only():
    """The conservative half. A live template might still be in use by an old fixture; an
    archived one, by definition, is not — and only the harness account is unambiguously this
    loop's own debris. Verified 2026-08-28: 33 rows removed on the harness account, the account's
    own 33 LIVE (non-archived) rows left untouched."""
    fn = _fn("sweep_archived_structure_templates")
    body = ast.get_source_segment(PROVISION, fn) or ""
    assert "OWNER_ID" in body, "the sweep is not scoped to the harness account"
    assert "is_archived" in body, "the sweep is not restricted to archived (already soft-deleted) rows"


def test_the_runner_calls_the_sweep_UNCONDITIONALLY_before_the_batch():
    """🔴 IT CANNOT BE LEFT TO THE SCENARIO'S OWN TEARDOWN. This seed has no book to tear down —
    that is the whole reason the debris exists — so the sweep has to run at the same point as
    the other pre-batch sweeps, unconditionally, or a crashed run leaves its debris for the next
    one to measure."""
    assert "await asyncio.to_thread(sweep_archived_structure_templates)" in RUNNER, (
        "the structure-template sweep is not called from the runner"
    )
    i = RUNNER.index("await asyncio.to_thread(sweep_archived_structure_templates)")
    j = RUNNER.index("async with httpx.AsyncClient(timeout=TURN_TIMEOUT) as client:")
    assert i < j, "the sweep runs after the batch, so a crash leaves the debris in place"
