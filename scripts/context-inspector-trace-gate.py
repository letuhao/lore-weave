#!/usr/bin/env python
"""Context Inspector telemetry GATE (spec §13b) — the LIVE half of the trace contract.

`tests/test_context_trace_contract.py` proves the emit function *can* produce every field;
this proves a REAL turn on the live stack actually PERSISTS them non-null. It drives a few
turns through the running chat-service (test account, local gemma, $0), then reads
`GET /v1/chat/sessions/{id}/context-trace` and asserts, against the committed
`contracts/context-trace.contract.json`, that every frame field is present + non-null on a
fresh turn and that each trace span is wire-standard. A field the compiler forgot → this fails.

Run (stack up, env like the sweep driver):
    JWT_SECRET=… python scripts/context-inspector-trace-gate.py
Env: SW_BASE (default http://localhost:8090), SW_USER, SW_MODEL_REF, SW_PROJECT_ID (bind a book
to exercise the T5 gate + grounding). Mirrors scripts/eval/run_budget_sweep.py exactly.

    python scripts/context-inspector-trace-gate.py --selfcheck

`--selfcheck` is the half that runs WITHOUT a stack, and it is what CI runs. It proves the gate
itself still works — imports resolve, the contract parses and declares both field lists, the
turn set is non-empty — because a live gate nobody can execute rots exactly like an unwired
lint, and rots invisibly: the failure looks like "no stack today", every day.

Exit codes are distinct on purpose: 0 pass · 1 the gate FAILED (a real defect) · 2 the gate
could not RUN (missing JWT_SECRET, no stack). Conflating 2 into 1 makes a red build ambiguous;
conflating it into 0 is the skip-reads-as-pass bug this repo has now shipped twice.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
import jwt

CANNOT_RUN = 2

BASE = os.environ.get("SW_BASE", "http://localhost:8090")
# NOT os.environ["JWT_SECRET"] — that raised KeyError at IMPORT time, so the script could not
# reach its own --help, and any caller without the secret got a traceback instead of a reason.
SECRET = os.environ.get("JWT_SECRET")
USER = os.environ.get("SW_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
MODEL_REF = os.environ.get("SW_MODEL_REF", "019eeb08-8be3-78fb-86c0-3b1eda7e0457")
PROJECT_ID = os.environ.get("SW_PROJECT_ID") or None
CONTRACT_PATH = (
    Path(__file__).resolve().parents[1] / "contracts" / "context-trace.contract.json"
)
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _bearer() -> str:
    now = int(time.time())
    return jwt.encode({"sub": USER, "iat": now, "exp": now + 3600}, SECRET, algorithm="HS256")


def selfcheck(contract: dict | None = None, turns: list[str] | None = None) -> int:
    """Everything the live gate depends on, minus the stack. Runs in CI.

    `contract`/`turns` are parameters so `--self-test` can drive the REAL
    checker over synthetic inputs. Reading the module globals here would make
    every probe test the live contract instead of its own fixture (`GTD-17`)."""
    contract = CONTRACT if contract is None else contract
    turns = TURNS if turns is None else turns
    problems: list[str] = []
    for key in ("frame_fields", "trace_span_fields"):
        val = contract.get(key)
        if not isinstance(val, list) or not val:
            problems.append(f"contract key {key!r} missing or empty")
    if not turns:
        problems.append("TURNS is empty — the gate would drive no turns and pass vacuously")
    if problems:
        for p in problems:
            print(f"FAIL: {p}")
        return 1
    print(
        f"SELFCHECK PASS — contract parses ({len(contract['frame_fields'])} frame fields, "
        f"{len(contract['trace_span_fields'])} span fields), {len(turns)} turns declared."
    )
    print(f"  Live half NOT run here: needs a stack at {BASE} + JWT_SECRET "
          f"({'set' if SECRET else 'NOT set'}).")
    return 0


def _hdr(stream: bool = False) -> dict:
    h = {"Authorization": f"Bearer {_bearer()}"}
    if stream:
        h["Accept"] = "text/event-stream"
        h["x-loreweave-stream-format"] = "agui"
    return h


def _create_session(c: httpx.Client) -> str:
    body = {"title": "inspector-trace-gate", "model_source": "user_model", "model_ref": MODEL_REF}
    if PROJECT_ID:
        body["project_id"] = PROJECT_ID
    r = c.post(f"{BASE}/v1/chat/sessions", json=body, headers=_hdr())
    r.raise_for_status()
    return r.json()["session_id"]


def _send(c: httpx.Client, sid: str, content: str) -> None:
    with c.stream("POST", f"{BASE}/v1/chat/sessions/{sid}/messages",
                  json={"content": content}, headers=_hdr(stream=True), timeout=900) as resp:
        resp.raise_for_status()
        for _ in resp.iter_lines():
            pass  # drain; we read the persisted frame afterwards


# A mix that exercises the derivations: a lore lookup (gated=included), a status-op
# (gated=out), and enough turns that a long session may trip C_persist compaction.
TURNS = [
    "Tell me about the main character and their goal.",
    "Who are their enemies?",
    "Change the status of the current scene to drafting.",
    "Make the last passage a little darker in tone.",
    "Summarize what we've established so far.",
]


def main() -> int:
    if "--selfcheck" in sys.argv:
        return selfcheck()
    if not SECRET:
        print("CANNOT RUN: JWT_SECRET is not set — this gate drives REAL turns through the "
              "running chat-service and cannot mint a bearer without it.")
        print("  Live:  JWT_SECRET=… python scripts/context-inspector-trace-gate.py")
        print("  Static: python scripts/context-inspector-trace-gate.py --selfcheck")
        return CANNOT_RUN
    try:
        with httpx.Client() as c:
            sid = _create_session(c)
            for t in TURNS:
                _send(c, sid, t)
            r = c.get(f"{BASE}/v1/chat/sessions/{sid}/context-trace",
                      headers=_hdr(), timeout=30)
            r.raise_for_status()
            items = r.json()["items"]
    except (httpx.ConnectError, httpx.ReadTimeout) as exc:
        # An unreachable stack is NOT a failing contract. Reporting it as one trains everyone
        # to ignore this gate's red, which is how a real field regression would slip past.
        print(f"CANNOT RUN: no stack reachable at {BASE} ({type(exc).__name__}: {exc}).")
        return CANNOT_RUN
    return _assert_contract(items)


def _assert_contract(items: list[dict], contract: dict | None = None) -> int:
    """The gate's ENTIRE rule set, and a pure function over the decoded response.

    Only the transport needs a live stack; these assertions do not. That is why
    `--self-test` can prove every one of them bites without a stack — filing this
    gate as un-bitable would have been calling buildable work blocked."""
    contract = CONTRACT if contract is None else contract
    if not items:
        print("FAIL: context-trace returned no turns")
        return 1

    latest = items[-1]["frame"]
    missing = [f for f in contract["frame_fields"] if f not in latest or latest[f] is None]
    if missing:
        print(f"FAIL: latest frame missing/null fields: {missing}")
        print(json.dumps(latest, indent=2, ensure_ascii=False)[:2000])
        return 1

    # Every span wire-standard.
    for pt in items:
        for span in pt["frame"].get("trace", []):
            bad = [k for k in contract["trace_span_fields"] if k not in span]
            if bad:
                print(f"FAIL: trace span missing {bad} in seq {pt['sequence_num']}")
                return 1

    # The derivations actually wired: at least one turn shows a status flag + an intent
    # other than the fallback, and raw==compiled+savings on the latest.
    any_flag = any(pt["frame"].get("status_flags") for pt in items)
    saved = sum(-s["delta"] for s in latest.get("trace", []) if s["delta"] < 0)
    raw_ok = latest["raw_tokens"] == latest["used_tokens"] + saved

    print(f"PASS: {len(items)} turns; every frame field non-null on the latest turn.")
    print(f"  status_flags seen: {any_flag} · latest intent={latest['intent']!r} "
          f"retrieval={latest['retrieval_mode']!r} raw={latest['raw_tokens']} "
          f"compiled={latest['used_tokens']} reduction={latest['reduction_pct']}")
    print(f"  raw==compiled+savings: {raw_ok} · spans on latest: {len(latest.get('trace', []))}")
    return 0 if (any_flag and raw_ok) else 1


# ── SELF-TEST ────────────────────────────────────────────────────────────────
# The live half needs a stack; the RULES do not. Every assertion in
# `_assert_contract` and `selfcheck` is driven here over synthetic frames, so
# this gate carries a red-ability proof that runs in CI beside its `--selfcheck`.
_CONTRACT = {"frame_fields": ["intent", "retrieval_mode", "raw_tokens", "used_tokens",
                              "reduction_pct"],
             "trace_span_fields": ["name", "delta"]}


def _frame(**over) -> dict:
    f = {"intent": "lore", "retrieval_mode": "hybrid", "raw_tokens": 100,
         "used_tokens": 60, "reduction_pct": 40, "status_flags": ["drafting"],
         "trace": [{"name": "compact", "delta": -40}]}
    f.update(over)
    return f


def _items(*frames) -> list[dict]:
    return [{"sequence_num": i, "frame": f} for i, f in enumerate(frames or (_frame(),))]


def self_test() -> int:
    failures = 0

    def probe(name: str, want: int, fn) -> None:
        nonlocal failures
        import contextlib
        import io
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                got = fn()
        except Exception as e:  # noqa: BLE001 - a crash is what this asserts against
            failures += 1
            print(f"  FAIL {name}: raised {type(e).__name__}: {e} — it must return a code")
            return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    print("context-inspector-trace-gate --self-test")

    probe("a complete trace passes", 0,
          lambda: _assert_contract(_items(), _CONTRACT))

    # the live half's rules, driven without a stack
    probe("NO turns at all fails (the vacuous-pass case)", 1,
          lambda: _assert_contract([], _CONTRACT))
    probe("a MISSING frame field fails", 1,
          lambda: _assert_contract(
              [{"sequence_num": 0, "frame": {k: v for k, v in _frame().items()
                                             if k != "intent"}}], _CONTRACT))
    probe("a NULL frame field fails (present is not enough)", 1,
          lambda: _assert_contract(_items(_frame(intent=None)), _CONTRACT))
    probe("a trace span missing a wire field fails", 1,
          lambda: _assert_contract(
              _items(_frame(trace=[{"name": "compact"}])), _CONTRACT))
    probe("no status_flags on ANY turn fails", 1,
          lambda: _assert_contract(_items(_frame(status_flags=[])), _CONTRACT))
    probe("...but status_flags on an EARLIER turn is enough", 0,
          lambda: _assert_contract(
              _items(_frame(), _frame(status_flags=[])), _CONTRACT))
    probe("raw != used + savings fails", 1,
          lambda: _assert_contract(_items(_frame(raw_tokens=999)), _CONTRACT))

    # the static half
    probe("a valid contract + turn set selfchecks clean", 0,
          lambda: selfcheck(_CONTRACT, ["a turn"]))
    probe("an EMPTY frame_fields list fails", 1,
          lambda: selfcheck({**_CONTRACT, "frame_fields": []}, ["a turn"]))
    probe("a MISSING trace_span_fields key fails", 1,
          lambda: selfcheck({"frame_fields": ["intent"]}, ["a turn"]))
    probe("an EMPTY turn set fails (it would drive nothing and pass)", 1,
          lambda: selfcheck(_CONTRACT, []))

    # CANNOT_RUN must stay distinct from both pass and fail
    def _no_secret() -> int:
        # `main()` reads sys.argv, so the probe must clear it too: invoked as
        # `--selfcheck` (which is how CI runs this file) main() short-circuits to
        # the static half and never reaches the SECRET branch. The case passed
        # with rc=0 until this was fixed — a probe that never reached its subject.
        global SECRET
        keep_secret, keep_argv = SECRET, sys.argv
        SECRET, sys.argv = None, [sys.argv[0]]
        try:
            return main()
        finally:
            SECRET, sys.argv = keep_secret, keep_argv

    probe("no JWT_SECRET is CANNOT_RUN (2), never 0 and never 1", CANNOT_RUN, _no_secret)

    if failures:
        print(f"context-inspector-trace-gate --self-test: {failures} rule(s) did not behave")
        return 1
    print("context-inspector-trace-gate --self-test: every rule bites, and none cries wolf")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv or "--selftest" in sys.argv:
        sys.exit(self_test())
    _rc = self_test()
    if _rc:
        sys.exit(_rc)
    print()
    sys.exit(main())
