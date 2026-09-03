#!/usr/bin/env python3
"""CP-0.6 — measure the PLAN BINDING FORMAT on our own model.

Spec: ``ARCHITECTURE.md`` §0.11 (*the plan lives outside the context; the projection never
compresses an identifier*) and §0.12 (*a measurement on data that has never been in production is
not trustworthy*).

**The question.** CP-3 hands the model a projection of a plan in which step 2 must consume an
identifier that step 1 produced. Which written form makes the model reliably use the value it was
given instead of inventing one? This is the 61.8% carry-forward class in miniature: 2,477 of 4,010
failures are on a declaration that ALREADY SUCCEEDED in the same session, and the sharpest specimen
is a tool that failed 101 of 101 times because the model kept sending ``placeholder_id_1``.

**Why this is measured here rather than cited.** The published progressive-disclosure benchmark that
would otherwise settle the question reports its gains as *"absent on Chinese"*, and this product's
own content is Vietnamese and CJK-heavy. Importing that result would be importing a number measured
on a population we are not. §0.12's rule, in one line: **a measurement over data that has never been
in production is not trustworthy** — so this runs on the model that actually serves turns, and its
output is a bound on THAT model, not a general finding.

**What is deliberately NOT concluded from this.** A format winning here does not admit it. Test
evidence may reject a format; the behavioural bound comes from production traffic. And the control
matters more than the winner: an arm whose answer is available WITHOUT reading the binding is
theatre — it would score high for a model that ignored the plan entirely. Hence the decoy arm.

Usage::

    python eval/arms/binding_format.py --trials 5
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "eval" / "arms" / "results"

MODEL = os.environ.get("ARMS_MODEL", "gemma-4-26b-a4b-it-uncensored-apex-quality")
BASE_URL = os.environ.get("ARMS_BASE_URL", "http://localhost:1234/v1")
TEMPERATURE = 0.2
CALL_TIMEOUT_S = int(os.environ.get("ARMS_TIMEOUT_S", "900"))

# The identifier the model must carry from step 1 to step 2. Deliberately a real-shaped UUID: the
# production failures are UUID-shaped, and a short friendly token would be easier to copy than the
# thing we actually need copied.
CHAPTER_ID = "0198f3c1-77aa-7b41-9c2e-5d3ab0f41e62"
DECOY_ID = "0198f3c1-77aa-7b41-9c2e-000000000000"

TOOLS = [{
    "type": "function",
    "function": {
        "name": "book_chapter_save_draft",
        "description": "Save draft prose into an existing chapter.",
        "parameters": {
            "type": "object",
            "properties": {
                "chapter_id": {"type": "string", "description": "The chapter to write into."},
                "content": {"type": "string"},
            },
            "required": ["chapter_id", "content"],
        },
    },
}]

TASK = "Now do step 2: save the draft prose 'The tide came in at dusk.' into the chapter."


def arm_prose(cid: str) -> str:
    """How the value reaches the model TODAY — buried in conversational narration."""
    return (
        "Earlier in this session you created a chapter titled 'The Tidewright'. The create call "
        f"came back and reported that the new chapter was registered under id {cid}, and that it "
        "is currently empty and ready for prose."
    )


def arm_labelled(cid: str) -> str:
    return f"PLAN STATE\n  step 1 (done) book_chapter_create\n  chapter_id: {cid}\n"


def arm_binding(cid: str) -> str:
    """The §0.11 shape — the binding named as a binding, with its producer."""
    return (
        "PLAN — bindings produced so far (use these values verbatim; do not invent):\n"
        f"  chapter_id = {cid}          <- emitted by step 1 (book_chapter_create)\n"
        "\nstep 2 book_chapter_save_draft  accepts: chapter_id <- step1.chapter_id, content\n"
    )


def arm_json(cid: str) -> str:
    return ("PLAN\n" + json.dumps({
        "steps": [
            {"n": 1, "tool": "book_chapter_create", "status": "done",
             "emits": {"chapter_id": cid}},
            {"n": 2, "tool": "book_chapter_save_draft", "status": "current",
             "accepts": {"chapter_id": "<- step1.emits.chapter_id", "content": "<prose>"}},
        ]
    }, indent=2))


def arm_decoy(cid: str) -> str:
    """CONTROL — two ids present, only one correct.

    Without this the whole measurement is theatre. An arm containing exactly one UUID scores a model
    that blindly copies the only id in sight identically to one that actually read the binding. Here
    the wrong id is the more recently mentioned, so copying the nearest token FAILS.
    """
    return (
        "PLAN — bindings produced so far (use these values verbatim; do not invent):\n"
        f"  chapter_id = {cid}          <- emitted by step 1 (book_chapter_create)\n"
        f"  cover_asset_id = {DECOY_ID}  <- emitted by step 1b (book_cover_upload)\n"
        "\nstep 2 book_chapter_save_draft  accepts: chapter_id <- step1.chapter_id, content\n"
    )


ARMS = {
    "prose": arm_prose,
    "labelled": arm_labelled,
    "binding": arm_binding,
    "json": arm_json,
    "decoy_control": arm_decoy,
}


def call(system: str) -> dict:
    body = {
        "model": MODEL, "temperature": TEMPERATURE,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": TASK}],
        "tools": TOOLS, "tool_choice": "auto",
        # Bounded because this model emits reasoning tokens before the call, and an unbounded
        # generation makes the sweep take hours. Generous enough that truncation before the tool
        # call would be visible as `no_call` rather than being mistaken for a refusal to act.
        "max_tokens": 600,
    }
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=CALL_TIMEOUT_S) as resp:
        return json.loads(resp.read())


def grade(resp: dict) -> dict:
    """Graded in CODE, on the argument actually sent.

    Never by asking a model whether the answer looks right, and never on prose. A check whose seed
    and control agree is theatre; the comparison belongs in code where it cannot be talked into
    agreeing.
    """
    msg = ((resp.get("choices") or [{}])[0]).get("message") or {}
    calls = msg.get("tool_calls") or []
    sent = None
    for c in calls:
        try:
            sent = json.loads(c.get("function", {}).get("arguments") or "{}").get("chapter_id")
        except (TypeError, ValueError):
            sent = c.get("function", {}).get("arguments")
        if sent:
            break
    text = (msg.get("content") or "")
    return {
        "called": [c.get("function", {}).get("name") for c in calls],
        "chapter_id_sent": sent,
        "exact": sent == CHAPTER_ID,
        "sent_decoy": sent == DECOY_ID,
        # The production signature: a value that is neither the real id nor absent, but invented —
        # `placeholder_id_1`, `current_book_id_placeholder`, the name of a missing tool.
        "invented": bool(sent) and sent not in (CHAPTER_ID, DECOY_ID)
        and not re.fullmatch(r"[0-9a-f-]{36}", str(sent) or ""),
        "no_call": not calls,
        "text": text[:200],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--arms", default=",".join(ARMS))
    args = ap.parse_args()

    selected = [a.strip() for a in args.arms.split(",") if a.strip()]
    results: dict[str, dict] = {}
    for name in selected:
        build = ARMS[name]
        trials = [grade(call(build(CHAPTER_ID))) for _ in range(args.trials)]
        exact = sum(1 for t in trials if t["exact"])
        results[name] = {
            "exact": exact, "n": args.trials,
            "invented": sum(1 for t in trials if t["invented"]),
            "sent_decoy": sum(1 for t in trials if t["sent_decoy"]),
            "no_call": sum(1 for t in trials if t["no_call"]),
            "trials": trials,
        }
        print(f"{name:>14}: {exact}/{args.trials} exact  "
              f"invented={results[name]['invented']} decoy={results[name]['sent_decoy']} "
              f"no_call={results[name]['no_call']}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = OUT_DIR / f"binding-format-{stamp}.json"
    out.write_text(json.dumps({
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL, "temperature": TEMPERATURE, "trials": args.trials,
        "chapter_id": CHAPTER_ID, "results": results,
        "_bound": (
            f"n={args.trials} per arm. A perfect arm bounds its failure rate at "
            f"<= 1-0.05**(1/{args.trials}) — state that bound, never a better one. This measurement "
            f"may REJECT a format; it cannot admit one."
        ),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
