#!/usr/bin/env python3
"""P3-EVAL / E5 — (re)build the raw-search golden set by mining the live oracle.

Anti-cheat: expected sets + graded relevance are DERIVED from the corpus via an
exact-substring oracle (psql over chapter_blocks), never hand-invented. Bands:

  - exact      : a distinctive term present verbatim (incl. WIDE terms — the E5
                 recall-fix target). expected = every containing chapter.
  - phrase     : a longer verbatim phrase.
  - paraphrase : a natural-language question; expected = the one chapter that
                 answers it (semantic-favorable; term may not appear verbatim).
  - typo       : a misspelled term (wrong CJK char); expected = the CORRECT
                 term's chapters (tests trigram fuzzy retrieval).
  - negative   : a term verified ABSENT from all chapters.

graded relevance: origin (title/topic) chapter = 3, other containing = 1.

Run (defaults target the E5 eval book):
  python scripts/build_rawsearch_golden.py [--book-id ...] [--project-id ...]
Writes services/knowledge-service/app/benchmark/rawsearch_golden.json.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_BOOK = "019ea2fc-ffc7-7dc6-8f09-1f8625584b59"
DEFAULT_PROJECT = "019ea2fd-0523-7c3d-ab59-72c0c0a73a3b"
OUT = Path("services/knowledge-service/app/benchmark/rawsearch_golden.json")
PG_CONTAINER = "infra-postgres-1"
_ST = re.compile(r"^(SELECT|INSERT|UPDATE)\b")

# (term, origin_sort) — origin = the chapter whose title/topic IS the term.
EXACT = [
    ("龙象般若", 5), ("天心剑法", 7), ("火蛇枪法", 27), ("时空秘典", 4),
    ("乾坤神木图", 32), ("清玄阁", 12), ("蛮神池", 30), ("铭纹公会", 33),
    ("铁皮蛮牛", 21), ("秦雅", 13), ("空间戒指", 39), ("林泞姗", 6),
    # WIDE terms — appear in many chapters; the E5 recall fix targets exactly
    # these (flat block LIMIT under-covered them). Measured via oracle-recall.
    ("神武印记", 2), ("黄极境", 3), ("拜月魔教", 37), ("青火鹿", 23),
]
PHRASE = [("屠天杀地", 31), ("全城戒严", 36), ("精神力", 34), ("轮脉", 38)]
PARA = [
    ("少年第一次开启神武印记的经过", 2),
    ("三年前到底发生了什么真相", 9),
    ("主角获得与时空有关的秘传典籍", 4),
    ("岁末考核中的比试表现", 18),
    ("铭纹公会是什么样的组织", 33),
]
# (typo_query, correct_term, origin)
TYPO = [("龙象班若", "龙象般若", 5), ("天心箭法", "天心剑法", 7), ("清玄各", "清玄阁", 12)]
NEG = ["封神榜", "量子计算机", "哈利波特", "区块链", "蜘蛛侠"]


def psql(book_db: str, sql: str) -> list[str]:
    cp = subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", "loreweave", "-d", book_db,
         "-tAc", sql], capture_output=True, text=True, encoding="utf-8")
    return [ln.strip() for ln in cp.stdout.strip().splitlines()
            if ln.strip() and not _ST.match(ln.strip())]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-id", default=DEFAULT_BOOK)
    ap.add_argument("--project-id", default=DEFAULT_PROJECT)
    ap.add_argument("--book-db", default="loreweave_book")
    args = ap.parse_args()
    bid = args.book_id

    smap: dict[int, str] = {}
    for ln in psql(args.book_db,
                   f"SELECT c.sort_order, c.id FROM chapters c "
                   f"WHERE c.book_id='{bid}' ORDER BY c.sort_order;"):
        so, cid = ln.split("|")
        smap[int(so)] = cid

    def oracle(term: str) -> list[int]:
        t = term.replace("'", "''")
        rows = psql(args.book_db,
                    "SELECT DISTINCT c.sort_order FROM chapter_blocks cb "
                    "JOIN chapters c ON c.id=cb.chapter_id "
                    f"WHERE c.book_id='{bid}' AND cb.text_content ILIKE '%{t}%' "
                    "ORDER BY c.sort_order;")
        return [int(r) for r in rows]

    queries: list[dict] = []
    skipped: list[str] = []

    def add_term(q: str, origin: int, band: str, oracle_term: str | None = None):
        ids = oracle(oracle_term or q)
        if not ids:
            skipped.append(f"{band}:{q}")
            return
        if origin not in ids and band != "typo":
            skipped.append(f"{band}:{q}(origin {origin} absent)")
            return
        expected = [smap[s] for s in ids]
        graded = {smap[s]: (3 if s == origin else 1) for s in ids}
        queries.append({"q": q, "band": band, "origin": origin,
                        "expected": expected, "graded": graded})

    for q, o in EXACT:
        add_term(q, o, "exact")
    for q, o in PHRASE:
        add_term(q, o, "phrase")
    for q, correct, o in TYPO:
        add_term(q, o, "typo", oracle_term=correct)
    for q, o in PARA:
        queries.append({"q": q, "band": "paraphrase", "origin": o,
                        "expected": [smap[o]], "graded": {smap[o]: 3}})
    for q in NEG:
        if oracle(q):
            skipped.append(f"negative:{q}(NOT absent)")
            continue
        queries.append({"q": q, "band": "negative", "expected": [], "graded": {}})

    bands: dict[str, int] = {}
    for qd in queries:
        bands[qd["band"]] = bands.get(qd["band"], 0) + 1

    doc = {
        "_about": "P3-EVAL/E5 golden set. Expected + graded MINED from the live "
                  "exact-substring oracle (anti-cheat). Rebuild: "
                  "python scripts/build_rawsearch_golden.py. Bands: exact (incl. "
                  "wide terms), phrase, paraphrase, typo (fuzzy), negative.",
        "book_id": bid, "project_id": args.project_id,
        "counts": bands, "total": len(queries),
        # EVAL-CI gate thresholds (run_rawsearch_eval.py --gate); tune as the
        # corpus/model evolve. Reflect the measured baseline with headroom.
        "thresholds": {
            "hybrid_hit@5": 0.90, "hybrid_ndcg@10": 0.70,
            "lexical_oracle_recall": 0.80, "semantic_ann_recall": 0.90,
            "max_negative_leak": 0,
        },
        "queries": queries,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}: {len(queries)} queries {bands}")
    if skipped:
        print("skipped (oracle miss):", skipped, file=sys.stderr)


if __name__ == "__main__":
    main()
