"""Phase 0 (frontend-tools → MCP migration) — the MCP-native validation seam.

`validate_frontend_tool_args` gives every frontend tool the arg validation a
backend MCP tool already inherits: the args are checked against the tool's own
canonical JSON-Schema (`function.parameters`) BEFORE the run suspends. The bug
this closes (session 019f771a): the model called `propose_edit` with
`propose_record_edit`'s arguments and nothing rejected it, so the turn suspended
and rendered an un-appliable Apply card.
"""
from __future__ import annotations

from app.services.frontend_tools import (
    CONFIRM_ACTION_TOOL,
    FRONTEND_TOOL_NAMES,
    PROPOSE_EDIT_TOOL,
    UI_OPEN_STUDIO_PANEL_TOOL,
    frontend_tool_def_by_name,
    generic_frontend_tool_def,
    validate_frontend_tool_args,
    _canonical_input_schema,
    _MISSING_REQUIRED_MARKER,
)


# ── the reported incident: propose_edit called with propose_record_edit's args ──
def test_incident_propose_edit_with_record_edit_args_is_rejected():
    """The exact 019f771a payload: propose_edit (requires operation+text,
    additionalProperties:false) called with the record-edit shape."""
    bad = {
        "domain": "book",
        "resource_ref": {"book_id": "b", "chapter_id": "c"},
        "base_version": "v1",
        "changes": [{"field_label": "x", "old_value": "a", "new_value": "b", "target": "t"}],
    }
    err = validate_frontend_tool_args("propose_edit", bad, PROPOSE_EDIT_TOOL)
    assert err is not None
    # missing-required is surfaced with the shared streak marker...
    assert _MISSING_REQUIRED_MARKER in err
    assert "operation" in err and "text" in err
    # ...and the record-edit-only keys are called out as disallowed.
    assert "base_version" in err or "resource_ref" in err


def test_valid_propose_edit_passes():
    ok = {"operation": "insert_at_cursor", "text": "Once upon a time."}
    assert validate_frontend_tool_args("propose_edit", ok, PROPOSE_EDIT_TOOL) is None


def test_valid_propose_edit_with_optional_rationale_passes():
    ok = {"operation": "replace_selection", "text": "new", "rationale": "why"}
    assert validate_frontend_tool_args("propose_edit", ok, PROPOSE_EDIT_TOOL) is None


def test_missing_required_reports_the_marker():
    err = validate_frontend_tool_args("propose_edit", {"operation": "insert_at_cursor"}, PROPOSE_EDIT_TOOL)
    assert err is not None
    assert _MISSING_REQUIRED_MARKER in err
    assert "text" in err


def test_bad_enum_value_is_rejected():
    """ui_open_studio_panel with an out-of-enum panel_id — the original
    silent-no-op bug class (a free-string panel that resolved to nothing)."""
    err = validate_frontend_tool_args(
        "ui_open_studio_panel", {"panel_id": "editor-does-not-exist"}, UI_OPEN_STUDIO_PANEL_TOOL
    )
    assert err is not None
    assert "panel_id" in err


def test_valid_enum_value_passes():
    err = validate_frontend_tool_args(
        "ui_open_studio_panel", {"panel_id": "editor"}, UI_OPEN_STUDIO_PANEL_TOOL
    )
    assert err is None


def test_disallowed_extra_prop_is_rejected():
    """additionalProperties:false — an unknown key must be caught even when all
    required props are present (the pure B↔C confusion tail)."""
    err = validate_frontend_tool_args(
        "confirm_action",
        {"confirm_token": "t", "descriptor": "book.publish", "title": "T", "domain": "book", "unexpected": 1},
        CONFIRM_ACTION_TOOL,
    )
    assert err is not None
    assert "unexpected" in err


# ── fail-open: never block a call we cannot judge ─────────────────────────────
def test_no_tool_def_fails_open():
    assert validate_frontend_tool_args("propose_edit", {"anything": 1}, None) is None


def test_tool_def_without_parameters_fails_open():
    empty = {"type": "function", "function": {"name": "x"}}
    assert validate_frontend_tool_args("x", {"a": 1}, empty) is None


