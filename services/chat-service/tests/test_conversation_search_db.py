"""T6 D6 — conversation_search recovery engine against REAL Postgres.

The ILIKE multilingual substring + session/owner/branch scoping is SQL a mock can't
validate. Marked xdist_group("pg") (CLAUDE.md — shared dev DB serialized). Skips
cleanly when the dev DB is unreachable.
"""
import os
import uuid

import asyncpg
import pytest

from app.db.conversation_search import (
    CONVERSATION_SEARCH_NAME,
    CONVERSATION_SEARCH_TOOL,
    ConversationHit,
    run_conversation_search,
    search_session_messages,
)

pytestmark = pytest.mark.xdist_group("pg")


def test_tool_def_is_wire_standard():
    """The agent-facing schema the tool-loop will advertise (ready-to-wire): a
    self-describing function tool, `query` required string, `limit` int, closed
    (additionalProperties False). No DB — a pure contract check."""
    fn = CONVERSATION_SEARCH_TOOL
    assert fn["type"] == "function"
    assert fn["function"]["name"] == CONVERSATION_SEARCH_NAME == "conversation_search"
    params = fn["function"]["parameters"]
    assert params["type"] == "object"
    assert params["required"] == ["query"]
    assert params["properties"]["query"]["type"] == "string"
    assert params["properties"]["limit"]["type"] == "integer"
    assert params["additionalProperties"] is False

DSN = os.environ.get("CHAT_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")
OWNER = uuid.UUID("019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")  # claude-test


@pytest.fixture
async def pool_and_session():
    try:
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    except Exception:
        pytest.skip("dev postgres unreachable")
    sid = uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO chat_sessions (session_id, owner_user_id, model_source, model_ref) "
            "VALUES ($1, $2, 'user_model', $3)",
            sid, OWNER, uuid.uuid4(),
        )

        async def _msg(seq, role, content, *, branch=0, err=False, owner=OWNER):
            await c.execute(
                "INSERT INTO chat_messages (message_id, session_id, owner_user_id, role, "
                "content, sequence_num, branch_id, is_error) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                uuid.uuid4(), sid, owner, role, content, seq, branch, err,
            )

        # a conversation with load-bearing facts across turns (VN + CJK names)
        await _msg(1, "user", "My protagonist is Lâm Uyển; her blade is the Crimson Codex.")
        await _msg(2, "assistant", "Noted: Lâm Uyển wields the Crimson Codex.")
        await _msg(3, "user", "万古神帝 is the final antagonist.")
        await _msg(4, "assistant", "(called story_search)")  # no fact
        await _msg(5, "user", "unrelated small talk here", err=True)  # error row: excluded
        await _msg(6, "user", "on another branch", branch=1)  # other branch: excluded
        await _msg(7, "user", "the ritual is 80% complete")  # literal % for the escape test
    try:
        yield pool, sid
    finally:
        async with pool.acquire() as c:
            await c.execute("DELETE FROM chat_sessions WHERE session_id = $1", sid)
        await pool.close()


async def test_recovers_vn_name_with_snippet(pool_and_session):
    pool, sid = pool_and_session
    hits = await search_session_messages(
        pool, session_id=str(sid), owner_user_id=str(OWNER), query="Lâm Uyển")
    assert len(hits) == 2  # user turn 1 + assistant turn 2
    assert [h.sequence_num for h in hits] == [1, 2]  # oldest-first
    assert "Lâm Uyển" in hits[0].snippet


async def test_recovers_cjk_name(pool_and_session):
    pool, sid = pool_and_session
    hits = await search_session_messages(
        pool, session_id=str(sid), owner_user_id=str(OWNER), query="万古神帝")
    assert len(hits) == 1 and hits[0].sequence_num == 3


async def test_case_insensitive(pool_and_session):
    pool, sid = pool_and_session
    hits = await search_session_messages(
        pool, session_id=str(sid), owner_user_id=str(OWNER), query="crimson codex")
    assert {h.sequence_num for h in hits} == {1, 2}


