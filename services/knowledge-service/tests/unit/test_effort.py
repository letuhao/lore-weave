"""D-RE-OTHER-AGENTIC-EFFORT — the reasoning-effort grant clamp (INV-T11)."""
from loreweave_grants import GrantLevel

from app.effort import clamp_effort_to_grant


def test_clamp_ceilings_by_grant():
    # View/None can't reason; Edit caps at medium; Manage/Owner at high.
    assert clamp_effort_to_grant("high", GrantLevel.OWNER) == ("high", False)
    assert clamp_effort_to_grant("high", GrantLevel.MANAGE) == ("high", False)
    assert clamp_effort_to_grant("high", GrantLevel.EDIT) == ("medium", True)
    assert clamp_effort_to_grant("medium", GrantLevel.EDIT) == ("medium", False)
    assert clamp_effort_to_grant("low", GrantLevel.EDIT) == ("low", False)
    assert clamp_effort_to_grant("high", GrantLevel.VIEW) == ("none", True)
    assert clamp_effort_to_grant("high", GrantLevel.NONE) == ("none", True)


def test_clamp_normalises_unknown_and_off():
    assert clamp_effort_to_grant("off", GrantLevel.OWNER) == ("none", False)
    assert clamp_effort_to_grant("bogus", GrantLevel.OWNER) == ("none", False)
    assert clamp_effort_to_grant(None, GrantLevel.OWNER) == ("none", False)
    assert clamp_effort_to_grant("HIGH", GrantLevel.MANAGE) == ("high", False)  # case-insensitive
