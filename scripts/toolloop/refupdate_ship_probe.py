"""SHIP audit for composition_reference_update — a tool that has NEVER completed a call.

Its required reference_id has no supplier on the agent surface (that is why it is blocked), but
the capability IS shipped: POST /works/{project_id}/references creates one. This probe uses the
REST route as FIXTURE SETUP only — the thing under test is still the MCP tool — so that the four
owed cases can be exercised and we learn whether the writer works at all.

Two throwaway books, provisioned and torn down.
"""
import json, sys, uuid
sys.path.insert(0, ".")
import httpx
from scripts.eval.tool_liveness import config as cfg
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError
from scripts.toolloop.provision import Throwaway, _tle_auth

m = MCPDirect()
EMBED_MODEL = "019e7f71-0271-722f-9c9c-3f049c0b26f4"  # bge-m3, capability_flags.embedding


def make_ref(fx, title):
    r = httpx.post(f"{cfg.DOMAIN_BASE['composition']}/v1/composition/works/{fx.project_id}/references",
                   headers=_tle_auth().bearer_header(), timeout=90,
                   json={"content": f"The tides of the Obsidian Trench, as recorded in {title}.",
                         "title": title, "author": "M. Solene",
                         "model_ref": EMBED_MODEL, "model_source": "user_model"})
    if r.status_code >= 400:
        return None, f"{r.status_code}: {r.text[:200]}"
    b = r.json()
    return (b.get("reference") or b).get("id") or b.get("reference_id"), None


def call(**args):
    try:
        r = m.call("composition_reference_update", args)
        return {"verdict": "SUCCEEDED", "detail": json.dumps(r, ensure_ascii=False)[:220]}
    except MCPToolError as e:
        return {"verdict": "refused", "detail": str(e)[:240]}


a = b = None
out = {}
try:
    a, b = Throwaway("ref-ship-a", mcp=m).build(), Throwaway("ref-ship-b", mcp=m).build()
    a_ref, a_err = make_ref(a, "Tidal Almanac")
    b_ref, b_err = make_ref(b, "Keep Ledger")
    out["_fixture"] = {"project_a": a.project_id, "ref_a": a_ref, "err_a": a_err,
                       "project_b": b.project_id, "ref_b": b_ref, "err_b": b_err}
    if not a_ref:
        raise SystemExit(json.dumps(out, indent=2, ensure_ascii=False))

    out["absent"] = call(project_id=a.project_id, reference_id=str(uuid.uuid4()), title="X")
    out["absent"]["asked"] = "a reference_id that does not exist"

    out["tenancy"] = call(project_id=a.project_id, reference_id=b_ref, title="X")
    out["tenancy"]["asked"] = "project B's reference offered to project A"

    out["no_fields"] = call(project_id=a.project_id, reference_id=a_ref)
    out["no_fields"]["asked"] = "NO field to change — a no-op patch"

    g = call(project_id=a.project_id, reference_id=a_ref, title="Tidal Almanac, Revised")
    g["asked"] = "a VALID metadata edit — the first call this tool has ever completed"
    out["gate"] = g

    g2 = call(project_id=a.project_id, reference_id=a_ref, title="Tidal Almanac, Revised")
    g2["asked"] = "the SAME edit twice"
    out["idempotency"] = g2

    chk = httpx.get(f"{cfg.DOMAIN_BASE['composition']}/v1/composition/works/{a.project_id}/references",
                    headers=_tle_auth().bearer_header(), timeout=60)
    out["_verify_via_rest"] = json.dumps(chk.json(), ensure_ascii=False)[:400]
finally:
    for fx in (a, b):
        if fx:
            try:
                fx.teardown()
            except Exception as e:  # noqa: BLE001
                out.setdefault("_teardown_errors", []).append(str(e)[:120])
print(json.dumps(out, indent=2, ensure_ascii=False))
