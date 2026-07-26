"""W1 — the context_breakdown column migration follows the repo's idempotent
additive-ALTER convention (chat-service has no real-PG test harness; the DDL
is one string executed at every boot, so idempotency == every statement being
IF-NOT-EXISTS-guarded, which this pins for the new column)."""
from __future__ import annotations

import re

from app.db.migrate import DDL


def test_context_breakdown_column_is_guarded_additive_alter():
    # the ALTER is wrapped in the information_schema existence check → safe to
    # re-run at every boot (same DO-block pattern as tool_calls/branch_id).
    guard = re.search(
        r"IF NOT EXISTS \(SELECT 1 FROM information_schema\.columns "
        r"WHERE table_name='chat_messages' AND column_name='context_breakdown'\) THEN\s*"
        r"ALTER TABLE chat_messages ADD COLUMN context_breakdown JSONB;",
        DDL,
    )
    assert guard, "context_breakdown ALTER must be IF-NOT-EXISTS guarded"


def test_w3_compact_columns_are_guarded_additive_alters():
    # W3 — chat_sessions.compact_summary + compacted_before_seq follow the same
    # DO-block IF-NOT-EXISTS convention (re-runnable at every boot).
    assert re.search(
        r"IF NOT EXISTS \(SELECT 1 FROM information_schema\.columns "
        r"WHERE table_name='chat_sessions' AND column_name='compact_summary'\) THEN\s*"
        r"ALTER TABLE chat_sessions ADD COLUMN compact_summary TEXT;",
        DDL,
    ), "compact_summary ALTER must be IF-NOT-EXISTS guarded"
    assert re.search(
        r"IF NOT EXISTS \(SELECT 1 FROM information_schema\.columns "
        r"WHERE table_name='chat_sessions' AND column_name='compacted_before_seq'\) THEN\s*"
        r"ALTER TABLE chat_sessions ADD COLUMN compacted_before_seq INT;",
        DDL,
    ), "compacted_before_seq ALTER must be IF-NOT-EXISTS guarded"


def test_track_b_project_ids_column_is_guarded_additive_alter():
    # Track B B1(2) — chat_sessions.project_ids (multi-KG grounding set) follows
    # the same DO-block IF-NOT-EXISTS convention. UUID[] with a NOT NULL DEFAULT
    # '{}' so existing rows back-fill to the empty (legacy single-project) set.
    assert re.search(
        r"IF NOT EXISTS \(SELECT 1 FROM information_schema\.columns "
        r"WHERE table_name='chat_sessions' AND column_name='project_ids'\) THEN\s*"
        r"ALTER TABLE chat_sessions ADD COLUMN project_ids UUID\[\] NOT NULL DEFAULT '\{\}';",
        DDL,
    ), "project_ids ALTER must be IF-NOT-EXISTS guarded with an empty-array default"


def test_chat_ai_prefs_table_and_session_override_columns():
    # Chat & AI settings unify — new per-user prefs table + guarded session
    # override columns (spec docs/specs/2026-07-05-chat-ai-settings.md §4).
    assert "CREATE TABLE IF NOT EXISTS user_chat_ai_prefs" in DDL
    assert re.search(r"owner_user_id\s+UUID PRIMARY KEY", DDL), (
        "user_chat_ai_prefs must be keyed by owner_user_id (Per-user tenancy tier)"
    )
    for col, typ in (
        ("grounding_enabled", "BOOLEAN"),
        ("voice_overrides", "JSONB"),
        ("context_overrides", "JSONB"),
    ):
        assert re.search(
            r"IF NOT EXISTS \(SELECT 1 FROM information_schema\.columns "
            r"WHERE table_name='chat_sessions' AND column_name='" + col + r"'\) THEN\s*"
            r"ALTER TABLE chat_sessions ADD COLUMN " + col + r" " + typ + r";",
            DDL,
        ), f"{col} ALTER must be IF-NOT-EXISTS guarded"


def test_ddl_has_no_unguarded_alter_add_column():
    # The property is IDEMPOTENCY: the boot DDL re-runs on every start, so a bare
    # `ALTER TABLE t ADD COLUMN c` crashes the second boot. TWO forms satisfy that,
    # and both are in use here:
    #   1. wrapped in a DO-block that information_schema-checks the column first;
    #   2. Postgres' native `ADD COLUMN IF NOT EXISTS` (self-guarding, no block needed).
    # Only accepting (1) would flunk perfectly safe DDL, so match on the guarantee
    # rather than on one spelling of it.
    for m in re.finditer(r"ALTER TABLE \w+ ADD COLUMN(?! IF NOT EXISTS)", DDL):
        preceding = DDL[: m.start()].rsplit("DO $$", 1)
        assert len(preceding) == 2 and "END $$" not in preceding[1], (
            f"unguarded ADD COLUMN at offset {m.start()}: "
            f"{DDL[m.start():m.start() + 80]!r} — wrap it in a DO-block that checks "
            f"information_schema first, or use ADD COLUMN IF NOT EXISTS; a bare "
            f"ADD COLUMN crashes the next boot."
        )


def test_the_add_column_guard_is_a_live_gate():
    """Negative control — a guard that cannot fail is not a gate."""
    bare = "ALTER TABLE chat_messages ADD COLUMN oops TEXT;"
    assert re.search(r"ALTER TABLE \w+ ADD COLUMN(?! IF NOT EXISTS)", bare), (
        "the pattern must still catch a bare, unguarded ADD COLUMN"
    )
    native = "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS ok TEXT;"
    assert not re.search(r"ALTER TABLE \w+ ADD COLUMN(?! IF NOT EXISTS)", native), (
        "the pattern must treat native IF NOT EXISTS as already guarded"
    )
