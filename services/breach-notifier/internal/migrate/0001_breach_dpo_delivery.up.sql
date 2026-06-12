-- breach-notifier 0001 — DPO-notice delivery-confirmed record
-- (106 / D-BREACH-DELIVERY-CONSUMER). Owned by services/breach-notifier in its OWN
-- database (NOT meta, NOT per-reality). One row per incident_id: the durable proof
-- that the GDPR Art.33 DPO notice was DELIVERED (delivered_at) — distinct from the
-- emitted obligation. status enum is delivered|failed; attempts counts tries;
-- last_error holds the latest failure; delivered_at is set + retained on success.
CREATE TABLE IF NOT EXISTS breach_dpo_delivery (
    incident_id   TEXT        NOT NULL PRIMARY KEY,
    subject       TEXT        NOT NULL,
    deadline      TIMESTAMPTZ NOT NULL,
    channel       TEXT        NOT NULL,
    status        TEXT        NOT NULL,
    attempts      INTEGER     NOT NULL DEFAULT 0,
    last_error    TEXT        NOT NULL DEFAULT '',
    delivered_at  TIMESTAMPTZ NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT breach_dpo_delivery_status_enum CHECK (status IN ('delivered', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_breach_dpo_delivery_status ON breach_dpo_delivery (status);
