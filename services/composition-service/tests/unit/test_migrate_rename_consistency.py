"""A column RENAME and every later reference to it live in the same transaction — a static guard.

The bug this exists to catch, in full: `_MOTIF_SCHEMA_SQL` renames `motif.language` to
`motif.original_language`, and four legacy index-repair statements *after* the rename still said
`language`. The whole block is one `conn.execute`, so on any database that actually had the old
column the rename succeeded, the first stale index failed with `column "language" does not exist`,
and the implicit transaction rolled back — which put the old column back, so the next startup failed
in exactly the same way. composition-service crash-looped and could not serve.

It was invisible for as long as it took to rebuild: the running containers were on an image from
before the rename was written, so nobody had executed the combination. That is the dangerous shape —
a migration defect that only appears on deploy, in a service that then will not start.

A test cannot execute this DDL without a database, but it does not need to: the defect is textual and
local. Parse the rename statements out of the SQL and assert nothing after each one still names the
old column.
"""

from __future__ import annotations

import re

from app.db import migrate

#: `ALTER TABLE <t> RENAME COLUMN <old> TO <new>`
_RENAME = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+RENAME\s+COLUMN\s+(\w+)\s+TO\s+(\w+)", re.I,
)


def _sql_blocks() -> list[tuple[str, str]]:
    """Every module-level SQL string in migrate.py, by name."""
    return [
        (name, value)
        for name, value in vars(migrate).items()
        if isinstance(value, str) and name.isupper() and "TABLE" in value.upper()
    ]


def test_no_statement_after_a_rename_still_uses_the_old_column_name():
    offenders: list[str] = []
    for block_name, sql in _sql_blocks():
        for m in _RENAME.finditer(sql):
            table, old, new = m.group(1), m.group(2), m.group(3)
            tail = sql[m.end():]
            # Only flag a use of the OLD name against the SAME table. `original_language` contains
            # `language`, so the word must be matched whole.
            word = re.compile(rf"\b{re.escape(old)}\b")
            for line in tail.splitlines():
                stripped = line.strip()
                if stripped.startswith("--") or table not in line:
                    continue
                if word.search(re.sub(r"--.*$", "", line)):
                    offenders.append(
                        f"{block_name}: after `{table}.{old}` -> `{new}`, this still says "
                        f"{old!r}: {stripped[:110]}"
                    )
    assert not offenders, (
        "a renamed column is referenced by its OLD name later in the SAME transaction — the "
        "migration will roll back and the service will crash-loop on startup:\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_would_actually_fire():
    """The guard is worthless if its parser silently matches nothing — pin that it detects the shape.

    (`test_no_statement_after_a_rename…` passing is otherwise indistinguishable from it having found
    no rename statements at all, which is the failure mode a text-scanning test dies of.)
    """
    sql = (
        "ALTER TABLE motif RENAME COLUMN language TO original_language;\n"
        "CREATE UNIQUE INDEX x ON motif(code, language);\n"
    )
    m = _RENAME.search(sql)
    assert m and m.group(2) == "language"
    tail = sql[m.end():]
    assert re.search(r"\blanguage\b", tail), "the parser cannot see the stale reference"


def test_the_real_migration_contains_the_rename_this_guards():
    """If the rename is ever removed the guard above goes vacuously green; fail loudly instead."""
    assert any(_RENAME.search(sql) for _, sql in _sql_blocks()), \
        "no RENAME COLUMN found in migrate.py — this guard is no longer guarding anything"
