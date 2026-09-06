#!/usr/bin/env python3
"""glossary_create_evidence's SHIP cases, against attribute values that actually exist.

    python scripts/toolloop/evidence_ship_probe.py

🔴 WHY NOT ship_probe.py. The generic probe builds its cases from required arguments and a fresh
UUID. This tool requires entity_id AND attr_value_id, so a fresh entity_id is refused at the ENTITY
gate and the attr_value_id is never looked at — the same "green boundary check that never reached
the boundary" its own docstring warns about, and the shape that made kg_triage_schema_write's first
probe worthless.

So this builds TWO real books, each with an adopted `character` kind and an entity carrying an
`occupation` attribute VALUE, and asks the questions the ship_audit owes:

  absent   an attr_value_id that does not exist              -> must refuse
  tenancy  an attr_value_id belonging to the OTHER book      -> must refuse, ideally IDENTICALLY,
           because a refusal that separates "not yours" from "no such thing" is an existence oracle
  empty    the required attr_value_id present but blank      -> must refuse and name the field
  mismatch a REAL attr_value_id with the WRONG entity_id     -> the tool's own description says the
           value "must belong to the entity", so this is the pairing rule stated on the tin

SAFETY: two throwaway books of this module's own making, torn down in a finally. The only write
attempted is against a fixture created seconds earlier, and every refusal is the expected outcome —
a call that SUCCEEDS where it should not is itself the finding and is reported as one.
"""
from __future__ import annotations

import json
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from scripts.eval.tool_liveness import config as cfg  # noqa: E402
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError  # noqa: E402
from scripts.toolloop.provision import Throwaway, _tle_auth  # noqa: E402


def _build(mcp: MCPDirect, label: str) -> tuple[Throwaway, str, str]:
    """A book with an adopted character kind and one entity carrying an occupation VALUE."""
    fx = Throwaway(label, mcp=mcp).build()
    r = httpx.post(f"{cfg.DOMAIN_BASE['glossary']}/v1/glossary/books/{fx.book_id}/adopt",
                   headers=_tle_auth().bearer_header(),
                   json={"genres": ["universal"], "kinds": ["character"]}, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"adopt failed {r.status_code}: {r.text[:200]}")
    mcp.call("glossary_propose_entities", {
        "book_id": fx.book_id,
        "items": [{"kind": "character", "name": f"Aldric Vane {label}",
                   "attributes": {"occupation": "cartographer"}}]})
    ent = mcp.call("glossary_search", {"book_id": fx.book_id, "query": "Aldric Vane"})
    blob = json.dumps(ent)
    # the entity id and its attribute value id both come from the read the platform offers
    eid = None
    for key in ("entity_id", "id"):
        i = blob.find(f'"{key}": "')
        if i >= 0:
            eid = blob[i + len(key) + 4:].split('"')[1]
            break
    detail = mcp.call("glossary_get_entity", {"book_id": fx.book_id, "entity_id": eid})
    d = json.dumps(detail)
    j = d.find('"attr_value_id": "')
    avid = d[j + 18:].split('"')[0] if j >= 0 else None
    return fx, eid, avid


def _call(mcp: MCPDirect, book: str, entity: str, avid: str) -> dict:
    try:
        res = mcp.call("glossary_create_evidence", {
            "book_id": book, "entity_id": entity, "attr_value_id": avid,
            "original_text": "Aldric Vane climbed the black stair.", "evidence_type": "quote"})
    except MCPToolError as exc:
        return {"verdict": "refused", "detail": str(exc)[:220]}
    return {"verdict": "SUCCEEDED", "detail": json.dumps(res, ensure_ascii=False)[:220]}


def main() -> int:
    mcp = MCPDirect()
    a = b = None
    out: dict[str, dict] = {}
    try:
        a, a_ent, a_av = _build(mcp, "evship-a")
        b, b_ent, b_av = _build(mcp, "evship-b")
        out["_fixture"] = {"a_entity": a_ent, "a_attr_value": a_av,
                           "b_entity": b_ent, "b_attr_value": b_av}
        if not (a_av and b_av):
            out["_abort"] = {"why": "could not read an attr_value_id from glossary_get_entity — "
                                    "the probe cannot reach the boundary and says so"}
            return 0

        out["absent"] = _call(mcp, a.book_id, a_ent, str(uuid.uuid4()))
        out["absent"]["asked"] = "an attr_value_id that does not exist"
        out["tenancy"] = _call(mcp, a.book_id, a_ent, b_av)
        out["tenancy"]["asked"] = "an attr_value_id belonging to the OTHER book's entity"
        out["oracle"] = {"identical": out["absent"]["detail"] == out["tenancy"]["detail"],
                         "why": "separating 'not yours' from 'no such thing' is an existence oracle"}
        out["empty"] = _call(mcp, a.book_id, a_ent, "")
        out["empty"]["asked"] = "the required attr_value_id present but blank"
        out["mismatch"] = _call(mcp, a.book_id, b_ent, a_av)
        out["mismatch"]["asked"] = ("a REAL attr_value_id paired with the WRONG entity_id — the "
                                    "tool's description says the value must belong to the entity")
    finally:
        for fx in (a, b):
            if fx is None:
                continue
            try:
                fx.teardown()
            except Exception as exc:  # noqa: BLE001
                print(f"teardown failed for {fx.book_id}: {exc}", file=sys.stderr)

    for k, v in out.items():
        if k == "oracle":
            print(f"  {k:9s} identical={v['identical']}")
        elif k.startswith("_"):
            print(f"  {k:9s} {json.dumps(v, ensure_ascii=False)[:150]}")
        else:
            print(f"  {k:9s} {v['verdict']:10s} {v['detail'][:120]}")
    dest = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14" / "evidence-ship-probe.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
