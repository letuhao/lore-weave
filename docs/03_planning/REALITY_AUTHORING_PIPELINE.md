# Reality Authoring Pipeline (RAP) — Design

> **Goal:** Build the data-preparation pipeline that turns book content into game-ready, typed `RealityManifest` entries (places first, then actors / items / factions). Authors and collaborators review and edit each candidate before it is promoted into a reality manifest staging snapshot.
>
> **Scope V1:** Place only — `PF_001 PlaceDecl`-shaped drafts. Framework extensible to the other 13 game-typed kinds.
>
> **Status:** DRAFT 2026-04-28 — Phase 0 design doc landing per `LLM_MMO_RPG` data-prep work item.
> **Stable-ID prefix:** `RAP-*` (RAP-A* axioms · RAP-D* deferrals · RAP-Q* open questions · AC-RAP-* acceptance scenarios)
> **Owners:** glossary-service (BE storage + CRUD) · knowledge-service (extraction pipeline) · frontend (review UI)
> **Builds on:**
> - `docs/03_planning/LLM_MMO_RPG/features/00_place/PF_001_place_foundation.md` — engine-side `PlaceDecl` shape (CANDIDATE-LOCK 2026-04-26)
> - `docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md` — existing two-layer pattern (glossary SSOT + knowledge graph derived)
> - `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md` — Pass-2 extraction pipeline reused by Pass-3
> - `services/glossary-service/internal/api/` — existing CRUD, evidence, recycle_bin, wiki primitives
> - `services/knowledge-service/app/extraction/` — existing pass2 orchestrator + glossary_sync
>
> **Resolves:** Engine-layer schema for Place is locked but no authoring pipeline exists. Without RAP, V1 cannot bootstrap a populated reality.
> **Does not block:** Phase 1–5 novel-platform work.
> **Blocks:** Any actual `LLM_MMO_RPG` engine implementation cycle (data must exist before engine consumes it).

---

## §0 Decisions locked at Phase 0

| ID | Decision | Source |
|---|---|---|
| **RAP-A1** | Service boundary: `glossary-service` mở rộng với `internal/place_drafts/` module (1 DB, không tách service mới) | Q1=A |
| **RAP-A2** | Pipeline location: `knowledge-service` thêm Pass-3 — tái sử dụng chunking + LLM client + retry/cost | Q2=A |
| **RAP-A3** | Cardinality glossary↔draft: 1-to-N theo composite `(reality_id, glossary_entity_id)`. Cùng glossary entry có thể fork vào nhiều realities | Q3=B |
| **RAP-A4** | V1 scope: Place only. Actor / Item / Faction reuse pattern này ở V1+ | User direction |
| **RAP-A5** | Auth model: `author` (chủ book) + `collaborator` (mời qua sharing-service) review/edit; admin override | OQ1 default |
| **RAP-A6** | Promote V1 ghi vào `reality_manifest_staging` table; engine consumption V1+ (engine chưa tồn tại) | OQ2 default |
| **RAP-A7** | Versioning: append-only revisions, không truncate (low write volume; matches existing `glossary_evidence` pattern) | OQ3 default |
| **RAP-A8** | i18n: LLM extract theo book locale (vi or en); manual locale fill sau qua form. Không auto-translate V1 | OQ4 default |
| **RAP-A9** | Re-extraction dedup: composite UPSERT vào revision history, không duplicate row | OQ5 default |
| **RAP-A10** | LLM cost: `max_chunks` + `max_candidates` per job + tracking qua `usage-billing-service` hiện hữu | OQ6 default |

---

## §1 Vision & three-layer architecture

### §1.1 Why this exists

LoreWeave's existing data plane has two layers:

```
L1  glossary-service (Go)           — authored text SSOT, RAG-friendly, multi-locale
       ↓ FK: glossary_entity_id
L2  knowledge-service (Python)      — fuzzy/semantic graph, derived
```

This stack is excellent for **AI reading the data** (RAG, search, chat grounding). It is insufficient for **the game engine consuming the data** because:

- Engine needs typed enums (`PlaceType { Tavern | Temple | Cave | … }`), not freeform tags.
- Engine needs structured graphs (`ConnectionDecl[]` between places), not narrative prose.
- Engine needs fixture inventories (`EnvObjectSeedDecl[]`), not "the tavern has a fireplace" in a markdown body.
- Engine needs validated invariants at bootstrap time (every cell has a place; every connection points to a known place).

RAP introduces L3:

```
L3  game-typed drafts (NEW)         — typed shells per kind, anchored to L1 entries
       ↓ promote
    reality_manifest_staging        — frozen snapshots ready for engine ingestion
```

### §1.2 Three-layer mapping (Place example)

