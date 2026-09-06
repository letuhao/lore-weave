#!/usr/bin/env python
"""Measure on the LIVE stack what the board can only prove in source.

🔴 WHY THIS EXISTS. `runstate.py` reads the repository. It answered `v1 IS DEAD` on 2026-09-03
while the RUNNING system still had chat-service's `frontend_tools.py` in its image, still
referenced `generic_frontend_tool_def` twice, and had an ai-gateway that predated the identity
fix. Every clause was true of the source and none of it was true of the thing serving traffic.

A source board cannot see a deployment. So this asks the running services directly:

  P1  the three KIND-C tools federate FROM ai-gateway, read from the live catalogue rather than
      from `contracts/tool-catalog-cache.json` (which is a SNAPSHOT and lags a rebuild)
  P2  V2 -- a gated confirm site answers a tasks-capable client with a durable TASK, and a
      non-capable client with a `confirm_token`. Both halves matter: GATE-2 keeps the token
      fallback PERMANENT, so "no tokens anywhere" would be a REGRESSION, not a win. What must
      not happen is a bare token going to a client that declared it can drive tasks.
  P3  no LIVE tool's model-facing text steers at a tool the superseded gate drops -- the same
      invariant as scripts/test_a_live_tool_never_sends_the_model_to_a_dropped_one.py, but
      against the live catalogue, so it closes without waiting for a cache refresh.

Every probe reports what it OBSERVED, never a verdict inferred from one sample.

Usage:
    python scripts/v1_retire/live_probe.py            # all probes
    python scripts/v1_retire/live_probe.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

GATEWAY = os.environ.get("AI_GATEWAY_URL", "http://localhost:8218")
APP = os.environ.get("LOREWEAVE_APP_URL", "http://localhost:5174")
CHAT_DB_CONTAINER = os.environ.get("CHAT_DB_CONTAINER", "infra-postgres-1")
INTERNAL_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev_internal_token")

#: The ext-tasks client-capability envelope. Byte-identical to what chat-service sends
#: (`task_detect.tasks_capability_meta`) and to what the server reads
#: (`loreweave_mcp.tasks_wire.client_supports_tasks`). If this drifts, P2 measures nothing:
#: the domain would answer with a token and the probe would call it a defect.
TASKS_META = {"io.modelcontextprotocol/clientCapabilities":
              {"extensions": {"io.modelcontextprotocol/tasks": {}}}}

V1_TOOLS = ("confirm_action", "glossary_confirm_action", "glossary_propose_entity_edit")
# 🔴 IMPORTED, NOT COPIED. This file had its own CONSUMER_LOCAL_OK literal for about an hour
# and P4 immediately failed on two names the real list had just gained -- a second copy of
# the answer, disagreeing with the first, inside the loop whose entire subject is one home
# per fact. gates.py owns it; everything else asks gates.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gates import CONSUMER_LOCAL_OK  # noqa: E402


def _rpc(method: str, params: dict, *, user_id: str = "probe") -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        f"{GATEWAY}/mcp", data=body, method="POST",
        headers={"content-type": "application/json",
                 "accept": "application/json, text/event-stream",
                 "x-internal-token": INTERNAL_TOKEN,
                 "x-user-id": user_id})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode("utf-8", "replace")
    # The gateway may answer SSE-framed JSON-RPC; take the first data: line if so.
    if raw.lstrip().startswith("event:") or raw.lstrip().startswith("data:"):
        for line in raw.splitlines():
            if line.startswith("data:"):
                raw = line[5:].strip()
                break
    return json.loads(raw)


def p1_federation() -> dict:
    """The three KIND-C tools are served, and served BY ai-gateway."""
    try:
        res = _rpc("tools/list", {})
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"state": "UNKNOWN", "detail": f"gateway unreachable: {exc}"}
    tools = ((res.get("result") or {}).get("tools")) or []
    by_name = {t.get("name"): t for t in tools if isinstance(t, dict)}
    missing = [n for n in V1_TOOLS if n not in by_name]
    served_by = {n: ((by_name.get(n) or {}).get("_meta") or {}).get("served_by")
                 for n in V1_TOOLS if n in by_name}
    ok = not missing
    return {"state": "PASS" if ok else "FAIL",
            "live_tool_count": len(tools),
            "missing": missing,
            "served_by": served_by,
            "detail": "read from the LIVE catalogue, not contracts/tool-catalog-cache.json"}


def p2_gate_negotiation() -> dict:
    """V2 — a tasks-capable client gets a durable TASK; everyone else keeps the token.

    🔴 BOTH HALVES ARE THE ASSERTION. It is tempting to read V2 as "no confirm_token anywhere on
    the wire", and that reading would make GATE-2 a bug: the token fallback is PERMANENT, because
    the public MCP edge and external agents cannot drive tasks. What must never happen is a BARE
    TOKEN GOING TO A CLIENT THAT SAID IT CAN DRIVE TASKS. So the probe makes the SAME call twice,
    differing only in the `_meta` capability envelope, and requires the two answers to differ in
    the specified direction. A probe that only sent the capability could not tell a working gate
    from a domain that had stopped minting tokens entirely.

    It needs a real user id, a session id and a book, because the domain rejects the call without
    them — and each of those was discovered by the call failing, not by reading a doc.

    SIDE EFFECT, stated rather than hidden: the capable arm opens ONE durable task in
    `input_required` on a throwaway book. That is the evidence, so it is not cleaned up; it is
    also why this never runs against the dogfood book.
    """
    try:
        import re as _re
        import pathlib as _pl
        import uuid as _uuid
        env_file = _pl.Path(__file__).resolve().parents[2] / "docs" / "dev" / "LOCAL_TEST_ENV.md"
        if not env_file.exists():
            return {"state": "UNKNOWN", "detail": f"{env_file} missing — cannot log in"}
        env = env_file.read_text(encoding="utf-8")
        m = _re.search(r"^email:\s*(\S+)", env, _re.M)
        pw = _re.search(r"^password:\s*(\S.*?)\s*$", env[m.end():], _re.M)
        body = json.dumps({"email": m.group(1), "password": pw.group(1)}).encode()
        req = urllib.request.Request(f"{APP}/v1/auth/login", data=body, method="POST",
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            login = json.loads(r.read())
        uid = (login.get("user_profile") or {}).get("user_id")
        tok = login.get("access_token") or login.get("accessToken")
        if not (uid and tok):
            return {"state": "UNKNOWN", "detail": "login returned no user_id/token"}

        def _api(path, payload):
            rq = urllib.request.Request(
                f"{APP}{path}", data=json.dumps(payload).encode(), method="POST",
                headers={"content-type": "application/json", "authorization": f"Bearer {tok}"})
            with urllib.request.urlopen(rq, timeout=90) as r:
                return json.loads(r.read() or b"{}")

        # 🔴 REUSE THE PROBE BOOK. The first version minted a new one every run, so a probe meant
        # to be re-run littered the account with near-identical throwaway books -- the same class
        # of mess as the 60 abandoned input_required tasks that motivated the expiry message.
        # A fixed title makes the probe idempotent in the only way that matters here.
        TITLE = "ZZ Throwaway v1-retire gate probe"
        rq = urllib.request.Request(f"{APP}/v1/books?limit=100",
                                    headers={"authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(rq, timeout=60) as r:
            listing = json.loads(r.read() or b"{}")
        rows = listing.get("items") or listing.get("books") or []
        existing = next((b for b in rows if (b.get("title") or "").startswith(TITLE)), None)
        if existing:
            bid = existing.get("book_id") or existing.get("id")
        else:
            book = _api("/v1/books", {"title": TITLE,
                                      "description": "live gate probe; safe to delete"})
            bid = book.get("book_id") or book.get("id")
        rq = urllib.request.Request(f"{APP}/v1/books/{bid}/chapters",
                                    headers={"authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(rq, timeout=60) as r:
            chs = json.loads(r.read() or b"{}")
        crows = chs.get("items") or chs.get("chapters") or []
        if crows:
            cid = crows[0].get("chapter_id") or crows[0].get("id")
        else:
            ch = _api(f"/v1/books/{bid}/chapters",
                      {"title": "Probe chapter", "content": "The gate opened.",
                       "original_language": "en"})
            cid = ch.get("chapter_id") or ch.get("id")
        sid = str(_uuid.uuid4())

        def _call(meta):
            params = {"name": "translation_start_job",
                      "arguments": {"book_id": bid, "chapter_ids": [cid], "target_language": "vi"}}
            if meta:
                params["_meta"] = meta
            b = json.dumps({"jsonrpc": "2.0", "id": 1,
                            "method": "tools/call", "params": params}).encode()
            rq = urllib.request.Request(
                f"{GATEWAY}/mcp", data=b, method="POST",
                headers={"content-type": "application/json",
                         "accept": "application/json, text/event-stream",
                         "x-internal-token": INTERNAL_TOKEN, "x-user-id": uid,
                         "x-session-id": sid, "x-book-id": bid})
            with urllib.request.urlopen(rq, timeout=180) as r:
                raw = r.read().decode("utf-8", "replace")
            if raw.lstrip().startswith(("event:", "data:")):
                for line in raw.splitlines():
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                        break
            res = (json.loads(raw).get("result")) or {}
            text = "".join(c.get("text", "") for c in (res.get("content") or [])
                           if isinstance(c, dict))
            try:
                return json.loads(text)
            except ValueError:
                return {"_unparsed": text[:200]}

        capable = _call(TASKS_META)
        plain = _call(None)
    except (urllib.error.URLError, OSError, ValueError, AttributeError, KeyError) as exc:
        return {"state": "UNKNOWN", "detail": f"probe could not run: {exc}"}

    got_task = capable.get("type") == "io.loreweave/task-handle" and bool(capable.get("taskId"))
    bare_token_to_capable = bool(capable.get("confirm_token"))
    got_token = bool(plain.get("confirm_token"))
    ok = got_task and not bare_token_to_capable and got_token
    return {"state": "PASS" if ok else "FAIL",
            "tasks_capable_client": ("durable task " + str(capable.get("status"))
                                     if got_task else f"NO TASK: {sorted(capable)}"),
            "bare_token_to_a_capable_client": bare_token_to_capable,
            "non_capable_client_keeps_the_token": got_token,
            "book": bid,
            "detail": "GATE-2: task-vs-token is negotiated PER CALL; the token fallback is permanent"}


def p3_steering() -> dict:
    """No live tool's model-facing text sends the model at a dropped tool."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "steer", os.path.join(os.path.dirname(__file__), "..",
                                  "test_a_live_tool_never_sends_the_model_to_a_dropped_one.py"))
        steer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(steer)
    except Exception as exc:  # noqa: BLE001 - the probe reports, it does not crash the run
        return {"state": "UNKNOWN", "detail": f"could not load the steering gate: {exc}"}
    try:
        res = _rpc("tools/list", {})
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"state": "UNKNOWN", "detail": f"gateway unreachable: {exc}"}
    tools = ((res.get("result") or {}).get("tools")) or []
    # Shape the live list like the cache the gate reads: {name: {description, inputSchema, meta}}.
    # Everything the live catalogue serves is by definition LIVE, so a dropped tool can only be
    # named -- never served -- and the gate needs the dropped set to compare against.
    live = {t["name"]: {"function": {"description": t.get("description") or "",
                                     "parameters": t.get("inputSchema") or {}}}
            for t in tools if isinstance(t, dict) and t.get("name")}
    cache_path = os.path.join(os.path.dirname(__file__), "..", "..",
                              "contracts", "tool-catalog-cache.json")
    with open(cache_path, encoding="utf-8") as fh:
        cache = json.load(fh)
    dropped = {n for n, r in cache.items()
               if (r.get("meta") or {}).get("visibility", "live") == "legacy"}
    merged = dict(live)
    for n in dropped:
        merged.setdefault(n, {"function": {"description": ""}, "meta": {"visibility": "legacy"}})
        merged[n]["meta"] = {"visibility": "legacy"}
    hits = steer.find(merged)
    return {"state": "PASS" if not hits else "FAIL",
            "live_tools": len(live),
            "dropped_named": {k: sorted(v) for k, v in hits.items()},
            "detail": "live descriptions, so it does not wait on a catalogue-cache refresh"}


