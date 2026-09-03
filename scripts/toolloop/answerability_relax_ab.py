#!/usr/bin/env python3
"""DQ-T32, measured: what does relaxing the answerability matcher actually buy, and cost?

    python scripts/toolloop/answerability_relax_ab.py

🔴 WHY A MEASUREMENT AND NOT A PATCH. DQ-T32 asks whether a declared synonym must match as a
CONTIGUOUS phrase. Cycle 1's diagnosis made it the loop's highest-leverage open question — 23 of
25 `P1-SURFACE` tools were never matched on their own measured turn — but the answer is not mine
to take, for two reasons the codebase states itself:

  * `_synonym_pattern`'s word-boundary work exists because "cat" matched inside "category" and
    cost a live run. Relaxing trades precision for recall across all 315 tools.
  * the CONSENT check depends on answerability — a read-only turn sets a standing write grant
    aside — so widening it changes a SAFETY property, not just surfacing.

Nothing here is imported by the service. The STRICT side is always the real `answerable_tools`;
the candidates live in this file.

WHAT IT FOUND, and why the obvious fix is not the fix. DQ-T32's option (b) is "an in-order word
subsequence with a bounded gap". Measured, it reaches 11 of 27 even at gap=5 — LESS THAN HALF —
because the misses are not one failure but three, and only the first is about gaps:

    mode 1  INTERPOSED  12   all the synonym's words are present, in order, split by other words
                             "turn off skill"  vs  "Turn off the GLOSSARY skill for me"
    mode 2  REORDERED    3   all the words are present, in the wrong order
                             "workflow steps"  vs  "the STEPS OF THE ... WORKFLOW"
    mode 3  ABSENT      12   no declared synonym has all its words in the sentence at all
                             "rename region"   vs  "Rename the AREA called The North"

**Mode 3 cannot be fixed by any matcher**, because the word the tool declares was never said. Those
are DECLARATION gaps, and they are mostly mechanical: a missing cross-product cell (the map family
declares {move, relabel, drag, rebind} x {pin, marker} and fills only some), a near-synonym the
platform already uses elsewhere ("area" is declared on the sibling tool), a spelling variant
("favorite" vs "favourite"), or the tool's own noun ("ontology template" on a tool named
`kg_ontology_propose`, which declares "graph template"). A handful are pronoun reference —
"Stop THE TRANSLATION ONE", "Deactivate THE LAST ONE" — which answerability cannot see at all,
because the referent is in the previous turn.

A NOTE ON THE DECOMPOSITION ITSELF: the first version used `str.split()` and mis-classified three
tools, because `_answer_norm` drops stop-words and keeps trailing punctuation ("workflow." is one
token). The classifier now uses the platform's own word-boundary regex, and the mode-1 count moved
10 -> 12 when it did. A tokenizer of my own is a measurement of my own.
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

from app.services.tool_surface import ANSWERABLE_MAX, _answer_norm, answerable_tools  # noqa: E402

CACHE = ROOT / "contracts" / "tool-catalog-cache.json"
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
PROBLEMS = ROOT / "contracts" / "tool-resolution-problems.json"

CHITCHAT = ["hello, how are you today", "thanks, that's great", "tell me a joke", "ok",
            "good morning", "who are you", "can you help me", "that sounds good to me"]
GAPS = (0, 1, 2, 3, 5)


def has(word: str, normed: str) -> bool:
    """The platform's word-boundary semantics, per word — never str.split()."""
    return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", normed) is not None


