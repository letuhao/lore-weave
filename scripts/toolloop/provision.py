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
import re
import pathlib
import subprocess
import sys
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from scripts.eval.tool_liveness.mcp_direct import MCPDirect  # noqa: E402
from scripts.eval.tool_liveness.auth import Auth as _TLEAuth  # noqa: E402
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

_AUTH_SINGLETON = None


def _tle_auth():
    """One cached bearer for the whole process — the token is good for 2h and re-logging in per
    fixture would make provisioning the slowest part of a batch."""
    global _AUTH_SINGLETON
    if _AUTH_SINGLETON is None:
        _AUTH_SINGLETON = _TLEAuth()
    return _AUTH_SINGLETON

CONTAINER = _tle_config.PG_CONTAINER
PG_USER = _tle_config.PG_USER

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

    def assert_seeded(self, checks: list[dict] | None) -> None:
        """Prove the fixture is in the state the scenario CLAIMS, by reading the store.

        🔴 THREE SCENARIOS IN A ROW MEASURED SOMETHING OTHER THAN WHAT THEY CLAIMED, AND THE THIRD
        INVERTED THE READING OF THREE EXPERIMENTS. The `glossary_list_ai_suggestions` fixture was
        supposed to hold three entities with exactly ONE tagged 'ai-suggested', so that a truthful
        answer ("one, Mira Solene") and a lazy one ("three") differ. It never did:
        `glossary_propose_entities` already tags everything it creates `ai-suggested+assistant`,
        so the SQL step that "tagged one" changed nothing observable. All three were always in the
        review queue.

        Every conclusion drawn on top of that was therefore wrong in the same direction: "3
        suggested entries" was the CORRECT answer being scored as a fabrication, and two fixes
        were evaluated against it — one of them reverted on that basis.

        A seed is a claim about the world. This makes the claim checkable at the moment it is
        made, against the store, before a single turn runs — so a scenario that cannot
        discriminate fails loudly instead of producing confident nonsense for an hour.
        """
        for c in (checks or []):
            sql = self._substitute(c["query"])
            rows = oracle.db_query(c["db"], sql)
            got = (rows[0][0] if rows and rows[0] else "")
            if str(got).strip() != str(c["expect"]).strip():
                raise ProvisionError(
                    f"SEED ASSERTION FAILED: {c.get('why', c['query'])}\n"
                    f"    expected {c['expect']!r}, store says {got!r}\n"
                    f"    The fixture is not in the state this scenario claims, so whatever it "
                    f"measures is not what it says it measures.")

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
        """One deterministic setup call. `{book_id}` / `{chapter_id}` / `{project_id}` in any
        string value are substituted with this fixture's real ids.

        Two step kinds. `{"tool": ...}` is an MCP call. `{"rest": {...}}` is a direct service
        call, needed where the MCP tool cannot seed deterministically — `glossary_adopt_standards`
        mints a confirm_token and writes nothing at call time, so a fixture that used it would
        report "no entities were created — unknown kind: character" and look like a glossary bug.
        """
        if "wait" in step:
            # 🔴 A SEED STEP CAN BE ASYNC, AND A FIXTURE THAT DOES NOT WAIT SATISFIES ITS OWN
            # ASSERTION WHILE THE PRECONDITION IS STILL MISSING. Measured 2026-08-14:
            # `plan_propose_spec` creates the plan_run synchronously and produces the SPEC
            # artifact on a job. The seed asserted the run existed — true immediately — and
            # `plan_compile` then failed 3/3 with "no spec to compile". The tool was reached and
            # behaved correctly; the fixture was not ready, and nothing said so.
            #
            # Polls a SQL predicate until it returns the expected value or the timeout expires,
            # and RAISES on timeout. A wait that gives up quietly is the same defect one layer
            # further out.
            spec = self._substitute(step["wait"])
            deadline = time.monotonic() + float(spec.get("timeout", 90))
            want = str(spec.get("expect", "1")).strip()
            last = None
            while time.monotonic() < deadline:
                rows = oracle.db_query(spec["db"], spec["query"])
                last = str(rows[0][0]).strip() if rows and rows[0] else ""
                if last == want:
                    self.seeded.append({"wait": spec["query"][:80], "settled": last})
                    return
                time.sleep(float(spec.get("poll", 2)))
            raise ProvisionError(
                f"SEED WAIT TIMED OUT after {spec.get('timeout', 90)}s: {spec.get('why', spec['query'])}\n"
                f"    expected {want!r}, store still says {last!r}\n"
                f"    The async half of this fixture never landed, so the scenario would measure "
                f"a tool refusing a precondition that was never met.")
        if "sql" in step:
            # A third setup kind, for substrate NO tool can create. `glossary_list_ai_suggestions`
            # reads entities tagged 'ai-suggested' — a tag the extractor writes and no MCP tool
            # sets, so without this the scenario could only ever exercise the EMPTY case and
            # would report "the inbox is empty" as if that were the tool working. Setup only:
            # the thing under test is still the model's turn, never this.
            spec = self._substitute(step["sql"])
            oracle.db_query(spec["db"], spec["statement"])
            self.seeded.append({"sql": spec["db"], "ok": True})
            return
        if "rest" in step:
            spec = self._substitute(step["rest"])
            base = _tle_config.DOMAIN_BASE[spec["domain"]]
            r = httpx.request(spec.get("method", "POST"), f"{base}{spec['path']}",
                              headers=_tle_auth().bearer_header(),
                              json=spec.get("json") or {}, timeout=60)
            if r.status_code == 404:
                # 🔴 A 404 HERE IS AS LIKELY TO BE THE WRONG SERVICE AS THE WRONG PATH, and the
                # wrong service is the harder one to see. Measured 2026-08-14: DOMAIN_BASE
                # pointed "translation" at localhost:8207, which is catalog-service — and it
                # answers /health with 200, so nothing upstream could flag it. The Go services
                # all return a bare "ok" with no identity, so only a ROUTE probe distinguishes
                # them. Name both possibilities rather than letting this read as a bad path.
                raise ProvisionError(
                    f"SEED REST 404: {spec.get('method', 'POST')} {base}{spec['path']}\n"
                    f"    Either the path is wrong, OR DOMAIN_BASE[{spec['domain']!r}] = {base} "
                    f"points at a DIFFERENT service. Check by route, not by /health — several "
                    f"services answer /health with a bare 'ok' and cannot be told apart by it.")
            r.raise_for_status()
            self.seeded.append({"rest": spec, "status": r.status_code})
            return
        tool = step["tool"]
        args = self._substitute(step.get("args") or {})
        r = self.mcp.call(tool, args)
        self.seeded.append({"tool": tool, "args": args, "result": r})

    _STEP_REF = re.compile(r"\{step:(\d+):([A-Za-z0-9_.]+)\}")

    def _step_value(self, idx: int, path: str):
        """A value RETURNED by an earlier seed step, addressed as `{step:0:world.world_id}`.

        🔴 A SEED COULD NOT USE WHAT AN EARLIER SEED PRODUCED, AND THAT MADE WHOLE TOOL FAMILIES
        UNTESTABLE. The world/map tools are the case: `world_map_create` needs the `world_id`
        that `world_create` just minted, and `world_map_add_marker` needs the `map_id` from
        that. With only {book_id}/{chapter_id}/{project_id} available, the chain could not be
        expressed at all — the fixture had to be built by hand outside the scenario, which
        breaks the per-repeat isolation the whole harness rests on.

        Reads the RESULT the step recorded, so it cannot drift from what actually happened.
        Raises rather than substituting empty: a silently blank id produces a tool call that
        fails for a reason the evidence cannot explain.
        """
        try:
            rec = self.seeded[idx]
        except IndexError:
            raise ProvisionError(
                f"seed step {idx} has not run yet — {{step:{idx}:{path}}} can only reference an "
                f"EARLIER step (this fixture has {len(self.seeded)} so far)") from None
        cur = rec.get("result")
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                raise ProvisionError(
                    f"seed step {idx} returned no {path!r} — got keys "
                    f"{sorted(cur) if isinstance(cur, dict) else type(cur).__name__}. The seed "
                    f"cannot reference a value the tool did not return.")
            cur = cur[part]
        return cur

    def _substitute(self, obj):
        if isinstance(obj, str):
            def _ref(m):
                return str(self._step_value(int(m.group(1)), m.group(2)))
            obj = self._STEP_REF.sub(_ref, obj)
            return (obj.replace("{book_id}", self.book_id or "")
                       .replace("{chapter_id}", self.chapter_id or "")
                       .replace("{project_id}", self.project_id or ""))
        if isinstance(obj, dict):
            return {k: self._substitute(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._substitute(v) for v in obj]
        return obj

    # ── teardown ─────────────────────────────────────────────────────────────────────────
    def is_gone(self) -> bool:
        """Did teardown actually work? Asked of the DATABASE, not of the return value.

        A teardown that reports success and leaves the row is worse than one that fails loudly:
        the book stays on the account, `book_list` keeps offering it to the model, and the next
        batch inherits an extra write target that its store diff cannot see. 16 fixtures survived
        one batch exactly this way.
        """
        if not self.book_id:
            return True
        q = self.book_id.replace("'", "''")
        rows = oracle.db_query(BOOK_DB, f"SELECT 1 FROM books WHERE id='{q}'")
        return not rows

    def teardown(self) -> dict:
        """Delete ONLY this fixture, and only after re-reading the row to confirm it is ours.

        The check is deliberately made against the DATABASE rather than against this object's
        own memory of what it created. An in-process assertion only proves the object is
        self-consistent; re-reading proves the id on disk is a throwaway owned by the harness
        account. A DELETE in this loop already removed 10 rows where 3 were meant, and the
        difference was exactly this: trusting a remembered scope instead of confirming it.
        """
        # 🔴 ACCOUNT-SCOPED FIXTURES DO NOT DIE WITH THE BOOK. A seed that creates a WORLD leaves
        # it on the account: worlds are not book-scoped, so `purge_book` cannot see them and the
        # next batch inherits an extra, plausible, wrongly-scoped write target — the same shape
        # as the 16 leaked books, one scope up. Removed FIRST, name-guarded, and only ever the
        # ones this fixture minted.
        out = {}
        try:
            out["worlds"] = self._purge_worlds()
        except Exception as e:  # noqa: BLE001 — a world sweep must never mask a book teardown
            out["worlds_error"] = f"{type(e).__name__}: {e}"
        if not self.book_id:
            out.update({"deleted": 0, "reason": "no book was created"})
            return out
        out.update(purge_book(self.book_id))
        return out

    def _purge_worlds(self) -> list[str]:
        """Delete the TITLE_PREFIX-named worlds this fixture's seed created.

        Guarded the same way `purge_book` is: the name is re-read from the tool's own listing
        rather than trusted from memory, so this can only ever remove a throwaway.
        """
        made = [r["result"] for r in self.seeded
                if r.get("tool") == "world_create" and isinstance(r.get("result"), dict)]
        if not made:
            return []
        ids = []
        for r in made:
            w = r.get("world") if isinstance(r.get("world"), dict) else r
            wid, name = w.get("world_id") or w.get("id"), str(w.get("name") or "")
            if wid and name.startswith(TITLE_PREFIX):
                self.mcp.call("world_delete", {"world_id": str(wid)})
                ids.append(str(wid))
        return ids


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

    🔴 ONE ROUND TRIP PER DATABASE, NOT ONE PER TABLE. The first version issued a separate
    `docker exec psql` per table per pass — around 140 process spawns per database, so a single
    teardown took minutes. That is not merely slow: teardown runs in a `finally` while the next
    scenario is already provisioning, and a minutes-long teardown under concurrency is how 16
    fixtures survived one batch. The leak then handed the model a foreign book to write into on
    the following run. Batching the statements makes teardown fast enough to finish inside the
    window it actually has.

    FK order is unknowable up front, so the whole batch runs TWICE inside the same call and
    every statement is independent (`ON_ERROR_ROLLBACK=on`): a child blocked on the first pass is
    gone by the second, and one failing DELETE cannot abort the rest.
    """
    tables = [(t[0] if t else "") or "" for t in oracle.db_query(
        db, "SELECT table_name FROM information_schema.columns WHERE table_schema='public' "
            f"AND column_name='{column}' ORDER BY table_name")]
    tables = [t for t in tables if t]
    if not tables:
        return
    stmts = [f'DELETE FROM public."{t}" WHERE {column}=\'{value}\';' for t in tables]
    sql = "\\set ON_ERROR_ROLLBACK on\n" + "\n".join(stmts + stmts)
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", PG_USER, "-d", db, "-q", "-At"],
        input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180,
    )


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