def p4_advertised_on_the_wire() -> dict:
    """D2 measured on the WIRE: every name chat-service ADVERTISED resolves federated.

    🔴 THE BOARD'S D2 CHECKS THREE NAMES BY HAND. It asks whether the three v1 tools appear in the
    federated catalogue, which cannot tell a real regression from a chat-native tool -- and cannot
    see a FOURTH local schema appearing tomorrow. This reads `chat_messages.advertised_tools`, the
    recorder chat-service itself writes each advertise pass, and requires every name in it to
    resolve from the live federated catalogue or sit on the measured CONSUMER_LOCAL_OK list.

    It found two on its first run: `conversation_search` and `chat_search_sessions`. Both are
    legitimate -- they read chat-service's own conversation store -- but the allowlist did not
    name them, so the board had no way to distinguish them from the thing it exists to forbid.

    Needs a REAL TURN to have happened. With no rows it reports UNKNOWN rather than PASS: an
    empty population is not evidence of a clean one.
    """
    try:
        q = ("SELECT advertised_tools::text FROM chat_messages WHERE advertised_tools IS NOT NULL "
             "ORDER BY created_at DESC LIMIT 20;")
        proc = subprocess.run(
            ["docker", "exec", CHAT_DB_CONTAINER, "psql", "-U", "loreweave", "-d",
             "loreweave_chat", "-t", "-A", "-c", q],
            capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            return {"state": "UNKNOWN",
                    "detail": f"could not read the recorder: {(proc.stderr or '').strip()[:160]}"}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"state": "UNKNOWN", "detail": f"could not read the recorder: {exc}"}

    names, passes = set(), 0
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows = json.loads(line)
        except ValueError:
            continue
        for r in (rows if isinstance(rows, list) else [rows]):
            if isinstance(r, dict) and r.get("names"):
                passes += 1
                names.update(r["names"])
    if not passes:
        return {"state": "UNKNOWN",
                "detail": "no advertise pass recorded — run a real chat turn first "
                          "(scripts/toolloop/fe_runner.py); an empty population is not evidence"}
    try:
        res = _rpc("tools/list", {})
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"state": "UNKNOWN", "detail": f"gateway unreachable: {exc}"}
    federated = {t.get("name") for t in ((res.get("result") or {}).get("tools") or [])}
    unresolved = sorted(n for n in names
                        if n not in federated and n not in CONSUMER_LOCAL_OK)
    return {"state": "PASS" if not unresolved else "FAIL",
            "advertise_passes": passes,
            "distinct_names": len(names),
            "unresolved_local_schemas": unresolved,
            "detail": "read from chat_messages.advertised_tools, the recorder chat-service writes"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = {"p1_federation": p1_federation(),
           "p2_gate_negotiation": p2_gate_negotiation(),
           "p3_steering": p3_steering(),
           "p4_advertised_on_the_wire": p4_advertised_on_the_wire()}
    if a.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print("LIVE PROBE — what the source board cannot see")
        print("=" * 66)
        for k, v in out.items():
            print(f"[{v['state']:7}] {k}")
            for kk, vv in v.items():
                if kk != "state":
                    print(f"          {kk}: {vv}")
        print("=" * 66)
    bad = [k for k, v in out.items() if v["state"] == "FAIL"]
    unknown = [k for k, v in out.items() if v["state"] == "UNKNOWN"]
    print(f"OVERALL: {'ALL LIVE PROBES PASS' if not bad and not unknown else ''}"
          f"{'FAIL: ' + ', '.join(bad) if bad else ''}"
          f"{('  UNKNOWN: ' + ', '.join(unknown)) if unknown else ''}")
    return 1 if bad or unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
