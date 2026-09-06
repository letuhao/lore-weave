"""SHIP audit for composition_motif_adopt — absent_case and the INVERSE tenancy check.

This tool crosses the tenancy boundary BY DESIGN, so the check is the opposite of every other
one in the loop: adopting a PUBLIC/system motif must be ALLOWED, and adopting another USER's
PRIVATE motif must NOT.

No DML and no fixture: the store already contains motifs owned by other users (read-only SELECT
confirmed three distinct foreign owners), so the foreign case is real rather than simulated.
Every call is a PROPOSE — the tool mints a confirm_token and clones nothing until redeemed, and
this probe never redeems one.
"""
import json, sys, uuid
sys.path.insert(0, ".")
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError

m = MCPDirect()
FOREIGN_PRIVATE = "019f0959-f128-79fd-995c-58c1eb3b5094"   # owner ff688755-…, visibility private
SYSTEM_PUBLIC = "007cefaa-947e-5b54-ac9e-8e1acb6c6275"     # owner NULL, unlisted, active


def call(**args):
    try:
        r = m.call("composition_motif_adopt", args)
        return {"verdict": "SUCCEEDED", "detail": json.dumps(r, ensure_ascii=False)[:220]}
    except MCPToolError as e:
        return {"verdict": "refused", "detail": str(e)[:260]}


out = {}
out["absent"] = call(motif_id=str(uuid.uuid4()))
out["absent"]["asked"] = "a motif_id that does not exist"

out["malformed"] = call(motif_id="face-slap-reversal")
out["malformed"]["asked"] = "a motif NAME where a UUID is required"

out["tenancy_foreign_private"] = call(motif_id=FOREIGN_PRIVATE)
out["tenancy_foreign_private"]["asked"] = (
    "another USER's PRIVATE motif — must be REFUSED (the half that protects the boundary)")

out["tenancy_public_allowed"] = call(motif_id=SYSTEM_PUBLIC)
out["tenancy_public_allowed"]["asked"] = (
    "a SYSTEM/public motif — must be ALLOWED (the half the tool exists for); a confirm_token "
    "only, nothing cloned")
out["tenancy_public_allowed"]["minted_token"] = "confirm_token" in (
    out["tenancy_public_allowed"].get("detail") or "")

out["retag_not_asked_for"] = call(motif_id=SYSTEM_PUBLIC, retag_genres=["horror"])
out["retag_not_asked_for"]["asked"] = (
    "retag_genres supplied — the falsifier calls silently re-genre-ing a clone a refutation, so "
    "this records what the tool DOES with it rather than asserting it should refuse")
print(json.dumps(out, indent=2, ensure_ascii=False))
