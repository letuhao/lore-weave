#!/usr/bin/env python
"""Drive MANY REAL chat turns concurrently, through the path the FE actually uses.

🔴 WHY NOT A UNIT TEST, AND WHY NOT THE MCP SWEEP. Two things make this system untestable by
either, and the 31-cycle ledger is the evidence:

  1. THE DEFECTS LIVE ABOVE THE TOOL. 14 of 23 proven defects are in chat-service — surfacing,
     the hot-seed budget, the rail driver, arg injection/repair, the dispatch chokepoint — not in
     the tool being tested. A probe that talks straight to an MCP endpoint starts BELOW all of
     them. It marked `composition_list_outline` clean, correctly, while the real turn had the
     model answer "your outline is currently empty" with seven rows in the store.

  2. THE CONSUMER IS AN LLM, SO ONE SAMPLE PROVES NOTHING. The model is local gemma-4-26b and it
     is stochastic: the same prompt reaches the tool on one run and narrates a fabricated answer
     on the next. A single green run is not evidence, which is why every scenario here runs N
     times and the report is a DISTRIBUTION, never a verdict from one sample.

So this runner is the real environment: the same endpoint, headers, body and streaming contract
the browser sends, against the real chat-service and the real model. Captured from a live browser
turn (reqid=168) rather than reconstructed from the FE source, so it cannot drift into a
plausible-but-different request.

What it still does NOT cover, stated so its silence is never read as proof: React rendering,
confirm-card UI, and the context panel. A tool whose story involves those needs a browser.

  POST /v1/chat/sessions/{id}/messages
  headers: authorization: Bearer …, content-type: application/json,
           x-loreweave-stream-format: agui
  body:    {"content", "thinking", "reasoning_effort", "editor_context", "book_context"}
  reply:   text/event-stream of AG-UI events, including the `agentSurface` CUSTOM event that
           carries hot_seed_count / advertised{core,frontend,activated} / schema_tokens

Usage:
    python scripts/toolloop/fe_runner.py scenarios.json --repeats 5 --concurrency 4
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
from collections import Counter

import httpx

BASE = "http://localhost:5174"
AUTH_FILE = pathlib.Path(__file__).with_name("fe_runner_auth.json")


class Auth:
    """Access tokens expire mid-run (measured: a 401 on POST .../messages silently dropped a turn
    and the harness read it as 'the model chose not to answer'). Refresh on 401, once, then fail
    loudly — a run that quietly loses turns is worse than a run that stops."""

    def __init__(self, refresh_token: str, access_token: str = ""):
        self.refresh_token = refresh_token
        self.access = access_token

    async def refresh(self, client: httpx.AsyncClient) -> None:
        """The refresh token is ROTATED and single-use, and the browser holds the rotation — so a
        token copied out of localStorage is usually already spent, while the ACCESS token beside
        it is good for ~90 minutes. Measured: refresh returned AUTH_TOKEN_EXPIRED on a token
        captured seconds earlier, and the same file's access token created a session (201).
        So: use the access token, refresh only when it actually 401s, and if that fails say
        plainly what to do rather than reporting every scenario as a failure."""
        r = await client.post(f"{BASE}/v1/auth/refresh",
                              json={"refresh_token": self.refresh_token})
        if r.status_code != 200:
            raise RuntimeError(
                "auth refresh failed (%s: %s). The refresh token is rotated and single-use — "
                "reload the LoreWeave tab, then re-export localStorage['lw_auth'] into "
                "scripts/toolloop/fe_runner_auth.json." % (r.status_code, r.text[:120]))
        r.raise_for_status()
        d = r.json()
        self.access = d.get("accessToken") or d.get("access_token") or ""
        self.refresh_token = d.get("refreshToken") or d.get("refresh_token") or self.refresh_token
        if not self.access:
            raise RuntimeError(f"refresh returned no access token: {list(d)}")

    def headers(self) -> dict:
        return {"authorization": f"Bearer {self.access}",
                "content-type": "application/json",
                "x-loreweave-stream-format": "agui"}


async def _json(client, auth, method, path, **kw):
    for attempt in (1, 2):
        r = await client.request(method, f"{BASE}{path}", headers=auth.headers(), **kw)
        if r.status_code == 401 and attempt == 1:
            await auth.refresh(client)
            continue
        r.raise_for_status()
        return r.json() if r.content else {}
    raise RuntimeError("unreachable")


async def send_turn(client, auth, session_id, content, *, book_id=None, chapter_id=None,
                    thinking=False, effort="off", timeout=180.0):
    """One real turn. Returns the parsed AG-UI stream, not a rendering of it."""
    body = {"content": content, "thinking": thinking, "reasoning_effort": effort}
    if book_id and chapter_id:
        body["editor_context"] = {"book_id": book_id, "chapter_id": chapter_id}
    if book_id:
        body["book_context"] = {"book_id": book_id}

    out = {"text": "", "tool_calls": [], "surface": None, "run_id": None,
           "events": Counter(), "error": None}
    for attempt in (1, 2):
        try:
            async with client.stream(
                "POST", f"{BASE}/v1/chat/sessions/{session_id}/messages",
                headers=auth.headers(), json=body, timeout=timeout,
            ) as r:
                if r.status_code == 401 and attempt == 1:
                    await r.aread()
                    await auth.refresh(client)
                    continue
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        ev = json.loads(line[6:])
                    except ValueError:
                        continue
                    t = ev.get("type")
                    out["events"][t] += 1
                    if t == "RUN_STARTED":
                        out["run_id"] = ev.get("runId")
                    elif t == "TEXT_MESSAGE_CONTENT":
                        out["text"] += ev.get("delta", "")
                    elif t == "CUSTOM" and ev.get("name") == "agentSurface":
                        # keep the LAST one: it is the pass that actually reached the model
                        out["surface"] = ev.get("value")
                    elif t in ("TOOL_CALL_START", "TOOL_CALL_END", "TOOL_CALL_ARGS"):
                        out["tool_calls"].append(ev)
                    elif t == "RUN_ERROR":
                        out["error"] = str(ev)[:300]
            return out
        except httpx.HTTPError as e:
            if attempt == 2:
                out["error"] = f"{type(e).__name__}: {e}"
                return out
    return out


async def run_scenario(client, auth, sc, idx):
    """One scenario, one repetition, in its OWN session — so repeats cannot contaminate each
    other through conversation history, which is the whole point of measuring a distribution."""
    sess = await _json(client, auth, "POST", "/v1/chat/sessions", json={
        # `user_model`, NOT `user`. Guessed wrong once and every turn 502'd with
        # "credential resolution failed" from provider-registry — the session was created
        # happily (201) and only the TURN failed, so the harness reported it as a model
        # failure. Read from the working session's own row rather than invented.
        "model_source": sc.get("model_source", "user_model"),
        "model_ref": sc["model_ref"],
        "title": f"sweep {sc['id']} #{idx}",
        **({"book_id": sc["book_id"]} if sc.get("book_id") else {}),
    })
    sid = sess.get("session_id") or sess.get("id")
    res = await send_turn(client, auth, sid, sc["prompt"],
                          book_id=sc.get("book_id"), chapter_id=sc.get("chapter_id"))
    res["session_id"] = sid
    res["scenario"] = sc["id"]
    res["rep"] = idx
    return res


async def main_async(scenarios, repeats, concurrency):
    auth_raw = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    auth = Auth(auth_raw["refreshToken"], auth_raw.get("accessToken", ""))
    sem = asyncio.Semaphore(concurrency)
    results = []

    async with httpx.AsyncClient(timeout=180.0) as client:
        if not auth.access:
            await auth.refresh(client)

        async def one(sc, i):
            async with sem:
                try:
                    return await run_scenario(client, auth, sc, i)
                except Exception as e:  # noqa: BLE001 — one bad scenario must not kill the run
                    return {"scenario": sc["id"], "rep": i, "error": f"{type(e).__name__}: {e}",
                            "text": "", "tool_calls": [], "surface": None}

        jobs = [one(sc, i) for sc in scenarios for i in range(repeats)]
        for coro in asyncio.as_completed(jobs):
            r = await coro
            results.append(r)
            mark = "!" if r.get("error") else "."
            print(mark, end="", flush=True)
    print()
    return results


def report(results, scenarios, repeats):
    by = {sc["id"]: sc for sc in scenarios}
    print(f"\n{'scenario':<28} {'runs':<5} {'tool called':<12} {'surface has tool':<17} errors")
    print("-" * 92)
    for sid, sc in by.items():
        rs = [r for r in results if r.get("scenario") == sid]
        want = sc.get("expect_tool")
        called = sum(1 for r in rs if want and want in json.dumps(r.get("tool_calls") or []))
        surfaced = sum(
            1 for r in rs
            if want and want in json.dumps((r.get("surface") or {}).get("advertised") or {}))
        errs = sum(1 for r in rs if r.get("error"))
        print(f"{sid:<28} {len(rs):<5} {f'{called}/{len(rs)}':<12} "
              f"{f'{surfaced}/{len(rs)}':<17} {errs}")
    print("\nA scenario is only informative across REPEATS — the consumer is stochastic, so "
          "'1/5 called' is a finding and '5/5 surfaced, 0/5 called' is a different finding "
          "from '0/5 surfaced'.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenarios")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    scenarios = json.loads(pathlib.Path(a.scenarios).read_text(encoding="utf-8"))["scenarios"]
    results = asyncio.run(main_async(scenarios, a.repeats, a.concurrency))
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(results, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
        print(f"raw results -> {a.out}")
    report(results, scenarios, a.repeats)


if __name__ == "__main__":
    sys.exit(main())