| Concern | L1 glossary | L2 knowledge | L3 RAP draft |
|---|---|---|---|
| Identity | `glossary_entity_id` (UUID) | linked via FK | linked via FK |
| Display name | `name` text + `aliases[]` | mirrors L1 | `display_name_vi` + `display_name_en` (typed) |
| Description | wiki article + attributes JSON | embeddings + relations | `narrative_drift` JSONB (structured) |
| Type/kind | `kind` tag (free text) | label | `place_type` enum (closed) |
| Spatial relations | n/a | graph edges (free predicates) | `connections[]: ConnectionDecl` (typed enum + canon_ref) |
| Fixture inventory | n/a | n/a | `fixture_seeds[]: EnvObjectSeedDecl` (typed) |
| Book provenance | `evidence` rows | n/a | `evidence_links[]` + `canon_ref` (typed) |
| State machine | n/a | n/a | `structural_state: StructuralState` (closed enum) |
| Workflow status | n/a | n/a | `status: pending_llm | pending_review | approved | rejected | superseded` |

L1 + L2 schemas remain **unchanged**. L3 anchors to L1 via FK — no content duplication.

### §1.3 Pipeline shape end-to-end

```
┌──────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│ book chapters    │ →   │ knowledge-service     │ →   │ glossary-service      │
│ (already ingested)│    │ Pass-3 place extractor│     │ /internal/persist     │
└──────────────────┘     │ (LLM, chunked)        │     │ → place_drafts        │
                         └──────────────────────┘     │   status=pending_review│
                                                       └──────────────────────┘
                                                                  ↓
                                            ┌──────────────────────────┐
                                            │ Frontend review UI       │
                                            │  list / form / diff      │
                                            │  edit → revision append  │
                                            │  approve / reject        │
                                            └──────────────────────────┘
                                                                  ↓ (approved)
                                            ┌──────────────────────────┐
                                            │ promote → staging         │
                                            │ reality_manifest_staging  │
                                            │ (frozen JSON for engine)  │
                                            └──────────────────────────┘
```

---

## §2 Typed schema (Place V1)

### §2.1 PlaceDraft Go struct (glossary-service domain)

Mirrors `PF_001 PlaceDecl` field-for-field, plus authoring/audit metadata.

