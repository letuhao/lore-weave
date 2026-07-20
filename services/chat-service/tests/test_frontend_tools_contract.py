"""Frontend-tool CONTRACT guard (anti-drift).

A *frontend tool* is a contract that spans two services in two languages: the
chat-service advertises the schema (here) and the browser resolver executes it
(frontend/src/features/**). The LLM is the only thing "connecting" the two — so
when a schema and its resolver disagree on an arg name, or a closed-set arg has
no enum, every isolated unit test stays green while the live loop silently dies.
(This is exactly how `ui_open_studio_panel` shipped broken: `panel_id` was a
free string with no enum, a weak model sent `panel:"editor"`, the resolver
no-op'd, the model hallucinated success. Fixed f1f9e9966.)

This test is the BE half of the guard. It:
  1. Snapshots every advertised frontend-tool schema into a committed,
     cross-language contract JSON (`contracts/frontend-tools.contract.json`) that
     the FE guard reads — so a schema change that isn't mirrored to the FE
     resolver turns a test red instead of a runtime hallucination.
  2. Enforces the CONVENTIONS (CLAUDE.md → Frontend-tool contract):
       • every FRONTEND_TOOL_NAMES entry has exactly one schema (no orphans);
       • every schema is wire-standard (function/name/object params/required ⊆
         properties/additionalProperties present);
       • every CLOSED-SET arg is an `enum` (never a bare string a weak model can
         drift the name OR value of).

To intentionally change a schema: update the code, then regenerate the contract
with `WRITE_FRONTEND_CONTRACT=1 pytest tests/test_frontend_tools_contract.py`
and commit the new JSON alongside the matching FE resolver change.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.services.frontend_tools import (
    FRONTEND_TOOL_NAMES,
    GLOSSARY_CONFIRM_ACTION_TOOL,
    GLOSSARY_PROPOSE_EDIT_TOOL,
    PROPOSE_EDIT_TOOL,
    UI_FOCUS_MANUSCRIPT_UNIT_TOOL,
    UI_OPEN_STUDIO_PANEL_TOOL,
    _GENERIC_FRONTEND_TOOLS_BY_NAME,
    _studio_panel_tool,
)

# ── the CHAT-SERVICE-owned frontend-tool set (name → schema) ─────────────────
# _GENERIC_FRONTEND_TOOLS_BY_NAME holds the generic tools (confirm_action,
# propose_record_edit, propose_edit); the two glossary tools are advertised via the
# book_scoped branch of frontend_tool_defs, so add them explicitly. Every
# FRONTEND_TOOL_NAMES entry MUST resolve to a schema here.
#
# Phase 3 (P3.2, 2026-07-20): the ui_* tools are NO LONGER chat-service frontend
# tools — they moved to ai-gateway as consumer-local directive tools. The shared
# contract JSON is now SPLIT-OWNED: chat-service owns these 5 entries; ai-gateway
# owns the 7 ui_* entries and drift-tests THEM against the same JSON in
# services/ai-gateway/test/ui-tools.spec.ts. So this test validates only its slice
# (subset-match) and the regen MERGES (never drops the ui_* entries).
ALL_FRONTEND_TOOLS: dict[str, dict] = {
    **_GENERIC_FRONTEND_TOOLS_BY_NAME,
    "glossary_propose_entity_edit": GLOSSARY_PROPOSE_EDIT_TOOL,
    "glossary_confirm_action": GLOSSARY_CONFIRM_ACTION_TOOL,
}

# Args whose valid values are a FINITE, code-known set. The contract requires
# each to be an `enum` so a weak model cannot drift the arg name or value. A
# `[]` segment descends into an array's item schema. Free-form args (UUIDs,
# prose, allowlisted paths, dynamic panel names) are deliberately NOT listed.
# (The ui_* closed-set args + propose_edit.operation are ai-gateway's now — enum-checked
# in ui-tools.spec.ts / propose-edit-tool.spec.ts.)
CLOSED_SET_ARGS: dict[str, list[str]] = {
    "glossary_propose_entity_edit": ["changes[].target"],
    "confirm_action": ["domain"],
    "propose_record_edit": ["domain"],
}

_CONTRACT_PATH = (
    Path(__file__).resolve().parents[3] / "contracts" / "frontend-tools.contract.json"
)


def _normalize(tool: dict) -> dict:
    """The wire-invariant slice the FE resolver must agree with: required arg
    names + each top-level arg's type/enum. Descriptions (prompt-only) are
    dropped so wording tweaks don't churn the contract."""
    params = tool["function"]["parameters"]
    args = {}
    for name, spec in params.get("properties", {}).items():
        entry = {"type": spec.get("type")}
        if "enum" in spec:
            entry["enum"] = spec["enum"]
        args[name] = entry
    return {"required": sorted(params.get("required", [])), "args": args}


def _resolve_arg_path(tool: dict, dotted: str) -> dict:
    """Walk `a.b[].c` into the nested property spec (arrays via `[]`)."""
    node = tool["function"]["parameters"]
    for seg in dotted.split("."):
        array = seg.endswith("[]")
        key = seg[:-2] if array else seg
        node = node["properties"][key]
        if array:
            node = node["items"]
    return node


def _build_contract() -> dict:
    return {name: _normalize(tool) for name, tool in sorted(ALL_FRONTEND_TOOLS.items())}


