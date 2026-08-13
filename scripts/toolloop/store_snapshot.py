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

**Tool-independent by construction.** It needs no per-tool knowledge: 67 tables across the four
owning databases carry a `book_id`, so the scope key is the book. Composition additionally scopes
by `project_id`, resolved from the book through `composition_work`. That is the whole contract —
which is why one snapshot covers all 285 tools.

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
DATABASES = (
    "loreweave_book",
    "loreweave_composition",
    "loreweave_glossary",
    "loreweave_knowledge",
)

CONTAINER = "infra-postgres-1"


def _psql(db: str, sql: str) -> list[str]:
    out = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "loreweave", "-d", db, "-At"],
        input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        return [f"__error__:{out.stderr.strip()[:120]}"]
    return [ln for ln in out.stdout.splitlines() if ln]


def _scoped_tables(db: str, column: str) -> list[str]:
    return [t for t in _psql(db, (
        "select table_name from information_schema.columns "
        f"where table_schema='public' and column_name='{column}' order by table_name;"
    )) if not t.startswith("__error__")]


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
        if r.startswith("__error__"):
            out["__error__"] = r
            continue
        bits = r.split("|")
        if len(bits) >= 2 and bits[1] != "0":
            out[bits[0]] = {"rows": int(bits[1]), "latest": bits[2] if len(bits) > 2 else "-"}
    return out


def snapshot(book_id: str) -> dict:
    """Everything the owning stores hold for this book. Empty tables are omitted, so a snapshot
    reads as "what exists" rather than a wall of zeros — and a table APPEARING in the diff is
    itself the signal that something was created."""
    snap: dict = {}
    for db in DATABASES:
        tables = _scoped_tables(db, "book_id")
        got = _counts(db, tables, "book_id", book_id)
        for k, v in got.items():
            snap[f"{db}.{k}"] = v
    # composition also scopes by project_id; resolve it from the book rather than being told.
    proj = _psql("loreweave_composition",
                 f"select project_id from composition_work where book_id='{book_id}' limit 1;")
    if proj and not proj[0].startswith("__error__"):
        ptables = _scoped_tables("loreweave_composition", "project_id")
        for k, v in _counts("loreweave_composition", ptables, "project_id", proj[0]).items():
            snap[f"loreweave_composition.{k}"] = v
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
