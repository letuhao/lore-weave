"""D-S5BEVAL-LEARNING-OUTBOX — DDL source-lock for the transactional outbox.

learning-service applies a single idempotent DDL string at startup (no Alembic, no
real-PG unit fixture here — the live-smoke exercises the real CREATE). This locks
that the `outbox_events` table + the columns worker-infra's relay SELECTs/UPDATEs
stay present, so a refactor can't silently drop the table the campaign eval-score
emit now depends on.
"""
from __future__ import annotations

from app.db.migrate import DDL


def test_ddl_defines_outbox_events_with_relay_contract_columns():
    assert "CREATE TABLE IF NOT EXISTS outbox_events" in DDL
    # The exact columns worker-infra/outbox_relay.go reads (SELECT) + writes (UPDATE).
    for col in (
        "id",
        "aggregate_type",
        "aggregate_id",
        "event_type",
        "payload",
        "created_at",
        "published_at",
        "retry_count",
        "last_error",
    ):
        assert col in DDL, f"outbox_events missing relay-contract column {col!r}"
    # The pending-relay partial index (the relay scans WHERE published_at IS NULL).
    assert "idx_outbox_pending" in DDL
    assert "WHERE published_at IS NULL" in DDL
    # aggregate_type defaults to the stream the campaign projection consumes
    # (relay stream = loreweave:events:<aggregate_type>).
    assert "DEFAULT 'translation_eval'" in DDL
