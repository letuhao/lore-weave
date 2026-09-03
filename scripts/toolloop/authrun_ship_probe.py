"""SHIP audit for composition_authoring_run_manage — driven over MCP against the deployed tool.

Four owed cases: absent, empty, tenancy, gate, idempotency. Every one is driven on a THROWAWAY
book provisioned and torn down here; nothing touches the dogfood book.
"""
import json, sys, uuid
sys.path.insert(0, ".")
import httpx
from scripts.eval.tool_liveness import config as cfg
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError
from scripts.toolloop.provision import Throwaway, _tle_auth


def confirm(token):
    """Redeem a confirm-token through the same REST route the UI uses."""
    r = httpx.post(f"{cfg.DOMAIN_BASE['composition']}/v1/composition/actions/confirm?token={token}",
                   headers=_tle_auth().bearer_header(), timeout=90)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {"text": r.text[:200]}

m = MCPDirect()
MD = "# Emberfall\n\n## Arc I\n### A\nAldric climbs.\n### B\nThe trench.\n\n## Arc II\n### C\nHe returns.\n### D\nIt closes.\n"


def build(label):
    fx = Throwaway(label, mcp=m).build()
    r = m.call("plan_propose_spec", {"book_id": fx.book_id, "mode": "rules", "source_markdown": MD})
    plan = r.get("run_id") or (r.get("run") or {}).get("id")
    return fx, plan


def call(**args):
    try:
        r = m.call("composition_authoring_run_manage", args)
        # `detail` is TRUNCATED for readability, so it must never be the thing we parse — the
        # first version of this probe json.loads()'d it and died on an unterminated string.
        return {"verdict": "SUCCEEDED", "detail": json.dumps(r, ensure_ascii=False)[:200], "_raw": r}
    except MCPToolError as e:
        return {"verdict": "refused", "detail": str(e)[:240]}


