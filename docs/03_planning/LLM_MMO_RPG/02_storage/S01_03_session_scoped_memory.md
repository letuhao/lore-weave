<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: S01_03_session_scoped_memory.md
byte_range: 203334-221774
sha256: 0aac8c0d71f5bdb6b7aba8c5fdd6a292aff874cbd75ada6aa091737d171fe273
generated_by: scripts/chunk_doc.py
-->

## 12S. Security Review — S1/S2/S3 Resolutions (2026-04-24)

**Origin:** Security Engineer / Threat Modeler adversarial review. S2 + S3 reshaped via user insight — capability-based data model replaces access-control-filter model. S3 extends with full Option A privacy tier system.

Fundamental shift: **knowledge flows through session participation**, not through post-hoc filtering. Cross-PC leak becomes structurally impossible.

### 12S.1 S1 — Reality creation rate limit (DOS prevention)

**Threat:** unbounded reality creation (locked MV4-b "V1 no quota") exhausts Postgres DB allocation per shard. Compromised account spawns 10K realities.

**Mechanism:** per-user rate limit + active-reality cap. Enforced at reality-creation request.

```sql
-- In meta registry
CREATE TABLE user_reality_creation_quota (
  user_id              UUID PRIMARY KEY,
  active_reality_count INT NOT NULL DEFAULT 0,
  creations_last_hour  INT NOT NULL DEFAULT 0,
  hour_window_start    TIMESTAMPTZ NOT NULL,
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Rate limiting enforced at creation request:
-- 1. Check creations_last_hour < max_per_hour
-- 2. Check active_reality_count < max_active
-- 3. If exceeded: 429 Too Many Requests
-- 4. Else: increment counters, proceed with creation
-- 5. On reality archive/close: decrement active_reality_count
```

**Config:**
```
reality.creation.rate_limit_per_user_per_hour = 5
reality.creation.max_active_per_user = 50
reality.creation.tier_multiplier = 1.0          # platform tiers can scale up
```

Audit log every creation attempt including rejections (for abuse pattern detection).

**V1 scope:** hard enforcement from launch. No grace period. Rate-limit rejections surface to user as explicit error with retry-after hint.

### 12S.2 S2 — Session-scoped memory model (REPLACES §12H per-pair)

**Design philosophy:** NPCs only have knowledge they acquired through session participation. No global query → filter model. Cross-PC leak impossible by construction.

**Supersedes** the per-pair `npc_pc_memory` aggregate from §12H.2 (second table). §12H.1 (core NPC aggregate) unchanged. §12H.3-6 (bounded growth, size enforcement, decay, lazy loading) concepts preserved but scope shifts from pairs to sessions.

#### 12S.2.1 Event visibility schema (extends §4.2 events)

```sql
ALTER TABLE events
  ADD COLUMN session_id          UUID,             -- NULL for non-session events
  ADD COLUMN visibility           TEXT NOT NULL DEFAULT 'public_in_session',
  ADD COLUMN whisper_target_type TEXT,             -- 'pc' | 'npc' | NULL
  ADD COLUMN whisper_target_id   UUID;

-- Constraint: whisper requires target
ALTER TABLE events
  ADD CONSTRAINT whisper_has_target
    CHECK (visibility != 'whisper' OR (whisper_target_type IS NOT NULL AND whisper_target_id IS NOT NULL));
```

**Visibility semantics (enum):**

| Value | Who perceives this event |
|---|---|
| `public_in_session` | All current participants of `session_id` |
| `whisper` | Only `whisper_target_id` + the actor (both directions) |
| `npc_internal` | Only the emitting NPC (internal thought, reflection) |
| `region_broadcast` | All sessions in region (propagated via R7 event-handler) |
| `reality_broadcast` | All sessions in reality (propagated via R7 event-handler) |

#### 12S.2.2 Session participants tracking

