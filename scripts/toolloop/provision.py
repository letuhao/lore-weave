#!/usr/bin/env python
"""A throwaway book per scenario — built, seeded, and torn down around every run.

🔴 WHY THIS EXISTS, IN ONE INCIDENT. On 2026-08-13 five read-intent turns against the shared
loop book took `outline_node` from 3 to 6: the model created three chapters and then described
them back as "your current plan". Because every scenario shared one book, the store diff could
not say WHICH scenario wrote — and because the book persisted between runs, the next run started
from the contaminated state and read as if nothing had happened. A per-scenario book fixes both:
the diff is attributable, and every run starts from the same substrate.

🔴 AND WHY IT SEEDS. A read-intent scenario against an EMPTY store cannot tell the two outcomes
apart that this loop most needs to separate:

    the model reached the tool and truthfully reported nothing
    the model never reached the tool and fabricated "you have nothing yet"

Both print the same sentence. Seeding makes the truthful answer specific — three named outline
nodes, a named canon rule — so a fabricated one is visibly wrong rather than merely unverifiable.
This is the same failure as `composition_list_canon_rules` answering "you haven't declared any"
with one row in the store.

Substrate is built by DIRECT MCP calls, never by the model: setup must be deterministic, or the
thing under test is the setup. The model only ever drives the TURN.

The teardown boundary is the title prefix. `teardown()` refuses to delete a book that this module
did not name, so no bug in a scenario file can reach a real book.

Usage (normally called by fe_runner, but runnable alone to inspect a fixture):
    python scripts/toolloop/provision.py --label smoke --keep
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.tool_liveness.mcp_direct import MCPDirect  # noqa: E402
from scripts.eval.tool_liveness import oracle  # noqa: E402

#: Every book this module creates carries this prefix, and teardown deletes nothing without it.
#: A constant rather than a parameter on purpose — a caller that can choose the prefix can choose
#: one that matches a real book.
TITLE_PREFIX = "LOOP-THROWAWAY-"

#: The account the loop runs as. Read from the same place the runner reads it so the two cannot
#: drift into provisioning as one user and driving turns as another — which would present as
#: "the tool returned nothing" for every single scenario.
from scripts.eval.tool_liveness import config as _tle_config  # noqa: E402

OWNER_ID = _tle_config.USER_ID

BOOK_DB = "loreweave_book"
COMP_DB = "loreweave_composition"


class ProvisionError(RuntimeError):
    pass


class Throwaway:
    """One scenario's substrate. Build it, use it, tear it down."""

    def __init__(self, label: str, *, mcp: MCPDirect | None = None) -> None:
        self.label = label
        self.run_id = uuid.uuid4().hex[:8]
        self.title = f"{TITLE_PREFIX}{label}-{self.run_id}"
        self.mcp = mcp or MCPDirect()
        self.book_id: str | None = None
        self.chapter_id: str | None = None
        self.project_id: str | None = None
        self.seeded: list[dict] = []

    # ── build ────────────────────────────────────────────────────────────────────────────
    def build(self, seed: list[dict] | None = None, *, chapter: bool = True) -> "Throwaway":
        r = self.mcp.call("book_create", {
            "title": self.title,
            "original_language": "en",
            "description": "Tool-loop throwaway fixture — created and deleted by "
                           "scripts/toolloop/provision.py. Safe to delete.",
            "genre_tags": ["fantasy"],
        })
        self.book_id = r.get("book_id") or r.get("id")
        if not self.book_id:
            raise ProvisionError(f"book_create returned no id: {json.dumps(r)[:200]}")

        if chapter:
            self.chapter_id = self._make_chapter()

        # The composition Work is provisioned ASYNCHRONOUSLY off `book.created` (measured
        # 0.2s–8.0s on this stack). Polling rather than sleeping, because a fixed sleep is
        # either flaky or slow and this runs once per scenario per batch.
        self.project_id = self._await_project()

        for step in (seed or []):
            self._seed_step(step)
        return self

    def _make_chapter(self) -> str | None:
        r = self.mcp.call("book_chapter_create", {
            "book_id": self.book_id,
            "original_language": "en",
            "title": "Chapter I — The Ember Codex",
            # `body`, not `content`. Guessed `content` on the first call and the gateway
            # rejected the whole request -- the schema is the authority, never the name.
            "body": "Aldric Vane climbed the black stair of Hollow Keep as the storm broke.",
        })
        return r.get("chapter_id") or r.get("id")

    def _await_project(self, timeout: float = 30.0) -> str | None:
        """Get the book's composition `project_id`, minting it if nobody has yet.

        🔴 WAITING FOR THIS IS WAITING FOREVER, AND THAT COST A WHOLE FIXTURE CYCLE. The
        `book.created` consumer DOES provision a composition Work within a second — but it
        provisions it LAZY: `project_id` NULL, `pending_project_backfill=true`, logged as
        "provisioned (pending project)". Nothing backfills it on a timer. The id is minted by
        the first caller that needs one, and `composition_create_work` is that caller: it
        resolves an existing book-typed knowledge project or creates one, then backfills THE
        pending row rather than minting a second Work.

        A poll therefore never converges, and the empty string it kept reading looked exactly
        like "composition is slow on this stack" — a provisioning bug wearing a performance
        bug's clothes. Ask for the thing instead of waiting for it.
        """
        r = self.mcp.call("composition_create_work", {"book_id": self.book_id})
        pid = r.get("project_id") or (r.get("work") or {}).get("project_id")
        if pid:
            return str(pid)
        # Fall back to the row: create_work is idempotent, so a Work that already existed with a
        # project comes back through the DB even if the response shape differs.
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rows = oracle.db_query(
                COMP_DB, "SELECT project_id FROM composition_work WHERE "
                         f"book_id='{(self.book_id or '').replace(chr(39), chr(39) * 2)}' "
                         "AND project_id IS NOT NULL LIMIT 1")
            if rows and rows[0] and rows[0][0]:
                return rows[0][0]
            time.sleep(0.5)
        # Not fatal: plenty of tools never touch composition. But it IS reported, because a
        # silent None here would later look like "the composition tool found nothing" — a
        # provisioning failure wearing a defect's clothes.
        print(f"  ! composition project never minted for {self.book_id} within {timeout}s")
        return None

    def _seed_step(self, step: dict) -> None:
        """One deterministic MCP call. `{book_id}` / `{chapter_id}` / `{project_id}` in any
        string value are substituted with this fixture's real ids."""
        tool = step["tool"]
        args = self._substitute(step.get("args") or {})
        r = self.mcp.call(tool, args)
        self.seeded.append({"tool": tool, "args": args, "result": r})

    def _substitute(self, obj):
        if isinstance(obj, str):
            return (obj.replace("{book_id}", self.book_id or "")
                       .replace("{chapter_id}", self.chapter_id or "")
                       .replace("{project_id}", self.project_id or ""))
        if isinstance(obj, dict):
            return {k: self._substitute(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._substitute(v) for v in obj]
        return obj

    # ── teardown ─────────────────────────────────────────────────────────────────────────
    def teardown(self) -> dict:
        """Delete ONLY this fixture, and only after re-reading the row to confirm it is ours.

        The check is deliberately made against the DATABASE rather than against this object's
        own memory of what it created. An in-process assertion only proves the object is
        self-consistent; re-reading proves the id on disk is a throwaway owned by the harness
        account. A DELETE in this loop already removed 10 rows where 3 were meant, and the
        difference was exactly this: trusting a remembered scope instead of confirming it.
        """
        if not self.book_id:
            return {"deleted": 0, "reason": "nothing was created"}
        return purge_book(self.book_id)


def purge_book(book_id: str) -> dict:
    q = book_id.replace("'", "''")
    rows = oracle.db_query(
        BOOK_DB, f"SELECT title, owner_user_id FROM books WHERE id='{q}'")
    if not rows or not rows[0] or not rows[0][0]:
        return {"deleted": 0, "reason": "no such book"}
    title, owner = rows[0][0], rows[0][1]
    if not title.startswith(TITLE_PREFIX):
        raise ProvisionError(
            f"REFUSING to delete book {book_id}: its title is {title!r}, which this module did "
            f"not create (every fixture is named {TITLE_PREFIX}*). Nothing was deleted.")
    if owner != OWNER_ID:
        raise ProvisionError(
            f"REFUSING to delete book {book_id}: owned by {owner}, not the harness account "
            f"{OWNER_ID}. Nothing was deleted.")

    deleted = {"book_id": book_id, "title": title, "tables": {}}
    # Composition first: its rows reference the book, and a project orphaned by a deleted book
    # is invisible to the book-scoped snapshot — it would accumulate silently, run after run.
    prows = oracle.db_query(COMP_DB, f"SELECT project_id FROM composition_work WHERE book_id='{q}'")
    for pr in prows:
        pid = (pr[0] if pr else "") or ""
        if pid:
            deleted["tables"]["composition(project)"] = pid
            _delete_scoped(COMP_DB, "project_id", pid)
    _delete_scoped(COMP_DB, "book_id", q)
    for db in ("loreweave_glossary", "loreweave_knowledge"):
        _delete_scoped(db, "book_id", q)
    _delete_scoped(BOOK_DB, "book_id", q)
    oracle.db_query(BOOK_DB, f"DELETE FROM books WHERE id='{q}'")
    return deleted


def _delete_scoped(db: str, column: str, value: str) -> None:
    """Delete this book's rows from every table in `db` that carries `column`.

    Table-driven rather than a hand-written list, for the same reason `store_snapshot` is: a
    hand list goes stale the moment someone adds a table, and the failure mode is silent
    leftover rows that the NEXT run reads as pre-existing state.
    """
    tables = oracle.db_query(
        db, "SELECT table_name FROM information_schema.columns WHERE table_schema='public' "
            f"AND column_name='{column}' ORDER BY table_name")
    for t in tables:
        name = (t[0] if t else "") or ""
        if not name:
            continue
        try:
            oracle.db_query(db, f'DELETE FROM public."{name}" WHERE {column}=\'{value}\'')
        except Exception:  # noqa: BLE001 — FK order is not knowable up front; a second pass clears it
            pass
    # second pass: rows blocked by a FK on the first sweep
    for t in tables:
        name = (t[0] if t else "") or ""
        if name:
            try:
                oracle.db_query(db, f'DELETE FROM public."{name}" WHERE {column}=\'{value}\'')
            except Exception:  # noqa: BLE001
                pass


def sweep_orphans(older_than_minutes: int = 0) -> list[str]:
    """Delete throwaway books left behind by a crashed run. Prefix-scoped, so it can never
    reach anything but this module's own fixtures."""
    rows = oracle.db_query(
        BOOK_DB, f"SELECT id FROM books WHERE title LIKE '{TITLE_PREFIX}%' "
                 f"AND owner_user_id='{OWNER_ID}' "
                 f"AND created_at < now() - interval '{int(older_than_minutes)} minutes'")
    out = []
    for r in rows:
        bid = (r[0] if r else "") or ""
        if bid:
            purge_book(bid)
            out.append(bid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="manual")
    ap.add_argument("--keep", action="store_true", help="build and print, do not tear down")
    ap.add_argument("--sweep", action="store_true", help="delete every leftover throwaway book")
    a = ap.parse_args()
    if a.sweep:
        gone = sweep_orphans()
        print(f"swept {len(gone)} throwaway book(s)")
        return 0
    fx = Throwaway(a.label).build()
    print(json.dumps({"book_id": fx.book_id, "chapter_id": fx.chapter_id,
                      "project_id": fx.project_id, "title": fx.title}, indent=2))
    if not a.keep:
        print(json.dumps(fx.teardown(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
