"""D-A-FEDERATED-TOOL-DUPLICATED-BY-AN-ALWAYS-ON-CONSUMER-LOCAL-TWIN.

workflow_list (consumer-local, always-on) fetches its per-turn workflow list scoped by
`surface`, and the registry's own closed set is book | editor | studio (validWorkflowSurfaces,
agent-registry-service/internal/api/workflows.go). `_wf_surface`'s derivation never produced
"studio" — it only ever computed admin/editor/book/chat — even though `_studio =
bool(studio_context)` was already sitting right beside it, computed for other purposes and never
consulted here.

The Studio Compose panel sends BOTH studio_context AND editor_context (a chapter open in the
dock) — ComposePanel.tsx's editorContext mirrors the legacy standalone editor's shape exactly.
So a Studio turn and a legacy-editor turn were indistinguishable to this ternary; both fell to
"editor". Measured live (registry_list_workflows' own twin row): 4 of 5 Studio-surface turns
reported 9 workflows as available when only 6 are studio-scoped — the always-on tool was not
missing a filter, it was asking the registry for the wrong bucket.

🔴 THE FIX IS ORDERING, NOT A NEW FLAG. `_studio` must be checked BEFORE `_editor`: a Studio
turn always also satisfies `_editor` (editor_context accompanies it), but a legacy-editor turn
never sets studio_context. Checking `_editor` first would make the fix inert.
"""
from __future__ import annotations

import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1].joinpath(
    "app", "services", "stream_service.py").read_text(encoding="utf-8")


def _ternary_segment() -> str:
    i = SRC.index('_wf_surface = (')
    return SRC[i:][:400]


def test_studio_is_a_reachable_branch_of_the_ternary():
    seg = _ternary_segment()
    assert '"studio" if _studio else' in seg, (
        "the ternary no longer names 'studio' as a branch — a Studio turn falls back to "
        "'editor' again, the exact defect this test guards"
    )


def test_studio_is_checked_BEFORE_editor():
    """Ordering is the whole fix. A Studio turn also satisfies `_editor` (it sends
    editor_context alongside studio_context), so checking `_editor` first would make the
    `_studio` branch permanently unreachable — present in the source, dead in practice."""
    seg = _ternary_segment()
    i_studio = seg.index('"studio" if _studio')
    i_editor = seg.index('"editor" if _editor')
    assert i_studio < i_editor, (
        "'_editor' is checked before '_studio' — the studio branch can never fire, because "
        "every studio turn also satisfies _editor"
    )


def test_admin_still_takes_priority_over_studio():
    """Unchanged by this fix: an admin surface must not be reclassified as studio just because
    an admin turn happens to also carry studio_context."""
    seg = _ternary_segment()
    assert seg.strip().startswith('_wf_surface = ("admin" if _admin else')


def test_studio_flag_is_computed_from_studio_context_not_editor_context():
    """The discriminator this fix relies on: `_studio` must come from `studio_context`, the
    field ONLY the Studio surface sends — not from `editor_context`, which both surfaces send."""
    i = SRC.index("_studio = bool(")
    line = SRC[i:i + 40]
    assert "_studio = bool(studio_context)" in line