async def test_excludes_error_and_other_branch_and_empty_query(pool_and_session):
    pool, sid = pool_and_session
    # the error row (seq 5) and other-branch row (seq 6) never surface
    assert await search_session_messages(
        pool, session_id=str(sid), owner_user_id=str(OWNER), query="small talk") == []
    assert await search_session_messages(
        pool, session_id=str(sid), owner_user_id=str(OWNER), query="another branch") == []
    # empty query short-circuits
    assert await search_session_messages(
        pool, session_id=str(sid), owner_user_id=str(OWNER), query="   ") == []


async def test_tenancy_other_owner_sees_nothing(pool_and_session):
    pool, sid = pool_and_session
    other = uuid.uuid4()
    assert await search_session_messages(
        pool, session_id=str(sid), owner_user_id=str(other), query="Lâm Uyển") == []


async def test_limit_clamped(pool_and_session):
    pool, sid = pool_and_session
    hits = await search_session_messages(
        pool, session_id=str(sid), owner_user_id=str(OWNER), query="Lâm Uyển", limit=1)
    assert len(hits) == 1


async def test_like_metachars_matched_literally(pool_and_session):
    pool, sid = pool_and_session
    # "80%" must match the literal "80% complete" turn (not treat % as a wildcard)
    hits = await search_session_messages(
        pool, session_id=str(sid), owner_user_id=str(OWNER), query="80%")
    assert [h.sequence_num for h in hits] == [7]
    # an underscore is literal too: "8_" must NOT match "80" (no such literal substring)
    assert await search_session_messages(
        pool, session_id=str(sid), owner_user_id=str(OWNER), query="8_") == []


# ── run_conversation_search — the tool-loop SHAPER (no DB; monkeypatched) ─────
# The engine above is validated against real PG; these prove the LLM-client-first
# result shaping the tool loop feeds back: never a silent no-op, a DB blip surfaces.

async def test_shaper_empty_query_prompts_for_input():
    out = await run_conversation_search(
        None, session_id="s", owner_user_id="o", args={"query": "   "})
    assert out == {"query": "", "count": 0, "hits": [],
                   "message": "Provide the exact name or phrase to search for."}


async def test_shaper_no_hits_returns_distinct_message(monkeypatch):
    async def _empty(*a, **k):
        return []
    monkeypatch.setattr(
        "app.db.conversation_search.search_session_messages", _empty)
    out = await run_conversation_search(
        None, session_id="s", owner_user_id="o", args={"query": "Zorro"})
    assert out["count"] == 0 and out["hits"] == []
    assert "Zorro" in out["message"]  # names the miss so the agent can conclude


async def test_shaper_shapes_hits(monkeypatch):
    async def _hits(*a, **k):
        return [ConversationHit(3, "user", "…Lâm Uyển wields the Crimson Codex…")]
    monkeypatch.setattr(
        "app.db.conversation_search.search_session_messages", _hits)
    out = await run_conversation_search(
        None, session_id="s", owner_user_id="o", args={"query": "Lâm Uyển", "limit": 5})
    assert out["count"] == 1
    assert out["hits"] == [
        {"turn": 3, "role": "user", "snippet": "…Lâm Uyển wields the Crimson Codex…"}]


async def test_shaper_db_error_surfaces_not_silent(monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("pg down")
    monkeypatch.setattr(
        "app.db.conversation_search.search_session_messages", _boom)
    out = await run_conversation_search(
        None, session_id="s", owner_user_id="o", args={"query": "x"})
    # a DB blip must NOT read as "not discussed" — it's an explicit error
    assert "error" in out and "pg down" in out["error"]
    assert "hits" not in out


async def test_shaper_bad_limit_falls_back_to_default(monkeypatch):
    seen = {}

    async def _cap(pool, *, session_id, owner_user_id, query, limit):
        seen["limit"] = limit
        return []
    monkeypatch.setattr(
        "app.db.conversation_search.search_session_messages", _cap)
    await run_conversation_search(
        None, session_id="s", owner_user_id="o",
        args={"query": "x", "limit": "not-an-int"})
    assert seen["limit"] == 8