```sql
CREATE TABLE session_participants (
  session_id         UUID NOT NULL,
  reality_id         UUID NOT NULL,
  participant_type   TEXT NOT NULL,           -- 'pc' | 'npc'
  participant_id     UUID NOT NULL,
  joined_at          TIMESTAMPTZ NOT NULL,
  left_at            TIMESTAMPTZ,              -- NULL = still in session
  PRIMARY KEY (session_id, participant_type, participant_id)
);

CREATE INDEX session_participants_by_entity
  ON session_participants (participant_type, participant_id, session_id);
```

Session is a first-class entity. Participation is the capability to receive session events.

#### 12S.2.3 NPC session memory (replaces npc_pc_memory)

```sql
CREATE TABLE npc_session_memory_projection (
  npc_id                UUID NOT NULL,
  session_id            UUID NOT NULL,
  reality_id            UUID NOT NULL,
  aggregate_id          UUID NOT NULL,            -- uuidv5('npc_session_memory', npc_id || session_id)
  summary               TEXT,                      -- LLM-compacted session summary
  facts                 JSONB NOT NULL DEFAULT '[]',  -- structured facts from THIS session only
  session_started_at    TIMESTAMPTZ,
  session_ended_at      TIMESTAMPTZ,
  interaction_count     INT NOT NULL DEFAULT 0,
  last_event_version    BIGINT NOT NULL,
  archive_status        TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'faded' | 'summary_only' | 'archived'
  PRIMARY KEY (npc_id, session_id)
);
CREATE INDEX ON npc_session_memory_projection (archive_status, session_ended_at);

-- Embedding separate (R8-L6 pattern preserved)
CREATE TABLE npc_session_memory_embedding (
  npc_id        UUID NOT NULL,
  session_id    UUID NOT NULL,
  embedding     vector(1536),
  content_hash  TEXT NOT NULL,
  updated_at    TIMESTAMPTZ,
  PRIMARY KEY (npc_id, session_id)
);
CREATE INDEX npc_session_memory_embedding_hnsw
  ON npc_session_memory_embedding USING hnsw (embedding vector_cosine_ops);
```

**Aggregate type:** `npc_session_memory`. One aggregate per (npc_id, session_id). Event sourcing applies — events update aggregate, snapshots every 500 events or 1 session-end.

**Lifecycle:**
- Session active: memory aggregate updated in real-time as events flow
- Session ended: final compaction via LLM summary
- Cold decay (§12H.5 pattern applied to sessions instead of pairs):
  - 0-30 days: full retention (summary + facts + embedding)
  - 30-90 days: keep summary + embedding, drop facts
  - 90-365 days: summary only
  - 365+ days: archive to MinIO

Config:
```
npc_memory.session.max_facts_per_session = 100
npc_memory.session.summary_rewrite_every_events = 50
npc_memory.session.cold_decay_fact_drop_days = 30
npc_memory.session.cold_decay_embedding_drop_days = 90
npc_memory.session.archive_days = 365
```

#### 12S.2.4 NPC relationship (new — derived stance)

Relationship CAPTURES HOW Elena feels, NOT what Elena KNOWS. Derived from session interactions; doesn't leak knowledge.

```sql
CREATE TABLE npc_pc_relationship_projection (
  npc_id                UUID NOT NULL,
  other_entity_id       UUID NOT NULL,
  other_entity_type     TEXT NOT NULL,            -- 'pc' | 'npc'
  reality_id            UUID NOT NULL,
  trust_level           INT NOT NULL DEFAULT 0,    -- -100 to +100
  familiarity_count     INT NOT NULL DEFAULT 0,   -- sessions shared
  last_session_id       UUID,                      -- most recent interaction session
  last_interaction_at   TIMESTAMPTZ,
  relationship_labels   TEXT[] NOT NULL DEFAULT '{}',  -- 'friend', 'rival', 'ally', 'debt_holder', ...
  last_event_version    BIGINT NOT NULL,
  PRIMARY KEY (npc_id, other_entity_id)
);
CREATE INDEX ON npc_pc_relationship_projection (npc_id, familiarity_count DESC);
```