def test_non_dict_args_fails_open():
    """A non-object payload (e.g. a stringified blob that slipped through) is not
    judged here — the arg-coercion layer handles that; we never crash on it."""
    assert validate_frontend_tool_args("propose_edit", "not a dict", PROPOSE_EDIT_TOOL) is None


def test_malformed_schema_fails_open(monkeypatch):
    broken = {"type": "function", "function": {"name": "x", "parameters": {"type": 123}}}
    # An invalid schema must never raise out of the validator — fail open.
    assert validate_frontend_tool_args("x", {"a": 1}, broken) is None


# ── enforcement: NO frontend tool may silently skip the validation seam ───────
def test_every_frontend_tool_name_resolves_to_a_validatable_schema():
    """The Phase 0 gate must cover EVERY frontend tool, not just the advertised
    subset. A future new frontend tool that forgets to register a schema-bearing
    def would slip past validation (fail-open) — this reds so it can't."""
    for name in FRONTEND_TOOL_NAMES:
        td = frontend_tool_def_by_name(name)
        assert td is not None, f"{name} has no canonical def for the validation seam"
        schema = _canonical_input_schema(td)
        assert schema is not None, f"{name} def has no canonical inputSchema"
        # An empty-args call must produce a validation error for any tool that has
        # required props (proves the schema is actually enforced, not inert).
        required = schema.get("required") or []
        if required:
            err = validate_frontend_tool_args(name, {}, td)
            assert err is not None and _MISSING_REQUIRED_MARKER in err, name


# ── the generic (cross-domain) resolver path is validated the same way ────────
def test_generic_resolver_def_validates():
    td = generic_frontend_tool_def("confirm_action")
    assert td is not None
    # confirm_action requires confirm_token, descriptor, title, domain
    err = validate_frontend_tool_args("confirm_action", {"confirm_token": "t"}, td)
    assert err is not None
    assert _MISSING_REQUIRED_MARKER in err
    ok = validate_frontend_tool_args(
        "confirm_action",
        {"confirm_token": "t", "descriptor": "book.publish", "title": "Publish", "domain": "book"},
        td,
    )
    assert ok is None


# ── UUID-shaped id args: the placeholder-id silent no-op (measured 2026-07-22) ────
# S00b real-stack E2E: asked to "Add a character called Lâm Uyên", gemma called
# glossary_propose_entity_edit 13× with entity_id="new_entity_id_placeholder" —
# effectful_tool_calls=0, book unchanged (DB-verified). Nothing rejected the placeholder,
# so the model got no signal and repeated the identical call. The id args now carry a UUID
# pattern so this is rejected BEFORE the suspend, with an explicit, re-routable message.


def _incident_args(**over):
    args = {
        "base_version": "0",
        "book_id": "current_book_id_placeholder",
        "entity_id": "new_entity_id_placeholder",
        "changes": [{"field_label": "Name", "new_value": "Lâm Uyên",
                     "old_value": "", "target": "short_description"}],
        "rationale": "Adding a new character to the book.",
    }
    args.update(over)
    return args


def test_placeholder_ids_are_rejected_before_suspend():
    from app.services.frontend_tools import frontend_tool_def_by_name, validate_frontend_tool_args
    name = "glossary_propose_entity_edit"
    err = validate_frontend_tool_args(name, _incident_args(), frontend_tool_def_by_name(name))
    assert err, "a placeholder entity_id must NOT sail through to a suspend (silent no-op)"
    assert "entity_id must be a real UUID" in err
    assert "new_entity_id_placeholder" in err  # names the offending value
    # and it must RE-ROUTE, not just complain — the create path is a different tool
    assert "glossary_propose_entities" in err


def test_real_uuids_still_validate():
    from app.services.frontend_tools import frontend_tool_def_by_name, validate_frontend_tool_args
    name = "glossary_propose_entity_edit"
    ok = _incident_args(book_id="019f84e1-8716-7c05-9696-1ebf2bde68fc",
                        entity_id="019f82b6-c31b-72e9-bf2a-3f37f4c8a847")
    assert validate_frontend_tool_args(name, ok, frontend_tool_def_by_name(name)) is None
