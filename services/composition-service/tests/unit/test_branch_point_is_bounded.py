"""TOOLV2 LOOP #178 — a derivative was created at a negative chapter index.

`branch_point` is documented as a 0-based chapter index. Nothing validated it. Measured on
composition_create_derivative's first invocation:

    propose(branch_point=-5)  -> a signed confirm_token
    confirm(that token)       -> {"outcome": "action_accepted", ...} — the derivative EXISTS
    database                  -> branch_point = -5 persisted

Deriving mints a fresh knowledge partition, is expensive, and is only archivable rather than
undoable — the tool's own description says so. A structurally impossible index should never reach
that write, and here it survived both halves of a confirm-gated flow.

The population says this was latent rather than active: 35 works carry a branch_point and every
organic one is sane (0). The single negative row is the one this iteration created.

The bound is DECLARED on the model rather than checked in the handler, because #166 measured the
difference in this same service. A bound the schema knows about is rejected before the handler runs
and explained for free — "Input should be greater than or equal to 0 (you sent -5)" — while a bound
living in a comment is neither enforced nor explained. The sibling `unit_index` already declares
minimum 0; branch_point declared nothing.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.mcp.server import _DeriveArgs

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_a_negative_branch_point_is_refused():
    with pytest.raises(ValidationError) as exc:
        _DeriveArgs(project_id="p", name="n", branch_point=-5)
    assert "branch_point" in str(exc.value)


def test_zero_is_still_valid_because_the_index_is_zero_based():
    """The control, and the off-by-one that a `gt=0` would have introduced: chapter 0 is a legal
    branch point and is the most likely one — branching before the first chapter."""
    assert _DeriveArgs(project_id="p", name="n", branch_point=0).branch_point == 0


def test_omitting_it_is_still_allowed():
    """None means 'no explicit branch point', which is not the same as 0 and must stay reachable."""
    assert _DeriveArgs(project_id="p", name="n").branch_point is None


def test_the_bound_is_declared_on_the_model_not_hidden_in_the_handler():
    """A handler check would be invisible to the schema, so the model could not reject it before
    the handler ran and the caller would never see the constraint in tools/list."""
    assert "branch_point: int | None = Field(default=None, ge=0)" in BODY, (
        "branch_point no longer declares its bound; a handler-side check is not equivalent"
    )