def positions(word: str, normed: str) -> list[int]:
    return [m.start() for m in
            re.finditer(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", normed)]


def load() -> tuple[list[dict], dict]:
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    defs = [{"type": "function", "function": {
        "name": n, "description": t.get("description") or "",
        "parameters": t.get("inputSchema") or {}, "_meta": t.get("meta") or {}}}
        for n, t in raw.items()]
    if "glossary_propose_translation" not in answerable_tools(
            "Give me vietnamese names for these characters", defs):
        raise SystemExit("ADAPTER BROKEN — positive control failed")
    if answerable_tools("hello, how are you today", defs):
        raise SystemExit("ADAPTER BROKEN — chitchat matched")
    return defs, raw


def _rank(hits: list[tuple[int, str]]) -> set[str]:
    hits.sort(key=lambda h: (-h[0], h[1]))
    return {n for _, n in hits[:ANSWERABLE_MAX]}


def in_order_gap(text: str, defs: list[dict], gap: int) -> set[str]:
    """DQ-T32 option (b): words in order, at most `gap` words between neighbours."""
    normed = _answer_norm(text)
    toks = normed.split()
    hits = []
    for td in defs:
        for syn in (td["function"]["_meta"].get("synonyms") or []):
            sw = _answer_norm(syn).split() if isinstance(syn, str) else []
            if not sw:
                continue
            i, ok = 0, True
            for k, w in enumerate(sw):
                rng = range(i, len(toks)) if k == 0 else range(i, min(len(toks), i + gap + 1))
                j = next((j for j in rng if has(w, toks[j])), -1)
                if j < 0:
                    ok = False
                    break
                i = j + 1
            if ok:
                hits.append((len(_answer_norm(syn)), td["function"]["name"]))
                break
    return _rank(hits)


def order_free(text: str, defs: list[dict]) -> set[str]:
    """The candidate that actually covers modes 1 AND 2: all words present, anywhere."""
    normed = _answer_norm(text)
    hits = []
    for td in defs:
        for syn in (td["function"]["_meta"].get("synonyms") or []):
            sw = _answer_norm(syn).split() if isinstance(syn, str) else []
            if sw and all(has(w, normed) for w in sw):
                hits.append((len(_answer_norm(syn)), td["function"]["name"]))
                break
    return _rank(hits)


def measured_turns() -> list[tuple[str, str, str]]:
    seen, out = set(), []
    for f in sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("scenarios", []):
            t = [x for x in [s.get("prompt")] + list(s.get("follow_ups") or []) if x]
            if t and s.get("tool_under_test") and (s["tool_under_test"], t[-1]) not in seen:
                seen.add((s["tool_under_test"], t[-1]))
                out.append((s["tool_under_test"], s.get("intent") or "?", t[-1]))
    return out


def target_turn(tool: str, ledger: dict, turns: list) -> str | None:
    rows = [x for x in turns if x[0] == tool]
    return rows[-1][2] if rows else None


def classify(tool: str, text: str, raw: dict) -> tuple[str, str]:
    normed = _answer_norm(text)
    syns = [(s, _answer_norm(s).split())
            for s in ((raw.get(tool, {}).get("meta") or {}).get("synonyms") or [])]
    for s, sw in syns:
        if not sw:
            continue
        pos = [positions(w, normed) for w in sw]
        if any(not p for p in pos):
            continue
        i, ordered = -1, True
        for p in pos:
            nxt = next((x for x in p if x > i), None)
            if nxt is None:
                ordered = False
                break
            i = nxt
        return ("1 INTERPOSED" if ordered else "2 REORDERED"), s
    best = min(((sum(1 for w in sw if not has(w, normed)), s, [w for w in sw if not has(w, normed)])
                for s, sw in syns if sw), default=(0, "", []))
    return "3 ABSENT", f"closest '{best[1]}' missing {best[2]}"


def main() -> int:
    defs, raw = load()
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    probs = json.loads(PROBLEMS.read_text(encoding="utf-8"))
    target = set()
    for pid in ("P1-SURFACE", "P8-ANSWERABILITY"):
        target |= set(next(p for p in probs["problems"] if p["id"] == pid)["tools"])
    turns = measured_turns()
    tier = lambda n: str(((raw.get(n) or {}).get("meta") or {}).get("tier") or "R")  # noqa: E731

    print(f"catalogue {len(defs)} tools | {len(turns)} distinct measured turns | "
          f"ANSWERABLE_MAX={ANSWERABLE_MAX} | target {len(target)} tools (P1 + P8)\n")

    for gap in GAPS:
        if has("cat", _answer_norm("what category is this")):
            raise SystemExit("DISQUALIFIED — 'cat' matched inside 'category'")
    print("boundary regression: 'cat' does NOT match inside 'category'  OK\n")

    def cost(fn):
        extra, writes = 0, collections.Counter()
        for tool, intent, text in turns:
            d = fn(text) - answerable_tools(text, defs)
            extra += len(d)
            if intent == "read":
                for n in d:
                    if tier(n) in ("A", "W", "S"):
                        writes[n] += 1
        chit = sum(len(fn(c)) for c in CHITCHAT)
        return extra / max(len(turns), 1), chit, writes

    def recall(fn):
        return sum(1 for t in sorted(target)
                   if (tx := target_turn(t, ledger, turns)) and t in fn(tx))

    print(f"{'candidate':28} {'recall':>10} {'extra/turn':>11} {'chitchat':>9} {'new writes on read':>19}")
    variants = [(f"in-order, gap={g}", (lambda g: lambda tx: in_order_gap(tx, defs, g))(g))
                for g in GAPS]
    variants.append(("ORDER-FREE (all words)", lambda tx: order_free(tx, defs)))
    for label, fn in variants:
        r = recall(fn)
        e, c, w = cost(fn)
        print(f"{label:28} {f'{r}/{len(target)}':>10} {e:>11.2f} {c:>9} {sum(w.values()):>19}")

    _, _, w = cost(lambda tx: order_free(tx, defs))
    print("\nORDER-FREE — write-tier tools newly matched on a READ-intent turn, BY NAME "
          "(one wrong write on a read turn is the whole risk, so it is never an average):")
    for n, k in sorted(w.items(), key=lambda x: -x[1]):
        print(f"  {n}  ({k} turn(s))")
    if not w:
        print("  none")

    print("\nWHY NO MATCHER REACHES THE REST — the three failure modes:")
    modes = collections.Counter()
    detail = collections.defaultdict(list)
    for tool in sorted(target):
        tx = target_turn(tool, ledger, turns)
        if not tx:
            modes["? no scenario"] += 1
            continue
        m, note = classify(tool, tx, raw)
        modes[m] += 1
        detail[m].append((tool, note))
    for m in sorted(modes):
        print(f"  {modes[m]:>3}  mode {m}")
    print("\n  mode 3 is a DECLARATION gap, not a matcher gap — the word was never said:")
    for tool, note in detail["3 ABSENT"]:
        print(f"    {tool:32} {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
