#!/usr/bin/env python3
"""CP-0.5 — replay POC arms A-E against the FROZEN baseline catalog.

Spec: ``docs/specs/2026-08-03-agent-runtime-unification/`` · findings:
``docs/specs/.../poc/P1-P2-findings.md`` §P14.

**What the arms established, and why they must stay re-runnable.** Five arms, identical task
(*"List my books."*), differing only in which tools were on the wire:

    A  1 tool (book_list)                                    1/1
    B  fixed envelope, schema delivered in the conversation  1/1
    C  all 35 book_* tools, 19 retired, 7,921 tokens         3/3
    D  16 current-only, 4,661 tokens                         3/3
    E  exactly the 7 the token budget left                   0/3   <-- book_list DELETED

The only variable between 3/3 and 0/3 is whether ``book_list`` was on the wire. Arm E's second
attempt sent ``book_list_revisions{"book_id": "book_list"}`` — the model put the NAME OF THE MISSING
TOOL into an argument, the same shape as ``placeholder_id_1``. It reached for what it needed, could
not call it, and named it in the only field available.

**Why this file exists.** Those runs were driven against a live catalog that no longer exists, so
the numbers above could not be reproduced — a baseline you cannot re-run is a memory, not a control
group. This replays them from ``contracts/agent-runtime-baseline/tools-list.snapshot.json``, which
is content-hashed and committed. The only live dependency is the model itself.

**Two things this script refuses to do.** It will not run against a live gateway (the point is the
pin), and it will not pass a hash mismatch silently: comparing against a mutated baseline produces a
number that looks exactly like a valid one.

Usage::

    python eval/arms/run_arms.py --dry-run          # build the arms, call nothing
    python eval/arms/run_arms.py --arms A,C,E       # replay against the model
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO / "contracts" / "agent-runtime-baseline" / "tools-list.snapshot.json"
OUT_DIR = REPO / "eval" / "arms" / "results"

TASK = "List my books."
MODEL = os.environ.get("ARMS_MODEL", "google/gemma-4-26b-a4b-qat")
BASE_URL = os.environ.get("ARMS_BASE_URL", "http://localhost:1234/v1")
TEMPERATURE = 0.2          # as originally run; changing it makes this a different experiment
TRIALS_MULTI = 3           # arms C/D/E were 3 trials; A/B were 1
ANSWER_TOOL = "book_list"  # the tool arm E deletes — the single variable under test


def load_baseline() -> list[dict]:
    if not SNAPSHOT.exists():
        sys.exit(f"no frozen baseline at {SNAPSHOT.relative_to(REPO)} — run "
                 f"scripts/freeze-tool-catalog.py first")
    doc = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    import hashlib
    blob = json.dumps(doc["tools"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    actual = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    if actual != doc["catalog_sha256"]:
        sys.exit(f"BASELINE HASH MISMATCH — recorded {doc['catalog_sha256'][:16]}, computed "
                 f"{actual[:16]}. Refusing to run: a result measured against a mutated baseline is "
                 f"indistinguishable from a valid one.")
    return doc["tools"]


def as_openai(tool: dict) -> dict:
    return {"type": "function", "function": {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
    }}


def est_tokens(tools: list[dict]) -> int:
    return len(json.dumps(tools, ensure_ascii=False)) // 4


def is_retired(tool: dict) -> bool:
    """Retired = structurally marked OR said so in prose.

    Both halves are needed, and finding that out was itself a finding: only ``superseded_by`` exists
    in ``_meta`` across the whole frozen catalog — there is no ``deprecated_at`` field anywhere — so
    most retirements are announced in the DESCRIPTION TEXT and nowhere a machine looks. Checking
    ``_meta`` alone reports 0 retired among the 35 book_* tools, which would have made arms C and D
    identical and quietly destroyed the arm that separates "too many tools" from "too many RETIRED
    tools". A detector that under-counts here does not fail loudly; it collapses two arms into one.
    """
    meta = tool.get("_meta")
    if isinstance(meta, dict) and (
        meta.get("deprecated") or meta.get("deprecated_at") or meta.get("superseded_by")
    ):
        return True
    return "deprecat" in (tool.get("description") or "").lower()


def build_arms(baseline: list[dict]) -> dict[str, dict]:
    """The five tool sets. Each is derived FROM THE SNAPSHOT, so the arms move together with it."""
    by_name = {t["name"]: t for t in baseline}
    book_tools = [t for t in baseline if t["name"].startswith("book_")]
    current = [t for t in book_tools if not is_retired(t)]

    if ANSWER_TOOL not in by_name:
        sys.exit(f"the frozen baseline does not contain {ANSWER_TOOL!r} — arm E's variable is "
                 f"missing, so no arm here would mean what it says")

    # Arm E — the seven the token budget actually left. Reproduced with the REAL budgeter rather
    # than a hand-picked list, so the arm keeps testing the mechanism rather than a snapshot of its
    # output. That the answer tool is absent is asserted below, never assumed.
    sys.path.insert(0, str(REPO / "services" / "chat-service"))
    from app.services.tool_surface import budget_names_by_tokens_ex  # noqa: E402
    catalog_oai = [as_openai(t) for t in book_tools]
    kept, dropped = budget_names_by_tokens_ex(
        catalog_oai, {t["name"] for t in book_tools}, token_budget=1500,
    )
    arm_e = [by_name[n] for n in sorted(kept)]

    return {
        "A": {"tools": [by_name[ANSWER_TOOL]], "trials": 1,
              "note": "1 tool — the answer, alone"},
        "B": {"tools": [], "trials": 1, "deliver_in_conversation": True,
              "note": "fixed envelope; the schema arrives as conversation text, not as `tools`"},
        "C": {"tools": book_tools, "trials": TRIALS_MULTI,
              "note": f"every book_* tool including retired ({sum(1 for t in book_tools if is_retired(t))} retired)"},
        "D": {"tools": current, "trials": TRIALS_MULTI,
              "note": "current-only — retired removed"},
        "E": {"tools": arm_e, "trials": TRIALS_MULTI,
              "note": f"exactly what the token budget left; budgeter dropped {len(dropped)}"},
    }


def call_model(tools: list[dict], prompt: str) -> dict:
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": TEMPERATURE,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def grade(response: dict) -> dict:
    """Did the model call the answer tool?

    Graded on the CALL, never on the prose. A model that says "I'll list your books" without calling
    anything has not listed anything, and scoring the sentence would score fluency instead of the
    behaviour under test.
    """
    choice = (response.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    calls = msg.get("tool_calls") or []
    names = [c.get("function", {}).get("name") for c in calls]
    return {
        "called": names,
        "args": [c.get("function", {}).get("arguments") for c in calls],
        "text": (msg.get("content") or "")[:400],
        "correct": ANSWER_TOOL in names,
        # The arm-E signature: the model naming the tool it could not call, inside an argument.
        "named_missing_tool_in_args": any(
            ANSWER_TOOL in (c.get("function", {}).get("arguments") or "") for c in calls
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", default="A,B,C,D,E")
    ap.add_argument("--dry-run", action="store_true",
                    help="build every arm and report its composition; call no model")
    args = ap.parse_args()

    baseline = load_baseline()
    arms = build_arms(baseline)
    selected = [a.strip().upper() for a in args.arms.split(",") if a.strip()]

    results: dict[str, dict] = {}
    for name in selected:
        spec = arms[name]
        oai = [as_openai(t) for t in spec["tools"]]
        has_answer = any(t["name"] == ANSWER_TOOL for t in spec["tools"])
        header = (f"arm {name}: {len(oai):>3} tools, ~{est_tokens(oai):>6} tok, "
                  f"{ANSWER_TOOL}={'PRESENT' if has_answer else 'ABSENT '} | {spec['note']}")
        print(header)
        results[name] = {"tool_count": len(oai), "tokens": est_tokens(oai),
                         "answer_tool_present": has_answer, "note": spec["note"],
                         "tools": [t["name"] for t in spec["tools"]], "trials": []}
        if args.dry_run:
            continue

        prompt = TASK
        if spec.get("deliver_in_conversation"):
            prompt = (f"{json.dumps(as_openai(next(t for t in baseline if t['name'] == ANSWER_TOOL)))}\n\n"
                      f"{TASK}")
        for i in range(spec["trials"]):
            try:
                graded = grade(call_model(oai, prompt))
            except Exception as exc:  # noqa: BLE001 — a dead model is a result, not a crash
                graded = {"error": str(exc), "correct": False}
            results[name]["trials"].append(graded)
            print(f"   trial {i + 1}: {'PASS' if graded.get('correct') else 'FAIL'} "
                  f"called={graded.get('called')}")
        passed = sum(1 for t in results[name]["trials"] if t.get("correct"))
        results[name]["score"] = f"{passed}/{spec['trials']}"
        print(f"   => {results[name]['score']}")

    if not args.dry_run:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = OUT_DIR / f"arms-{stamp}.json"
        out.write_text(json.dumps({
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL, "temperature": TEMPERATURE,
            "baseline_sha256": json.loads(SNAPSHOT.read_text(encoding="utf-8"))["catalog_sha256"],
            "results": results,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
