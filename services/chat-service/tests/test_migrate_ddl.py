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


def test_ddl_has_no_unguarded_alter_add_column():
    # every ALTER ... ADD COLUMN in the boot DDL must live inside a DO-block
    # guard — a bare one would crash the second boot. Cheap structural pin.
    for m in re.finditer(r"ALTER TABLE \w+ ADD COLUMN", DDL):
        preceding = DDL[: m.start()].rsplit("DO $$", 1)
        assert len(preceding) == 2 and "END $$" not in preceding[1], (
            f"unguarded ADD COLUMN at offset {m.start()}"
        )