**Projection updater** (R7 event-handler side-effect): on session-end events, iterate pairs of participants, update relationship derived from session outcome.

Relationship leaks MINIMAL info (trust/familiarity counts) — not sensitive content.

#### 12S.2.5 Prompt-assembly query contract

When NPC Elena responds in session S, capability-based event access:

```sql
-- Elena's "perceived events" for prompt context
WITH elena_sessions AS (
  -- All sessions Elena participated in (including ancestor realities via cascade)
  SELECT DISTINCT session_id, reality_id
  FROM session_participants
  WHERE participant_type = 'npc'
    AND participant_id = 'elena_id'
    AND (left_at IS NULL OR left_at > :as_of_time)
    -- Cascade extends to ancestor realities (§12M severance filter applies)
),
elena_perceived_events AS (
  -- Session events Elena can see
  SELECT e.* FROM events e
  INNER JOIN elena_sessions es USING (session_id)
  WHERE e.reality_id = es.reality_id
    AND (
      -- Public in session
      e.visibility = 'public_in_session'
      -- OR whisper TO Elena
      OR (e.visibility = 'whisper'
          AND e.whisper_target_type = 'npc'
          AND e.whisper_target_id = 'elena_id')
      -- OR Elena's own events (actions, internal thoughts)
      OR (e.actor_type = 'npc' AND e.actor_id = 'elena_id')
    )
    -- Respect privacy_level + cascade_policy (§12S.3)
    AND NOT (
      e.reality_id != :current_reality_id
      AND (e.cascade_policy = 'not_inherit' OR e.privacy_level != 'normal')
    )
  UNION ALL
  -- Region/reality broadcasts for regions Elena was in
  SELECT e.* FROM events e
  WHERE e.visibility IN ('region_broadcast', 'reality_broadcast')
    AND e.reality_id = :current_reality_id
    AND e.region_id IN (regions Elena was present in during broadcast)
)
SELECT * FROM elena_perceived_events ORDER BY created_at;
```

**Key properties:**
- Elena cannot read events from sessions she wasn't in
- Elena cannot read whispers not targeting her
- Elena cannot read other NPCs' internal thoughts
- Cross-PC leak: impossible (structural)
- Cross-reality privacy: respected (S3 cascade_policy + privacy_level)

**Enforcement:** this query is canonical, implemented in `contracts/meta/` or reality-DB query layer. All LLM prompt assembly goes through it. No application-level filter → no filter bugs.

#### 12S.2.6 Supersession of §12H per-pair model

**§12H.2 (per-pair NPC-PC memory aggregate): SUPERSEDED** by this session-scoped model.

Retained from §12H:
- §12H.1 NPC core aggregate (mood, location, core_beliefs, flexible_state) — unchanged
- §12H.3 size enforcement + auto-compaction — applies to session memories
- §12H.4 bounded memory per aggregate — max_facts_per_session instead of max_facts_per_pc
- §12H.5 cold decay — applies to sessions (30d/90d/365d)
- §12H.6 lazy loading — loads current session's memories + relationships
- §12H.7 embedding storage separation — applies to session-scoped embedding table

Superseded:
- ~~npc_pc_memory_projection~~ → `npc_session_memory_projection` + `npc_pc_relationship_projection`
- ~~npc_pc_memory_embedding~~ → `npc_session_memory_embedding`
- ~~Per-pair lazy loading~~ → per-session + active-relationships loading

Migration: no code written yet; §12H updated in place via this §12S.

### 12S.3 S3 — Cascade policy + privacy level (full tier)

#### 12S.3.1 Cascade policy

```sql
ALTER TABLE events
  ADD COLUMN cascade_policy TEXT NOT NULL DEFAULT 'inherit';
-- 'inherit' (default) | 'not_inherit' | 'expire_at_fork' (V2+)
```

