#!/usr/bin/env python3
"""Repair `chapter_entity_links.chapter_index` to mean the chapter's position IN THE BOOK.

**The defect.** The extraction worker wrote `chapter_index` as the `enumerate()` index over
the job's chapter list — job-relative. glossary-service's `known-entities` endpoint
documents and windows the same column as a position in the BOOK
(`before_chapter_index` — "only count links strictly before this chapter"). Producer and
consumer disagreed about what the number meant.

Measured on 封神演義 before the fix: index `0` named **six different chapters**, `1`–`14`
named three each, and 87 distinct chapters carried links whose index never exceeded 56 —
because the book had been extracted across several jobs (the original 57-chapter run, then
two 15-chapter A/B jobs). Everything keyed on chapter order — known-entity windowing,
spoiler windows, timeline cutoffs — was reading a number that did not mean what it said.

**Why this is fully recoverable.** The link row stores `chapter_id`, which is
unambiguous. The true index is `chapters.sort_order` for that id. Nothing was lost; only
the derived number was wrong.

The two tables live in different databases (`loreweave_glossary` and `loreweave_book`), so
the mapping is read from one and applied to the other rather than joined.

    python scripts/backfill-chapter-link-index.py --book <uuid>          # report only
    python scripts/backfill-chapter-link-index.py --book <uuid> --apply  # write
"""
from __future__ import annotations

import argparse
import subprocess


def psql(db: str, query: str, quiet: bool = False) -> list[list[str]]:
    names = subprocess.run(["docker", "ps", "--filter", "name=postgres", "--format",
                            "{{.Names}}"], capture_output=True, text=True).stdout.split()
    if not names:
        raise SystemExit("no running postgres container found")
    out = subprocess.run(["docker", "exec", "-i", names[0], "psql", "-U", "loreweave",
                          "-d", db, "-At", "-F", "\t", "-c", query],
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        raise SystemExit(out.stderr[:800])
    return [] if quiet else [ln.split("\t") for ln in out.stdout.splitlines() if ln.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    truth = {cid: int(so) for cid, so in psql("loreweave_book", f"""
        SELECT id::text, sort_order FROM chapters
        WHERE book_id = '{a.book}' AND trashed_at IS NULL
    """)}
    print(f"chapters in book: {len(truth)}")

    current = psql("loreweave_glossary", f"""
        SELECT cl.chapter_id::text, cl.chapter_index::text, count(*)::text
        FROM chapter_entity_links cl
        JOIN glossary_entities g ON g.entity_id = cl.entity_id
        WHERE g.book_id = '{a.book}'
        GROUP BY 1, 2
    """)
    wrong = [(cid, idx, n) for cid, idx, n in current
             if cid in truth and int(idx or -1) != truth[cid]]
    unknown = [(cid, idx, n) for cid, idx, n in current if cid not in truth]
    links = sum(int(n) for _c, _i, n in current)
    bad = sum(int(n) for _c, _i, n in wrong)

    # The symptom that made this visible: one index naming several chapters.
    collisions = psql("loreweave_glossary", f"""
        SELECT count(*)::text FROM (
          SELECT cl.chapter_index FROM chapter_entity_links cl
          JOIN glossary_entities g ON g.entity_id = cl.entity_id
          WHERE g.book_id = '{a.book}'
          GROUP BY 1 HAVING count(DISTINCT cl.chapter_id) > 1) x
    """)
    print(f"link rows: {links}   with a WRONG index: {bad}   "
          f"({len(wrong)} of {len(current)} distinct chapters)")
    print(f"indices naming more than one chapter: {collisions[0][0]}")
    if unknown:
        print(f"⚠ {len(unknown)} chapter_id(s) not found in the book — left untouched")
    for cid, idx, n in wrong[:6]:
        print(f"   {cid}  index {idx} -> {truth[cid]}   ({n} link rows)")

    if not wrong:
        print("nothing to repair")
        return
    if not a.apply:
        print("\ndry run — pass --apply to write")
        return

    cases = " ".join(f"WHEN '{cid}'::uuid THEN {truth[cid]}" for cid, _i, _n in wrong)
    ids = ",".join(f"'{cid}'::uuid" for cid, _i, _n in wrong)
    psql("loreweave_glossary", f"""
        UPDATE chapter_entity_links cl
        SET chapter_index = CASE cl.chapter_id {cases} END
        FROM glossary_entities g
        WHERE g.entity_id = cl.entity_id AND g.book_id = '{a.book}'
          AND cl.chapter_id IN ({ids})
    """, quiet=True)

    after = psql("loreweave_glossary", f"""
        SELECT count(*)::text FROM (
          SELECT cl.chapter_index FROM chapter_entity_links cl
          JOIN glossary_entities g ON g.entity_id = cl.entity_id
          WHERE g.book_id = '{a.book}'
          GROUP BY 1 HAVING count(DISTINCT cl.chapter_id) > 1) x
    """)
    print(f"\napplied — indices naming more than one chapter: {after[0][0]} (was "
          f"{collisions[0][0]})")


if __name__ == "__main__":
    main()