```go
// services/glossary-service/internal/domain/place_drafts.go

type PlaceDraftStatus string

const (
    StatusPendingLLM    PlaceDraftStatus = "pending_llm"     // pipeline picked up; LLM call in flight
    StatusPendingReview PlaceDraftStatus = "pending_review"  // candidate landed; awaits human
    StatusApproved      PlaceDraftStatus = "approved"        // reviewer approved; ready to promote
    StatusRejected      PlaceDraftStatus = "rejected"        // reviewer rejected; archived
    StatusSuperseded    PlaceDraftStatus = "superseded"      // re-extraction produced newer; old kept
)

type PlaceType string  // closed enum — must match PF_001 §4 V1 set

const (
    PlaceTypeResidence    PlaceType = "Residence"
    PlaceTypeTavern       PlaceType = "Tavern"
    PlaceTypeMarketplace  PlaceType = "Marketplace"
    PlaceTypeTemple       PlaceType = "Temple"
    PlaceTypeWorkshop     PlaceType = "Workshop"
    PlaceTypeOfficialHall PlaceType = "OfficialHall"
    PlaceTypeRoad         PlaceType = "Road"
    PlaceTypeCrossroads   PlaceType = "Crossroads"
    PlaceTypeWilderness   PlaceType = "Wilderness"
    PlaceTypeCave         PlaceType = "Cave"
)

type StructuralState string  // closed enum — must match PF_001 §7

const (
    StatePristine  StructuralState = "Pristine"
    StateDamaged   StructuralState = "Damaged"
    StateDestroyed StructuralState = "Destroyed"
    StateRestored  StructuralState = "Restored"
)

type ConnectionKind string  // matches PF_001 §6 V1 set

const (
    ConnPublic  ConnectionKind = "Public"
    ConnPrivate ConnectionKind = "Private"
    ConnLocked  ConnectionKind = "Locked"
    ConnHidden  ConnectionKind = "Hidden"
    ConnOneWay  ConnectionKind = "OneWay"
)

type ConnectionDecl struct {
    ToPlaceDraftID uuid.UUID       `json:"to_place_draft_id"`         // intra-reality FK
    Kind           ConnectionKind  `json:"kind"`
    Bidirectional  bool            `json:"bidirectional"`
    CanonRef       *BookCanonRef   `json:"canon_ref,omitempty"`
    GateSlotID     *string         `json:"gate_slot_id,omitempty"`    // when kind=Locked
}

type EnvObjectKind string  // 11 V1 kinds — matches PF_001

type EnvObjectSeedDecl struct {
    EnvObjectKind       EnvObjectKind   `json:"envobject_kind"`
    SlotID              string          `json:"slot_id"`
    DefaultAffordances  []string        `json:"default_affordances"`   // bitset → string list at draft layer
    InitialState        json.RawMessage `json:"initial_state"`
}

type BookCanonRef struct {
    Kind      string  `json:"kind"`           // "BookPassage" | "AuthorCreated"
    BookID    *uuid.UUID `json:"book_id,omitempty"`
    ChapterID *uuid.UUID `json:"chapter_id,omitempty"`
    PassageRangeStart *int `json:"passage_range_start,omitempty"`
    PassageRangeEnd   *int `json:"passage_range_end,omitempty"`
}

type LLMProvenance struct {
    Model         string    `json:"model"`
    PromptVersion string    `json:"prompt_version"`
    Confidence    float32   `json:"confidence"`        // [0,1]
    RawResponse   string    `json:"raw_response"`      // truncated; full in object store V1+
    ExtractedAt   time.Time `json:"extracted_at"`
    JobID         uuid.UUID `json:"job_id"`
}

type PlaceDraft struct {
    ID                 uuid.UUID         `json:"id"`
    RealityID          uuid.UUID         `json:"reality_id"`
    GlossaryEntityID   *uuid.UUID        `json:"glossary_entity_id,omitempty"`  // null until linked
    PlaceType          PlaceType         `json:"place_type"`
    DisplayNameVi      string            `json:"display_name_vi"`
    DisplayNameEn      *string           `json:"display_name_en,omitempty"`
    StructuralState    StructuralState   `json:"structural_state"`
    NarrativeDrift     json.RawMessage   `json:"narrative_drift"`     // freeform JSON object
    Connections        []ConnectionDecl  `json:"connections"`
    FixtureSeeds       []EnvObjectSeedDecl `json:"fixture_seeds"`
    CanonRef           *BookCanonRef     `json:"canon_ref,omitempty"`
    Status             PlaceDraftStatus  `json:"status"`
    LLMProvenance      *LLMProvenance    `json:"llm_provenance,omitempty"`
    CreatedByUserID    uuid.UUID         `json:"created_by_user_id"`
    LastEditedByUserID *uuid.UUID        `json:"last_edited_by_user_id,omitempty"`
    LastEditedAt       *time.Time        `json:"last_edited_at,omitempty"`
    PromotedAt         *time.Time        `json:"promoted_at,omitempty"`
    PromotedSnapshotID *uuid.UUID        `json:"promoted_snapshot_id,omitempty"`
    CreatedAt          time.Time         `json:"created_at"`
    UpdatedAt          time.Time         `json:"updated_at"`
}
```

### §2.2 Database tables (Postgres migration)