Semantics:
- `inherit`: descendants see event via cascade read
- `not_inherit`: event visible only in originating reality; descendants don't see
- `expire_at_fork`: reserved V2+

**Cascade-read query updated** (builds on §12M severance filtering):

```sql
-- Events accessible from current reality including ancestor cascade
SELECT * FROM events
WHERE reality_id IN (current_reality ∪ ancestors_up_to_fork_or_severance)
  AND NOT (
    -- Filter out not_inherit events from ancestor realities
    reality_id != :current_reality_id AND cascade_policy = 'not_inherit'
  )
  AND NOT (
    -- Filter out sensitive+ privacy events from ancestors
    reality_id != :current_reality_id AND privacy_level != 'normal'
  )
```

#### 12S.3.2 Privacy level — full Option A tier

```sql
ALTER TABLE events
  ADD COLUMN privacy_level TEXT NOT NULL DEFAULT 'normal',
  ADD COLUMN privacy_metadata JSONB;
-- 'normal' | 'sensitive' | 'confidential'
```

**Tier definitions (V1 enforcement):**

| Tier | Retention (hot) | Admin access | Cascade_policy forced | Force-propagate (M4-D3) | Encryption (V2+) |
|---|---|---|---|---|---|
| `normal` | Per event_type (R1-L3) | Tier 1-2 admin | Any (default `inherit`) | Allowed | Standard at-rest |
| `sensitive` | 30 days max | Tier 2 + alert on access | Forced to `not_inherit` | **Blocked** | Standard V1; per-event V2+ |
| `confidential` | 7 days max | Tier 3 + double-approval | Forced to `not_inherit` | **Blocked** | Per-event key (V2+) |

**V1 enforcement:**
- Force-propagate refuses on `privacy_level != 'normal'`
- Cascade auto-constrained: `privacy_level != 'normal'` → `cascade_policy = 'not_inherit'` (overrides default)
- Tier-based retention (via R1-L3 discipline + per-tier override)
- Admin access enforced via R13 three-tier classification (S5 — lock pending)

**V2+ enforcement:**
- Per-event encryption (MinIO SSE-C per tier for `confidential`)
- Retention hard-enforced at archive layer
- Compliance export workflows

#### 12S.3.3 Integrity constraint

```sql
-- privacy_level + cascade_policy consistency
ALTER TABLE events ADD CONSTRAINT privacy_cascade_consistency
  CHECK (
    privacy_level = 'normal' OR cascade_policy = 'not_inherit'
  );

-- Rate-limit flags for admin-level overrides
-- (M4-D3 force-propagate must reject if any event has privacy_level != 'normal';
--  enforced at application layer, not DB constraint)
```

#### 12S.3.4 Player-facing UX

Whisper command variants:

| Command | visibility | cascade_policy | privacy_level |
|---|---|---|---|
| `/whisper <target>` (default) | whisper | inherit | normal |
| `/whisper-private <target>` (UI checkbox "Private across timelines") | whisper | not_inherit | normal |
| `/whisper-sensitive <target>` (UI checkbox "Sensitive") | whisper | not_inherit | sensitive |
| `/whisper-confidential <target>` (power user, retention warning shown) | whisper | not_inherit | confidential |

UI discloses retention + cascade implications before player commits.

#### 12S.3.5 Fork UX warning

Before creating a fork of current reality, UI shows:

```
⚠ Forking this reality

Players in the new reality will inherit:
  • All public session events (X events)
  • NPC memories + relationships

They will NOT inherit:
  • Private whispers (Y events) — cascade_policy='not_inherit'
  • Sensitive content (Z events) — privacy_level='sensitive'
  • Confidential content (W events) — privacy_level='confidential'

Proceed? [Yes] [No]
```

Informed consent before fork.

### 12S.4 Cross-cutting impact

