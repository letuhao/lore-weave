# S1 — campaign-service spine (Auto-Draft Factory)

> **Slice:** S1 of the Auto-Draft Factory. Per-slice DESIGN + PLAN.
> **Parent design (CLOSED):** [`2026-06-08-auto-draft-factory-architecture-readiness.md`](2026-06-08-auto-draft-factory-architecture-readiness.md) — §"Revised slicing v2" S1 row + decisions A, B, H, I.
> **Size:** XL · **Mode:** v2.2 (no AMAW, PO-chosen) · one loom, one commit.
> **PO decisions (CLARIFY 2026-06-09):** no AMAW; build all of S1 in one loom.

---

## S1 acceptance criteria (from parent S1 row + H/I/J)

1. New **`campaign-service`** (Python/FastAPI, own DB `loreweave_campaign`) — skeleton, `/health`, idempotent migrations.
2. `campaigns` + `campaign_chapters(campaign_id, chapter_id, ingest|knowledge|translation|eval status, attempts, last_error, …)` — the **unified per-chapter cross-pipeline projection** (G7).
3. **Projection consumer**: a Redis-Streams consumer (`campaign-collector` group) over the existing streams, updating `campaign_chapters` from per-chapter events.
4. **`knowledge.chapter_extracted`** — NEW per-chapter emit (decision H) from worker-ai's chapter-success path → existing knowledge outbox → `loreweave:events:knowledge`.
5. **Saga driver + reconcile loop** — stateless, re-derives "what's next" from `campaign_chapters` on every tick → crash-resumable (decision D).
6. **Ownership verify-once + propagate** (decision A): verify book ownership once at create (book-service `/internal/.../projection`), then drive downstream job-create over **internal-token + asserted `user_id`** — **no minted user-JWTs**.
7. **Gating interface, both modes** (decision B): `phase_barrier` (knowledge-ALL → translate) and `cold_start` (interleave) — user-selected per campaign.
8. Scope: campaign = **knowledge → translation → eval**; **ingest is a precondition** (decision I), not a stage; eval rides on translation events (H).
9. No FE (S5/S6).

---

## The one design decision the parent doc left implicit: internal dispatch endpoints

Decision A says "propagate the verified `user_id` over internal-token calls — no minted user-JWTs." But the existing job-create surfaces are **JWT-only**:
- translation: `POST /v1/translation/books/{book_id}/jobs` (`get_current_user`) — **no internal variant** (verified by grep).
- knowledge: `POST /v1/knowledge/projects/{id}/extraction/start` (`get_current_user`) — rich `/internal/*` surface exists, but not a job-*start*.

So the driver cannot dispatch without either (a) minting a user-JWT (forbidden) or (b) a new internal endpoint that trusts internal-token + an asserted `user_id`. **We add (b)** — the "assert-verified-user_id" pattern already used across `/internal/*`:

- **translation-service** — `POST /internal/translation/dispatch-job` (X-Internal-Token; body carries `user_id`, `book_id`, `chapter_ids`, model refs, target_language). Thin wrapper reusing the existing `create_job` core; trusts the asserted `user_id` (campaign-service already verified ownership at create).
- **knowledge-service** — `POST /internal/knowledge/projects/{project_id}/dispatch-extraction` (X-Internal-Token; body carries `user_id`, `scope`, `scope_range`, model refs). Thin wrapper over the existing extraction-start core.

These keep ownership-verification at the campaign boundary (verify-once) and make every downstream hop a trusted S2S call — exactly decision A. This widens S1 to a **3-service** change (campaign + translation + knowledge), which is inherent to A, not scope creep. `chapter_range` honouring inside the knowledge **runner** stays in **S2** (`D-K16.2-02b`); S1 only passes `scope_range` through the new dispatch endpoint.

---

## Data model (`loreweave_campaign`)