```sql
-- 00NN_place_drafts.up.sql

CREATE TABLE place_drafts (
    id                          UUID PRIMARY KEY DEFAULT uuidv7(),
    reality_id                  UUID NOT NULL,
    glossary_entity_id          UUID REFERENCES glossary_entities(id) ON DELETE SET NULL,
    place_type                  TEXT NOT NULL CHECK (place_type IN (
        'Residence','Tavern','Marketplace','Temple','Workshop',
        'OfficialHall','Road','Crossroads','Wilderness','Cave')),
    display_name_vi             TEXT NOT NULL,
    display_name_en             TEXT,
    structural_state            TEXT NOT NULL DEFAULT 'Pristine'
        CHECK (structural_state IN ('Pristine','Damaged','Destroyed','Restored')),
    narrative_drift             JSONB NOT NULL DEFAULT '{}'::jsonb,
    connections                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    fixture_seeds               JSONB NOT NULL DEFAULT '[]'::jsonb,
    canon_ref                   JSONB,
    status                      TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (status IN ('pending_llm','pending_review','approved','rejected','superseded')),
    llm_provenance              JSONB,
    created_by_user_id          UUID NOT NULL,
    last_edited_by_user_id      UUID,
    last_edited_at              TIMESTAMPTZ,
    promoted_at                 TIMESTAMPTZ,
    promoted_snapshot_id        UUID,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (reality_id, glossary_entity_id)   -- RAP-A9 dedup invariant
);

CREATE INDEX idx_place_drafts_reality_status ON place_drafts (reality_id, status);
CREATE INDEX idx_place_drafts_glossary       ON place_drafts (glossary_entity_id) WHERE glossary_entity_id IS NOT NULL;
CREATE INDEX idx_place_drafts_promoted       ON place_drafts (reality_id, promoted_at) WHERE promoted_at IS NOT NULL;

CREATE TABLE place_draft_revisions (
    id                  UUID PRIMARY KEY DEFAULT uuidv7(),
    draft_id            UUID NOT NULL REFERENCES place_drafts(id) ON DELETE CASCADE,
    revision_no         INT NOT NULL,
    snapshot            JSONB NOT NULL,
    edited_by_user_id   UUID,
    edit_summary        TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (draft_id, revision_no)
);

CREATE INDEX idx_pdr_draft ON place_draft_revisions (draft_id, revision_no DESC);

CREATE TABLE place_draft_review_assignments (
    id                  UUID PRIMARY KEY DEFAULT uuidv7(),
    draft_id            UUID NOT NULL REFERENCES place_drafts(id) ON DELETE CASCADE,
    reviewer_user_id    UUID NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('assigned','in_review','approved','rejected')),
    reason              TEXT,
    assigned_by_user_id UUID NOT NULL,
    assigned_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ
);

CREATE INDEX idx_pdra_reviewer ON place_draft_review_assignments (reviewer_user_id, status);

CREATE TABLE place_draft_evidence_links (
    draft_id            UUID NOT NULL REFERENCES place_drafts(id) ON DELETE CASCADE,
    glossary_evidence_id UUID NOT NULL,    -- FK to existing glossary_evidence (cross-table)
    relevance           TEXT NOT NULL CHECK (relevance IN
        ('canon_ref','fixture_seed','connection','general')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (draft_id, glossary_evidence_id, relevance)
);

CREATE TABLE reality_manifest_staging (
    id                  UUID PRIMARY KEY DEFAULT uuidv7(),
    reality_id          UUID NOT NULL,
    section             TEXT NOT NULL CHECK (section IN ('places')),  -- V1+ adds 'actors','items',...
    entry_id            UUID NOT NULL,    -- e.g., place_draft_id
    payload             JSONB NOT NULL,    -- typed decl ready for engine bootstrap
    promoted_by_user_id UUID NOT NULL,
    promoted_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at       TIMESTAMPTZ,       -- nullable; set when same entry_id re-promoted
    UNIQUE (reality_id, section, entry_id, promoted_at)
);

CREATE INDEX idx_rms_reality_active ON reality_manifest_staging (reality_id, section)
    WHERE superseded_at IS NULL;
```

**Notes:**
- `uuidv7()` from PG18 — time-ordered UUIDs already used elsewhere per `101_DATA_RE_ENGINEERING_PLAN.md`.
- `glossary_entity_id` nullable: drafts can be created manually before being linked to a glossary entry.
- `place_draft_evidence_links.glossary_evidence_id` FK is **logical** (declared in app code, not enforced at DB level) because evidence may live in a separate schema in the future. Validation lives in the repo layer.

---

## §3 API contract

OpenAPI spec lives in `contracts/api/glossary/v1/openapi.yaml`. Below is the human-readable surface.

### §3.1 Public CRUD endpoints

All endpoints require JWT with the user's identity. Path prefix: `/v1/realities/{reality_id}/place-drafts`.

| Method | Path | Auth gate | Description |
|---|---|---|---|
| GET | `/` | author or collaborator on reality | List drafts; query: `status`, `place_type`, `assignee_user_id`, `cursor`, `limit` (≤100, default 50) |
| GET | `/{draft_id}` | author or collaborator | Get one draft + last 5 revisions inline; `?include=full_revisions` returns all |
| POST | `/` | author | Manual create (no LLM); body: `PlaceDraftCreateRequest` |
| PATCH | `/{draft_id}` | author or assigned reviewer | Edit fields; writes a new revision row |
| DELETE | `/{draft_id}` | author | Soft-delete (status → `rejected` with reason `'author_deleted'`) |
| POST | `/{draft_id}/approve` | assigned reviewer | Mark approved; transitions status; locks edits except by author |
| POST | `/{draft_id}/reject` | assigned reviewer | Mark rejected; body: `{ reason: string }` |
| POST | `/{draft_id}/promote` | author | Approved → staging; idempotent if already-promoted unchanged |
| POST | `/{draft_id}/assignments` | author | Assign reviewer; body: `{ reviewer_user_id }` |
| DELETE | `/{draft_id}/assignments/{assignment_id}` | author | Unassign |
| GET | `/{draft_id}/revisions` | author or collaborator | Paginated revision history |