| Affected section | Change |
|---|---|
| §4.2 events schema | +5 columns: session_id, visibility, whisper_target_{type,id}, cascade_policy, privacy_level, privacy_metadata |
| §5.2 projections | +3 tables (session_participants, npc_session_memory, npc_pc_relationship); 2 tables DROPPED (npc_pc_memory × 2); 1 new embedding table (session-scoped) |
| §12H.2 | Per-pair aggregate SUPERSEDED (cross-ref to §12S.2) |
| §12M severance | Cascade filter extended for cascade_policy + privacy_level |
| §12G.7 | Whisper semantics respected (already NPC single-session) |
| R13 admin tiers | S5 three-tier classification becomes V1 prerequisite (previously proposed) |
| M4-D3 force-propagate | Refuses on `privacy_level != 'normal'` |
| R1-L3 retention | Tier-overrides per privacy_level |
| R5-L2 user deletion | Cascade respects privacy (sensitive/confidential get scrubbed faster) |
| G1/G2/G3 testing | Add S2 capability-based access test cases |

### 12S.5 Implementation ordering

**V1 launch (mandatory):**
- Event schema additions (session_id, visibility, whisper_target, cascade_policy, privacy_level, privacy_metadata)
- session_participants table + maintenance via session lifecycle events
- npc_session_memory_projection replacing npc_pc_memory
- npc_pc_relationship_projection derived from session events
- Prompt-assembly canonical query in `contracts/meta/`
- Rate limit enforcement (S1)
- Fork UX warning dialog
- Force-propagate rejection on privacy_level != 'normal'
- Cascade auto-constrain on privacy_level != 'normal'

**V1 + 30 days:**
- Tier-based retention cron (sensitive 30d / confidential 7d)
- ~~Admin access tier gates (requires S5 three-tier admin classification lock first)~~ **→ MOVED TO V1** (S5 ImpactClass unblocks this 2026-04-24; see [§12U.7](#12u7-interaction-with-s3-privacy-access))
- Fork UX counts + filters

**V2+:**
- Per-event encryption for confidential tier (MinIO SSE-C)
- Compliance export workflows
- `expire_at_fork` cascade_policy
- Advanced privacy_metadata field usage

### 12S.6 Config consolidated

```
# S1 rate limits
reality.creation.rate_limit_per_user_per_hour = 5
reality.creation.max_active_per_user = 50
reality.creation.tier_multiplier = 1.0

# S2 session memory (replaces §12H per-pair config)
npc_memory.session.max_facts_per_session = 100
npc_memory.session.summary_rewrite_every_events = 50
npc_memory.session.cold_decay_fact_drop_days = 30
npc_memory.session.cold_decay_embedding_drop_days = 90
npc_memory.session.archive_days = 365

# S3 privacy tier retention
privacy.tier.normal.retention_days = null   # inherits per-event-type retention (R1-L3)
privacy.tier.sensitive.retention_days = 30
privacy.tier.confidential.retention_days = 7
privacy.tier.confidential.admin_access_requires_double_approval = true
privacy.encryption.enabled = false   # V1; V2+ true for confidential
```

### 12S.7 What this resolves + residuals

✅ **Resolved:**
- S1: reality creation DOS — rate limit + active cap
- S2: cross-PC memory leak — structurally impossible via session-scoped model
- S3: cross-reality privacy — cascade_policy opt-in + privacy tier full system

✅ **Additional wins:**
- Realistic epistemics (NPCs know what they experienced)
- Privacy by construction (no filter bugs possible)
- GDPR-friendlier (tier retention, faster scrubbing for sensitive)
- Compliance-ready hooks (privacy_metadata JSONB for future)
- Defense in depth (visibility + cascade + privacy_level = three axes)

⚠️ **Residuals (accept as documented):**
- Relationship stance leaks minimal info (trust/familiarity counts) — de minimis
- Session participation records leak metadata (Elena + Alice were in session X) — acceptable game-world info
- LLM output may leak knowledge via persuasion / jailbreak (05_LLM_SAFETY_LAYER concern)
- V1 lacks per-event encryption (deferred V2+; standard at-rest sufficient for most cases)

