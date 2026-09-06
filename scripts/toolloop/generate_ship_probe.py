"""SHIP audit for composition_generate — absent_case and tenancy, over MCP.

This tool SPENDS. Every call here is a PROPOSE: Tier W mints a confirm_token and runs nothing
until the token is redeemed, and this probe NEVER redeems one. Two throwaway books, torn down.
"""
import json, sys, uuid
sys.path.insert(0, ".")
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError
from scripts.toolloop.provision import Throwaway

m = MCPDirect()
REAL_MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"  # settings_list_models -> user_model_id


def call(**args):
    try:
        r = m.call("composition_generate", args)
        return {"verdict": "SUCCEEDED", "detail": json.dumps(r, ensure_ascii=False)[:180]}
    except MCPToolError as e:
        return {"verdict": "refused", "detail": str(e)[:260]}


a = b = None
out = {}
try:
    a = Throwaway("gen-ship-a", mcp=m).build()
    b = Throwaway("gen-ship-b", mcp=m).build()
    out["_fixture"] = {"book_a": a.book_id, "project_a": a.project_id, "chapter_a": a.chapter_id,
                       "book_b": b.book_id, "project_b": b.project_id, "chapter_b": b.chapter_id}
    base = {"project_id": a.project_id, "model_source": "user_model", "model_ref": REAL_MODEL}

    out["absent_chapter"] = call(**base, chapter_id=str(uuid.uuid4()))
    out["absent_chapter"]["asked"] = "a chapter_id that does not exist"

    out["absent_outline_node"] = call(**base, outline_node_id=str(uuid.uuid4()))
    out["absent_outline_node"]["asked"] = "an outline_node_id that does not exist"

    out["neither_target"] = call(**base)
    out["neither_target"]["asked"] = "NEITHER chapter_id nor outline_node_id — must refuse, not default"

    out["both_targets"] = call(**base, chapter_id=a.chapter_id, outline_node_id=str(uuid.uuid4()))
    out["both_targets"]["asked"] = "BOTH targets — the description says exactly one"

    out["invented_model_ref"] = call(project_id=a.project_id, model_source="platform_model",
                                     model_ref="default", chapter_id=a.chapter_id)
    out["invented_model_ref"]["asked"] = "model_ref='default' — the measured invention"

    out["tenancy_foreign_chapter"] = call(**base, chapter_id=b.chapter_id)
    out["tenancy_foreign_chapter"]["asked"] = "book B's chapter offered to book A's project"

    out["tenancy_foreign_project"] = call(project_id=b.project_id, model_source="user_model",
                                          model_ref=REAL_MODEL, chapter_id=a.chapter_id)
    out["tenancy_foreign_project"]["asked"] = "book A's chapter against book B's project"

    # 🔴 THE CONTROL NEEDS A CHAPTER THAT CAN ACTUALLY BE GENERATED. Since 2026-08-24 a chapter
    # target is refused at propose unless it has a SCENE PLAN — the precondition the engine
    # itself enforces (NO_CHAPTER_PLAN). A fresh fixture chapter has none, so without this seed
    # every case refuses and the probe cannot tell "correctly strict" from "broken".
    try:
        m.call("composition_outline_node_create", {
            "project_id": a.project_id, "kind": "scene", "chapter_id": a.chapter_id,
            "title": "The black stair", "goal": "Aldric reaches the codex",
            "synopsis": "He climbs as the storm breaks."})
        out["_seeded_scene"] = "ok"
    except MCPToolError as e:
        out["_seeded_scene"] = f"FAILED: {str(e)[:200]}"

    g = call(**base, chapter_id=a.chapter_id)
    g["asked"] = ("a VALID propose, on a chapter that HAS a scene plan — must mint a "
                  "confirm_token and RUN NOTHING. This is the control: without it, the refusals "
                  "above would look identical to a tool that refuses everything.")
    g["minted_token"] = "confirm_token" in (g.get("detail") or "")
    out["gate"] = g

    out["still_refused_without_a_plan"] = call(**base, chapter_id=b.chapter_id)
    out["still_refused_without_a_plan"]["asked"] = (
        "book B's chapter, which has no scene plan — still refused, so the seed did not simply "
        "disable the check")
finally:
    for fx in (a, b):
        if fx:
            try:
                fx.teardown()
            except Exception as e:  # noqa: BLE001
                out.setdefault("_teardown_errors", []).append(str(e)[:120])
print(json.dumps(out, indent=2, ensure_ascii=False))