class TestFrontendToolContract:
    def test_every_advertised_name_has_exactly_one_schema(self):
        # No orphan names (a name the loop suspends on but has no schema) and no
        # orphan schemas (a def never actually advertised).
        assert set(FRONTEND_TOOL_NAMES) == set(ALL_FRONTEND_TOOLS)

    @pytest.mark.parametrize("name", sorted(ALL_FRONTEND_TOOLS))
    def test_schema_is_wire_standard(self, name):
        fn = ALL_FRONTEND_TOOLS[name]
        assert fn["type"] == "function"
        assert fn["function"]["name"] == name
        params = fn["function"]["parameters"]
        assert params["type"] == "object"
        props = set(params.get("properties", {}))
        assert set(params.get("required", [])) <= props, f"{name}: required arg not in properties"
        # additionalProperties must be pinned (False, or True only for open bags).
        assert "additionalProperties" in params, f"{name}: additionalProperties not pinned"

    @pytest.mark.parametrize("name", sorted(CLOSED_SET_ARGS))
    def test_closed_set_args_are_enums(self, name):
        # THE rule that would have caught the ui_open_studio_panel bug: a finite
        # arg must be an enum so a weak model can't guess the value (or, by the
        # enum reinforcing the arg, the name).
        for dotted in CLOSED_SET_ARGS[name]:
            spec = _resolve_arg_path(ALL_FRONTEND_TOOLS[name], dotted)
            assert spec.get("type") == "string", f"{name}.{dotted}: closed-set arg must be a string"
            assert spec.get("enum"), f"{name}.{dotted}: closed-set arg MUST declare an enum"

    def test_contract_json_matches_the_live_schemas(self):
        # The committed cross-language contract the FE guard reads. Regenerate on
        # an intentional schema change (see module docstring) — a silent drift here
        # is a red test, not a broken agent→GUI loop.
        #
        # Phase 3 split-ownership: the JSON also holds ai-gateway-owned ui_* entries
        # (drift-tested in ui-tools.spec.ts). So we validate only the CHAT-SERVICE
        # slice (subset-match) and MERGE on regen — never drop the ui_* entries.
        built = _build_contract()
        assert _CONTRACT_PATH.exists(), (
            "contracts/frontend-tools.contract.json missing — generate with "
            "WRITE_FRONTEND_CONTRACT=1 pytest tests/test_frontend_tools_contract.py"
        )
        on_disk = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
        if os.environ.get("WRITE_FRONTEND_CONTRACT") == "1":
            merged = {**on_disk, **built}  # chat-service slice over the existing (ui_*-preserving) JSON
            _CONTRACT_PATH.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            pytest.skip("regenerated contracts/frontend-tools.contract.json (merged chat-service slice)")
        for name, schema in built.items():
            assert name in on_disk, f"{name} missing from the committed contract — regenerate"
            assert on_disk[name] == schema, (
                f"{name} drifted from the committed contract — regenerate with "
                "WRITE_FRONTEND_CONTRACT=1 and update the matching FE resolver"
            )


# ── Residual RELOCATED defs still ADVERTISED by chat-service (drift guard) ────
# Phases 2/3 relocated propose_edit + the studio ui_* to ai-gateway (execution +
# validation live there, drift-tested vs the SAME contract JSON in
# ui-tools.spec.ts / propose-edit-tool.spec.ts). But chat-service still ADVERTISES
# these three to the model (frontend_tool_defs: propose_edit on the editor branch,
# ui_open_studio_panel + ui_focus_manuscript_unit on the studio branch) from its own
# local const schemas — a SECOND copy of each schema. They dropped out of
# FRONTEND_TOOL_NAMES / _GENERIC / ALL_FRONTEND_TOOLS above, so nothing on the chat
# side re-checked them: the advertised copy could silently DRIFT from ai-gateway's
# validated copy (the model would call the args chat-service advertised, ai-gateway
# would reject them — the exact both-sides-must-agree failure the LOCKED Frontend-Tool
# Contract exists to prevent). Until P4 sources the advertisement from the catalog and
# these consts are deleted, pin the advertised copy to the single contract SoT so both
# copies stay machine-checked. (Retiring the defs is large; guarding them is cheap.)
_RESIDUAL_ADVERTISED: dict[str, dict] = {
    "propose_edit": PROPOSE_EDIT_TOOL,
    "ui_open_studio_panel": UI_OPEN_STUDIO_PANEL_TOOL,
    "ui_focus_manuscript_unit": UI_FOCUS_MANUSCRIPT_UNIT_TOOL,
}


class TestResidualAdvertisedDefsMatchContract:
    """The relocated-but-still-advertised chat-side schemas must equal the committed
    contract SoT — the same JSON ai-gateway drift-tests its copy against. This closes
    the drift surface the migration left open (a chat-only edit to these consts would
    otherwise pass every test yet diverge from ai-gateway's validator)."""

    @pytest.mark.parametrize("name", sorted(_RESIDUAL_ADVERTISED))
    def test_advertised_copy_matches_committed_contract(self, name):
        on_disk = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
        assert name in on_disk, (
            f"{name} missing from contracts/frontend-tools.contract.json — it is "
            "ai-gateway-owned; regenerate the ai-gateway slice"
        )
        assert _normalize(_RESIDUAL_ADVERTISED[name]) == on_disk[name], (
            f"{name}: the schema chat-service ADVERTISES drifted from the contract "
            "(ai-gateway validates against it). Re-sync the const in frontend_tools.py "
            "or regenerate the ai-gateway contract slice — both copies must agree."
        )

    def test_compact_studio_panel_never_trims_the_enum(self):
        # The compact ui_open_studio_panel variant (F7c, default-on) must trim only the
        # PROSE, never the panel_id enum — a free-string panel_id was the original
        # silent-no-op bug. Both variants must normalize to the SAME contract slice.
        assert _normalize(_studio_panel_tool(compact=True)) == _normalize(
            _studio_panel_tool(compact=False)
        )
