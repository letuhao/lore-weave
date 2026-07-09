"""WS-2b — workflow_list / workflow_load consumer-local meta-tools + async guard.

Pure functions (no DB/port) — no xdist_group mark needed.
"""

import app.services.workflow_runner as wr


def _wf(**over):
    base = {
        "slug": "glossary-bootstrap",
        "title": "Set up a glossary",
        "description": "Adopt standards then curate entities.",
        "tier": "system",
        "surfaces": ["chat"],
        "inputs": {"book_id": "required"},
        "steps": [
            {"id": "precheck", "tool": "book_get", "gate": "none"},
            {"id": "adopt", "tool": "glossary_adopt_standards", "gate": "confirm"},
            {"id": "extract", "tool": "glossary_extract_entities_from_doc", "gate": "none"},
        ],
        "notes_md": "why each step",
    }
    base.update(over)
    return base


# ── is_async_job_tool ────────────────────────────────────────────────────────

def test_async_job_tool_detects_job_starters():
    assert wr.is_async_job_tool("book_translate")
    assert wr.is_async_job_tool("glossary_extract_entities_from_doc")
    assert wr.is_async_job_tool("book_import_pdf")
    assert not wr.is_async_job_tool("book_get")
    assert not wr.is_async_job_tool("glossary_search")
    assert not wr.is_async_job_tool("")


# ── workflow_list_result ─────────────────────────────────────────────────────

def test_workflow_list_result_shape_and_sorted():
    out = wr.workflow_list_result([_wf(slug="zeta"), _wf(slug="alpha")])
    assert out["count"] == 2
    assert [w["slug"] for w in out["workflows"]] == ["alpha", "zeta"]
    assert out["workflows"][0]["title"] and out["workflows"][0]["description"]


def test_workflow_list_result_empty_gives_reason():
    out = wr.workflow_list_result([])
    assert out["count"] == 0
    assert out["reason"] == "no workflows"


# ── workflow_load_result ─────────────────────────────────────────────────────

def test_workflow_load_returns_rail_and_step_tools():
    payload, tools = wr.workflow_load_result([_wf()], "glossary-bootstrap")
    assert payload["slug"] == "glossary-bootstrap"
    assert payload["inputs"] == {"book_id": "required"}
    # step tools are de-duplicated, in order
    assert tools == ["book_get", "glossary_adopt_standards", "glossary_extract_entities_from_doc"]
    ids = [s["id"] for s in payload["steps"]]
    assert ids == ["precheck", "adopt", "extract"]


def test_workflow_load_annotates_async_and_gate():
    payload, _ = wr.workflow_load_result([_wf()], "glossary-bootstrap")
    steps = {s["id"]: s for s in payload["steps"]}
    # confirm gate preserved
    assert steps["adopt"]["gate"] == "confirm"
    # async job step annotated; a plain read is not
    assert steps["extract"].get("async_job") is True
    assert "async_job" not in steps["precheck"]
    # guidance mentions both the gate flow and async watching
    joined = " ".join(payload["guidance"]).lower()
    assert "confirm" in joined or "approval" in joined
    assert "job" in joined


def test_authored_async_flag_overrides_heuristic():
    # authored async_job=True on a tool the heuristic would NOT flag → honored
    wf = _wf(steps=[{"id": "s1", "tool": "kg_reindex", "gate": "none", "async_job": True}])
    payload, _ = wr.workflow_load_result([wf], wf["slug"])
    assert payload["steps"][0].get("async_job") is True
    # authored async_job=False on a tool the heuristic WOULD flag → suppressed
    wf2 = _wf(steps=[{"id": "s1", "tool": "book_translate", "gate": "none", "async_job": False}])
    payload2, _ = wr.workflow_load_result([wf2], wf2["slug"])
    assert "async_job" not in payload2["steps"][0]


def test_catalog_async_flag_flags_tool_over_heuristic():
    # a tool the name heuristic does NOT know, but the CATALOG marks _meta.async
    wf = _wf(steps=[{"id": "s1", "tool": "obscure_job_starter", "gate": "none"}])
    payload, _ = wr.workflow_load_result([wf], wf["slug"], frozenset({"obscure_job_starter"}))
    assert payload["steps"][0].get("async_job") is True
    # precedence: authored False beats a catalog-async flag
    wf2 = _wf(steps=[{"id": "s1", "tool": "obscure_job_starter", "gate": "none", "async_job": False}])
    payload2, _ = wr.workflow_load_result([wf2], wf2["slug"], frozenset({"obscure_job_starter"}))
    assert "async_job" not in payload2["steps"][0]


def test_media_read_tool_not_flagged_async():
    # regression: 'media' substring was dropped so media READ tools don't strand ui_watch_job
    wf = _wf(steps=[{"id": "s1", "tool": "media_list", "gate": "none"}])
    payload, _ = wr.workflow_load_result([wf], wf["slug"])
    assert "async_job" not in payload["steps"][0]


def test_malformed_empty_tool_step_skipped():
    wf = _wf(steps=[
        {"id": "ok", "tool": "book_get", "gate": "none"},
        {"id": "bad", "tool": "", "gate": "none"},
        {"id": "bad2", "gate": "none"},  # no tool key
    ])
    payload, tools = wr.workflow_load_result([wf], wf["slug"])
    assert [s["id"] for s in payload["steps"]] == ["ok"]
    assert tools == ["book_get"]


def test_workflow_load_bad_gate_normalized_to_none():
    wf = _wf(steps=[{"id": "s1", "tool": "book_get", "gate": "bogus"}])
    payload, _ = wr.workflow_load_result([wf], wf["slug"])
    assert payload["steps"][0]["gate"] == "none"


def test_workflow_load_not_found():
    payload, tools = wr.workflow_load_result([_wf()], "ghost")
    assert payload["not_found"] == "ghost"
    assert tools == []
    assert "workflow_list" in payload["reason"]


def test_workflow_load_repeat_and_when_carried():
    wf = _wf(
        inputs={"docs": "required"},
        steps=[{"id": "s1", "tool": "glossary_propose_entities", "gate": "approval",
                "repeat": "per_item:docs", "when": "docs.length > 0"}],
    )
    payload, _ = wr.workflow_load_result([wf], wf["slug"])
    s = payload["steps"][0]
    assert s["repeat"] == "per_item:docs"
    assert s["when"] == "docs.length > 0"
    assert s["gate"] == "approval"


def test_tool_defs_are_wellformed():
    for td in (wr.WORKFLOW_LIST_TOOL, wr.WORKFLOW_LOAD_TOOL):
        assert td["type"] == "function"
        assert td["function"]["name"] in (wr.WORKFLOW_LIST_NAME, wr.WORKFLOW_LOAD_NAME)
        assert "parameters" in td["function"]
    # load requires a slug
    assert wr.WORKFLOW_LOAD_TOOL["function"]["parameters"]["required"] == ["slug"]