### §3.2 Internal pipeline endpoint

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/internal/place-drafts/persist` | service token (knowledge-service → glossary-service) | Batch upsert candidates from pipeline |

Body shape:

```json
{
  "reality_id": "uuid",
  "job_id": "uuid",
  "candidates": [
    {
      "glossary_entity_id": "uuid|null",
      "place_type": "Tavern",
      "display_name_vi": "Tửu lâu Tụ Tiên",
      "display_name_en": null,
      "narrative_drift": { "ambient": "smoke and lantern light" },
      "connections": [],
      "fixture_seeds": [
        { "envobject_kind": "Door", "slot_id": "front_door",
          "default_affordances": ["Open","Close"], "initial_state": {} }
      ],
      "canon_ref": { "kind": "BookPassage", "book_id": "...", "chapter_id": "...",
                     "passage_range_start": 120, "passage_range_end": 145 },
      "evidence_links": [{ "glossary_evidence_id": "uuid", "relevance": "canon_ref" }],
      "llm_provenance": {
        "model": "gpt-4o", "prompt_version": "v1.0",
        "confidence": 0.82, "raw_response": "...", "extracted_at": "..."
      }
    }
  ]
}
```

Response: per-candidate result `{ candidate_index, status: 'created'|'updated'|'unchanged'|'error', draft_id?, revision_no?, error? }`.

**Idempotency (RAP-A9):** Composite key `(reality_id, glossary_entity_id)`:
- If no row: INSERT new draft with `status=pending_review`, revision_no=1.
- If row exists and content differs: UPDATE + append revision; reset status to `pending_review` if it was `rejected`. Existing `approved` rows are NOT auto-touched — pipeline marks them `superseded` and inserts a sibling new draft (manual reconciliation).
- If row exists and content identical (hash match): no-op, return `unchanged`.

### §3.3 Promotion semantics

`POST /{draft_id}/promote`:

1. Validate `status == 'approved'`.
2. Build `payload` JSON in `RealityManifest.places[]` shape (matches PF_001 §9).
3. UPSERT into `reality_manifest_staging` keyed on `(reality_id, section, entry_id)`:
   - If existing active row: set `superseded_at = now()` on old, INSERT new active row.
   - Else: INSERT new active row.
4. Update `place_drafts.promoted_at` and `promoted_snapshot_id`.
5. Return `{ snapshot_id, snapshot_version }`.

Engine V1+ will read `reality_manifest_staging WHERE reality_id = ? AND superseded_at IS NULL` at reality bootstrap to build the in-memory `RealityManifest`.

---

## §4 Pipeline architecture (knowledge-service Pass-3)

### §4.1 Files to land

```
services/knowledge-service/app/extraction/
  llm_prompts/
    place_extraction.py           NEW — system + few-shot prompt; structured JSON output schema
  pass3_place_extractor.py        NEW — orchestrator (chunk loader → LLM → dedupe → writer)
  place_writer.py                 NEW — HTTP client → glossary-service /internal/place-drafts/persist
services/knowledge-service/app/jobs/
  place_extraction_job.py         NEW — worker handler for AMQP job kind=place_extraction
services/knowledge-service/app/routers/
  extraction.py                   MOD — register POST /v1/extraction/places
```

### §4.2 Job submission API

```
POST /v1/extraction/places
{
  "reality_id": "uuid",
  "book_id": "uuid",
  "chapter_range": { "start_idx": 0, "end_idx": 50 } | null,   // null = all chapters
  "max_chunks": 200,                                            // RAP-A10 cost cap
  "max_candidates_per_chunk": 5
}
→ 202 { "job_id": "uuid" }

GET /v1/extraction/jobs/{job_id}
→ 200 { "job_id", "status": "queued|running|succeeded|failed",
        "candidates_emitted": 42, "chunks_processed": 87, "errors": [...] }
```

### §4.3 Orchestrator flow (`pass3_place_extractor.py`)

```
1. Resolve chapters from book-service (book_id + chapter_range).
2. Chunk text per existing pass2 chunker (reuse).
3. For each chunk (rate-limited, max_chunks cap):
     a. Call LLM with place_extraction prompt + chunk text + reality canon hint.
     b. Parse JSON-mode response → list[PlaceCandidate].
     c. For each candidate:
          - Resolve glossary entity via existing entity_resolver
            (if no match, try to create via glossary_sync.upsert_entity with kind='place');
            if resolver returns ambiguous, attach BOTH candidate + ambiguity flag in evidence_links.
          - Compute content_hash for dedup.
4. Batch candidates → call place_writer.persist_batch(reality_id, job_id, candidates).
5. Track per-job stats; emit metrics; record cost via existing pricing.py.
```

### §4.4 LLM prompt skeleton (`place_extraction.py`)

```
SYSTEM:
You are an extraction agent for a tabletop-RPG-style game built from a fiction book.
Given a passage of book text, extract every distinct PHYSICAL or NAMED location
mentioned and return one JSON object per location.

