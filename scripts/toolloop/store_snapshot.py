#!/usr/bin/env python
"""The DATA bar, automated — what the OWNING STORES hold for one book, before and after a turn.

🔴 WHY THIS IS THE BAR THAT MATTERS. Both defects this loop found on 2026-08-13 were caught by
reading the store, not by reading the model's answer:

  * asked "Show me the outline I've planned", the reply described "three main story arcs" — and
    the model had CREATED them seconds earlier. `outline_node` went 7 -> 10. The prose was
    plausible; only the row count refuted it.
  * asked "What canon rules have I declared", the reply said "you haven't declared any" while the
    store held one.

A tool's own response cannot settle either case, and neither can the model's narration. Only the
store can. So this is snapshotted before and after every scenario, and `gate.py` refuses to
conclude a read-intent tool whose snapshot CHANGED.

**Tool-independent by construction.** It needs no per-tool knowledge: the scope keys are the
fixture's own ids, and every table carrying one is swept.

🔴 THIS PARAGRAPH USED TO READ "67 tables across the four owning databases carry a `book_id`, so
the scope key is the book", AND THAT SENTENCE WAS THE DEFECT. A count derived once and then
trusted forever — services landed afterwards and nobody re-derived it. Measured 2026-08-22: four
more databases hold 30 book-scoped tables, 17 tables are CHAPTER-scoped with no book_id, and the
whole world/map store keys on map_id/world_id and carries neither. For every tool writing to any
of those, "the store did not change" was a sentence about a place the snapshot never looked.

So the scope is now four keys, and each exists because a real tool was invisible without it:

    book_id      the original sweep, across every owning database
    chapter_id   tables like `active_chapter_translation_versions`, keyed (chapter_id, language)
    project_id   composition, resolved from the book through `composition_work`
    world_id     `world_maps`/`map_regions`/`map_markers`, which have no book column at all

and `scripts/test_the_snapshot_sweeps_every_book_scoped_store_gate.py` fails when a database with
book-scoped tables is missing from DATABASES, so the list cannot silently go stale again.

**It counts rows AND the latest `updated_at`.** A count alone misses an in-place edit: overwriting
chapter 1's body (which this loop did to the author's real book on 2026-07-11, silently, under a
standing approval) changes no count at all.

Usage:
    python scripts/toolloop/store_snapshot.py <book_id>            # print a snapshot
    python scripts/toolloop/store_snapshot.py <book_id> --diff f.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

#: The owning stores. A tool that writes outside these is out of scope for the book-scoped diff —
#: and that gap is stated rather than hidden, because a snapshot whose silence is read as "nothing
#: happened" is exactly the failure this file exists to prevent.
#:
#: 🔴 THIS LIST WAS FOUR ENTRIES LONG AND SILENTLY WRONG. It was true when written; then services
#: landed and nobody re-derived it. Measured 2026-08-22 against the live databases, FOUR MORE carry
#: book-scoped tables and none was swept:
#:
#:     loreweave_translation       9 tables with a book_id
#:     loreweave_agent_registry   10
#:     loreweave_lore_enrichment  10
#:     loreweave_sharing           1
#:
#: Thirty book-scoped tables invisible to the bar that exists to see them. It surfaced because the
#: idempotency probe reported "the FIRST call changed nothing either" for two translation tools
#: that had plainly just written — the warning was there to stop a two-no-op probe being read as
#: proof, and it caught the store instead.
#:
#: This file's own docstring said "67 tables across the four owning databases carry a book_id, so
#: the scope key is the book" — a count derived once and then trusted forever, which is the exact
#: class this loop keeps finding. The list stays EXPLICIT so a sweep is predictable, and
#: `scripts/test_the_snapshot_sweeps_every_book_scoped_store_gate.py` fails when a database with
#: book-scoped tables is missing from it. The list is the decision; the gate is the derivation.
DATABASES = (
    "loreweave_book",
    "loreweave_composition",
    "loreweave_glossary",
    "loreweave_knowledge",
    "loreweave_translation",
    "loreweave_agent_registry",
    "loreweave_lore_enrichment",
    "loreweave_sharing",
)

CONTAINER = "infra-postgres-1"


class SnapshotUnavailable(RuntimeError):
    """A store probe could not run, so there is no snapshot — only the absence of one."""


def _psql(db: str, sql: str) -> list[str]:
    """🔴 THIS USED TO RETURN THE STRING "__error__:<stderr>" AND LET IT FLOW ON AS DATA.

    Measured 2026-08-22. The stack was idling at 96 of 100 Postgres connections, a probe was
    refused, and `_counts` filed the sentinel under `out["__error__"]`. That key reached the run's
    `store` as though it were a table, so `diff` reported

        {"loreweave_composition.__error__": {"before": null,
                                             "after": "__error__:... too many clients"}}

    which is A DIFF — and the gate reads a diff as the owning store having MOVED. The affected
    entry's wrote_count was 1 entirely because of it.

    `_scoped_tables` was the same bug wearing quieter clothes: it filtered the sentinel out and
    returned `[]`, so a failed information_schema probe produced an EMPTY snapshot that reads
    exactly like "no tables matched".

    Both directions are wrong in a way that matters: a phantom diff is a false "this READ wrote to
    the store"; an empty snapshot is a false "the write landed nothing". Either way the DATA bar —
    the one assertion a stochastic model cannot talk its way past — is decided on a measurement
    that never happened.

    So it raises. The caller records the run as errored, and the gate's EXISTING "LIVE clean" bar
    refuses the batch: a transport failure is not a model result, it is a re-run condition. No new
    bar, no new sentinel, and nothing for a later reader to mistake for data.
    """
    out = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "loreweave", "-d", db, "-At"],
        input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        raise SnapshotUnavailable(f"{db}: {out.stderr.strip()[:160]}")
    return [ln for ln in out.stdout.splitlines() if ln]


def _scoped_tables(db: str, column: str) -> list[str]:
    # No sentinel filter any more — _psql raises, so an empty list here means the query really
    # returned no rows. That distinction is the whole point.
    return list(_psql(db, (
        "select table_name from information_schema.columns "
        f"where table_schema='public' and column_name='{column}' order by table_name;"
    )))


def _counts(db: str, tables: list[str], column: str, value: str) -> dict:
    """One round trip per database, not per table — 67 tables would otherwise be 67 exec calls."""
    if not tables:
        return {}
    # `updated_at` is not universal, so probe for it and fold it in only where it exists. A count
    # alone cannot see an in-place edit, and an in-place edit is how this loop damaged a real book.
    has_upd = set(_scoped_tables(db, "updated_at"))
    parts = []
    for t in tables:
        upd = (f", coalesce(max(updated_at)::text,'-')" if t in has_upd else ", '-'")
        parts.append(
            f"select '{t}', count(*)::text{upd} from public.\"{t}\" where {column} = '{value}'"
        )
    rows = _psql(db, " union all ".join(parts) + ";")
    out = {}
    for r in rows:
        bits = r.split("|")
        if len(bits) >= 2 and bits[1] != "0":
            out[bits[0]] = {"rows": int(bits[1]), "latest": bits[2] if len(bits) > 2 else "-"}
    return out


def _neo4j(project_id: str | None) -> dict:
    """Graph counts — the store the Postgres sweep CANNOT see.

    🔴 THIS BLIND SPOT NEARLY PRODUCED A FALSE DEFECT. `memory_remember` returned
    {"remembered": true, "fact_id": ..., "confidence": 0.7} and the Postgres snapshot said the
    store was unchanged, which is the textbook silent-success shape — and I was one step from
    filing it. The tool was honest: `_handle_memory_remember` ends in `merge_fact` inside
    `neo4j_session()`, so memory facts live in the GRAPH and no amount of Postgres sweeping will
    ever see them.

    This file's own docstring already warned that a tool writing outside the four databases is
    out of scope "because a snapshot whose silence is read as 'nothing happened' is exactly the
    failure this file exists to prevent". The warning was written and still nearly missed, which
    is the argument for measuring rather than documenting.

    Counted globally as well as per-project: a fact stored with project_id NULL is invisible to
    a project-scoped count, and that is precisely the case that surfaced here (339 of 343 facts
    carry a project; the one this turn wrote did not).
    """
    pw = subprocess.run(["docker", "exec", "infra-knowledge-service-1", "printenv",
                         "NEO4J_PASSWORD"], capture_output=True, text=True).stdout.strip()
    if not pw:
        return {}

    def q(cypher: str) -> str:
        out = subprocess.run(
            ["docker", "exec", "-i", "infra-neo4j-1", "cypher-shell", "-u", "neo4j", "-p", pw,
             "--format", "plain", cypher],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        lines = [ln.strip() for ln in out.stdout.splitlines()
                 if ln.strip() and not ln.startswith("WARNING")]
        return lines[-1] if len(lines) >= 2 else "0"

    snap = {"neo4j.Fact.total": {"rows": int(q("MATCH (f:Fact) RETURN count(f);") or 0),
                                 "latest": "-"}}
    if project_id:
        snap["neo4j.Fact.project"] = {
            "rows": int(q(f"MATCH (f:Fact) WHERE f.project_id = '{project_id}' "
                          "RETURN count(f);") or 0), "latest": "-"}
    return snap


def _world_counts(world_id: str) -> dict:
    """🔴 THE WORLD/MAP STORE HAS NO `book_id`, SO THE SWEEP BELOW HAS NEVER SEEN IT.

    Measured 2026-08-22, and it is the worst thing this loop has found in its own instrument.
    `map_regions` is keyed (id, map_id, name, polygon, entity_id, created_at, updated_at) and
    `world_maps` by (id, world_id, owner_user_id, …). Neither carries `book_id`, and `snapshot`
    sweeps exactly the tables that do. So for the entire world/map family the DATA bar's
    "store unchanged" was VACUOUS — it was not looking at the store those tools write.

    It surfaced because the approved arm called `world_map_update_region` 5/5 with the card
    removed, the tool returned `{"ok": true, "result": {"region": {"name": "The Frozen North",
    "updated_at": "2026-08-22T12:05:41Z"}}}` — the rename landed — and `store_diff` was `{}`.
    A write the tool itself reports, invisible to the bar that exists to catch exactly that.

    SCOPED TO THE RUN'S OWN WORLD, not to the owner. An owner-wide sweep would fold in the
    account's 28 unrelated worlds and destroy the attribution that per-scenario fixtures exist to
    provide. The world id comes from the fixture's own `world_create`, so every count here belongs
    to this run.
    """
    q = world_id.replace("'", "''")
    rows = _psql("loreweave_book", (
        f"select 'world_maps', count(*)::text, coalesce(max(updated_at)::text,'-') "
        f"from world_maps where world_id='{q}' "
        f"union all select 'map_regions', count(*)::text, coalesce(max(r.updated_at)::text,'-') "
        f"from map_regions r join world_maps m on m.id=r.map_id where m.world_id='{q}' "
        f"union all select 'map_markers', count(*)::text, coalesce(max(k.updated_at)::text,'-') "
        f"from map_markers k join world_maps m on m.id=k.map_id where m.world_id='{q}';"))
    out = {}
    for r in rows:
        bits = r.split("|")
        if len(bits) >= 2 and bits[1] != "0":
            out[f"loreweave_book.{bits[0]}"] = {
                "rows": int(bits[1]), "latest": bits[2] if len(bits) > 2 else "-"}
    return out


def snapshot(book_id: str, project_id: str | None = None,
             world_id: str | None = None, chapter_id: str | None = None) -> dict:
    """Everything the owning stores hold for this book. Empty tables are omitted, so a snapshot
    reads as "what exists" rather than a wall of zeros — and a table APPEARING in the diff is
    itself the signal that something was created.

    `world_id` extends the sweep to a store that has no `book_id` at all — see `_world_counts`.
    """
    snap: dict = {}
    for db in DATABASES:
        tables = _scoped_tables(db, "book_id")
        got = _counts(db, tables, "book_id", book_id)
        for k, v in got.items():
            snap[f"{db}.{k}"] = v
        # 🔴 A CHAPTER-SCOPED TABLE IS NOT A BOOK-SCOPED ONE, and 17 of them were invisible.
        # `translation_set_active_version` is the case that found it: the active version lives in
        # `active_chapter_translation_versions`, keyed (chapter_id, target_language, …) with NO
        # book_id, so the tool wrote, the probe reported "the FIRST call changed nothing either",
        # and its idempotency was unmeasurable. Counted across the swept databases: 7 such tables
        # in book, 4 in translation, 3 each in composition and glossary.
        #
        # Only tables the book sweep did NOT already cover — a table carrying both keys would
        # otherwise be counted twice under the same name and read as a phantom change.
        if chapter_id:
            chap = [t for t in _scoped_tables(db, "chapter_id") if t not in set(tables)]
            for k, v in _counts(db, chap, "chapter_id", chapter_id).items():
                snap[f"{db}.{k}"] = v
    # composition also scopes by project_id; resolve it from the book rather than being told.
    proj = _psql("loreweave_composition",
                 f"select project_id from composition_work where book_id='{book_id}' limit 1;")
    if proj:
        ptables = _scoped_tables("loreweave_composition", "project_id")
        for k, v in _counts("loreweave_composition", ptables, "project_id", proj[0]).items():
            snap[f"loreweave_composition.{k}"] = v
        project_id = project_id or proj[0]
    if world_id:
        snap.update(_world_counts(world_id))
    try:
        snap.update(_neo4j(project_id))
    except Exception as e:  # noqa: BLE001 — a graph that is down must not silently read as "clean"
        snap["neo4j.__error__"] = {"rows": -1, "latest": str(e)[:80]}
    return snap


def diff(before: dict, after: dict) -> dict:
    """What CHANGED. A read-intent turn must produce an empty diff — that is the assertion the
    gate enforces, and it needs no knowledge of which tool ran."""
    out = {}
    for key in sorted(set(before) | set(after)):
        b, a = before.get(key), after.get(key)
        if b != a:
            out[key] = {"before": b, "after": a}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_id")
    ap.add_argument("--diff", help="a previously saved snapshot to diff against")
    ap.add_argument("--out", help="write the snapshot here")
    a = ap.parse_args()
    snap = snapshot(a.book_id)
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(snap, indent=2), encoding="utf-8")
    if a.diff:
        before = json.loads(pathlib.Path(a.diff).read_text(encoding="utf-8"))
        d = diff(before, snap)
        print(json.dumps(d, indent=2) if d else "(no change)")
        return 1 if d else 0
    print(json.dumps(snap, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
