#!/usr/bin/env python3
"""kg_triage_schema_write's SHIP cases, driven at a project that ACTUALLY EXISTS.

    python scripts/toolloop/kg_triage_ship_probe.py

🔴 WHY THIS EXISTS INSTEAD OF ship_probe.py. The generic probe builds its cases from a tool's
required arguments and a fresh UUID. For this tool that never reaches the boundary: both `absent`
and `tenancy` came back

    Error executing tool kg_triage_schema_write: {"message": "project not found"}

which is the PROJECT gate refusing one level before the signature is ever looked at. The run reads
"refused / refused / oracle identical" and is worth nothing — the exact failure ship_probe.py's own
docstring warns about ("a green boundary check that never reached the boundary is worse than no
check, because it is recorded as evidence"). Only `empty` genuinely landed, on
"signature: String should have at least 1 character".

So this provisions two REAL throwaway projects, adopts an ontology into each, and then asks the
questions the ship_audit actually owes:

  gate     a Tier-W write must MINT a confirm_token and change nothing until it is redeemed
  absent   a signature that is not in this project's triage queue must be refused
  tenancy  a signature that exists in ANOTHER project must be refused here, and ideally with the
           SAME words as `absent` — a refusal that distinguishes "not yours" from "no such thing"
           is an existence oracle
  empty    carried over from the generic probe, which did reach it

SAFETY: two throwaway books of this module's own making, torn down in a finally. Nothing touches a
pre-existing project, and the only write attempted is against a fixture created seconds earlier.
"""
from __future__ import annotations

import json
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError  # noqa: E402
from scripts.toolloop.provision import Throwaway  # noqa: E402

FANTASY = "019feb06-2a98-710f-8d39-bdce8ec022ee"  # scope=system, deprecated_at IS NULL


def _adopt(mcp: MCPDirect, project_id: str) -> None:
    """Adopt the system Fantasy ontology into a throwaway project, INCLUDING the redemption.

    kg_adopt_template is confirm-gated: it mints a token and adopts nothing at call time. A probe
    that skipped the redemption would be testing an un-adopted project again and would get the
    precondition refusal, not the boundary.
    """
    import httpx
    from scripts.eval.tool_liveness import config as cfg
    from scripts.toolloop.provision import _tle_auth

    r = mcp.call("kg_adopt_template", {"project_id": project_id, "source_schema_id": FANTASY})
    tok = r.get("confirm_token")
    if not tok:
        raise RuntimeError(f"kg_adopt_template minted no confirm_token: {json.dumps(r)[:200]}")
    resp = httpx.post(f"{cfg.DOMAIN_BASE['knowledge']}/v1/kg/actions/confirm",
                      headers=_tle_auth().bearer_header(),
                      json={"confirm_token": tok}, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"adopt confirm failed {resp.status_code}: {resp.text[:200]}")


def _edge_codes(mcp: MCPDirect, project_id: str) -> list[str]:
    """The project's current edge-type codes, read from the tool the platform offers for it."""
    try:
        r = mcp.call("kg_schema_read", {"project_id": project_id})
    except MCPToolError as exc:
        return [f"<kg_schema_read failed: {exc}>"]
    blob = json.dumps(r)
    return sorted({c for c in ("allied_with",) if c in blob}) or ["<none of the probed codes>"]


def _redeem_and_diff(mcp: MCPDirect, project_id: str, sig: str) -> dict:
    """Propose against an invented signature, redeem the token, and report what the schema did."""
    import httpx
    from scripts.eval.tool_liveness import config as cfg
    from scripts.toolloop.provision import _tle_auth

    before = _edge_codes(mcp, project_id)
    try:
        r = mcp.call("kg_triage_schema_write", {
            "project_id": project_id, "signature": sig, "action": "add_to_schema",
            "code": "allied_with", "label": "Allied With"})
    except MCPToolError as exc:
        return {"verdict": "refused at propose", "detail": str(exc)[:220], "before": before}
    tok = r.get("confirm_token")
    if not tok:
        return {"verdict": "no token minted", "detail": json.dumps(r)[:220], "before": before}
    resp = httpx.post(f"{cfg.DOMAIN_BASE['knowledge']}/v1/kg/actions/confirm",
                      headers=_tle_auth().bearer_header(),
                      json={"confirm_token": tok}, timeout=60)
    after = _edge_codes(mcp, project_id)
    return {
        "verdict": ("REDEEMED and the schema changed" if after != before
                    else "redeemed, schema UNCHANGED" if resp.status_code < 400
                    else "refused at confirm"),
        "confirm_status": resp.status_code,
        "confirm_body": str(resp.text)[:220],
        "before": before, "after": after,
        "asked": ("whether redeeming a token minted for a signature that was never in the triage "
                  "queue actually mutates the schema"),
    }