OUTPUT JSON SCHEMA (strict):
{
  "places": [
    {
      "display_name_vi": string,                  // primary name in book locale
      "display_name_en": string | null,
      "place_type": one of [Residence, Tavern, Marketplace, Temple, Workshop,
                            OfficialHall, Road, Crossroads, Wilderness, Cave],
      "narrative_drift": { "ambient": string, "notable_features": [string] },
      "fixture_seeds": [ {envobject_kind, slot_id, default_affordances[], initial_state{}} ],
      "suggested_connections": [
        { "to_display_name_vi": string, "kind": one of [Public, Private, Locked, Hidden, OneWay] }
      ],
      "passage_evidence": { "start_offset": int, "end_offset": int, "quote": string },
      "confidence": float [0,1]
    }
  ]
}

RULES:
- Only return places with explicit textual evidence in this passage.
- Do NOT guess place_type if the passage is ambiguous; pick the closest V1 enum or omit.
- Preserve the book's original locale spelling.
- Include passage_evidence quotes ≤200 chars each for grounding.
```

### §4.5 Connection resolution (cross-chunk)

Pipeline emits `suggested_connections` keyed by display name. Resolver phase (post-batch) tries to match each `to_display_name_vi` against existing place drafts in the same reality:

- Exact match → fill `to_place_draft_id`.
- No match → leave as unresolved suggestion; surface in form for human to pick.

This matches the existing `entity_resolver` pattern in knowledge-service and reuses its alias index.

### §4.6 Cost & telemetry

- Existing `app/metrics.py` and `pricing.py` already compute per-call cost. Pass-3 adds tags: `extractor=place`, `reality_id`, `book_id`, `chunk_index`.
- Per-job aggregates persisted to `extraction_jobs` table (existing schema; add `kind='place'` enum value).
- Per-user/per-reality cost surfaced via `usage-billing-service` existing rollup.

---

## §5 Frontend flow

### §5.1 Routes

| Path | View |
|---|---|
| `/realities/{reality_id}/authoring/places` | List view |
| `/realities/{reality_id}/authoring/places/extraction-jobs` | Job queue & retry |
| `/realities/{reality_id}/authoring/places/{draft_id}` | Review form + diff |

### §5.2 Feature folder

```
frontend/src/features/place-drafts/
  api.ts
  types.ts
  context/
    PlaceDraftListContext.tsx         — stable list + filter state (RAG-friendly)
    PlaceDraftReviewContext.tsx       — volatile per-draft edit state
  hooks/
    usePlaceDraftList.ts
    usePlaceDraftEditor.ts
    usePromoteDraft.ts
    useExtractionJobs.ts
  components/
    PlaceDraftListView.tsx
    PlaceDraftReviewForm.tsx
    PlaceDraftDiffView.tsx
    fields/
      PlaceTypePicker.tsx
      ConnectionGraphEditor.tsx       — visual node-edge picker; uses existing graph component or simple table
      FixtureSeedEditor.tsx           — table CRUD per row; EnvObjectKind picker per row
      NarrativeDriftEditor.tsx        — JSON textarea + schema hint chips
      EvidenceLinkPanel.tsx           — book passage previews via book-service chapter API
      DisplayNameI18nFields.tsx       — vi required + en optional
  routes.tsx
  __tests__/
