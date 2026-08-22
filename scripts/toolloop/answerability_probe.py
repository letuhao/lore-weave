#!/usr/bin/env python3
"""Does answerability MATCH a tool on the turn it was measured on? Offline, deterministic.

    python scripts/toolloop/answerability_probe.py --problem P1-SURFACE
    python scripts/toolloop/answerability_probe.py --correlation

🔴 WHY THIS EXISTS. `P1-SURFACE` — 25 tools, the resolution loop's largest problem — arrived with
its cause UNKNOWN and three hypotheses already retired by live measurement (ranking, tier/scope/
family, batch composition). Each retirement cost live runs. This asks the same question offline,
against the real `answerable_tools` and the cached catalogue, for the price of a second.

WHAT IT READS, and why every input is the platform's rather than mine:
  * `app.services.tool_surface.answerable_tools` — THE REAL FUNCTION, imported, never reimplemented.
    A reimplementation would measure my copy; the one thing this must not do is agree with itself.
  * `contracts/tool-catalog-cache.json` — the catalogue as the model receives it, 315 tools.
  * the SCENARIO files — for the MEASURED turn, which is the LAST one. The evidence files record
    `run.prompt` as the scenario's FIRST turn on batches written before `scenario_prompt` landed,
    and reading that gave "List my worlds." for three four-turn world-map scenarios. Caught by
    eye, and it would have made every world_map row a lie about what was said.

THE ADAPTER IS CONTROLLED. The cache is MCP-shaped (`meta`) and `answerable_tools` reads OpenAI
shape (`function._meta`), so there is a conversion, and a wrong conversion would report "nothing
matches" for everything — the exact answer the hypothesis wanted. So a positive control (a known
verbatim synonym must match) and a negative control (chitchat must match nothing) run first and
raise before any number is printed.

WHAT IT CANNOT TELL YOU: answerability is the LAST word on the surface, not the only one — the
hot-seed and domain selection put tools on the wire too, and `filter_intent_gated_setup_tools`
removes five tools from the catalogue BEFORE answerability ever runs. So a match is not a promise
the tool was advertised, and a miss is not a proof it was not. What the `--correlation` mode
measures is how strongly the two travel together, and it prints the exceptions by name.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

from app.services.tool_surface import (  # noqa: E402
    ANSWERABLE_MAX, _answer_norm, _synonym_pattern, answerable_tools,
)

CACHE = ROOT / "contracts" / "tool-catalog-cache.json"
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
PROBLEMS = ROOT / "contracts" / "tool-resolution-problems.json"
SURFACED = re.compile(r"[Ss]urfaced (\d+)\s*/\s*(\d+)")


def catalog() -> tuple[list[dict], dict]:
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    defs = [{"type": "function", "function": {
        "name": n, "description": t.get("description") or "",
        "parameters": t.get("inputSchema") or {}, "_meta": t.get("meta") or {}}}
        for n, t in raw.items()]
    # The adapter controls. These raise rather than warn: every figure below is meaningless if
    # the conversion dropped `synonyms`, and "nothing matched" is what a broken adapter says.
    pos = answerable_tools("Give me vietnamese names for these characters", defs)
    if "glossary_propose_translation" not in pos:
        raise SystemExit(f"ADAPTER BROKEN — positive control matched {sorted(pos)}")
    neg = answerable_tools("hello, how are you today", defs)
    if neg:
        raise SystemExit(f"ADAPTER BROKEN — chitchat matched {sorted(neg)}")
    return defs, raw


def scenario_index() -> dict[str, list[tuple[str, dict]]]:
    idx: dict[str, list[tuple[str, dict]]] = {}
    for f in sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("scenarios", []):
            if s.get("tool_under_test"):
                idx.setdefault(s["tool_under_test"], []).append(
                    (f.stem.replace("scenarios-", ""), s))
    return idx


def measured_turn(tool: str, idx: dict, ledger: dict) -> str | None:
    """The LAST turn of the scenario this tool was concluded on. Not the first."""
    cands = idx.get(tool)
    if not cands:
        return None
    ev = (ledger["tools"].get(tool) or {}).get("evidence_file") or ""
    want = pathlib.Path(ev).stem
    s = next((x for n, x in cands if n == want), None) or cands[-1][1]
    turns = [t for t in [s.get("prompt")] + list(s.get("follow_ups") or []) if t]
    return turns[-1] if turns else None


def ranking(text: str, defs: list[dict]) -> list[tuple[int, str]]:
    """The ranking `answerable_tools` computes internally, so a tool cut by ANSWERABLE_MAX can be
    told apart from one that never matched. Membership always comes from the real function; this
    only EXPLAINS a membership answer, and is never the source of one."""
    lp = _answer_norm(text)
    hits: list[tuple[int, str]] = []
    for td in defs:
        for syn in (td["function"]["_meta"].get("synonyms") or []):
            ns = _answer_norm(syn) if isinstance(syn, str) else ""
            if not ns:
                continue
            pat = _synonym_pattern(ns)
            if pat.search(lp) if pat is not None else ns in lp:
                hits.append((len(ns), td["function"]["name"]))
                break
    hits.sort(key=lambda h: (-h[0], h[1]))
    return hits


def cmd_problem(a) -> int:
    defs, raw = catalog()
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    idx = scenario_index()
    probs = json.loads(PROBLEMS.read_text(encoding="utf-8"))
    p = next((x for x in probs["problems"] if x["id"] == a.problem), None)
    if p is None:
        raise SystemExit(f"no such problem: {a.problem}")
    print(f"{p['id']} — {len(p['tools'])} tool(s). ANSWERABLE_MAX={ANSWERABLE_MAX}\n")
    counts = {"A": 0, "B": 0, "C": 0, "?": 0}
    detail = []
    for tool in p["tools"]:
        text = measured_turn(tool, idx, ledger)
        if not text:
            counts["?"] += 1
            print(f"  {tool:32} ?  no scenario on disk")
            continue
        chosen = answerable_tools(text, defs)
        hits = ranking(text, defs)
        rank = next((i + 1 for i, (_, n) in enumerate(hits) if n == tool), None)
        if tool in chosen:
            v, k = "C  answerability said YES — look downstream", "C"
        elif rank:
            v, k = f"B  matched, CUT by the ceiling (rank {rank} of {len(hits)})", "B"
        else:
            v, k = "A  never matched", "A"
        counts[k] += 1
        detail.append((k, tool, text, (raw.get(tool, {}).get("meta") or {}).get("synonyms") or []))
        print(f"  {tool:32} {v}")
    print()
    for k in "ABC?":
        if counts[k]:
            print(f"  {counts[k]:>3}  outcome {k}")
    if a.verbose:
        for k, tool, text, syns in detail:
            if k == "A":
                print(f"\n{tool}\n  said:     {text}\n  declares: {syns}")
    return 0


def cmd_correlation(a) -> int:
    """Both directions, because one direction is not evidence.

    If tools that DID surface also fail answerability, then answerability is not what advertises
    them and the whole diagnosis is wrong. That is the control this mode exists to run."""
    defs, _ = catalog()
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    idx = scenario_index()
    full, none_ = [], []
    for tool, v in ledger["tools"].items():
        if v.get("counts_toward_release") is False:
            continue
        m = SURFACED.search(f"{v.get('note') or ''} {v.get('blocked_reason') or ''}")
        text = measured_turn(tool, idx, ledger) if m else None
        if not m or not text:
            continue
        got, n = int(m.group(1)), int(m.group(2))
        matched = tool in answerable_tools(text, defs)
        if n and got == n:
            full.append((tool, matched))
        elif got == 0:
            none_.append((tool, matched))

    def rate(rows):
        return f"{sum(1 for _, mm in rows if mm)}/{len(rows)}" if rows else "0/0"

    print(f"surfaced N/N  -> answerability matched {rate(full)}")
    print(f"surfaced 0/N  -> answerability matched {rate(none_)}")
    print("\nSURFACED but NOT matched — another path put these on the wire:")
    for t, mm in full:
        if not mm:
            print(f"  {t}")
    print("\nMATCHED but NOT surfaced — something downstream dropped these:")
    for t, mm in none_:
        if mm:
            print(f"  {t}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(required=False)
    ap.add_argument("--problem", help="a problem id from tool-resolution-problems.json")
    ap.add_argument("--verbose", action="store_true", help="show declarations for the misses")
    ap.add_argument("--correlation", action="store_true", help="both directions, with exceptions")
    a = ap.parse_args()
    if a.correlation:
        return cmd_correlation(a)
    if a.problem:
        return cmd_problem(a)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
