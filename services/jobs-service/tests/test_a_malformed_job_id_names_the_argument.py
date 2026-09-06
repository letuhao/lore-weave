"""A rejection the caller cannot act on is the defect, one layer below the kit.

    jobs_cancel(job_id="")  ->  invalid input for query argument $2: '' (invalid UUID '':
                                length must be between 32..36 characters, got 0)

`$2` is a position in a query the caller never saw. It names no argument the model passed and no
rule it broke. Compare composition_derivative_edit on the same input — "project_id must be a
UUID — received ''" — the field named, the rule stated, the value echoed.

🔴 THE ROW NAMED TWO TOOLS; IT IS THREE. Measured 2026-08-26 against the deployed build, for an
empty string AND for 'not-a-uuid': jobs_cancel, jobs_pause AND jobs_get all reached asyncpg. Same
store call, same driver error — one cause under three names.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from app.mcp import server

SRC = pathlib.Path(inspect.getfile(server)).read_text(encoding="utf-8")


class TestTheValidatorSaysWhatIsWrong:
    @pytest.mark.parametrize("bad", ["", "not-a-uuid", "01a03000-0000", None, 12345])
    def test_it_names_the_field_and_echoes_the_value(self, bad):
        with pytest.raises(ValueError) as ei:
            server._job_uuid(bad)
        msg = str(ei.value)
        assert "job_id must be a UUID" in msg, msg
        assert repr(bad) in msg, "the caller cannot see a duplicated segment unless it is echoed"

    def test_it_points_at_where_the_id_COMES_FROM(self):
        """Naming the rule is half of it; a caller that does not hold a valid id needs the
        supplier, not just the complaint."""
        with pytest.raises(ValueError) as ei:
            server._job_uuid("")
        assert "jobs_list" in str(ei.value)

    def test_a_valid_id_passes_through_unchanged(self):
        good = "01a03000-0000-7000-8000-000000000000"
        assert server._job_uuid(good) == good


class TestEveryToolTakingAJobIdValidatesIt:
    """The class, enforced. A new job tool that forwards a raw id fails here rather than being
    found by a caller reading a query position."""

    def _tools_taking_job_id(self):
        tree = ast.parse(SRC)
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            args = [a.arg for a in node.args.args] + [a.arg for a in node.args.kwonlyargs]
            if "job_id" not in args:
                continue
            body = ast.get_source_segment(SRC, node) or ""
            yield node.name, body

    def test_none_of_them_forwards_an_unvalidated_id(self):
        unguarded = [
            name for name, body in self._tools_taking_job_id()
            if "store.get_job(" in body and "_job_uuid(" not in body
        ]
        assert not unguarded, (
            "these reach the store with a raw job_id, so the driver answers instead of the tool: "
            + ", ".join(unguarded)
        )

    def test_the_three_measured_tools_are_covered(self):
        """cancel and pause share `_control`; jobs_get is its own path and was NOT in the row."""
        assert "_job_uuid(job_id)" in inspect.getsource(server._control)
        names = {n for n, _ in self._tools_taking_job_id()}
        assert {"jobs_get", "jobs_cancel", "jobs_pause"} <= names | {"_control"}


def test_the_validation_happens_BEFORE_the_store_call():
    """Order is the whole fix. Validating after the query would still let the driver answer."""
    body = inspect.getsource(server._control)
    assert body.index("_job_uuid(job_id)") < body.index("store.get_job(")
