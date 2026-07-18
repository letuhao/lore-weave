"""CD4 · the tool_list ship gate (Track D · WS-D3).

`tool_list` MUST NOT advertise a tool the liveness matrix proved cannot execute. A broken
tool is worse than an absent one: the model spends a turn on it, gets an error, and often
reports success anyway (the false-persist bug class).

The three-valued `executes` is the whole point, and both directions are load-bearing:
  * `None` (never checked) must NOT hide the tool — that would empty the catalog, since
    ~200 tools have no probe yet.
  * `False` (proven broken) MUST hide it.
  * `True` with a failing G1 (RED-SELECT) must NOT hide it — the tool works; the model
    just didn't pick it from its description. Hiding it guarantees it never gets picked.

Pure functions (no DB/port) — no xdist_group mark needed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.services.tool_discovery as td
import app.services.tool_liveness as tl


def _tool(name: str, desc: str = "d", tier: str = "R") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": {}},
            "_meta": {"tier": tier},
        },
    }


@pytest.fixture
def fake_manifest(monkeypatch):
    """Swap the generated manifest for a fixture covering all four verdicts."""
    tools = {
        "book_list": {"status": "PASS", "executes": True, "proven": True},
        "glossary_broken": {"status": "RED-CAPABILITY", "executes": False, "proven": False},
        "book_unchecked": {"status": "RED", "executes": None, "proven": False},
        "book_unpicked": {"status": "RED-SELECT", "executes": True, "proven": False},
    }
    monkeypatch.setattr(tl, "TOOLS", tools)
    return tools


class TestManifestIsGeneratedNotHandEdited:
    def test_service_copy_matches_the_contract_sot(self):
        """The copy beside tool_liveness.py must be byte-identical to
        contracts/tool-liveness.json. It is a copy only because Python package data
        cannot climb out of its module; both are written by
        scripts/eval/tool_liveness/manifest.py. Hand-editing either is the drift this
        test catches."""
        here = Path(tl.__file__).with_name("tool-liveness.json")
        # app/services/tool_liveness.py → app/services → app → chat-service → services → repo
        root = Path(tl.__file__).resolve().parents[4]
        sot = root / "contracts" / "tool-liveness.json"
        # NOT a skip. A drift lock that quietly skips is worse than no drift lock — it
        # reports green while checking nothing. If the SoT moved, this test must go red.
        assert sot.exists(), (
            f"contracts/tool-liveness.json not found at {sot} — the drift lock cannot "
            "run. Fix the path; do not skip."
        )
        assert here.read_text(encoding="utf-8").replace("\r\n", "\n") == \
            sot.read_text(encoding="utf-8").replace("\r\n", "\n"), (
            "service copy has DRIFTED from contracts/tool-liveness.json — re-run: "
            "python -m scripts.eval.tool_liveness.manifest <matrix.json>"
        )

    def test_real_manifest_loads_and_is_non_empty(self):
        assert tl.SCHEMA_VERSION == 2  # v2 (D-TRACKD-REACCOUNT) adds waived:{reason,gate}
        assert tl.TOOLS, "manifest is empty — the CD4 gate would be silently inert"

    def test_real_manifest_never_reads_null_executes_as_broken(self):
        """The shipped manifest today has unchecked tools. None of them may be hidden."""
        raw = json.loads(Path(tl.__file__).with_name("tool-liveness.json").read_text(encoding="utf-8"))
        unchecked = [n for n, v in raw["tools"].items() if v["executes"] is None]
        assert unchecked, "fixture assumption: at least one unchecked tool exists"
        for n in unchecked:
            assert not tl.tool_is_broken(n), f"{n}: executes=null must not be treated as broken"


class TestPredicates:
    def test_broken_only_on_explicit_false(self, fake_manifest):
        assert tl.tool_is_broken("glossary_broken")
        assert not tl.tool_is_broken("book_list")
        assert not tl.tool_is_broken("book_unchecked"), "null == not checked, not broken"
        assert not tl.tool_is_broken("never_probed"), "absent == unproven, not broken"
        assert not tl.tool_is_broken("book_unpicked"), "RED-SELECT means the tool WORKS"

    def test_proven_is_all_gates_pass(self, fake_manifest):
        assert tl.tool_is_proven("book_list")
        for n in ("glossary_broken", "book_unchecked", "book_unpicked", "absent"):
            assert not tl.tool_is_proven(n)

    def test_broken_tool_names_is_exactly_the_hidden_set(self, fake_manifest):
        assert tl.broken_tool_names() == {"glossary_broken"}


class TestToolListWithdrawsBrokenTools:
    CATALOG = [
        _tool("book_list"), _tool("book_unchecked"), _tool("book_unpicked"),
        _tool("glossary_broken", tier="A"),
    ]

    def test_visible_tools_hides_only_the_broken_one(self, fake_manifest):
        names = [t["name"] for t in td.visible_tools(self.CATALOG)]
        assert "glossary_broken" not in names
        # everything else survives — including the unchecked and the merely-unpicked
        assert {"book_list", "book_unchecked", "book_unpicked"} <= set(names)

    def test_tool_list_result_hides_the_broken_one(self, fake_manifest):
        payload = td.tool_list_result(self.CATALOG, "book")
        names = [t["name"] for t in payload["tools"]]
        assert "glossary_broken" not in names
        assert payload["count"] == len(names)

    def test_a_healthy_catalog_is_completely_unaffected(self, monkeypatch):
        """No manifest entry ⇒ nothing hidden. The gate must be inert on an unprobed
        catalog, not a catalog-emptying filter."""
        monkeypatch.setattr(tl, "TOOLS", {})
        names = [t["name"] for t in td.visible_tools(self.CATALOG)]
        assert len(names) == 4


class TestToolLoadRefusesBrokenToolsOutLoud:
    CATALOG = [_tool("book_list"), _tool("glossary_broken", tier="A")]

    def test_load_by_name_reports_unavailable_never_silently_drops(self, fake_manifest):
        payload, activated = td.tool_load_result(self.CATALOG, name="glossary_broken")
        assert activated == [], "a broken tool must never be activated"
        assert payload["unavailable"] == ["glossary_broken"]
        assert "not_found" not in payload, (
            "a broken tool is not 'not found' — saying so would send the model hunting "
            "for a name that exists"
        )
        assert "do not retry" in payload["unavailable_reason"].lower()

    def test_load_by_category_skips_broken_without_an_unavailable_key(self, fake_manifest):
        """Loading a whole category never *asked* for the broken tool, so it is simply
        absent — no `unavailable` noise for a tool the model didn't name."""
        payload, activated = td.tool_load_result(self.CATALOG, category="book")
        assert "glossary_broken" not in activated
        assert "unavailable" not in payload

    def test_mixed_request_loads_the_good_and_reports_the_broken(self, fake_manifest):
        payload, activated = td.tool_load_result(
            self.CATALOG, names=["book_list", "glossary_broken", "ghost"])
        assert activated == ["book_list"]
        assert payload["unavailable"] == ["glossary_broken"]
        assert payload["not_found"] == ["ghost"]
