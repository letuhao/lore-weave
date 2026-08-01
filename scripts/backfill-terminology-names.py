#!/usr/bin/env python3
"""Recover the entity names that the extraction writeback silently dropped.

**The defect.** glossary-service's writeback resolved an entity's display attribute with a
hardcoded `attrDefMap[kindID+":name"]`, while every read path uses `code IN ('name','term')`.
`terminology` is the only kind whose display attribute is `term`, so the write missed, the
`entity_attribute_values` row was never inserted, and the trigger that derives
`cached_name`/`normalized_name` from it had nothing to read. Measured on 封神演義: **215 of
224** terminology entities had no `term` row, no `cached_name` and no `normalized_name`.

`normalized_name` is the dedup key (`findEntityByNameOrAlias`, `findEntityCrossKind`), so
each re-encounter created ANOTHER nameless row instead of merging — visible as duplicate
definitions in the data.

**The recovery.** The name was never stored, but the model's parsed output survives in
`extraction_raw_outputs.parsed_entities`. This matches an orphaned entity to its raw entry
on the *definition* text (the one attribute that did land) and restores the name by
inserting the `term` attribute value the writeback should have written. The trigger then
recomputes `cached_name` and `normalized_name` by itself.

Safe to re-run: the insert is `ON CONFLICT DO NOTHING`, and only entities that currently
have no display value are touched.

    python scripts/backfill-terminology-names.py --book <uuid>          # report only
    python scripts/backfill-terminology-names.py --book <uuid> --apply  # write
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def psql(db: str, query: str, quiet: bool = False) -> list[list[str]]:
    name = subprocess.run(["docker", "ps", "--filter", "name=postgres", "--format",
                           "{{.Names}}"], capture_output=True, text=True).stdout.split()
    if not name:
        raise SystemExit("no running postgres container found")
    out = subprocess.run(["docker", "exec", "-i", name[0], "psql", "-U", "loreweave",
                          "-d", db, "-At", "-F", "\t", "-c", query],
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        raise SystemExit(out.stderr[:800])
    if quiet:
        return []
    return [ln.split("\t") for ln in out.stdout.splitlines() if ln.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--kind", default="terminology")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    # 1. Entities that lost their name: no display value, so cached_name is empty.
    orphans = psql("loreweave_glossary", f"""
        SELECT g.entity_id::text,
               replace(replace(coalesce(av.original_value,''), chr(9),' '), chr(10),' ')
        FROM glossary_entities g
        JOIN book_kinds bk ON bk.book_kind_id = g.kind_id AND bk.code = '{a.kind}'
        LEFT JOIN entity_attribute_values av ON av.entity_id = g.entity_id
             AND av.attr_def_id = (SELECT ba.attr_id FROM book_attributes ba
                                   WHERE ba.kind_id = g.kind_id AND ba.code='definition'
                                   LIMIT 1)
        WHERE g.book_id = '{a.book}' AND g.alive AND coalesce(g.cached_name,'') = ''
    """)
    print(f"orphaned {a.kind} entities (no display value): {len(orphans)}")
    if not orphans:
        return

    # 2. The model's own output, still on disk. definition -> name.
    raw = psql("loreweave_translation", f"""
        SELECT DISTINCT
               replace(replace(coalesce(e->'attributes'->>'definition',''), chr(9),' '), chr(10),' '),
               coalesce(e->>'name', e->>'term', '')
        FROM extraction_raw_outputs r, jsonb_array_elements(r.parsed_entities) e
        WHERE r.book_id = '{a.book}' AND e->>'kind_code' = '{a.kind}'
              AND coalesce(e->'attributes'->>'definition','') <> ''
              AND coalesce(e->>'name', e->>'term', '') <> ''
    """)
    by_def: dict[str, str] = {}
    ambiguous: set[str] = set()
    for definition, name in raw:
        if definition in by_def and by_def[definition] != name:
            ambiguous.add(definition)     # same definition, two names — do not guess
        by_def.setdefault(definition, name)
    print(f"recoverable definition->name pairs in raw output: {len(by_def)}"
          f"  (ambiguous, skipped: {len(ambiguous)})")

    matched = [(eid, by_def[d]) for eid, d in orphans
               if d and d in by_def and d not in ambiguous]
    print(f"matched: {len(matched)} / {len(orphans)}"
          f"   unrecoverable: {len(orphans) - len(matched)}")
    for eid, name in matched[:8]:
        print(f"   {eid}  ->  {name}")

    if not a.apply:
        print("\ndry run — pass --apply to write")
        return

    # 3. Insert the display attribute the writeback should have written. The trigger on
    #    entity_attribute_values recomputes cached_name + normalized_name by itself, which
    #    is what restores the dedup key.
    # SQL string literals, not JSON: json.dumps emits DOUBLE quotes, which Postgres reads
    # as an identifier — the first run failed with `column "行瘟使者" does not exist`.
    def lit(s: str) -> str:
        return "'" + s.replace("'", "''") + "'"

    values = ",".join(f"('{eid}'::uuid, {lit(name)})" for eid, name in matched)
    psql("loreweave_glossary", f"""
        INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
        SELECT v.entity_id,
               (SELECT ba.attr_id FROM book_attributes ba
                JOIN glossary_entities g2 ON g2.entity_id = v.entity_id
                WHERE ba.kind_id = g2.kind_id AND ba.code IN ('name','term')
                ORDER BY CASE ba.code WHEN 'name' THEN 0 ELSE 1 END LIMIT 1),
               -- Same language the entity's surviving attributes were stored in, so the
               -- restored name is not stamped with a language the rest of the row denies.
               (SELECT av2.original_language FROM entity_attribute_values av2
                WHERE av2.entity_id = v.entity_id
                ORDER BY av2.attr_value_id LIMIT 1),
               v.name
        FROM (VALUES {values}) AS v(entity_id, name)
        ON CONFLICT (entity_id, attr_def_id) DO NOTHING
    """, quiet=True)
    print(f"\napplied — inserted display values for {len(matched)} entities")

    left = psql("loreweave_glossary", f"""
        SELECT count(*) FROM glossary_entities g
        JOIN book_kinds bk ON bk.book_kind_id=g.kind_id AND bk.code='{a.kind}'
        WHERE g.book_id='{a.book}' AND g.alive AND coalesce(g.cached_name,'')=''
    """)
    print(f"still nameless after backfill: {left[0][0]}")


if __name__ == "__main__":
    sys.exit(main())
