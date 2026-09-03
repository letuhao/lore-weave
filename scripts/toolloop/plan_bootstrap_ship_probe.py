#!/usr/bin/env python3
"""plan_bootstrap_apply's SHIP cases, driven through the real proposal chain.

    python scripts/toolloop/plan_bootstrap_ship_probe.py

WHY THIS EXISTS INSTEAD OF ship_probe.py. The generic probe builds its cases from a tool's
required arguments and a fresh UUID. plan_bootstrap_apply takes `book_id` and `proposal_id`,
and a fresh UUID for the second one only ever reaches "no such proposal" — which is a real
`absent` answer but tells us nothing about `gate`, `tenancy` or `idempotency`, because those
three all need a proposal that genuinely EXISTS. A proposal is minted by one tool at the end
of a three-step chain, so the fixture has to walk it:

    plan_propose_spec(book_id, mode=rules, source_markdown)  -> run_id
    plan_bootstrap_propose(book_id, run_id)                  -> proposal_id + new_chapters
    plan_bootstrap_apply(book_id, proposal_id)               -> confirm_token   <- the tool
    POST /v1/composition/actions/confirm?token=...           -> the chapters exist

The cases this owes, and what each is actually asking:

  gate         a Tier-A write must MINT a confirm_token and create NOTHING until it is redeemed.
               Asserted by counting chapters BEFORE the call, AFTER the call, and AFTER the
               redemption — the middle count is the one that matters, and a probe that only
               checked the last would pass on a tool that wrote immediately.
  absent       a proposal_id that does not exist must be refused.
  tenancy      book B's REAL proposal_id, offered against book A's book_id, must be refused.
               Ideally with the SAME words as `absent`: a refusal that distinguishes "not yours"
               from "no such thing" is an existence oracle.
  idempotency  redeeming the SAME confirm token twice must not create the chapters twice.

SAFETY: two throwaway books of this module's own making, torn down in a `finally`. Nothing
touches a pre-existing book, and every write is against a fixture created seconds earlier.
"""
from __future__ import annotations

import json
import pathlib
import sys
import uuid

sys.path.insert(0, ".")

import httpx  # noqa: E402

from scripts.eval.tool_liveness import config as cfg  # noqa: E402
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError  # noqa: E402
from scripts.toolloop.provision import Throwaway, _tle_auth  # noqa: E402

m = MCPDirect()

SPEC_MD = (
    "# Emberfall\n\n## Arc I - The Emberfall\n"
    "### The Ember Codex\nAldric Vane climbs the black stair and finds the codex burning.\n"
    "### The Waterline\nThe Obsidian Trench is walkable only at low tide.\n"
    "\n## Arc II - The Reckoning\n"
    "### The Black Stair Again\nAldric returns to the keep with the codex.\n"
    "### The Last Tide\nThe trench closes for good and the keep is cut off.\n"
)


def chapters(book_id: str) -> int:
    """Chapter count as the PLATFORM reports it, not as a DB query — the store this
    tool exists to move is the one the author sees."""
    r = m.call("book_list_chapters", {"book_id": book_id})
    blob = r if isinstance(r, dict) else {}
    for key in ("chapters", "items", "results"):
        if isinstance(blob.get(key), list):
            return len(blob[key])
    return json.dumps(r, ensure_ascii=False).count('"chapter_id"')


def build(label: str):
    """A throwaway book carried as far as a REAL, unredeemed proposal."""
    fx = Throwaway(label, mcp=m).build()
    spec = m.call("plan_propose_spec", {
        "book_id": fx.book_id, "mode": "rules", "source_markdown": SPEC_MD})
    run_id = spec["run_id"]
    prop = m.call("plan_bootstrap_propose", {"book_id": fx.book_id, "run_id": run_id})
    return fx, run_id, prop


def apply_call(book_id: str, proposal_id: str) -> dict:
    try:
        r = m.call("plan_bootstrap_apply", {"book_id": book_id, "proposal_id": proposal_id})
        return {"verdict": "SUCCEEDED", "raw": r,
                "detail": json.dumps(r, ensure_ascii=False)[:220]}
    except MCPToolError as e:
        return {"verdict": "refused", "raw": None, "detail": str(e)[:260]}


def redeem(token: str) -> dict:
    resp = httpx.post(
        f"{cfg.DOMAIN_BASE['composition']}/v1/composition/actions/confirm?token={token}",
        headers=_tle_auth().bearer_header(), timeout=90)
    body: object
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:200]
    return {"status": resp.status_code, "body": json.dumps(body, ensure_ascii=False)[:260]}


a = b = None
out: dict = {}
try:
    a, a_run, a_prop = build("pbs-a")
    b, b_run, b_prop = build("pbs-b")
    out["_fixture"] = {
        "a_book": a.book_id, "a_proposal": a_prop.get("proposal_id"),
        "a_new_chapters": a_prop.get("new_chapters_count"),
        "b_book": b.book_id, "b_proposal": b_prop.get("proposal_id"),
    }

    # ── absent ───────────────────────────────────────────────────────────────
    out["absent_case"] = apply_call(a.book_id, str(uuid.uuid4()))
    out["absent_case"]["asked"] = "a proposal_id that does not exist"

    # ── tenancy ──────────────────────────────────────────────────────────────
    out["tenancy"] = apply_call(a.book_id, b_prop["proposal_id"])
    out["tenancy"]["asked"] = "book B's REAL proposal offered against book A"

    # ── gate ─────────────────────────────────────────────────────────────────
    # The middle count is the whole point: a tool that created chapters at call
    # time would still pass a probe that only compared before with after-redeem.
    before = chapters(a.book_id)
    got = apply_call(a.book_id, a_prop["proposal_id"])
    after_call = chapters(a.book_id)
    token = (got.get("raw") or {}).get("confirm_token") if got["raw"] else None
    gate = {
        "asked": "a Tier-A write must MINT a token and create nothing until redeemed",
        "verdict": got["verdict"], "detail": got["detail"],
        "minted_token": bool(token),
        "chapters_before": before, "chapters_after_call": after_call,
    }
    if token:
        gate["redeem"] = redeem(token)
        gate["chapters_after_redeem"] = chapters(a.book_id)
        gate["held_until_redeemed"] = (after_call == before)
        gate["created_on_redeem"] = gate["chapters_after_redeem"] > before
    out["gate"] = gate

    # ── idempotency ──────────────────────────────────────────────────────────
    if token:
        second = redeem(token)
        out["idempotency"] = {
            "asked": "the SAME confirm token redeemed twice",
            "second_redeem": second,
            "chapters_after_second": chapters(a.book_id),
            "no_double_create": chapters(a.book_id) == gate.get("chapters_after_redeem"),
        }
    else:
        out["idempotency"] = {"asked": "the SAME confirm token redeemed twice",
                              "verdict": "NOT REACHED — no token was minted"}
finally:
    for fx in (a, b):
        if fx:
            try:
                fx.teardown()
            except Exception as e:  # noqa: BLE001 — teardown must not mask a result
                print("teardown:", e, file=sys.stderr)

for k, v in out.items():
    if k.startswith("_"):
        continue
    print(f"  {k:14s} {str(v.get('verdict', ''))[:10]:10s} {str(v.get('detail', ''))[:110]}")
print()
print(json.dumps(out, indent=2, ensure_ascii=False)[:2400])

pathlib.Path("docs/eval/toolloop/2026-08-14/plan-bootstrap-ship-probe.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
