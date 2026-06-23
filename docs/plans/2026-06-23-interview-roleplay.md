# Plan — Interview-Practice Roleplay (POC for roleplay-service)

- **Date:** 2026-06-23
- **Spec:** [docs/specs/2026-06-23-interview-roleplay.md](../specs/2026-06-23-interview-roleplay.md)
- **Size:** L (cross-service: `chat-service` + `knowledge-service`; contract change to `build_context`)
- **Strategy:** contract-first → deliver anti-drift value early (charter+anchoring) → executive →
  evaluate → seed+FE. Each milestone is a **risk boundary + commit point**. TDD per milestone.
- **Checkpoint cadence:** commit at each milestone; POST-REVIEW (human) at M3 (anti-drift proven
  on voice) and M5 (executive live). Cross-service live-smoke required at M3 + M5.

---

## Goal-authority seam (the POC throughline)

`charter` is written by a **goal authority**; for this build the authority is the **static
template** (write-once ⇒ frozen). The write path is isolated (M2/M4) so roleplay later swaps it
for the **world model** without touching `working_memory` / `executive` / `anchoring`. Every
milestone keeps the executive **strictly out of `charter`**.

---

## Milestones

### M1 — Contracts & schema (contract-first) · `chat` + `knowledge`
Freeze the cross-service surface before any behavior.
- `working_memory` JSON schema (versioned): `charter{goal,phases,checklist,time_budget_min,language}`
  + `state{phase,covered[],elapsed_min,drift_note,redirect_hint}`. Put in `contracts/` + a shared
  validator.
- DDL: `session_templates` (chat-service DB) with tenancy keys (`UNIQUE(owner_user_id,code)`,
  System rows admin-only); `chat_sessions.working_memory_seed JSONB` (charter seed / degraded
  fallback, EC-4).
- Contract change: `build_context` response gains `working_memory: str` (default `""`,
  backward-compat — mirror `KnowledgeContext` in [knowledge_client.py](../../services/chat-service/app/client/knowledge_client.py)).
- **Verify:** migrations apply up/down; schema validator unit tests; contract snapshot updated.
- **Gate:** no behavior yet → no live-smoke. Commit.

### M2 — Templates + charter seed · `chat-service`
- `session_templates` CRUD with tiers: System read-only to users / admin-write; Per-user
  `UNIQUE(owner_user_id,code)`; resolution merges System→Per-user by `code`.
- "Start practice": clone template → `POST /sessions` (existing `system_prompt`+`model_ref` path,
  [models.py](../../services/chat-service/app/models.py)) → **seed `charter`** into
  `chat_sessions.working_memory_seed` (goal authority = template, write-once). **EC-2 closed.**
- **Verify (TDD):** tenancy **deny** test (regular user cannot write a System template — the
  canonical tenancy bug); clone test; seed present on created session.
- Commit.

### M3 — Anchoring, text + voice · `chat-service`  ⟵ delivers anti-drift from charter alone
- Source `working_memory` from `build_context.working_memory`; when absent (knowledge has no block
  yet — true until M4) fall back to `working_memory_seed` on the session row (this is also the EC-4
  degraded path).
- [stream_service.py](../../services/chat-service/app/services/stream_service.py) (~L899-1040):
  **pin** rendered `working_memory` into `stable_context` (primacy) **and** **tail-inject** a 1–2
  line condensed note right before the latest user turn (recency / depth-0). `charter.goal` in
  **both**, always.
- [voice_stream_service.py](../../services/chat-service/app/services/voice_stream_service.py):
  same via the shared build path (do NOT fork logic). **EC-3 closed.**
- **Verify / live-smoke:** drive a **text** and a **voice** session; assert anchor present in both
  placements; **force window eviction** (long filler) → AI still steers to `charter.goal`; tail
  note does not leak into output (EC-7).
- **POST-REVIEW checkpoint #1** (anti-drift proven). Commit.

### M4 — `working_memory` block in knowledge-service (becomes SSOT) · `knowledge-service`
- New selector/block under [context/selectors/](../../services/knowledge-service/app/context/selectors/)
  + a store row keyed by `(project_id, session)`; emitted into `stable_context` and the new
  `working_memory` field by [context/builder.py](../../services/knowledge-service/app/context/builder.py).
