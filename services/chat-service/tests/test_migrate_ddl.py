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


def test_ddl_has_no_unguarded_alter_add_column():
    # every ALTER ... ADD COLUMN in the boot DDL must live inside a DO-block
    # guard — a bare one would crash the second boot. Cheap structural pin.
    for m in re.finditer(r"ALTER TABLE \w+ ADD COLUMN", DDL):
        preceding = DDL[: m.start()].rsplit("DO $$", 1)
        assert len(preceding) == 2 and "END $$" not in preceding[1], (
            f"unguarded ADD COLUMN at offset {m.start()}"
        )