```sql
CREATE TABLE IF NOT EXISTS campaigns (
  campaign_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id      UUID NOT NULL,
  book_id            UUID NOT NULL,
  name               TEXT NOT NULL,
  status             TEXT NOT NULL DEFAULT 'created',
    -- created | running | paused | completed | failed | cancelling | cancelled
  gating_mode        TEXT NOT NULL DEFAULT 'phase_barrier',  -- phase_barrier | cold_start
  stages             TEXT[] NOT NULL DEFAULT '{knowledge,translation,eval}',
  target_language    TEXT,
  knowledge_model_source   TEXT, knowledge_model_ref   UUID,
  translation_model_source TEXT, translation_model_ref UUID,
  knowledge_project_id     UUID,   -- the project the knowledge stage extracts into
  chapter_from       INT,          -- range (sort_order), NULL = whole book
  chapter_to         INT,
  total_chapters     INT NOT NULL DEFAULT 0,
  error_message      TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at         TIMESTAMPTZ,
  finished_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_campaigns_owner ON campaigns(owner_user_id, created_at DESC);
-- Driver-claim index: only non-terminal campaigns are reconciled.
CREATE INDEX IF NOT EXISTS idx_campaigns_active ON campaigns(status)
  WHERE status IN ('running','cancelling');

CREATE TABLE IF NOT EXISTS campaign_chapters (
  campaign_id        UUID NOT NULL,
  chapter_id         UUID NOT NULL,
  chapter_sort       INT  NOT NULL DEFAULT 0,
  ingest_status      TEXT NOT NULL DEFAULT 'done',     -- precondition (decision I)
  knowledge_status   TEXT NOT NULL DEFAULT 'pending',  -- pending|dispatched|done|failed|skipped
  translation_status TEXT NOT NULL DEFAULT 'pending',
  eval_status        TEXT NOT NULL DEFAULT 'pending',
  knowledge_attempts   INT NOT NULL DEFAULT 0,
  translation_attempts INT NOT NULL DEFAULT 0,
  last_error         TEXT,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (campaign_id, chapter_id)
);
CREATE INDEX IF NOT EXISTS idx_campchap_campaign ON campaign_chapters(campaign_id);
```

**This projection is the single source of truth for "what's done"** (decision J): the driver dispatches a `(chapter, stage)` only when its status is `pending|failed` (never `dispatched|done|skipped`). Each stage is idempotent underneath, so a stray re-dispatch is safe — the gate just avoids the cost.

---

## Event contracts (consumed by the projection)

| Stream | event_type | maps to | projection effect |
|---|---|---|---|
| `loreweave:events:knowledge` | `knowledge.chapter_extracted` **(NEW)** | knowledge stage done | `knowledge_status='done'` for `(campaign?, chapter)` |
| `loreweave:events:chapter` | `chapter.translated` | translation stage done | `translation_status='done'` |
| `loreweave:events:translation` | `translation.quality` | eval signal | `eval_status='done'` |
| `loreweave:events:chapter` | `chapter.saved` | ingest precondition | (advisory; ingest defaults `done`) |

**Event→campaign correlation:** events carry `(user_id, book_id, chapter_id)` but **not** `campaign_id`. The consumer maps an event to rows by `chapter_id` joined to active campaigns for that `book_id`/`user_id`. A chapter may belong to ≥1 active campaign on the same book — update **all** matching rows (idempotent). The dedup key is the relay's `outbox_id` (stream field); the consumer is idempotent regardless (status set is convergent), so at-least-once delivery is safe.

`knowledge.chapter_extracted` payload (worker-ai emits, best-effort, on chapter success):
```json
{ "user_id": "...", "project_id": "...", "book_id": "...", "chapter_id": "...", "status": "extracted" }
```

---

## Saga driver + gating (pure-logic core, heavily unit-tested)