- `charter` bound from the template seed at session/project link (goal-authority write path lives
  HERE — documented as the world-model swap point); `state` initialized empty.
- chat-service anchor source flips seed → knowledge block; seed stays as degraded fallback (EC-4).
- **Verify:** block round-trips through `build_context`; degraded path still anchors from seed.
- Commit.

### M5 — `executive` worker · `knowledge-service`
- Job on the existing `scope='chat'` **FIFO-per-session** drainer
  ([events/handlers.py](../../services/knowledge-service/app/events/handlers.py)); cadence **N≈5
  turns / M≈8 min** whichever first; out-of-band.
- Reads recent turns + current `state` → small LLM call via
  [clients/llm_client.py](../../services/knowledge-service/app/clients/llm_client.py) (provider-registry,
  cheap utility capability, **no hardcoded model**) → writes **`state` only**: `covered` monotonic,
  schema-validated, bad diff → keep prior; emits in `charter.language` (EC-9). **Charter untouched.**
- Graceful skip when no utility model configured (EC-10); single-writer via drainer (EC-11).
- **Verify / live-smoke (cross-service):** real chat turns on a stack-up → executive updates
  `state` → anchor reflects new phase/covered; dropped-`covered` diff is rejected (EC-1).
- **POST-REVIEW checkpoint #2** (executive live). Suggest `/review-impl` (load-bearing: cross-tenant
  worker reading session turns + LLM write-back). Commit.

### M6 — Evaluation endpoint · `chat-service`
- `POST /v1/chat/sessions/{id}/evaluate`: non-agentic pipeline (provider-registry) over transcript
  + final `working_memory` + template rubric → structured scorecard → stored as `ChatOutput`.
- Partial-transcript safe (EC-13); session-owner scoped.
- **Verify:** scorecard on a full and a partial transcript; ownership deny test.
- Commit.

### M7 — System seed templates + Frontend
- Admin migration seeds 3 System templates ("FAANG SWE", "Behavioral HR", "System Design").
- FE feature (`features/interview/`, MVC rules): persona picker (controller hook) → **reuse the
  existing chat + voice components** (no fork) → scorecard view. No new turn-loop UI.
- **Verify:** browser smoke (test account) — pick persona → short voice exchange → end → scorecard.
- **POST-REVIEW checkpoint #3** (shippable). Commit.

---

## Cross-cutting (every milestone)
- **Invariants:** provider-registry only; no hardcoded model; pipelines exempt from MCP-first;
  tenancy keys present; gateway unchanged. Run `python scripts/ai-provider-gate.py` before each commit.
- **TDD:** failing test → implement → verify fresh run (no "should pass").
- **Executive never writes `charter`** — assert in tests at M4/M5.

## Acceptance → milestone map (spec §8)
| Acceptance | Milestone |
|---|---|
| Seed present turn 1 (EC-2) | M2 |
| Voice anchor in both placements (EC-3) | M3 |
| 2h eviction → still on goal | M3 (charter) reinforced M5 (state) |
| Dropped-`covered` diff rejected (EC-1) | M5 |
| Degraded knowledge → seed fallback (EC-4) | M3/M4 |
| Scorecard on partial transcript (EC-13) | M6 |
| provider-gate green | all |

## Risks / watch
- **M3 is the value gate** — if charter+anchoring alone don't hold the goal under eviction, the
  whole premise (and the roleplay POC) is in question. Treat M3 live-smoke as go/no-go.
- **Voice cadence** — executive by *time* not turn-count for voice (turns are fuzzy); revisit at M5.
- **Token budget at 2h** — assert bounded per-turn budget (pinned block is fixed-size) at M3.

## Deferred (post-MVP, tracked)
- Cross-session weak-spot recall (long_term_memory) — separate tier.
- User re-charter mid-session — locked out for MVP (new session instead).
- World-model goal authority — the roleplay extension this POC de-risks (§9 of spec).
