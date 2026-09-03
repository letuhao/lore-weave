"""A database with book-scoped tables that the snapshot does not sweep is a silent DATA bar.

FOUND 2026-08-22. `store_snapshot.DATABASES` listed four databases, and its own docstring
explained the reasoning: "67 tables across the four owning databases carry a `book_id`, so the
scope key is the book." That was true when it was written. Then services landed, and nobody
re-derived it. Measured against the live cluster, **four more** carry book-scoped tables:

    loreweave_translation       9 tables with a book_id
    loreweave_agent_registry   10
    loreweave_lore_enrichment  10
    loreweave_sharing           1

Thirty book-scoped tables invisible to the bar whose entire job is to see them. Every translation
tool, every lore-enrichment tool and the sharing/publication tools had a DATA bar that could only
ever say "unchanged".

HOW IT SURFACED, which is the argument for the warning that found it: the idempotency probe
reported *"the FIRST call changed nothing either, so this probe measured two no-ops and proves
nothing"* for two translation tools that had plainly just written. That line exists to stop a
two-no-op probe being mistaken for proof of idempotency. It caught the store instead.

THE INVARIANT: the sweep's scope is DERIVED from the cluster, never typed once and trusted. The
list stays explicit in `store_snapshot` so a sweep is predictable and reviewable — this test is the
derivation that keeps it honest.

WHAT IT DOES NOT COVER, stated so its green is not over-read:
  * A store with no `book_id` at all is invisible to this check as well as to the sweep. That is a
    different defect (D-DATA-BAR-BLIND-TO-A-NON-BOOK-SCOPED-STORE) and needs a per-store fix, as
    world/map got. `user_models` and the registry's `skills` are the known remaining cases.
  * It says nothing about whether a swept table is the RIGHT one for a given tool.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MOD = ROOT / "scripts" / "toolloop" / "store_snapshot.py"

_SPEC = importlib.util.spec_from_file_location("store_snapshot_scope", MOD)
ss = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ss)

#: Ephemeral databases created by other suites. Excluded by NAME rather than by guessing at
#: content: `loreweave_glossary_t31mig2` and friends are migration scratch, not owning stores.
_EPHEMERAL = re.compile(r"(test|audit|smoke|migtest|_gw\d|_ws\d|_s\d|_m\d|_ss\d|_final|_t\d)")

#: Not owning stores for a BOOK: identity, telemetry, scheduling, billing. Listed so a reader can
#: see the judgement rather than infer it from an absence.
_NOT_OWNING = {
    "loreweave_auth", "loreweave_chat", "loreweave_events", "loreweave_meta",
    "loreweave_notification", "loreweave_scheduler", "loreweave_statistics",
    "loreweave_usage_billing", "loreweave_provider_registry", "loreweave_learning",
    "loreweave_catalog", "loreweave_jobs", "loreweave_campaign", "loreweave_roleplay",
}


def _psql(db: str, sql: str) -> list[str]:
    out = subprocess.run(
        ["docker", "exec", "-i", ss.CONTAINER, "psql", "-U", "loreweave", "-d", db, "-At"],
        input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    if out.returncode != 0:
        pytest.skip(f"postgres not reachable: {out.stderr.strip()[:120]}")
    return [ln for ln in out.stdout.splitlines() if ln]


def _book_scoped_databases() -> dict[str, int]:
    names = _psql("postgres", "select datname from pg_database where datname like 'loreweave_%';")
    found = {}
    for db in sorted(names):
        if _EPHEMERAL.search(db) or db in _NOT_OWNING:
            continue
        n = _psql(db, "select count(*) from information_schema.columns "
                      "where table_schema='public' and column_name='book_id';")
        if n and int(n[0]) > 0:
            found[db] = int(n[0])
    return found


def test_every_book_scoped_database_is_swept():
    found = _book_scoped_databases()
    missing = {db: n for db, n in found.items() if db not in ss.DATABASES}
    assert not missing, (
        "these databases hold book-scoped tables the snapshot never sweeps, so every tool that "
        "writes there has a DATA bar that can only say 'unchanged': "
        + ", ".join(f"{db} ({n} tables)" for db, n in sorted(missing.items()))
        + " — add them to store_snapshot.DATABASES, or exclude them by name in this test with the "
          "reason"
    )


def test_the_sweep_does_not_list_a_database_with_nothing_to_sweep():
    """A list that only ever grows stops being a decision. If a database no longer has book-scoped
    tables it should leave, so the sweep's cost stays proportional to what it can find."""
    found = _book_scoped_databases()
    dead = [db for db in ss.DATABASES if db not in found]
    assert not dead, (
        f"{dead} are swept but hold no book-scoped tables — remove them from DATABASES, or say "
        "here why they are kept"
    )


def test_the_four_that_were_missing_are_now_present():
    """The original instance, kept red-able by name. If any of these leaves DATABASES the
    regression is exactly the one that hid thirty tables."""
    for db in ("loreweave_translation", "loreweave_agent_registry",
               "loreweave_lore_enrichment", "loreweave_sharing"):
        assert db in ss.DATABASES, f"{db} was one of the four found missing on 2026-08-22"