```

Adheres to **Frontend Architecture Rules** in CLAUDE.md (hooks own logic, components render-only, split context by update frequency, max ~100 lines per component).

### §5.3 List view

- Table columns: name (vi), type, status (badge), confidence, last edited, assignee.
- Filters: status (multi), place_type (multi), assignee (single), free-text name search.
- Bulk actions: assign reviewer, bulk reject.
- Row click → review form.
- Header CTA: "Run extraction" → opens job submit dialog (book picker + chapter range + cost cap preview).

### §5.4 Review form

- Top: status pill + LLM confidence + book-passage preview side panel.
- Body sections (collapsible):
  1. **Identity** — display_name_vi, display_name_en, glossary entity link picker.
  2. **Type & state** — PlaceTypePicker, StructuralState picker.
  3. **Narrative drift** — ambient text, notable features chip array, free JSON escape hatch.
  4. **Fixture seeds** — table; row = (envobject_kind, slot_id, affordances, initial state JSON).
  5. **Connections** — table; row = (to draft picker, kind, bidirectional, gate slot id).
  6. **Evidence** — passage quotes + relevance tags; link to book chapter view.
- Footer: Save draft (revision append), Approve, Reject (reason required), Promote (only if approved).
- Diff view toggle: show LLM original vs current (deep-diff JSON colored).

### §5.5 Frontend rules to enforce

- `PlaceDraftReviewForm.tsx` must NOT exceed 100 lines — extract field components.
- `usePlaceDraftEditor.ts` owns all save/approve/reject/promote calls — components dispatch via callbacks, no direct API in components.
- Auto-save: debounced 800ms after edit pause; uses tap-to-confirm pattern (not aggressive on every keystroke).
- Form state lives in volatile context to avoid list re-render on each keystroke.

---

## §6 Extension pattern (V1+ kinds)

When adding Actor / Item / Faction / etc., the pattern is:

1. **Engine schema lock first.** Foundation feature must be CANDIDATE-LOCK before authoring tooling.
2. **New tables** (mirror place_drafts shape):
   - `actor_drafts`, `actor_draft_revisions`, `actor_draft_review_assignments`, `actor_draft_evidence_links`.
   - Reality manifest staging gains a new `section` enum value (`'actors'`).
3. **New CRUD module** in glossary-service: `internal/actor_drafts/` symmetric to `internal/place_drafts/`.
4. **New extraction prompt** in knowledge-service: `app/extraction/llm_prompts/actor_extraction.py`.
5. **New pass orchestrator**: `pass3_actor_extractor.py` (or extend pass3 to dispatch by kind).
6. **New frontend folder**: `features/actor-drafts/` reusing `fields/` primitives where possible (`DisplayNameI18nFields`, `EvidenceLinkPanel` are kind-agnostic).
7. **New OpenAPI section.**

Estimated effort per additional kind: 3-4 commits (schema + CRUD + prompt + form) — **70-80% of place infrastructure is reusable**.

---

## §7 Acceptance criteria (V1)

| ID | Scenario | Verification |
|---|---|---|
| **AC-RAP-1** | Pipeline ingests one Wuxia chapter and emits ≥3 place candidates with `place_type` + `display_name_vi` + `canon_ref` populated | Integration test against test reality + 1 fixture chapter |
| **AC-RAP-2** | Re-running the same pipeline job produces zero new rows; existing rows unchanged (status `unchanged`) | Run job twice; assert row count + content hash |
| **AC-RAP-3** | Re-running with content change (LLM re-extracts richer fixture list) produces 1 new revision; status reset to `pending_review` if previously `rejected` | Mock LLM returns updated payload |
| **AC-RAP-4** | Author can manually create a place draft (no LLM); `llm_provenance = null`; status = `pending_review` | API test |
| **AC-RAP-5** | Reviewer with `assigned` assignment can PATCH; reviewer without assignment gets 403 | Authz test |
| **AC-RAP-6** | Approve transition rejects body if status != `pending_review` | API test |
| **AC-RAP-7** | Promote on non-approved draft returns 409 | API test |
| **AC-RAP-8** | Promote of approved draft creates `reality_manifest_staging` row; second promote of same draft (after edit + re-approve) supersedes the previous staging row | DB assertion |
| **AC-RAP-9** | Frontend list filters by status + place_type and renders ≤50 rows per page; "Run extraction" submits a valid job | Vitest + Playwright happy path |
| **AC-RAP-10** | Review form persists edits as revision rows; revision history shows ≥2 entries after one author edit + one reviewer edit | Vitest |
| **AC-RAP-11** | Connection editor allows picking another draft in the same reality; cross-reality picker is forbidden | Vitest |
| **AC-RAP-12** | Cost cap enforced: job with `max_chunks=10` does not call LLM more than 10 times | Mock LLM call counter |
| **AC-RAP-13** | Smoke E2E: ingest 1 sample chapter → run pass-3 → land ≥1 candidate → review → approve → promote → query staging table sees row | Compose integration |

---

## §8 Deferrals

### V1+ (next-step extensions)

| ID | Item | Reason |
|---|---|---|
| **RAP-D1** | Actor draft kind | Wait for ACT_001 actor schema to be CANDIDATE-LOCK and PCS_001 V1+ activation |
| **RAP-D2** | Item draft kind | Wait for future Item foundation feature |
| **RAP-D3** | Faction draft kind | Wait for FAC_001 to gain authoring need |
| **RAP-D4** | Auto-translate vi↔en for `display_name_*` | Translation-service integration; V1 manual fill |
| **RAP-D5** | Cross-reality draft cloning ("import places from reality A into reality B") | Heresy V2+ scope |
| **RAP-D6** | Visual graph editor for connections (force-directed, drag-drop) | V1 uses table editor |

### V1+30d (fast-follow ops)

| ID | Item | Reason |
|---|---|---|
| **RAP-D7** | Bulk re-extraction with diff-only writes | V1 always writes revisions |
| **RAP-D8** | Reviewer assignment auto-balancer | V1 manual assign |
| **RAP-D9** | Cost preview before job submit (estimate from chunk count + token avg) | V1 just enforces cap |
| **RAP-D10** | Slack/email reviewer notification on assignment | V1 polled in UI |

### V2+

| ID | Item | Reason |
|---|---|---|
| **RAP-D11** | Live promotion to running reality (Forge admin action) | Engine must exist |
| **RAP-D12** | Multi-reviewer consensus gate (N-of-M approval) | Single reviewer V1 sufficient |
| **RAP-D13** | Branch-and-merge for collaborative draft editing | Single-writer V1 |

---

## §9 Risks & mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| LLM hallucinates places not in book | Med | `passage_evidence` quote required; confidence threshold; reviewer gate is mandatory |
| Pipeline cost runs away on large books | High | `max_chunks` cap + per-job cost ceiling + existing usage-billing telemetry |
| Schema drift between PF_001 and PlaceDraft | High | Single-source-of-truth: PF_001 §2.1 owns enum sets; this doc references them — any PF_001 change requires RAP review (locked in `_boundaries/02_extension_contracts.md` follow-up at Phase 1 commit) |
| Glossary entity FK churn (entity merged/renamed) | Med | `ON DELETE SET NULL`; reviewer warned in form when FK target moved |
| Promotion of stale approved draft after PF_001 enum extension | Med | Promotion path validates payload against current `PlaceDecl` schema; V2+ adds payload version field |
| Concurrent edits by author + reviewer | Low | Optimistic concurrency: PATCH requires `If-Match: <revision_no>` header; conflicts return 412 |

---

## §10 Open questions remaining

| ID | Question | Status | Resolution path |
|---|---|---|---|
| **RAP-Q1** | Should fixture-seed `default_affordances` be a closed bitset enum at L3 or stay free-text array until EnvObject foundation feature locks? | Open | Defer to EnvObject feature kickoff; V1 stores as `string[]`, validation lax |
| **RAP-Q2** | When glossary entity is renamed, should existing drafts auto-update `display_name_vi`? | Open | Default: no — drafts keep their own copy; reviewer sees a "glossary diverged" badge. Confirm at Phase 2 |
| **RAP-Q3** | Should `reality_manifest_staging` live in glossary-service DB or in a dedicated `reality-engine` DB? | Open | V1: glossary-service DB. Migrate when engine service exists. Note in Phase 5 docs |
| **RAP-Q4** | Visual connection graph editor at V1 or V1+? | Leaning V1+ | Table editor is sufficient for ≤20 connections per place; visual graph at V1+ when scale demands |
| **RAP-Q5** | Should the pipeline emit Pass-3 candidates BEFORE reviewer assignments exist, or auto-create unassigned queue? | Default: unassigned | V1: candidates land with no assignment; author later assigns reviewer. Confirm at Phase 1 |

---

## §11 Cross-references

- **PF_001 PlaceDecl** (engine schema source-of-truth) — `docs/03_planning/LLM_MMO_RPG/features/00_place/PF_001_place_foundation.md`
- **Two-layer pattern** — `docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md`
- **Knowledge-service architecture** — `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md`
- **Glossary CRUD primitives** — `services/glossary-service/internal/api/`
- **Existing extraction pipeline** — `services/knowledge-service/app/extraction/pass2_orchestrator.py`
- **Multiverse model** (per-reality data isolation rationale) — `docs/03_planning/LLM_MMO_RPG/03_multiverse/_index.md`
- **Boundary discipline** (will register `place_drafts` aggregate ownership) — `docs/03_planning/LLM_MMO_RPG/_boundaries/01_feature_ownership_matrix.md`

---

## §12 Phase plan (this doc → implementation)

| Phase | Name | Files | Size | Deliverable |
|---|---|---|---|---|
| 0 | Design landing | this doc | XL (docs only) | Sign-off gate |
| 1 | BE schema | migrations + domain + repo | L (BE) | place_drafts tables + Go domain + repo tests |
| 2 | BE CRUD API | handlers + OpenAPI | L (BE) | 11 endpoints + handler tests + contract update |
| 3 | Pipeline | knowledge-service Pass-3 | L (BE) | Prompt + orchestrator + writer + job endpoint |
| 4 | Frontend | features/place-drafts/ | XL (FE) | List + form + diff + extraction job UI |
| 5 | Integration + smoke | compose + docs + E2E | M | E2E test on test reality + SESSION_PATCH update |

Each phase = one commit cycle following project workflow (CLARIFY → DESIGN → PLAN → BUILD → VERIFY → REVIEW → QC → POST-REVIEW → SESSION → COMMIT → RETRO).

---

## §13 Status

- **Created:** 2026-04-28 by main session (Phase 0 design landing)
- **Phase:** DRAFT — awaits user sign-off before Phase 1
- **Status target:** CANDIDATE-LOCK after user approval; LOCK after AC-RAP-1..13 pass at Phase 5
- **Companion docs:** —
- **Sign-off gate:** user reads §0 + §2 + §3 + §7 + §10; confirms or redirects each open RAP-Q.
