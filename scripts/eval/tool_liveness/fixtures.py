"""Fixture factory — throwaway book + chapter + adopted ontology + seed entities
for a run, plus teardown. THE SAFETY BOUNDARY: destructive (Tier-W) and paid
probes may only touch ids this factory created; a probe never targets a real book.

Repo precedent for why this is mandatory: `kg-integration-tests-truncate-shared-dev-db`
— an ontology test once TRUNCATED the live dev DB. Every id here is minted fresh and
recorded; teardown deletes ONLY those recorded ids (scoped, never a blanket wipe).

Substrate is built by DIRECT MCP calls (no LLM) so probe state is deterministic.
"""
from __future__ import annotations

import uuid

import httpx

from . import config, oracle
from .auth import Auth
from .mcp_direct import MCPDirect

_SEED_CHAPTER = (
    "Aldric Vane climbed the black stair of Hollow Keep as the storm broke. "
    "At the top waited Mira Solene, keeper of the Ember Codex, who alone knew "
    "the way through the Sunless Marsh. 'The Codex must not fall to the Pale "
    "Regent,' she said, pressing the warm book into his hands."
)


class Fixture:
    def __init__(self) -> None:
        self.run_id = uuid.uuid4().hex[:8]
        self.mcp = MCPDirect()
        self.book_id: str | None = None
        self.chapter_id: str | None = None
        self.entities: list[dict] = []          # [{entity_id, name, kind}]
        self.extra_books: list[str] = []         # books created BY probes (for teardown)
        self.adopted_kinds: list[str] = []

    # ── build ────────────────────────────────────────────────────────────────
    def build(self) -> "Fixture":
        title = f"TLE-fixture-{self.run_id}"
        r = self.mcp.call("book_create", {
            "title": title, "original_language": "en",
            "description": "Tool-Liveness-Eval throwaway fixture — safe to delete.",
            "genre_tags": ["fantasy"],
        })
        self.book_id = r.get("book_id") or r.get("id")
        if not self.book_id:
            raise RuntimeError(f"fixture book_create returned no id: {r}")

        # Adopt the ontology via the REST /adopt edge (writes directly). The MCP
        # `glossary_adopt_standards` tool is deliberately NOT used here: it mints a
        # confirm_token and writes nothing at call time (a CD1 finding), so it can't
        # deterministically seed the fixture.
        self.adopted_kinds = ["character", "location", "item"]
        base = config.DOMAIN_BASE["glossary"]
        r = httpx.post(
            f"{base}/v1/glossary/books/{self.book_id}/adopt",
            headers=Auth().bearer_header(),
            json={"genres": ["universal"], "kinds": self.adopted_kinds},
            timeout=60,
        )
        r.raise_for_status()

        ch = self.mcp.call("book_chapter_bulk_create", {
            "book_id": self.book_id, "original_language": "en",
            "chapters": [{"title": "Chapter I — The Ember Codex",
                          "original_filename": "tle-ch01.txt", "content": _SEED_CHAPTER}]})
        ids = ch.get("chapter_ids") or [
            c.get("chapter_id") or c.get("id")
            for c in (ch.get("chapters") or ch.get("created") or [])]
        ids = [i for i in ids if i]
        self.chapter_id = ids[0] if ids else None

        # seed 3 entities directly (tier-A draft write) so read/delete probes have
        # known state; 3 so a delete probe can remove one and leave the fixture intact.
        seed = [{"kind": "character", "name": "Aldric Vane"},
                {"kind": "character", "name": "Mira Solene"},
                {"kind": "item", "name": "Ember Codex"}]
        self.mcp.call("glossary_propose_entities", {"book_id": self.book_id, "items": seed})
        # read the minted entity_ids back from the DB (independent of the write path)
        self._load_entities()
        return self

    def _load_entities(self) -> None:
        db = config.DOMAIN_DB["glossary"]
        rows = oracle.db_query(
            db, "SELECT entity_id, cached_name FROM glossary_entities "
                f"WHERE book_id='{self.book_id}' AND alive=true ORDER BY created_at")
        self.entities = [{"entity_id": r[0], "name": r[1]} for r in rows if r and r[0]]

    # ── tier-A approval allowlist (so auto-writes don't suspend on the card) ───
    # Spec §4 Tier-A note: pre-allowlist `user_tool_approvals` so the run doesn't
    # stall. `user_tool_approvals(user_id, tool_name)` lives in loreweave_chat.
    def allowlist_tools(self, tools: list[str]) -> None:
        db = "loreweave_chat"
        self._allowlisted = list(tools)
        for t in tools:
            oracle.db_query(
                db, "INSERT INTO user_tool_approvals (user_id, tool_name) VALUES "
                    f"('{config.USER_ID}', '{t}') ON CONFLICT DO NOTHING")

    def _clear_allowlist(self) -> None:
        for t in getattr(self, "_allowlisted", []):
            try:
                oracle.db_query(
                    "loreweave_chat", "DELETE FROM user_tool_approvals WHERE "
                    f"user_id='{config.USER_ID}' AND tool_name='{t}'")
            except Exception:
                pass

    def spare_entity(self) -> dict | None:
        """An entity a destructive probe may delete (never the last one)."""
        self._load_entities()
        alive = [e for e in self.entities]
        return alive[-1] if len(alive) >= 1 else None

    # ── teardown (scoped to recorded ids ONLY) ────────────────────────────────
    def teardown(self) -> dict:
        self._clear_allowlist()
        if config.KEEP_FIXTURES:
            return {"kept": True, "book_id": self.book_id, "extra_books": self.extra_books}
        book_db = config.DOMAIN_DB["book"]
        gloss_db = config.DOMAIN_DB["glossary"]
        deleted = {"books": 0, "chapters": 0, "glossary_rows": 0}
        book_ids = [b for b in ([self.book_id] + self.extra_books) if b]
        for bid in book_ids:
            q = bid.replace("'", "''")
            try:
                oracle.db_query(book_db, f"DELETE FROM chapters WHERE book_id='{q}'")
                oracle.db_query(book_db, f"DELETE FROM books WHERE id='{q}'")
                deleted["books"] += 1
            except Exception:
                pass
            try:
                oracle.db_query(gloss_db, f"DELETE FROM glossary_entities WHERE book_id='{q}'")
            except Exception:
                pass
        deleted["scoped_ids"] = book_ids
        return deleted
