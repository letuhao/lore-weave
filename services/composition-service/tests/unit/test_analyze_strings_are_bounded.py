"""Every free-text string ANALYZE can emit is bounded, and SPEC is not touched.

F8 (plan `2026-09-13-green-honestly`): the analyze step was truncated at 12,000 tokens on 12 of 14
controlled replays of one production request. The model never closed a string — an arc's `theme`
kept reading the author's document, then looped the arc list. With every free-text string bounded
the same replays parsed 8 of 8, extracting exactly what the unbounded arm did when it survived.

These tests pin the CONTRACT that measurement produced, not a model output.
"""

from __future__ import annotations

import json

from app.engine.plan_forge.schemas import ANALYZE_SCHEMA, SPEC_SCHEMA, _STR


def _strings(node, key=None, out=None):
    out = [] if out is None else out
    if isinstance(node, dict):
        if node.get("type") == "string":
            out.append((key, node))
        for k, v in (node.get("properties") or {}).items():
            _strings(v, k, out)
        if isinstance(node.get("items"), dict):
            _strings(node["items"], key, out)
    return out


def test_every_free_text_string_in_analyze_is_bounded():
    unbounded = [k for k, n in _strings(ANALYZE_SCHEMA) if "enum" not in n and "maxLength" not in n]
    assert unbounded == [], f"an unbounded analyze string is a runaway exit: {unbounded}"


def test_caps_match_the_measured_arm():
    """ids 80, prose 900, everything else 300 — the exact schema that parsed 8/8."""
    arc = ANALYZE_SCHEMA["properties"]["arcs"]["items"]["properties"]
    assert arc["id"]["maxLength"] == 80
    assert arc["theme"]["maxLength"] == 300
    assert ANALYZE_SCHEMA["properties"]["document_summary"]["maxLength"] == 900
    assert ANALYZE_SCHEMA["properties"]["variables"]["items"]["properties"]["code"]["maxLength"] == 80


def test_caps_are_per_field_not_one_shared_object():
    """`_STR` is one dict referenced by every string field. A deepcopy keeps that sharing, so every
    field became the SAME object and the last cap written won everywhere. This was caught, not
    assumed — the first version shipped ids at 300."""
    arc = ANALYZE_SCHEMA["properties"]["arcs"]["items"]["properties"]
    assert arc["id"] is not arc["theme"]
    assert arc["id"]["maxLength"] != arc["theme"]["maxLength"]


def test_enums_stay_enums():
    assert "maxLength" not in ANALYZE_SCHEMA["properties"]["arcs"]["items"]["properties"]["arc_kind"]


def test_the_shared_string_is_untouched():
    """Bounding works on copies; the module-level `_STR` every schema is built from stays bare."""
    assert _STR == {"type": "string"}


def test_every_free_text_string_in_spec_is_bounded():
    """F11 — materialize loops the same way (weaker evidence; see the note in schemas.py)."""
    unbounded = [k for k, n in _strings(SPEC_SCHEMA) if "enum" not in n and "maxLength" not in n]
    assert unbounded == [], f"an unbounded SPEC string is a runaway exit: {unbounded}"


def test_spec_caps_where_the_loops_were_seen():
    meta = SPEC_SCHEMA["properties"]["meta"]["properties"]
    assert meta["version_label"]["maxLength"] == 80      # looped source_checksum in a finished run
    assert meta["source_checksum"]["maxLength"] == 80    # a sha256 hex is 64
    chars = SPEC_SCHEMA["properties"]["layers"]["properties"]["characters"]["items"]["properties"]
    assert chars["baseline_notes"]["maxLength"] == 900
    assert "maxLength" not in SPEC_SCHEMA["properties"]["links"]["items"]["properties"]["kind"]