def _call(mcp: MCPDirect, args: dict) -> tuple[str, str]:
    try:
        res = mcp.call("kg_triage_schema_write", args)
    except MCPToolError as exc:
        return "refused", str(exc)[:220]
    return "SUCCEEDED", json.dumps(res)[:220]


def main() -> int:
    mcp = MCPDirect()
    out: dict[str, dict] = {}
    a = Throwaway("kgship-a", mcp=mcp).build()
    b = Throwaway("kgship-b", mcp=mcp).build()
    try:
        _adopt(mcp, a.project_id)
        _adopt(mcp, b.project_id)

        # ── gate ────────────────────────────────────────────────────────────────────────
        # A signature the queue does not hold still exercises the GATE if the tool proposes
        # before it validates; if it refuses instead, that IS the absent case and the gate is
        # exercised by the live batch's 5/5 confirm_token instead. Report which happened.
        sig = f"allied_with|character|character|{uuid.uuid4().hex[:6]}"
        verdict, detail = _call(mcp, {"project_id": a.project_id, "signature": sig,
                                      "action": "add_to_schema", "code": "allied_with",
                                      "label": "Allied With"})
        out["absent"] = {"verdict": verdict, "detail": detail,
                         "asked": "a signature that is not in this project's triage queue"}

        # ── tenancy ─────────────────────────────────────────────────────────────────────
        # The SAME signature, offered to the OTHER project. If `absent` refused, this must refuse
        # identically; if `absent` succeeded, this succeeding would be a cross-project write.
        verdict_b, detail_b = _call(mcp, {"project_id": b.project_id, "signature": sig,
                                          "action": "add_to_schema", "code": "allied_with",
                                          "label": "Allied With"})
        out["tenancy"] = {"verdict": verdict_b, "detail": detail_b,
                          "asked": "the same signature against a project that does not own it"}
        out["oracle"] = {
            "identical": detail == detail_b,
            "why": ("a refusal that distinguishes 'not yours' from 'no such thing' tells a "
                    "stranger which signatures are real"),
        }

        # ── empty ───────────────────────────────────────────────────────────────────────
        verdict_e, detail_e = _call(mcp, {"project_id": a.project_id, "signature": "",
                                          "action": "add_to_schema"})
        out["empty"] = {"verdict": verdict_e, "detail": detail_e,
                        "asked": "the required signature present but blank"}

        # ── bad action ──────────────────────────────────────────────────────────────────
        verdict_x, detail_x = _call(mcp, {"project_id": a.project_id, "signature": sig,
                                          "action": "definitely_not_an_action"})
        out["closed_set"] = {"verdict": verdict_x, "detail": detail_x,
                             "asked": "an action outside the declared closed set"}

        # ── gate: does REDEEMING an invented signature's token actually change the schema? ──
        # `absent` SUCCEEDED, so propose does not validate the signature. That is only a defect
        # if the redemption applies it — otherwise the gate is where validation lives and the
        # token is an offer the confirm step refuses. This is the question that decides it, and
        # it can only be answered by redeeming one. Written to THIS run's own project, which is
        # torn down in the finally below.
        out["gate"] = _redeem_and_diff(mcp, a.project_id, sig)
    finally:
        for fx in (a, b):
            try:
                fx.teardown()
            except Exception as exc:  # noqa: BLE001
                print(f"teardown failed for {fx.book_id}: {exc}", file=sys.stderr)

    for case, r in out.items():
        if case == "oracle":
            print(f"  {case:11s} identical={r['identical']}")
            continue
        print(f"  {case:11s} {r.get('verdict','?'):24s} "
              f"{str(r.get('detail') or r.get('confirm_body') or '')[:120]}")
    dest = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14" / "kg-triage-ship-probe.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
