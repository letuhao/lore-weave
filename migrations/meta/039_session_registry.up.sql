-- 039_session_registry.up.sql
-- `DP-C8` — the capability STORE. The control plane records every capability it
-- issues, so that a capability can be VALIDATED and REVOKED rather than merely
-- minted and forgotten.
-- Source: docs/plans/2026-08-08-reality-layer-RUN-STATE.md slice `5B` (the
--         sealed fork, the amendment, and the PO decision behind it)
-- Written by: the control plane on bind / refresh / revoke, via
--   contracts/meta MetaWrite() (I8) -- never a direct INSERT.
-- Read by: capability validation on every SDK entry (DP-K2 check_live's
--   server-side counterpart), `GetSessionNode` (DP-C1), and the auto-dormant
--   scan (DP-Ch32).
--
-- @pii_sensitivity: none (opaque uuids, a service name, a node name and a hash;
--   no user reference at all -- a session here binds a SERVICE to a reality,
--   and the human-to-actor binding lives in 034_actor_control_binding)
-- @retention_class: operational
-- @retention_hot: 90d
-- @erasure_method: hard_delete
-- @legal_basis: legitimate_interest
--
-- ── THIS TABLE IS NOT NEW, IT WAS NEVER DECLARED ────────────────────────────
--
-- Phase 0 asked "what already models this concept" and the answer was that the
-- locked specs have been REFERENCING `session_registry` for months without ever
-- declaring it:
--
--   05_control_plane_spec.md:25   "CP serves the binding from its session
--                                  registry; SDKs cache for 300 s"
--   05_control_plane_spec.md:245  revocation = "remove the session's row from
--                                  session registry"
--   17_channel_lifecycle.md:119   `SELECT current_channel_id FROM
--                                  session_registry WHERE active = true`
--
-- and `DP-C2`'s enumerated list of CP tables does not include it. So this is a
-- spec GAP being closed, not a table being invented -- which is also why the
-- column names below are the spec's own (`active`, `current_channel_id`) rather
-- than better ones.
--
-- ── WHY THE META DATABASE ───────────────────────────────────────────────────
--
-- `DP-C2` says CP owns "its own small Postgres" and lists `reality_registry`
-- among its tables. `reality_registry` is in THIS database, so in this repo the
-- control plane's Postgres IS the meta database, and its session registry
-- belongs beside its reality registry. The longer argument for control data in
-- meta rather than per-reality is written out in 034_actor_control_binding and
-- is not repeated here; the short form is that a session is a CROSS-reality
-- question ("where is session S") and a per-reality home makes it a fan-out.
--
-- ── THE SECRET IS NOT STORED, ITS HASH IS ───────────────────────────────────
--
-- `capability_hash` is SHA-256 over the bearer secret. The control plane mints
-- the secret, hands it to the caller ONCE, and keeps only the digest -- so a
-- dump of this table, a stray log of a row, or a support engineer reading it
-- yields no usable capability. Validation hashes what was presented and looks
-- the digest up, which is why the column is UNIQUE: the digest IS the lookup
-- key, and two sessions sharing one are the confused-deputy state.
--
-- This is the property that makes `@pii_sensitivity: none` honest. A table
-- storing live bearer credentials in plaintext would be a credential store
-- whatever its PII classification said.
--
-- ── TENANCY ─────────────────────────────────────────────────────────────────
-- Tier: System. Every row is written by the control plane and by nothing else;
-- no regular user can create, read or mutate one, and there is no per-user
-- scope key because the subject is a SERVICE, not a human. The scope key for
-- fan-out queries is `reality_id`.
--
-- ── TWO SPEC COLUMNS DELIBERATELY ABSENT, AND WHAT WAKES THEM UP ────────────
--
--   `current_channel_id`  DP-Ch32's scan selects it. Nothing produces a
--                         ChannelId yet -- `move_session_to_channel` (DP-Ch9)
--                         is slice `5D`. A nullable UUID here would be a column
--                         that is NULL in every row, which is the orphan shape
--                         with a schema. Its sibling `DEFERRED_SESSION_FIELDS`
--                         in crates/dp/src/session.rs already reds when the
--                         producer lands.
--
--   `active`              DP-Ch32 writes `WHERE active = true`. It is NOT a
--                         column here and must not become one: liveness is
--                         `revoked_at IS NULL AND expires_at > now()`, and a
--                         stored boolean would be a second SSOT for a fact the
--                         clock already decides -- stale the moment a
--                         capability expires with nobody watching.
--
-- `DP-Ch32`'s query also joins `channels` (PER-REALITY) against this table
-- (META) in one statement, which cannot run once they are in two databases.
-- That is a real conflict, it belongs to `5D`, and it is tracked in the
-- RUN-STATE rather than silently patched here.

