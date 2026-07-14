"""M2 batch runner — run the authorable discoverability scenarios to ground truth, x3 each.

The all-green bar (spec 2026-07-13-all-tracks-clear §1) is: every scenario passes >=2/3 consecutive
runs, scored by DB GROUND TRUTH — never the model's own words, never the harness's summary line.

This runner loops each scenario, builds a FRESH fixture per run (so runs are independent — one run's
writes cannot flatter the next), invokes the real harness inside chat-service, then reads the effect
straight from Postgres. It prints a JSON scoreboard.

Token-discipline note: this is ONE process doing all of M2, not N agent calls. The scenarios run on
local gemma ($0); the only cost here is launching + reading ground truth.

    python -m scripts.eval.run_m2_batch S00c S00d S07        # a subset
    python -m scripts.eval.run_m2_batch all                  # everything

Judge-only scenarios (S00a/S08/S09) record the transcript path for a human/agent read — their crux is
in the assistant's words, not a DB row, so this runner marks them JUDGE and does not auto-pass them.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid

from .tool_liveness import config, oracle
from . import discoverability_fixtures as fx

CHAT = "infra-chat-service-1"
PG = config.PG_CONTAINER
USER = config.USER_ID
GEMMA = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"

DBK = {"book": "loreweave_book", "glossary": "loreweave_glossary",
       "composition": "loreweave_composition", "knowledge": "loreweave_knowledge"}


def _sql(db: str, q: str) -> str:
    out = subprocess.run(
        ["docker", "exec", PG, "psql", "-U", config.PG_USER, "-d", db, "-tA", "-c", q],
        capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"sql failed ({db}): {out.stderr.strip()[:200]}")
    return out.stdout.strip()


def _fresh_book(title: str, lang: str = "en") -> str:
    _sql(DBK["book"],
         f"INSERT INTO books (owner_user_id,title,original_language,kind,lifecycle_state) "
         f"VALUES ('{USER}','{title}','{lang}','novel','active')")
    return _sql(DBK["book"], f"SELECT id FROM books WHERE title='{title}' ORDER BY created_at DESC LIMIT 1")


def _book_with_ontology(title: str) -> str:
    b = _fresh_book(title)
    fx._adopt(b, ["character", "location", "item"])
    return b


def _run_harness(scenario_id: str, book_id: str, label: str) -> dict:
    """docker exec the harness for ONE scenario; return its metrics dict (+ transcript path)."""
    out_dir = f"/tmp/m2/{label}"
    env = [
        "-e", f"QG_RUN_LABEL={label}", "-e", f"QG_MODEL_REF={GEMMA}",
        "-e", f"SKILL_BOOK_ID={book_id}", "-e", f"QG_SCENARIOS=/tmp/scen/{scenario_id}.json",
        "-e", f"QG_OUT={out_dir}", "-e", "QG_KEEP_SESSIONS=1", "-e", "QG_REPORT_DATE=2026-07-14",
        "-e", "QG_AUTO_APPROVE=1",
    ]
    subprocess.run(["docker", "exec", *env, CHAT, "python", "/tmp/ds.py"],
                   capture_output=True, text=True, timeout=1800)
    raw = subprocess.run(
        ["docker", "exec", CHAT, "cat", f"{out_dir}/{label}/{scenario_id}-metrics.json"],
        capture_output=True, text=True, timeout=30)
    metrics = json.loads(raw.stdout) if raw.stdout.strip() else {}
    metrics["_transcript"] = f"{CHAT}:{out_dir}/{label}/{scenario_id}-transcript.jsonl"
    return metrics


# ── per-scenario: (fixture builder -> book_id) and (book_id -> ground-truth pass?) ──────────
def _gt_kinds(b: str) -> tuple[bool, str]:
    n = int(_sql(DBK["glossary"], f"SELECT count(*) FROM book_kinds WHERE book_id='{b}'"))
    return n > 0, f"book_kinds={n}"


def _gt_entities(b: str) -> tuple[bool, str]:
    n = int(_sql(DBK["glossary"], f"SELECT count(*) FROM glossary_entities WHERE book_id='{b}'"))
    return n > 0, f"glossary_entities={n}"


def _gt_plan(b: str) -> tuple[bool, str]:
    n = int(_sql(DBK["composition"], f"SELECT count(*) FROM plan_run WHERE book_id='{b}'"))
    return n > 0, f"plan_run={n}"


def _gt_prose(b: str) -> tuple[bool, str]:
    n = int(_sql(DBK["book"],
                 f"SELECT count(DISTINCT c.id) FROM chapters c JOIN chapter_blocks bl ON bl.chapter_id=c.id "
                 f"WHERE c.book_id='{b}' AND bl.text_content ~ '[^[:space:]]'"))
    return n > 0, f"chapters_with_prose={n}"


def _gt_authoring(b: str) -> tuple[bool, str]:
    n = int(_sql(DBK["composition"], f"SELECT count(*) FROM authoring_runs WHERE book_id='{b}'"))
    return n > 0, f"authoring_runs={n}"


def _gt_conformance(b: str) -> tuple[bool, str]:
    # canon-check: a conformance run was created for this book (arc_conformance_state carries book_id)
    n = int(_sql(DBK["composition"],
                 f"SELECT count(*) FROM arc_conformance_state WHERE book_id='{b}'"))
    return n > 0, f"conformance_state={n}"


# ── S03 entity-triage: a book with a DRAFT PILE the agent must drain (keep/junk/merge) ──────
def _s03_book(lbl: str) -> str:
    """A book with adopted kinds + a pile of DRAFT entities (an ai-suggested inbox to triage).
    Unlike the S04 fixture, these are LEFT as drafts — the pile is the point."""
    b = _book_with_ontology(f"M2-S03-{lbl}")
    fx._propose(fx._mcp(), b, [
        {"kind": "character", "name": f"Draft Char {i}"} for i in range(4)
    ] + [{"kind": "location", "name": "Draft Place"}])
    return b


def _gt_triaged(b: str) -> tuple[bool, str]:
    # The pile drained iff at least one draft got a triage decision (→ active, or rejected/removed).
    total = int(_sql(DBK["glossary"], f"SELECT count(*) FROM glossary_entities WHERE book_id='{b}'"))
    drafts_alive = int(_sql(DBK["glossary"],
                            f"SELECT count(*) FROM glossary_entities WHERE book_id='{b}' AND status='draft' AND alive=true"))
    triaged = total - drafts_alive
    return triaged > 0, f"triaged={triaged} (total={total}, drafts_left={drafts_alive})"


# scenario -> (fixture_fn(run_label)->book, ground_truth_fn(book)->(ok,detail), judge?)
SCEN = {
    "S00c": (lambda lbl: _fresh_book(f"M2-S00c-{lbl}"), _gt_kinds, False),
    "S00d": (lambda lbl: _fresh_book(f"M2-S00d-{lbl}"), _gt_kinds, False),
    "S00b": (lambda lbl: _book_with_ontology(f"M2-S00b-{lbl}"), _gt_entities, False),
    # S01/S02/S03 passed in a PRIOR run but the goal needs a >=2/3 re-prove in THIS run's transcript.
    "S01":  (lambda lbl: _fresh_book(f"M2-S01-{lbl}"), _gt_kinds, False),        # glossary-bootstrap
    "S02":  (lambda lbl: _book_with_ontology(f"M2-S02-{lbl}"), _gt_entities, False),  # populate-glossary
    "S03":  (_s03_book, _gt_triaged, False),                                     # entity-triage (drain a pile)
    "S07":  (lambda lbl: _fresh_book(f"M2-S07-{lbl}"), _gt_plan, False),
    "S06b": (lambda lbl: fx.build_plan(lbl)["book_id"], _gt_prose, False),
    # S12's GOAL is "chapters get drafted", not "the authoring-run FSM was used". Score the OUTCOME
    # (prose landed), not the mechanism — the agent legitimately drafts directly (proven 2026-07-14:
    # authoring_runs=0 but chapters_with_prose=1). Measuring the FSM falsely RED'd a working scenario.
    "S12":  (lambda lbl: fx.build_plan(lbl)["book_id"], _gt_prose, False),
    # S09 canon-check: composition_conformance_run is ASYNC and can take many minutes — it outlives a
    # single live turn, so arc_conformance_state may not have landed when the harness returns. Its crux
    # (did the agent FIND the planted green-vs-blue-eyes contradiction, honestly) is in the assistant
    # text ⇒ judge-only.
    "S09":  (lambda lbl: fx.build_s09(lbl)["book_id"], None, True),
    # judge-only (crux is in the assistant text, not a DB row):
    "S00a": (lambda lbl: _fresh_book(f"M2-S00a-{lbl}"), None, True),
    "S08":  (lambda lbl: None, None, True),
}


def run_scenario(sid: str, runs: int = 3) -> dict:
    fixture_fn, gt_fn, judge = SCEN[sid]
    results = []
    for i in range(runs):
        lbl = f"2026-07-14-{sid}-r{i + 1}-{uuid.uuid4().hex[:4]}"
        # ROBUSTNESS: a fixture-build or harness TIMEOUT must fail THIS run, not crash the batch.
        # (2026-07-14: an S09 conformance run timed out at 1200s and killed the whole batch, so
        # S00a/S08 never ran. One slow run is a run-level failure, never a batch-level one.)
        try:
            book = fixture_fn(lbl)
            m = _run_harness(sid, book or "none", lbl)
        except Exception as e:  # noqa: BLE001 — a run failing for ANY reason is just a failed run
            results.append({"run": i + 1, "book": None, "pass": False, "error": str(e)[:200]})
            continue
        row = {
            "run": i + 1, "book": book,
            "effectful": m.get("effectful_tool_calls"),
            "empty_intent_find_tools": m.get("empty_intent_find_tools"),
            "silent_success": m.get("silent_success_calls"),
            "persist_claims": m.get("persist_claims_without_write"),
            "transcript": m.get("_transcript"),
        }
        if gt_fn and book:
            ok, detail = gt_fn(book)
            row["ground_truth"] = detail
            row["pass"] = ok
        else:
            row["pass"] = None  # judge
        results.append(row)
    passes = sum(1 for r in results if r["pass"] is True)
    return {"scenario": sid, "judge": judge, "passes": passes, "of": runs,
            "green": (passes >= 2) if not judge else None, "runs": results}


def main(argv):
    which = argv[1:] if len(argv) > 1 else ["all"]
    if which == ["all"]:
        which = list(SCEN)
    # stage the scenario files + harness once
    subprocess.run(["docker", "exec", CHAT, "mkdir", "-p", "/tmp/scen"], capture_output=True)
    subprocess.run(["docker", "cp", "scripts/eval/run_discoverability_scenario.py",
                    f"{CHAT}:/tmp/ds.py"], capture_output=True)
    import glob
    import os
    for f in glob.glob("scripts/eval/discoverability_scenarios/*.json"):
        sid = os.path.basename(f).split("-")[0]
        subprocess.run(["docker", "cp", f, f"{CHAT}:/tmp/scen/{sid}.json"], capture_output=True)

    board = {}
    for sid in which:
        if sid not in SCEN:
            print(f"skip unknown {sid}", file=sys.stderr)
            continue
        print(f"=== {sid} x3 ===", file=sys.stderr, flush=True)
        board[sid] = run_scenario(sid)
        print(json.dumps(board[sid], indent=1))
        sys.stdout.flush()
    print("\n===== M2 SCOREBOARD =====")
    for sid, r in board.items():
        tag = "JUDGE" if r["judge"] else ("GREEN" if r["green"] else "RED")
        print(f"{sid:5s} {r['passes']}/{r['of']}  {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
