"""Which store axes cannot see an in-place edit — the DATA bar's own blind spots.

D-SNAPSHOT-IS-BLIND-TO-AN-IN-PLACE-EDIT-WITH-NO-UPDATED-AT and
D-IDEMPOTENCY-PROBE-IS-BLIND-TO-NEO4J-OWNED-TOOLS are ONE CAUSE under two names, and both
rows say so themselves: "the same warning, two different blind spots, and neither is the tool
being quiet."

    THE INVARIANT. An axis the snapshot cannot see a MUTATION on must report itself BLIND.
    Reporting "unchanged" for a table it can only see CREATIONS in is not a weaker answer than
    the truth — it is the OPPOSITE of it, and the probe then prints "STRICTLY IDEMPOTENT".

Measured 2026-08-27 across the four owning databases:

    78  tables carry book_id
    14  of them have ONLY a creation timestamp (max(created_at) does not move on an UPDATE)
     2  have no timestamp column at all
     8  of those 16 are genuinely UPDATEd in place somewhere in services/ -> BLIND
     8  are append-only, where a row count IS sufficient -> NOT blind

The second half of that measurement is the whole point. "No updated_at" alone would have cried
blind on `entity_revisions` and `extraction_batch_outcomes`, which are append-only by design and
perfectly visible to a count. A blind list that is 50% false positives gets ignored, and an
ignored refusal is the same as no refusal.

WHY THE SOURCE GREP IS HERE AND NOT IN THE SNAPSHOT. It is slow and it depends on the checkout,
so it runs at GATE time and lands in a contract file; the snapshot and the probe read the file.
One home, and a new blind table fails CI instead of appearing silently in a batch.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "data-bar-blind-axes.json"

#: The four owning databases the book-scoped sweep covers, plus the two the loop reads
#: through their own scoped counters.
DBS = ("loreweave_book", "loreweave_composition", "loreweave_knowledge", "loreweave_glossary",
       "loreweave_translation", "loreweave_jobs", "loreweave_chat")

#: A timestamp that records CREATION only. `max()` over one of these does not move when a row
#: is updated in place, so a table whose timestamps are all of this kind is count-only.
CREATION_ONLY = frozenset({"created_at", "inserted_at", "created", "creation_time", "added_at"})

PG = ("docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave")


def _psql(db: str, sql: str) -> list[str]:
    out = subprocess.run([*PG, "-d", db, "-At", "-F", "|", "-c", sql],
                         capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"psql failed ({db}): {out.stderr.strip()[:300]}")
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def timestamp_columns(db: str) -> dict[str, set[str]]:
    """book_id table -> its timestamp columns (empty set when it has none)."""
    named: dict[str, set[str]] = {
        t: set() for t in _psql(db, "select table_name from information_schema.columns "
                                    "where table_schema='public' and column_name='book_id';")}
    for row in _psql(db, "select c.table_name, c.column_name from information_schema.columns c "
                         "where c.table_schema='public' and c.data_type like 'timestamp%' "
                         "and c.table_name in (select table_name from information_schema.columns "
                         "  where table_schema='public' and column_name='book_id');"):
        t, _, col = row.partition("|")
        if t in named:
            named[t].add(col)
    return named


def is_updated_in_place(table: str) -> bool:
    """Does any service actually UPDATE this table?

    The half that keeps the blind list honest. Without it, append-only tables — which a row
    count sees perfectly well — land on a list that then means nothing."""
    pat = re.compile(rf'update\s+(public\.)?"?{re.escape(table)}"?[\s("]', re.I)
    for p in (ROOT / "services").rglob("*"):
        if p.suffix not in (".py", ".go", ".sql") or not p.is_file():
            continue
        try:
            if pat.search(p.read_text(encoding="utf-8", errors="ignore")):
                return True
        except OSError:
            continue
    return False


def derive() -> dict:
    """The blind set, re-derived from the live catalogue and the checkout."""
    blind: list[str] = []
    considered = 0
    for db in DBS:
        for table, cols in sorted(timestamp_columns(db).items()):
            considered += 1
            if cols - CREATION_ONLY:
                continue                       # has a mutation timestamp: visible
            if not is_updated_in_place(table):
                continue                       # append-only: a count is sufficient
            blind.append(f"{db}.{table}")
    return {"considered": considered, "count": len(blind), "axes": sorted(blind)}


def blind_axes() -> set[str]:
    """The recorded blind set, for the snapshot and the probe. Reads the CONTRACT, never the
    database — a batch must not pay for a catalogue sweep per run."""
    try:
        return set(json.loads(CONTRACT.read_text(encoding="utf-8"))["axes"])
    except (OSError, ValueError, KeyError):
        return set()


def blind_in_scope(snap: dict) -> list[str]:
    """The blind axes this snapshot actually covered.

    Keys look like `loreweave_composition.divergence_spec` or `<db>.<table>.<scope>`, so the
    axis is the first two dotted segments."""
    known = blind_axes()
    return sorted({".".join(k.split(".")[:2]) for k in snap
                   if ".".join(k.split(".")[:2]) in known})


if __name__ == "__main__":
    d = derive()
    CONTRACT.write_text(json.dumps(
        {"_what": __doc__.strip().splitlines()[0],
         "_derived_by": "python scripts/toolloop/blind_axes.py",
         **d}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"considered {d['considered']} book-scoped tables; {d['count']} are BLIND")
    for a in d["axes"]:
        print("  -", a)