CREATE TABLE IF NOT EXISTS session_registry (
    -- The session the control plane minted. Matches `dp::SessionId`.
    session_id       UUID         NOT NULL,

    -- WHICH world. Names a reality in reality_registry; deliberately not an FK,
    -- for the same reason 034 gives -- a registry row may be archived while an
    -- expired session row is still within its retention window, and a cascade
    -- there would silently destroy the audit of who was connected.
    reality_id       UUID         NOT NULL,

    -- WHERE the session is pinned. `GetSessionNode` (DP-C1) answers from this
    -- column; it is the session-stickiness binding the transparent-routing path
    -- consults on a stale-gateway failure (DP-Ch41).
    node_id          TEXT         NOT NULL,

    -- WHO bound. The caller's service identity -- the field whose absence meant
    -- `bind` authenticated nothing: the control plane could confirm the reality
    -- existed and accepted commands, but never that anyone in particular was
    -- asking. Under mTLS (DP-C3) this is the peer certificate's subject; the
    -- column records what the transport asserted, so a capability is always
    -- attributable.
    --
    -- NOTE what this is NOT: it is not an authorization decision. `DP-C4`'s
    -- `tier_capability` is what authorizes a service for an aggregate set, and
    -- it has no producer in this repo yet (its rows come from "a deploy
    -- manifest calling CP's admin API", which does not exist). Shipping it
    -- empty would be a table nothing writes to. Tracked in the RUN-STATE.
    service_identity TEXT         NOT NULL,

    -- SHA-256 of the bearer secret. 32 bytes, never the secret itself.
    capability_hash  BYTEA        NOT NULL,

    issued_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- When the capability stops being valid. The control plane mints this as
    -- `now + TTL`; `RefreshCapability` moves it forward on an unexpired row.
    expires_at       TIMESTAMPTZ  NOT NULL,

    -- `DP-C8` says immediate revocation "removes the session's row". A
    -- timestamp instead, and the difference is deliberate: a DELETE destroys
    -- the record of the revocation along with the session, so the one event an
    -- operator most wants to see after an incident is the one thing not kept.
    -- Validation treats a revoked row exactly as it treats an absent one, so
    -- the observable behaviour `DP-C8` specifies is unchanged. Same choice, and
    -- for the same reason, as 034_actor_control_binding.revoked_at.
    revoked_at       TIMESTAMPTZ  NULL,

    PRIMARY KEY (session_id),

    -- The digest is the lookup key, so it must name at most one session.
    CONSTRAINT session_registry_capability_hash_unique UNIQUE (capability_hash),

    -- 32 bytes of SHA-256. A short digest here would be a truncation nobody
    -- notices until it collides.
    CONSTRAINT session_registry_hash_is_sha256 CHECK (
        octet_length(capability_hash) = 32
    ),

    -- A capability that expires before it is issued is not a grant. Without
    -- this, a clock fault or a negative TTL mints a row that is born dead and
    -- looks like a validation bug rather than a minting bug.
    CONSTRAINT session_registry_expires_after_issued CHECK (
        expires_at > issued_at
    ),

    CONSTRAINT session_registry_revoked_after_issued CHECK (
        revoked_at IS NULL OR revoked_at >= issued_at
    ),

    -- An empty service identity is the state this column exists to abolish: a
    -- capability nobody is accountable for. Refused in the SDK too, and here as
    -- well, because a check that lives only in one language is a check the next
    -- caller routes around.
    CONSTRAINT session_registry_service_identity_present CHECK (
        length(btrim(service_identity)) > 0
    ),

    CONSTRAINT session_registry_node_present CHECK (
        length(btrim(node_id)) > 0
    )
);

-- `DP-Ch32`'s auto-dormant scan and every "who is in this reality" question.
-- Not partial on liveness: `expires_at > now()` is not IMMUTABLE, so it cannot
-- appear in an index predicate -- a partial index here would have to be built
-- on `revoked_at IS NULL` alone, which is the weaker half of the predicate and
-- would read as if liveness were indexed when it is not.
CREATE INDEX IF NOT EXISTS idx_session_registry_reality
    ON session_registry (reality_id, expires_at DESC);

-- Revocation by service: the incident query. "Revoke everything <service> holds"
-- is the broad revocation `DP-C8` otherwise answers with a signing-key rotation.
CREATE INDEX IF NOT EXISTS idx_session_registry_service
    ON session_registry (service_identity)
    WHERE revoked_at IS NULL;

COMMENT ON TABLE session_registry IS
    'DP-C8 capability store. One row per capability the control plane issued: '
    'who asked (service_identity), for which reality, pinned to which node, and '
    'the SHA-256 of the bearer secret -- never the secret. Validation is a '
    'digest lookup, which is why revocation here is immediate and needs no '
    'signing-key rotation. Referenced by DP-C1/DP-C8/DP-Ch32 since before it '
    'was ever declared; this migration closes that gap.';
COMMENT ON COLUMN session_registry.capability_hash IS
    'SHA-256 of the bearer secret. The secret is handed to the caller once and '
    'never stored, so this table cannot leak a usable capability.';
COMMENT ON COLUMN session_registry.service_identity IS
    'The caller mTLS asserted (DP-C3). Attribution, NOT authorization -- '
    'DP-C4 tier_capability is the authorization table and has no producer yet.';
COMMENT ON COLUMN session_registry.revoked_at IS
    'DP-C8 says revocation removes the row; a timestamp is kept instead so the '
    'revocation itself survives. Validation treats revoked and absent alike.';