**`gating.py` — `next_dispatches(campaign, chapters) -> list[Dispatch]`** (pure function):
- `phase_barrier`: dispatch **translation** for a chapter only once **every** chapter's `knowledge_status ∈ {done,skipped}` (glossary stable). Until then, dispatch only **knowledge** for `pending|failed` chapters.
- `cold_start`: dispatch **knowledge** and **translation** independently per chapter as soon as each stage's predecessor allows (translation may start before the whole book's knowledge is done).
- Both: never dispatch a stage whose status is `dispatched|done|skipped`; respect `chapter_from/to`; cap attempts (`*_attempts < MAX_ATTEMPTS`) → else mark `failed` terminal.
- eval is **observed**, not dispatched (rides translation.quality).

**`driver.py` — reconcile tick** (stateless): for each `running` campaign → load projection → `next_dispatches` → call the internal clients (paced, bounded in-flight) → mark dispatched rows. On restart, re-derives from the projection — no in-memory state. Completion: all in-scope chapters `done|skipped` across required stages → `status='completed'`. `cancelling` → stop dispatch, let in-flight drain, → `cancelled`.

> S1 builds the dispatch + gating + reconcile **logic** and wires it to real internal endpoints. Heavy hardening (rate-limit governor, circuit-breaker, budget-pause, paced fairness, backoff) is **S3** — S1's pacing is a simple bounded-in-flight window.

---

## File inventory

**New service `services/campaign-service/`:** `requirements.txt`, `Dockerfile`, `pytest.ini`, `app/__init__.py`, `app/main.py`, `app/config.py`, `app/database.py`, `app/migrate.py`, `app/deps.py`, `app/models.py`, `app/routers/campaigns.py`, `app/repositories.py` (campaigns + campaign_chapters), `app/events/consumer.py` (projection), `app/saga/gating.py`, `app/saga/driver.py`, `app/clients/{book,translation,knowledge}_client.py`, `tests/conftest.py` + `tests/test_*.py`.

**knowledge / worker-ai (decision H):** `services/worker-ai/app/outbox_emit.py` (+`emit_chapter_extracted`), `services/worker-ai/app/runner.py` (call it on chapter success), `services/worker-ai/tests/test_chapter_extracted_emit.py`.

**Internal dispatch endpoints (decision A):** `services/translation-service/app/routers/internal_dispatch.py` + test; `services/knowledge-service/app/routers/internal_dispatch.py` + test (or fold into existing `internal_*`).

**Infra/gateway:** `infra/docker-compose.yml` (campaign-service block), `infra/postgres-init/01-databases.sql` + `infra/db-ensure.sh` (`loreweave_campaign`), `services/api-gateway-bff/src/gateway-setup.ts` + `src/main.ts` (`/v1/campaigns` proxy).

---

## Test plan (TDD)

- **gating** (pure): phase-barrier holds translation until knowledge-complete; cold-start interleaves; range filter; attempt cap; never re-dispatch done/dispatched. *(the load-bearing logic — most tests here)*
- **projection consumer**: each event type sets the right status; multi-campaign fan-out by chapter; idempotent re-delivery; unknown chapter ignored.
- **campaigns API**: create verifies ownership (403 mismatch, 404 missing, 502 book-svc down); create seeds `campaign_chapters`; get returns projection; cancel transitions.
- **driver**: dispatch only pending/failed; mark dispatched; completion transition; reconcile re-derives after "restart" (no state).
- **internal dispatch endpoints**: reject without internal-token; create job/extraction with asserted user_id.
- **knowledge.chapter_extracted emit**: chapter-success path inserts the outbox row with correct payload; best-effort (never raises).

## VERIFY

≥2 services touched → **live-smoke token required**. Full 4-service saga bring-up + a multi-chapter campaign at dev time is heavy; plan to **`LIVE-SMOKE deferred to D-CAMPAIGN-S1-LIVE-SMOKE`** unless a quick stack-up proves a single create→dispatch hop. Unit suites (campaign-service + the 3 touched services) must be green.

## Deferred rows opened by S1

- `D-CAMPAIGN-S1-LIVE-SMOKE` — real create→knowledge-dispatch→projection hop on a stack-up.
- (carried) `D-K16.2-02b` (knowledge runner honour `chapter_range`) → **S2**.