a = b = None
out = {}
try:
    a, a_plan = build("authrun-ship-a")
    b, b_plan = build("authrun-ship-b")
    out["_fixture"] = {"book_a": a.book_id, "plan_a": a_plan, "book_b": b.book_id, "plan_b": b_plan}

    out["absent"] = call(op="create", book_id=a.book_id, plan_run_id=str(uuid.uuid4()),
                         budget_usd=5, pause_after_each_unit=True)
    out["absent"]["asked"] = "op=create with a plan_run_id that does not exist"

    out["empty_plan_run_id"] = call(op="create", book_id=a.book_id, plan_run_id="",
                                    budget_usd=5, pause_after_each_unit=True)
    out["empty_plan_run_id"]["asked"] = "plan_run_id present but EMPTY"

    out["omitted_required"] = call(op="create", book_id=a.book_id)
    out["omitted_required"]["asked"] = "op=create with all three create-required args omitted"

    out["tenancy_plan_from_other_book"] = call(op="create", book_id=a.book_id, plan_run_id=b_plan,
                                               budget_usd=5, pause_after_each_unit=True)
    out["tenancy_plan_from_other_book"]["asked"] = "book B's plan run offered to book A"

    out["absent_run_id"] = call(op="start", book_id=a.book_id, run_id=str(uuid.uuid4()))
    out["absent_run_id"]["asked"] = "op=start on a run_id that does not exist"

    # GATE — a cost-bearing create must mint a confirm-token and create NOTHING at call time.
    # scope AND tool_allowlist must both be non-empty or op=gate refuses ("scope is empty",
    # then "tool_allowlist must be a non-empty list") — start is unreachable until both are set,
    # so the idempotency claim is untestable without them. This is the same wall the model hit
    # live: "I first need to define exactly which chapters the autopilot should work through".
    g = call(op="create", book_id=a.book_id, plan_run_id=a_plan, budget_usd=5,
             pause_after_each_unit=True, scope=[a.chapter_id],
             tool_allowlist=["composition_write_prose"])
    g["asked"] = "a VALID create — must mint a confirm_token and write nothing yet"
    g["minted_token"] = "confirm_token" in (g.get("detail") or "")
    lst = m.call("composition_authoring_run_list", {"book_id": a.book_id})
    g["runs_after_propose"] = json.dumps(lst, ensure_ascii=False)[:200]
    out["gate"] = g

    # IDEMPOTENCY — the same propose twice must not leave two runs behind (nothing is created
    # until confirm, so two proposes must still leave zero).
    g2 = call(op="create", book_id=a.book_id, plan_run_id=a_plan, budget_usd=5,
              pause_after_each_unit=True)
    g2["asked"] = "the SAME create proposed twice (nothing is created until confirm, so BOTH "
    g2["asked"] += "must still leave zero runs)"
    lst2 = m.call("composition_authoring_run_list", {"book_id": a.book_id})
    g2["runs_after_second_propose"] = json.dumps(lst2, ensure_ascii=False)[:200]
    out["gate_second_propose"] = g2

    # 🔴 THE SCENARIO'S ship_audit ASKS SOMETHING STRICTLY STRONGER than proposing twice:
    # "op=start on an already-started run must not start a second one". Proving the weaker
    # claim and recording it under the stronger one's name is how a ship bar gets hollowed
    # out, so drive the real thing: redeem the token, start the run, then start it AGAIN.
    code, body = confirm((g.get("_raw") or {}).get("confirm_token")) if g["verdict"] == "SUCCEEDED" else (None, {})
    run = (body or {}).get("run") or {}
    run_id = run.get("run_id") or run.get("id")
    out["_created"] = {"confirm_status": code, "run_id": run_id, "status": run.get("status")}
    if run_id:
        # 🔴 THE LIFECYCLE IS draft -> gated -> running, AND SKIPPING THE GATE MAKES THE
        # IDEMPOTENCY CLAIM VACUOUS. The first version of this probe went straight to op=start
        # and got 409 "start requires status=gated, run is draft" on BOTH calls — two identical
        # refusals that look exactly like a passing idempotency check while proving nothing,
        # because the run was never started even once.
        gt = call(op="gate", book_id=a.book_id, run_id=run_id)
        gt["asked"] = "op=gate — the draft -> gated transition start requires"
        gtok = (gt.get("_raw") or {}).get("confirm_token")
        if gtok:
            gt["confirm_status"], _gb = confirm(gtok)
            gt["confirm_body"] = json.dumps(_gb, ensure_ascii=False)[:220]
        out["gate_transition"] = gt
        s1 = call(op="start", book_id=a.book_id, run_id=run_id)
        s1["asked"] = "op=start on the created run (propose)"
        tok = (s1.get("_raw") or {}).get("confirm_token")
        if tok:
            c1, b1 = confirm(tok)
            s1["confirm_status"], s1["confirm_body"] = c1, json.dumps(b1, ensure_ascii=False)[:200]
        out["start_first"] = s1
        s2 = call(op="start", book_id=a.book_id, run_id=run_id)
        s2["asked"] = "op=start AGAIN on the now-started run"
        tok2 = (s2.get("_raw") or {}).get("confirm_token")
        if tok2:
            c2, b2 = confirm(tok2)
            s2["confirm_status"], s2["confirm_body"] = c2, json.dumps(b2, ensure_ascii=False)[:200]
        out["idempotency"] = s2
        # 🔴 COUNT IT, do not print a TRUNCATED list and eyeball it — the whole assertion is
        # "not a second one", and a string cut at 400 chars cannot answer how many there are.
        _end = m.call("composition_authoring_run_list", {"book_id": a.book_id})
        _items = _end.get("items") or []
        out["idempotency"]["run_count_at_end"] = len(_items)
        out["idempotency"]["run_states_at_end"] = [
            {"run_id": i.get("run_id"), "status": i.get("status")} for i in _items]
finally:
    for fx in (a, b):
        if fx:
            try:
                fx.teardown()
            except Exception as e:  # noqa: BLE001
                out.setdefault("_teardown_errors", []).append(str(e)[:120])
for _v in out.values():
    if isinstance(_v, dict):
        _v.pop("_raw", None)
print(json.dumps(out, indent=2, ensure_ascii=False))
