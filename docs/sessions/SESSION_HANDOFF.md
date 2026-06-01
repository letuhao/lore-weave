# Session Handoff — Session 105 (eval R&D closed + Production Eval Flywheel track planned)

> **Purpose:** orient the next agent in one read. This file is the single, unversioned handoff — updated in place at the end of each session. (Older `SESSION_PATCH.md` is deprecated → archive later.)
> **Date:** 2026-06-01 (session 105 — closed knowledge R&D arc; designed the production eval+feedback track; human-in-loop v2.2).
> **HEAD:** TBD (post-commit). Branch: `main`.

## ▶ NEXT SESSION — start here

**State:** **Knowledge-extraction R&D arc CLOSED.** Independent-judge baseline measured + locked: **F1 = 0.869**, 95% CI [0.842, 0.895] (disjoint median, gemma + phi4 over 9 golden chapters; `tests/quality/eval_runs/c74c-clean-rejudge` via `compute_ensemble_macros.py`). Confirms the ~4-5pp self-reinforcement (0.913 self-graded → 0.869 clean). 0.869 is now the honest baseline of record.

**NEW TRACK DESIGNED (this session):** **Production Eval + Feedback Flywheel** — design-checkpoint artifact written + committed (NO code yet): [`docs/plans/2026-06-01-production-eval-feedback-flywheel-track.md`](../plans/2026-06-01-production-eval-feedback-flywheel-track.md). Grounded in a 6-dimension industry research workflow (OpenAI / Anthropic / Google Vertex / LLM-observability platforms / vendor-neutral ML patterns / codebase audit) + an adversarial critique pass (all 6 fixes folded). 12 phases Q0→Q9 (Q10 LoRA spun out to Track-2).

**PO decisions locked (doc §11):** (1) Q2 = time-window attribution first (no node→run link unless noise hurts); (2) Q4 = structural-only online eval first, `save_raw_extraction` LLM-judge opt-in is fast-follow; (3) baseline of record = **0.869** (retire 0.913 from gate use); (4) stays in `docs/plans/`, promote to numbered track if BUILD >5 sessions.

**Q0 DONE (this session)** — `loreweave_eval` SDK package created (`sdks/python/loreweave_eval/`): the cycle-72–74 scorer lifted out of `tests/quality/` so learning-service (Q4) + knowledge-service (R&D) import the SAME code. **0a** = byte-identical lift (4 modules copied; `canonicalize_entity_name`→SDK direct; `LLMClient`→injected `JudgeLLMClient` Protocol; old `tests/quality/*` are re-export shims; 2 file-path lock tests + the SDK ensemble test repointed). **0b** = `JudgePanel` (parameterized the hardcoded extractor/filter UUIDs `019e6a20`/`019e5650`) + `score_dump`→`EvalResult` facade + `EvalSink` Protocol + `FileSink` (DbSink deferred to Q1, NOT in SDK). **Verified:** byte-identical new≡shim≡0.869 on c74c; SDK suite 398 passed (6 pre-existing fails, net-zero new); KS unit 1929 passed; 5 new 0b tests. Single commit (files mix 0a/0b in `__init__`/`compute_ensemble_macros`).

**Q1 DONE (this session)** — quality DB schema in learning-service: `score_config`/`eval_runs`/`eval_results`/`quality_scores` (idempotent DDL, mirrors `project_embedding_benchmark_runs` house style). `app/db/eval_repo.py` (`persist_eval_result` with fail-fast write-time score_config validation + idempotent re-score; `ensure_score_configs` seed; `list_eval_runs`/`get_eval_run`); `app/db/eval_sink.py` `DbSink` (impl `loreweave_eval.EvalSink`, now async — sinks.py made async in SDK); `routers/eval.py` `GET /v1/learning/eval-runs` (+ `/{id}`), per-owner. Dual dedup on `quality_scores` (partial unique: consumed `origin_event_id` + self-produced `source_eval_run_id+target+metric+judge`). `judge_panel` table DEFERRED (panel inline in `eval_runs.judges` JSONB). learning-service Dockerfile now installs the SDK. **Live-smoke PASSED** (host→Postgres :5555): DDL idempotent ×2, persist idempotent (same key→same row, children replaced), **0.869 baseline materialized** (`source='baseline'`, eval_run `6bd195f7…`), owner-isolation (other user→0 rows), read path OK. 60 lrn unit + 5 SDK eval tests green.

Baseline tool: `services/learning-service/scripts/materialize_eval_baseline.py <dump> <owner_uuid> [label]`.

**Q2 DONE (this session)** — corrections-as-gold projection. `app/db/gold.py` `get_gold_labels` projects the corrections log into preference triples (`preferred`=after / `non_preferred`=before + `change_magnitude` = # differing structural keys), redact-by-default (structural + hash only), per-owner, both routes via `origin_service`. `GET /v1/learning/gold-labels` (corrections router). Fixed the stale `get_outcome_recompute` docstring (it uses **time-window attribution** via the `source_extraction_run_id IS NULL` branch — PO-locked; returns one row PER RUN, not empty). **Live-verified**: gold_labels SQL runs (0 corrections→empty), outcome_recompute returns all 14 runs for owner `019d5e3c` (NOT empty). 7 gold tests + 67 lrn suite green. Node→run provenance link deferred (time-window suffices until noise hurts).

**Q3a DONE (backend, this session)** — chat-turn feedback capture. chat-service: `message_feedback` table + `POST /v1/chat/messages/{id}/feedback` (owner-scoped, txn INSERT + outbox emit `chat.message_feedback`) + `MessageFeedbackRequest/Response` models. Gateway needs NO change (`/v1/chat` catch-all proxy). learning-service: added `loreweave:events:chat` to consumer STREAMS + `handle_chat_feedback` (registered `chat.message_feedback`) → `persist_consumed_score` (new in eval_repo: validate vs score_config + ON CONFLICT origin dedup) → `quality_scores`(target_kind=chat_message, metric=`chat_user_rating`, source=human); seeded `chat_user_rating` numeric[-1,1]. Regenerate-as-negative = rating −1 + `regenerated_from_message_id`. **Verified:** chat 253 suite + 4 feedback tests; learning 74 suite + 7 handler tests. **Live (both DB halves, host→Postgres :5555):** chat `message_feedback` DDL idempotent ×2 (8 cols); learning persist writes a `chat_message` score + **consumed-event dedup held** (insert#1 True, #2 False, 1 row). **Full E2E POST→outbox→relay→learning deferred to D-Q3-CHAT-FEEDBACK-E2E** (needs chat+learning container rebuild — contract covered by unit + both live DB halves).

**Q3b DONE (FE, this session)** — chat feedback UI. `api.ts` `submitMessageFeedback` → `POST /v1/chat/messages/{id}/feedback`; `hooks/useMessageFeedback.ts` (controller: rating state + optimistic/rollback + toast, server source of truth, no localStorage); `AssistantMessage.tsx` thumbs up/down (aria-pressed highlight) + wrapped regenerate to post implicit `rating=-1 reason=regenerated`; i18n `message.feedback_{up,down,thanks,error}` ×4 locales. **Verified:** 5 feedback vitest + 29 chat-feature tests green; tsc clean. **Q3 COMPLETE (a+b).**

**Q3.5 DONE (this session)** — judge calibration + panel safety, in `loreweave_eval/calibration.py` (pure, data-independent): `cohen_kappa` / `balanced_accuracy` / `confusion` / `raw_agreement` over paired `(human_correct, judge_correct)` labels; `calibrate_judge → JudgeCalibration` with the trust gate (`passed` = balanced_acc ≥ 0.75 AND κ ≥ 0.4, both tunable; degenerate single-class set → not passed). **Anti-self-reinforcement enforced + visible:** `panel_safety(excluded_refs, judge_uuids) → PanelSafety`; `score_dump` now sets `EvalResult.panel_safe` + `panel_safety_reason` on EVERY run (False when <2 disjoint judges or a generator self-grades). **Verified:** 18 calibration + 5 scorer tests; full SDK suite net-zero new; learning 74. c74c baseline `panel_safe=True`.
- **Data note:** the live judge-vs-human agreement (pair construction from corrections + per-item judge verdicts) is NOT wired — live DB has 0 corrections AND per-item judge verdicts aren't persisted yet (Q1 stores per-judge macro). Q4 builds the pairs (it produces per-item verdicts) and calls `calibrate_judge`; Q4 also calls `panel_safety` in-process to gate before trusting scores. panel_safe DB persistence (eval_runs column) deferred to Q4.

**Q4a DONE (online-eval consumer, this session)** — the flywheel now samples production runs automatically. Online eval of a production chapter has NO gold/source (golden-set P/R/F1 N/A), so per the PO-locked structural-first decision the signal is `structural_completeness` = fraction of core categories (entity/relation/event) with output (`app/db/online_eval.py`). New **`eval-runner`** second Redis consumer group on `loreweave:events:knowledge` (`app/events/eval_runner.py`) — best-effort (droppable, no DLQ), **every msg XACKed** (sampled-out immediately, no PEL churn), group at `$` (forward-looking). `should_sample` = deterministic `sha256(run_id) mod` (idempotent re-delivery). `online_eval_rule` table (rate+enabled, seeded global default 0.1). `persist_online_eval` → `eval_runs`(source=online, idempotent `online:<run_id>`) + `quality_scores`(online_structural_completeness, validated). **Cleared Q3.5 defer:** `panel_safe`/`panel_safety_reason` columns on `eval_runs`; `persist_eval_result` writes them. Wired into `main.py` lifespan (gated `online_eval_enabled`). **Verified:** 15 Q4 + 89 learning suite. **Live (Postgres :5555):** migration idempotent ×2, rule seeded, 14 runs eval'd + idempotent, `panel_safe=True`; **real completeness dist 0.0×3 / 0.33×3 / 0.67×8** (3 degenerate runs surfaced; none reached 1.0 — a genuine pipeline-health finding). Smoke rows cleaned up.

**★ FULL LIVE E2E Q0→Q4 PASSED (this session)** — rebuilt + restarted learning-service + chat-service containers, ran the whole flywheel through the gateway (:3123):
- **Q1**: `GET /v1/learning/eval-runs` → test-acct baseline (0.869, 2 judges); `/{id}` detail → 2 per-judge results. Owner-isolation confirmed (the 019d4966 baseline is invisible to other users).
- **Q2**: `GET /v1/learning/gold-labels` → 200 (empty, 0 corrections).
- **Q3a** (FULL cross-service): gateway `POST /v1/chat/messages/{id}/feedback` → chat `message_feedback` → outbox → relay → `loreweave:events:chat` → learning → `quality_scores`(chat_user_rating=1.0, source=human, origin=chat). ✓
- **Q3.5**: `panel_safe=True` ("2 disjoint judges, no generator in panel") persisted on the baseline.
- **Q4**: injected a synthetic `extraction_run_completed` onto the knowledge stream → **eval-runner consumed it in the live container** → `eval_runs`(source=online, completeness=1.0). ✓
- **D-Q3-CHAT-FEEDBACK-E2E + D-Q4-EVAL-RUNNER-E2E → CLEARED.** Synthetic E2E data cleaned up; rule rate reset to 0.1.

**⚠ Regression fixed during E2E (`<commit>`)**: the rebuild pulled **redis-py 8.0** (`redis>=5.0` unpinned). In redis-py 8 a blocking `XREADGROUP(block=N)` with no data raises `TimeoutError` (5.x returned empty) → BOTH learning consumers hot-looped. Fixed: catch `aioredis.TimeoutError` → `continue` (normal idle) in `consumer.py` + `eval_runner.py`. **Platform risk (D-REDIS8-CONSUMERS):** knowledge-service `consumer.py` + any other blocking Redis consumer have the same unpinned dep + pattern — they'll hot-loop on their next rebuild until they get the same catch OR redis is pinned `<8`.

**NEXT (Q4 structural done; LLM-judge half + downstream):**
- **Q4b (LLM-judge online eval)** — richer semantic signal. Needs `save_raw_extraction` opt-in (source text) + per-item judge verdict persistence (so Q3.5 `calibrate_judge` runs live). Host-orchestrate judge via provider-registry :8208 (NOT in-container 26B); sorted-set paced queue cost governor. Data-gated (0 opted-in projects).
- **Q5 (L) eval-case dataset from failures** (depends Q2) — versioned `eval_cases` from corrections + judge-disagreement; filtered-view not annotation-queue (critique). Unblocked.
- **Q6a/b (shadow runs)** (depends Q4) — replay challenger config, log projection, paired compare. Unblocked.
- Small: add `panel_safe` to the `eval-runs` read model + `list_eval_runs`/`get_eval_run` queries (column is written + live-confirmed, just not surfaced by the API yet).
- **D-REDIS8-CONSUMERS** (above) — port the TimeoutError catch to knowledge-service consumer / pin redis.

(Critical path: Q0✓→Q1✓→Q2✓→Q3✓→Q3.5✓→Q4✓→Q6a→Q6b→Q8; Q9 privacy gate before any cross-tenant Q7 surface. See track doc §5.)

**Q1 note:** 0.913 historical NOT materialized (it's the retired self-graded number from a different 3-judge dump; PO retired it from gate use, so it's not needed as a row). For c74c's 2 independent judges, full-panel == disjoint == 0.869.

**Deferred / flagged:**
- **3 pre-existing `test_pass2_writer.py` failures** (`test_facts_merged_with_evidence`, `test_k17_9_fact_content_injection_sanitized`, `test_full_pipeline_all_candidate_types`) — from last session's FACT_TYPES filter (`0bf049cd`); the tests assert pre-filter behavior (type='description' facts merged) but they're now skipped. **Small fix: update the 3 tests** (or reconsider filter). Outside Q0 scope; do next.
- Outcome refinement batch job (correction-join recompute on `extraction_runs`) — subsumed by track Q2.
- Archive job: `SESSION_PATCH.md` (974KB) + trim this file — separate session.
- Track-2 (doc §10): LoRA distillation, weighted-canary rollout state machine, CUPED/sequential testing.

<details><summary>(historical) Phase B complete — push options (all done/superseded)</summary>

<details><summary>(historical) earlier state note</summary>
**State:** Phase B was FEATURE-COMPLETE (pre-browser-smoke).</details> The full two-axis-Axis-1 correction loop is built + committed: users can correct **entities** (edit/delete/merge), **relations** (correct/mark-wrong), and **events** (edit/delete) in the UI → each emits a `knowledge.*_corrected` / enriched `glossary.entity_updated` → relay → `learning-service.corrections`. Backend live-smoke-verified end-to-end (all types); frontend tsc-clean + 469 knowledge vitest pass + AMAW-adversary-folded. **Only residual: a Playwright BROWSER smoke** (D#054, LOW) — the contract is already covered by component tests + BE live-smokes.

**NEXT options (historical, resolved):** push done; Phase C (D#048) or B2 (D#055) were the choices — B2 was chosen.
</details>

<details><summary>(historical) C-FE views scope — now DONE</summary>

Built this session: mirror `EntityEditDialog`+`useEntityMutations`+`ifMatch`/`isVersionConflict` →
- `RelationEditDialog` (predicate/endpoint correct → `POST /v1/knowledge/relations/correct`; "mark wrong" → `POST /relations/{id}/invalidate`), wired from the read-only `RelationRow` in [EntityDetailPanel.tsx](../../frontend/src/features/knowledge/components/EntityDetailPanel.tsx).
- `EventEditDialog` (title/summary/time_cue/event_date_iso edit → `PATCH /v1/knowledge/events/{id}` with If-Match; archive → `DELETE /events/{id}`), wired from [TimelineEventRow.tsx](../../frontend/src/features/knowledge/components/TimelineEventRow.tsx).
- `api.ts`: `getRelation`/`correctRelation`/`invalidateRelation`/`updateEvent`/`archiveEvent`; hooks `useRelationMutations`/`useEventMutations` (react-query invalidation + 412 refetch).
- a11y: 44×44 icon-only tap targets; visibility-transition tests for both dialogs (standing FE lessons).
- a11y: 44×44 icon-only tap targets; 412 conflict handling per the entity pattern.
</details>

**Sub-session A shipped (cycle 75b):** new `learning-service` (Python/FastAPI, host 8222) with `corrections` table (redact/hash schema) + Redis-Streams consumer (`learning-collector`, with `XAUTOCLAIM` reclaim) + read API (`/v1/learning/corrections`) + gateway proxy + compose/db-ensure. worker-infra relay now carries `outbox_id` on the wire (F1/F2) + `streamMaxLen` 200k for glossary/knowledge + retention 30d. glossary `entity_updated` enriched with `actor_type`/`actor_id`/before/after (PATCH made transactional for consistent capture). **Cross-service live smoke PASSED** (glossary outbox→relay→learning: user corrections persisted+deduped on outbox_id, pipeline skipped, raw content NULL). AMAW code-review REJECTED→fixed (dead-retry reclaim F-A1, PATCH-contract F-A3; F-A2 deferred D#052). 23 learning unit tests + Go suites green.

**Sub-session B specifics:** KS gains its first outbox (`outbox_events` in `migrate.py`, `aggregate_type='knowledge'`); `app/events/outbox_emit.py` best-effort `emit_correction` (cross-store try/except — Neo4j is SoT, PG outbox best-effort, §6.6); emit on `patch_entity`/`merge_entity_into`/`archive_user_entity` ([entities.py](../../services/knowledge-service/app/routers/public/entities.py)) with SAME-Cypher before-capture (§6.3, MED-3 — NOT read-before-write); `update_entity_fields` must RETURN the pre-edit snapshot. Add `knowledge:<dsn>` to `OUTBOX_SOURCES` in compose. learning-service already consumes `loreweave:events:knowledge` + handles `knowledge.*_corrected` (wired in subA, untested live until B). Live-smoke KS-entity-edit→learning.

**Carry-forward gotchas (live-verified in A):** `origin_event_id := EventData.outbox_id` (NOT aggregate_id/message_id); empty outbox_id → DLQ not silent ""; diff_class is op-first; relation correct needs the dedicated `recreate_relation` (F5, sub-session C). Port the XAUTOCLAIM reclaim to knowledge-service too (D#051).

---

### (prior) Phase-B DESIGN checkpoint — session 75a

**State:** Phase-B **DESIGN is locked + checkpoint-committed** (session 75). The design doc [`docs/specs/2026-05-31-phase-b-correction-capture.md`](../specs/2026-05-31-phase-b-correction-capture.md) survived 3 AMAW adversary rounds (REJECTED→REJECTED→APPROVED_WITH_WARNINGS) + a /review-impl pass; all BLOCK/MED findings folded. Prior cycles 74d–74f + this design checkpoint on `main`, **NOT pushed** (push needs approval).

**Scope locked with PO (bigger than the original handoff):** Phase B = **XL** = the correction CAPTURE spine **+ build the rel/event user-edit endpoints that produce corrections** (they didn't exist — `invalidate_relation` was unwired, events had no edit primitive). Decisions: **new `learning-service`** (Python/FastAPI) owns the corrections store; **redact/hash content** (no raw novel text persisted — structural + content-hash only); **build the replay/backfill tool** (high MAXLEN + retained `event_log` + worker-infra idempotent replay). Tier-1 anchor reuse → **Phase C** (deferred, D#048); config telemetry → **B2** (D#055).

**NEXT = BUILD, in 3 sub-sessions (each its own VERIFY+POST-REVIEW+COMMIT), per design §12:**
1. **Sub-session A (foundation):** `learning-service` scaffold (clone chat-service shell + KS consumer) + `corrections` DDL (redact/hash schema §3) + consumer (`learning-collector` group) + read API + gateway route + compose/db-ensure. **worker-infra: add `outbox_id` to relay XADD (F1/F2 — 5-place sync, §4.0), high `streamMaxLen` for glossary/knowledge, replay task (§10.1).** glossary `entity_updated` enrichment (actor + before/after, SELECT-old-in-tx on PATCH). Live-smoke glossary→learning.
2. **Sub-session B:** KS first Postgres outbox + `emit_correction` + emit on existing entity edits (PATCH/merge/archive, same-Cypher before-capture §6.3) + add `knowledge:` to `OUTBOX_SOURCES`. Live-smoke KS-entity→learning.
3. **Sub-session C:** new relation + event correction repo primitives (`recreate_relation` — structurally separate from extraction `create_relation`, F5; `update_event_fields`/`archive_event` + `:Event.version`) + public routers + emission; FE relation/event edit UI.

**BUILD must-dos baked into the design:** F4 grep-gate (`outbox_id` ≥5 hits); F5 regression-lock (Pass-2 re-extraction leaves invalidated SVO `valid_until` NON-null); empty-`outbox_id`→DLQ (R3-W1); cross-service live-smoke token. Deferred rows: D#045 live-smoke, D#046 reconcile, D#055 B2, D#048 Phase-C anchor, D#049 replay tool, D#050 raw-content opt-in.

**Eval note (unchanged):** for any A/B use the **DISJOINT median of record** (`compute_ensemble_macros.py`), never the full-panel 0.913. Host harness: `tests/quality/run_rejudge_resumable.py` docstring (host → provider-registry `:8208` → LM Studio `:1234`, token `dev_internal_token`).

<details><summary>Copy-paste resume prompt</summary>

```
Resume LoreWeave session 76. Read docs/sessions/SESSION_HANDOFF.md (top "NEXT SESSION" block) + the locked design docs/specs/2026-05-31-phase-b-correction-capture.md (esp §3 schema, §4.0 outbox_id sync, §6 KS changes, §10.1 durability, §12 BUILD sequencing) FIRST. AMAW is the workflow.

State: Phase-B DESIGN locked + checkpoint-committed on main (NOT pushed). Phase B = XL = correction-capture spine + new rel/event user-edit endpoints, into a NEW learning-service (Python/FastAPI). Redact/hash content (no raw text); build the replay tool. Tier-1 anchor = Phase C (deferred).

GOAL: BUILD sub-session A (foundation) per design §12 — learning-service scaffold + corrections DDL (§3 redact/hash) + consumer (learning-collector) + read API + gateway + compose/db-ensure; worker-infra outbox_id XADD (§4.0 5-place sync) + high streamMaxLen + replay task (§10.1); glossary entity_updated enrichment (actor + before/after, SELECT-old in tx). Live-smoke glossary→learning. Each sub-session = its own VERIFY+POST-REVIEW+COMMIT.

Hard gotchas from the design review: origin_event_id := EventData.outbox_id (NOT aggregate_id, NOT message_id); EventData lives in dispatcher.py:19-28; empty outbox_id → DLQ not silent ""; grep outbox_id ≥5 hits before VERIFY.
```
</details>

## Session 75 — cycle 75g: Phase B C-FE views — relation/event edit UI (FEATURE-COMPLETE)

**The user-facing correction UI. Phase B is now feature-complete.**

- **`RelationEditDialog`** ([components](../../frontend/src/features/knowledge/components/RelationEditDialog.tsx)): predicate correct → `correctRelation`; "mark wrong" (confirm) → `invalidateRelation`. Mounted **once at panel scope** (adversary F3 — keyed by `editingRelation`, not one-per-row), opened from the Pencil CTA on each `RelationRow` in `EntityDetailPanel.tsx`.
- **`EventEditDialog`** ([components](../../frontend/src/features/knowledge/components/EventEditDialog.tsx)): title/summary/time_cue/event_date_iso edit with If-Match → `updateEvent`; **ISO-date validation** (`YYYY|YYYY-MM|YYYY-MM-DD`, adversary F1) + empty-date = no-change (F2, avoids `""` corrupting the lexicographic date axis). Wired into `TimelineEventRow` expanded detail + an archive (`DELETE`) button → `archiveEvent`.
- i18n `relations.*` + `events.*` added to all 4 locales (en/ja/vi/zh-TW).
- **Tests:** 9 new dialog tests (pre-fill, diff-only+If-Match, 412 conflict, no-op, mark-wrong confirm/cancel) + 24 affected (EntityDetailPanel/TimelineTab) green. **469 knowledge vitest pass; frontend tsc clean.**
- **AMAW cold-start adversary (FE): WARN×3** — the high-value `version`-undefined probe CLEARED (BE timeline list returns `version`). F1/F2 (date integrity) + F3 (per-row dialog hoist) all folded + re-tested.
- **Residual:** D#054 (LOW) — the pure browser-CLICK layer. **Post-commit (session 75): the REAL relation `invalidate` endpoint was live-smoked end-to-end** — KS-direct HTTP route → `invalidate_relation` → emit → relay → learning corrections row (seeded an `:Entity→:Entity` relation; the test user's real graph only has `:Entity→:Fact` edges + 0 events, so the in-UI flow needs seeded data). Empirically confirmed D#053 (a non-UUID-coercible id → `emit_correction` silently drops — harmless for real 32-hex ids). gateway + auth-service are currently **Exited** (restart for any gateway-routed work).

**Phase B = COMPLETE + browser-verified** (D#054 Playwright smoke passed — see ▶ NEXT SESSION). Options: push / Phase C / B2.

## Session 75 — cycle 75f: Phase B C-FE data layer (api + hooks)

**The FE data/controller layer for relation/event corrections (MVC split: api.ts + hooks/). Views deferred to D#054.**

- [api.ts](../../frontend/src/features/knowledge/api.ts): added `version: number` to `TimelineEvent` (If-Match); `RelationCorrectPayload` + `EventUpdatePayload` types; methods `getRelation`, `invalidateRelation`, `correctRelation`, `updateEvent` (If-Match), `archiveEvent` — mirroring `updateEntity`/`mergeEntityInto`.
- `hooks/useRelationMutations.ts` (`useInvalidateRelation`, `useCorrectRelation` — invalidate `['knowledge-entity-detail', userId]` prefix so either endpoint's open detail refreshes) + `hooks/useEventMutations.ts` (`useUpdateEvent` w/ 412-refetch, `useArchiveEvent` — invalidate `['knowledge-timeline', userId]`).
- **frontend `tsc --noEmit` clean.** No FE runtime path until the views wire it; BE endpoints already live-smoked.
- Self-review: hooks are thin wrappers mirroring the adversary-reviewed `useEntityMutations`; invalidation keys verified.

**NEXT:** C-FE views (D#054) — `RelationEditDialog` + `EventEditDialog` + wiring into `RelationRow`/`TimelineEventRow` + i18n + vitest + **browser smoke** + final cold-start adversary on the full C surface. **This is the LAST Phase-B slice.**

## Session 75 — cycle 75e: Phase B BUILD C2 + C3 — event corrections + entity merge emission

**AMAW. Completes the BE capture spine — all 4 correction types now flow.**

- **C2 events:** added `version` to `:Event` (ON CREATE=1; merge_event ON MATCH does NOT bump → user If-Match baseline survives re-extraction; test-locked). `update_event_fields` (same-Cypher before-capture §6.3, If-Match, version bump, returns `(event, before)`) + `archive_event` (single-return, read-before in handler) in [events.py](../../services/knowledge-service/app/db/neo4j_repos/events.py). New events router ([events.py](../../services/knowledge-service/app/routers/public/events.py)): `PATCH /v1/knowledge/events/{id}` (428/412 ETag, mirrors entity PATCH) + `DELETE /{id}` (archive). Emits `knowledge.event_corrected`.
- **C3 merge emission:** `merge_entity_into` now emits `knowledge.entity_corrected` op=merge (before=source snapshot read pre-merge, after=merged target). `merge_entities` repo unchanged.
- `outbox_emit` gained `event_correction_payload`/`event_snapshot_dict` (structural=`event_date_iso`, content=`title/summary/time_cue/participants`).
- **Tests:** 12 new event tests (update/archive repo + router 428/412/404/204 + version-no-bump-on-merge lock). Full KS unit **1892 pass**. Merge route tests unaffected by the emit (best-effort no-op in unit).
- **LIVE SMOKE PASS:** `knowledge.event_corrected` → learning: `update→other` (events have no kind/name → coarser than entities) + `delete→spurious-drop`, target_type=event. (relation + entity smokes in prior cycles.)
- Self-review (event PATCH mirrors the adversary-reviewed entity PATCH; merge emit mirrors entity emit); full cold-start adversary deferred to C-FE close.

**NEXT:** C-FE (frontend) — the last Phase-B slice. See ▶ NEXT SESSION.

## Session 75 — cycle 75d: Phase B BUILD C1 — relation corrections (F5)

**AMAW. Relation correction endpoints + the F5-critical `recreate_relation`.**

- **`recreate_relation`** ([relations.py](../../services/knowledge-service/app/db/neo4j_repos/relations.py)) — the user-correct primitive, DELIBERATELY separate from extraction's `create_relation`: its ON MATCH clears `valid_until` (resurrects a previously-invalidated edge) + pins confidence=1.0/pending=false. Extraction's `create_relation` ON MATCH still never touches `valid_until` (F5 invariant — test-locked in `test_recreate_cypher_resurrects_valid_until`, asserting create's ON MATCH has no `valid_until`).
- **Public relations router** (`/v1/knowledge/relations`): `GET /{id}`, `POST /{id}/invalidate` (op=invalidate, after=null → spurious-drop), `POST /relations/correct` (invalidate old + recreate new). **Correct ordering = recreate-FIRST-then-invalidate** (self-review fix: a 409 on a missing endpoint leaves the old edge intact, no half-applied state) + skips invalidate when the corrected id maps onto the same edge. `after` is re-read post-write (F3).
- `emit_correction` reused; `relation_correction_payload` + `relation_snapshot` (all-structural: subject/object/predicate/confidence/valid_until) added to outbox_emit.
- **Tests:** 9 (recreate resurrect-invariant + create-doesn't-resurrect lock; builds-edge; endpoint-missing→None; router GET 404, invalidate happy/404, correct happy/old-404/recreate-409). Full KS unit **1880 pass**.
- **LIVE SMOKE PASS:** `knowledge.relation_corrected` → relay → learning: `predicate_fix→predicate-fix` + `invalidate→spurious-drop`, target_type=relation, origin_service=knowledge.
- Self-review caught + fixed the recreate/invalidate ordering; full cold-start adversary deferred to C-complete.

**NEXT:** C2 (events), C3 (merge emission), C-FE. See ▶ NEXT SESSION.

## Session 75 — cycle 75c: Phase B BUILD sub-session B (KS entity-correction emission)

**AMAW. KS→learning correction capture, live-smoke verified.**

- **knowledge-service gained its FIRST transactional outbox:** `outbox_events` (aggregate_type='knowledge') in `migrate.py`; `app/events/outbox_emit.py` `emit_correction` — best-effort, acquires the pool internally + wraps everything in try/except (cross-store §6.6: Neo4j is SoT, a dropped row never fails the user edit nor corrupts the graph; aggregate_id = the 32-hex canonical id, UUID-coercible).
- **Same-Cypher before-capture (design §6.3):** `_UPDATE_ENTITY_FIELDS_CYPHER` now projects a pre-edit `{name,kind,aliases}` map in the `WITH` (eager, before the FOREACH SET); `update_entity_fields` returns `(entity, before)`. `archive_entity` kept single-return (12 integration sites) — archive captures `before` via read-before-`get_entity` in the handler (idempotent + op=delete → spurious-drop, so low-stakes; documented).
- **Emission wired:** `patch_entity` → `knowledge.entity_corrected` op=update (before via canonical `entity_snapshot`); `archive_user_entity` → op=delete (after=null). Merge emission deferred to sub-session C.
- **compose:** `knowledge:<dsn>` added to `OUTBOX_SOURCES` (relay now polls loreweave_knowledge).
- **Tests:** updated `update_entity_fields` tuple call sites (unit mutations + browse-api + user-entities archive route mocks `get_entity` + 2 integration sites) + new `test_outbox_emit.py` (payload shape, UUID coercion, pool-failure swallow). **Full KS unit suite 1871 pass.**
- **LIVE SMOKE PASS (KS→learning):** KS outbox(`knowledge.entity_corrected`) → relay (knowledge source, `outbox_id`) → learning persisted `update→kind-change` + `delete→spurious-drop`, `origin_service=knowledge`, `origin_event_id`=outbox PK. KS `outbox_events` migration created live on restart.
- **AMAW code-review APPROVED_WITH_WARNINGS:** F2 (canonical before shape) fixed; F1 (permanent emit-failure surfacing) deferred D#053; F3 (read-before-archive) accepted.

**NEXT:** sub-session C (relation + event edits + FE + merge emission). See ▶ NEXT SESSION.

## Session 75 — cycle 75b: Phase B BUILD sub-session A (foundation)

**AMAW. The correction-capture foundation, end-to-end live-smoke verified.**

- **NEW `learning-service`** (`services/learning-service/`, Python/FastAPI, internal 8094 / host 8222, DB `loreweave_learning`): `corrections` table (redact/hash schema — structural + content-hash, raw `*_content` reserved NULL); Redis-Streams consumer (`learning-collector` group, `XAUTOCLAIM` reclaim); `diff_class` derivation (op-first); snapshot privacy-split; read API `GET /v1/learning/corrections(/stats)` (keyset pagination, strict JWT user-scoping); gateway `/v1/learning` proxy; compose + db-ensure + postgres-init.
- **worker-infra relay (F1/F2):** XADD now carries `outbox_id` (the row PK — the end-to-end dedup key; extracted to `relayStreamValues` + unit-tested); `streamMaxLen` glossary/knowledge → 200k; `OUTBOX_CLEANUP_RETAIN_DAYS` 7→30 (§10.1 replay backstop).
- **glossary-service:** `glossary.entity_updated` enriched with `actor_type`/`actor_id`/`before`/`after` (additive — KS glossary_sync unaffected). CREATE+PATCH thread `actor=user`; PATCH made **transactional** for consistent before/after capture (MED-3); bulk = `pipeline`. Removed the dead best-effort `emitEntityUpdated`.
- **Tests:** 23 learning unit (diff_class, snapshot, handlers incl. F2 + R3-W1, read-API scoping/redact); glossary outbox payload tests (actor/before/after); worker-infra `relayStreamValues` outbox_id contract + maxLenFor. All green; gateway tsc clean.
- **LIVE SMOKE PASS (cross-service):** inserted enriched glossary outbox rows → real relay shipped with `outbox_id` (verified on the Redis stream via XREVRANGE) → learning-service persisted 2 user corrections (`missing-add` + `boundary`), **skipped the pipeline event**, **deduped on outbox_id not aggregate_id** (F2), `before_content` NULL (R2 redact). 3 images rebuilt + healthy.
- **AMAW code-review: REJECTED → fixed.** F-A1 (BLOCK) dead-retry-in-steady-state → periodic `XAUTOCLAIM` reclaim; F-A3 (WARN) transactional-PATCH contract → outbox.go comment; F-A2 (WARN) diff_class description granularity → deferred D#052. KS has the same reclaim bug → D#051.

**NEXT:** sub-session B (KS outbox + entity-correction emission). See ▶ NEXT SESSION.

## Session 75 — cycle 75a: Phase B DESIGN checkpoint (correction capture + learning-service)

**DESIGN-only, no code (checkpoint-commit artifact).** AMAW. Doc: [`docs/specs/2026-05-31-phase-b-correction-capture.md`](../specs/2026-05-31-phase-b-correction-capture.md).

- **CLARIFY found 3 plan-vs-code divergences:** (1) `glossary.entity_updated` carries no actor field + fires on user-create/patch AND pipeline bulk (route middleware distinguishes via JWT-vs-internal-token, payload doesn't); (2) `invalidate_relation` is **unwired** + events have **no edit primitive** → no user path to correct a relation/event today; (3) knowledge-service has **no outbox** (graph is Neo4j, outbox must be Postgres → no true atomicity).
- **PO locked scope (maximal):** build the rel/event edit endpoints too (XL); **new `learning-service`** (Python/FastAPI, port 8094/host 8222, DB `loreweave_learning`); **redact/hash content** (no raw novel text — structural + content-hash; raw reserved for Phase-E per-tenant opt-in); **build the replay tool** (high MAXLEN + retained `event_log` + worker-infra idempotent replay). Tier-1 anchor reuse correctly re-scoped to **Phase C** (plan §4; handoff had conflated it into B).
- **AMAW design review (3 cold-start adversary rounds): REJECTED → REJECTED → APPROVED_WITH_WARNINGS.** Caught + folded: **F1/F2 (BLOCK)** — the idempotency key didn't exist on the wire (relay never XADDs the outbox row id; `aggregate_id` is the reused target id) → relay now carries `outbox_id` (5-place platform sync, §4.0); **F5 (BLOCK)** — "extend `create_relation` ON MATCH to clear `valid_until`" would silently resurrect user-invalidated relations on every re-extraction → forced a dedicated `recreate_relation`; F3/F4/F6 + R3-W1 folded.
- **/review-impl pass:** 5 more findings — MED-2 (before/after shape unpinned per target_type), MED-3 (KS before-capture must be same-Cypher, TOCTOU), LOW-4 (user_id-vs-actor_id latent under future write-collab), LOW-5 (cross-store drop = chain-break) all folded; MED-1 (durability) → PO chose build-replay-now.
- **All open questions R1–R5 + MED-1 resolved** (design §13). Audit trail: `docs/audit/AUDIT_LOG.jsonl` (3 review-design rounds + review-impl). Deferred: D#045–D#050.

**NEXT:** BUILD sub-session A (foundation) — see the ▶ NEXT SESSION block + design §12.

## Session 74 — cycle 74f: Phase A eval hygiene — disjoint-judge metric of record + bootstrap CI

**Plan §3 Phase A (first implementation cycle off the 74e plan).** [compute_ensemble_macros.py](../../services/knowledge-service/tests/quality/compute_ensemble_macros.py) now:
- discovers ALL `judge_verdicts_*.json`, reads each `judge_uuid`, and flags the **EXTRACTOR** (`019e6a20`) / **FILTER** (`019e5650`) judges by role (env-overridable `KNOWLEDGE_EXTRACTOR_MODEL`/`KNOWLEDGE_FILTER_MODEL`);
- reports the **DISJOINT median of record** (median F1 over judges that are NEITHER extractor nor filter) alongside the historical full-panel median, with a **deterministic percentile bootstrap CI** over the common chapter set (seed `0xC74E`, `KNOWLEDGE_BOOTSTRAP_N` default 2000); warns when <2 disjoint judges.
- **Measured:** c73b-drop-realized full-panel **0.913** vs disjoint **0.888** (gemma only → 1J warn = why phi4/qwen35 were added); c74c-clean disjoint **0.869** 95% CI **[0.842, 0.895]** (±2.6pp — proves cycle deltas of ±0.1–0.3pp are sub-noise).
- A3 (demote external anchors): **already done** — `test_anchor_eval.py` only asserts the sanity-floor, F1 is informational. A4 (rename `claude-4.7-opus`): mitigated by the role column; full historical-filename rename deferred (low-value cosmetic).

**Tests:** `test_compute_ensemble_macros.py` 4/4 (per-chapter PR, harmonic F1, disjoint exclusion by uuid, deterministic CI). Backward-compat `compute_per_judge_macros` wrapper kept.

**NEXT:** Phase B/B2 capture plumbing (corrections log + config telemetry) per plan §2.1/§4. Phase A is A/B-trustworthiness; the loop is the accuracy engine.

## Session 74 — cycle 74e: eval-data survey + accuracy/eval PLAN (correction + config-telemetry loop)

**Docs/data checkpoint (no code).** Resolved the production-readiness gate and reframed the eval strategy after PO feedback.

- **Clean re-judge (self-reinforcement quantified):** judges disjoint from extractor `019e6a20` + filter `019e5650` → 2 cross-arch judges (gemma `019dc3df` **0.888** + phi4 `019dc3ab-2b65` **0.851**) median **0.869** vs locked **0.913**; extractor self-grades **0.972**. → ~4–5pp self-inflation on the *relative* signal. (qwen35 3rd judge stopped — pathologically slow, conclusion already firm.) Artifacts in `eval_runs/c74c-clean-rejudge/`. Gotcha: clean judges needed a `{input_per_mtok:0,output_per_mtok:0}` pricing row in provider_registry or the gateway 402s.
- **Public dataset survey** → [docs/reports/2026-05-31-eval-dataset-survey.md](../reports/2026-05-31-eval-dataset-survey.md): LitBank (CC-BY 4.0, en entities) usable as independent anchor; lancopku (no license, modern-zh, coarse) + NCRE (no license, Jin-Yong-copyrighted, great taxonomy) = anchor/reference only. **No drop-in relation gold exists.** LitBank alignment measured: shared-kind P≈0.80, recall low **by design** (omission) — external numbers deflated by *definition*, not model error.
- **PO reframe (key):** genre + dynamic-taxonomy bias is a **FEATURE**, not a defect. → external benchmarks = sanity-floor only; don't grow a "neutral" gold set. Real accuracy engine = **learning-from-users loop**.
- **PLAN** → [docs/plans/2026-05-31-extraction-accuracy-and-eval-plan.md](../plans/2026-05-31-extraction-accuracy-and-eval-plan.md): production **ship-ready**; two-axis loop (Axis 1 corrections + Axis 2 config-adjustment telemetry) on existing outbox/EAV/wiki_suggestions infra; 3-part content-addressed capture schema (config_registry + adjustment_events + runs.outcome); data-mining tier (golden prompts/model×task/default-drift) with popularity≠quality + explore/exploit guards; cheap eval hygiene (disjoint-judge metric + bootstrap CI) as near-term Phase A.
- **5 candidate chapters** sourced (verbatim PD) in `tests/fixtures/golden_candidates/` (S&S, P&P ch3, 三國 oath, 紅樓夢 ch3, Lục Vân Tiên) — un-annotated, relation-dense; kept as small product-policy regression set.

**NEXT:** Phase A — cheap eval hygiene (bake disjoint-judge metric + bootstrap CI into the locked metric; demote external anchors to sanity-floor; rename `claude-4.7-opus`). Then Phase B/B2 capture plumbing.

## Session 74 — cycle 74d: Neo4j 2-hop retrieval hotfix (audit HIGH) + clean-judge re-judge

**Cycle 74d (S/SHIP-pending-approval) — D-RAG-2HOP-DEAD-CODE → FIXED.**

The audit's HIGH defect is fixed: [facts.py](../../services/knowledge-service/app/context/selectors/facts.py) `select_l2_facts` now passes the **required** `hop1_types` to `find_relations_2hop()`. Gate = new module constant `_RELATIONAL_HOP1_PREDICATES` (durable structural predicates only — kinship/mentorship/authority/social-state; spatial+action deliberately excluded as fan-out explosions, mirrors `relation_extraction_system.md` vocab). The 2-hop block is wrapped in its own `try/except` so a future 2-hop failure degrades to 1-hop-only instead of letting `_safe_l2_facts` swallow it and zero the whole L2 layer.

**Why it slipped:** the happy-path unit test mocked `find_relations_2hop` with a bare `AsyncMock` (accepts any kwargs). Added 2 regressions in [test_facts_selector.py](../../services/knowledge-service/tests/unit/test_facts_selector.py): (1) `test_select_2hop_passes_required_hop1_types` uses a stub mirroring the REAL required-kwarg+non-empty contract; (2) `test_select_2hop_failure_degrades_to_1hop`.

**VERIFY:** 11/11 facts selector unit (9+2) + 30/30 mode_full green on host. **LIVE SMOKE PASS** — host python (edited source) → live Neo4j (`bolt://localhost:7688`): seeded `Arthur -married_to-> Guinevere -knows-> Lancelot`, RELATIONAL intent → L2 returns 1-hop `Arthur — married_to — Guinevere` AND 2-hop `Arthur — married_to — Guinevere — knows — Lancelot` (was empty/`TypeError` pre-fix). MED L2 temporal-bucketing (all→`background`) still deferred, untouched.

**Clean-judge re-judge (eval-flaw #1 quantified)** over the c73b-drop-realized ship dump, judges disjoint from extractor `019e6a20` + filter `019e5650`: gemma `019dc3df` **0.888** + phi4 `019dc3ab-2b65` **0.851** (+ qwen35 `019dc3fb` running). 2-judge clean median **0.869** vs locked headline **0.913** = **~4–5pp self-inflation** (extractor self-grades **0.972**, filter self-grades 0.913 = the pinned median). Confirms the audit's self-reinforcement claim empirically. Needed a one-time provider-registry pricing row (`{input_per_mtok:0,output_per_mtok:0}`) on phi4+qwen35 to clear the gateway 402. Artifacts: `tests/quality/eval_runs/c74c-clean-rejudge/` (not committed with the hotfix).

**NEXT:** eval-architecture cycle (bake disjoint-judge metric + bootstrap CIs + rename claude-4.7-opus). User drives scope.

## Session 74 — cycle 74c: relation-lever refutations + full architecture/eval audit

### Part A — four relation/events R&D levers investigated, ALL refuted (no code shipped)

User wanted to push extraction quality. I rigorously investigated and **refuted every candidate cheap lever** — banked as negatives so they are not re-litigated:

1. **Events fuzzy-match (D-EVENT-AGGREGATOR-FUZZY-MATCH) → STALE.** Premise ("events weakest") dates to cycle 69. Current macro F1 by category (c73e-on verdicts): entity 0.93–0.99, **relation 0.69–0.94 (weakest)**, event 0.945–0.983 (strong). The LLM recall judge already matches "under any phrasing", so granularity drift is absorbed. **Close this deferred row as stale.**
2. **Filter confirmed-endpoint exemption → REFUTED.** "Keep relations whose both endpoints are confirmed entities" would recover 39/48 filter-dropped relations — but ~37 are garbage the filter correctly dropped (`White Rabbit -located_in-> waistcoat-pocket`, `Bingley -married_to-> Netherfield Park`). Both-endpoints-are-entities ≠ predicate is correct. Would tank precision.
3. **Deterministic predicate↔object-kind rule → REFUTED.** No clean separator: same predicates/kinds appear in garbage AND good (person obj 16 dropped/35 kept; `lives_in` 3/9; `married_to` 1/3). Garbage-vs-good is semantic — exactly what the LLM filter judges.
4. **Confidence-threshold prune → UNMEASURABLE.** Eval dumps carry no confidence (0/121 relations) — needs re-extraction.

**Conclusion:** the relation extractor over-extracts spurious relations (48 dropped corpus-wide, mostly garbage); the filter correctly cleans them; shipped relation *precision* is already 0.89–0.94. No cheap lever remains; the only path is a risky+expensive prompt-tightening re-extraction (cycle-71 lessons warn of regression). Pass2 relation R&D is at the **cheap-lever frontier**.

### Part B — full RAG + extraction + eval architecture audit → [docs/reports/2026-05-30-rag-pipeline-audit.html](../reports/2026-05-30-rag-pipeline-audit.html)

User distrusted the eval results. I ran a 3-pipeline audit (extraction, RAG retrieval, eval framework) via parallel subagents + direct verification, and produced a detailed technical HTML report. **Corrected verdict (after user feedback that local models are strong + a strong model already validated outputs):**

- **Models are NOT the problem.** Extractor/judges are near-top-tier open models (Google Gemma-26B, Alibaba Qwen-30B/35B). Strong-model (Claude) manual review across sessions — incl. this session's spot-checks — corroborates the extraction output is genuinely good. Results are **not fake**.
- **RAG retrieval architecture = correct** (mode dispatch, L0–L3 layers, bge-m3 1024-d cosine vector + MMR λ=0.7 + hub-penalty/recency, oversample-then-tenant-filter, token budgeting). Standard, sound. **Two defects, not design errors:**
  - 🐞 **HIGH — 2-hop graph retrieval is dead code.** `app/context/selectors/facts.py:183` calls `find_relations_2hop()` without the **required** kw-only `hop1_types` (`db/neo4j_repos/relations.py:547`, no default) → `TypeError` swallowed by `_safe_l2_facts` → **entire L2 fact layer returns empty for every RELATIONAL-intent query**. Verified. Fix + regression test.
  - MED — L2 temporal bucketing unimplemented (all relations → `background`).
- **Eval design = above-average, but two SETUP-correctness flaws inflate the absolute numbers (independent of model quality):**
  - **Self-reinforcement WIRING:** extractor `019e6a20` == ensemble Judge B (qwen-30b); precision filter `019e5650` == ensemble Judge C ("claude-4.7-opus", which is actually a local `huihui-qwen3.6-35b-…-abliterated` fine-tune, NOT Anthropic Claude). Only Judge A (gemma `019dc3df`) is independent. Grading your own output inflates F1 regardless of grader strength. The locked 3-judge median includes both self-overlapping judges.
  - **Undersized gold set + no CIs:** 9 chapters, 1–6 gold items each (3 chapters have exactly 1 gold relation), macro-averaged, no confidence intervals — yet ships on ±0.1–0.3pp. A single-run nondeterminism swing of −29pp on alice_ch01 already exceeds every cycle's claimed lift.
  - CoNLL 0.219 / DocRED 0.127 are a **domain-mismatch sanity floor (news/Wiki NER ≠ fiction extraction), NOT a quality verdict** — do not read as "real accuracy is 0.22".
- **Net:** eval is reliable as a *relative same-judge drift signal*; its *absolute F1 is inflated by self-grading* and *sub-0.5pp deltas are noise*. Fixable without new models: make judges disjoint from extractor/filter, grow the gold set, add CIs.

### NEXT WORK (user directive) — production-readiness evaluation, then conditional improvement plan

Decision gate the next session must resolve:
- **If the architecture is already good at production level → STOP.**
- **If quality is low OR cost is too high → make a plan** to improve via architecture changes / additional algorithms / techniques that **reduce cost and improve quality**. **Priority order: precision (quality) FIRST, cost SECOND, latency LAST** (a precision-first RAG pipeline tolerates latency).

To evaluate cleanly, the next session should FIRST neutralize the two eval-setup flaws so the readiness number isn't self-inflated:
1. **Get a self-reinforcement-free quality number** — re-judge with the judge set restricted to models that are NEITHER the extractor (`019e6a20`) NOR the filter (`019e5650`); i.e. judge with gemma + one or more *other* models not used in extraction/filtering. Compare to the current 0.913. (Re-judge runs from HOST via `tests/quality/run_rejudge_resumable.py`, host→provider-registry :8208→LM Studio :1234 — bypasses the container OOM blocker.)
2. **Measure COST** — tokens + wall-clock per chapter for the full pipeline (extract ×4 + relation filter + writes + embeddings). The relation-only drop filter adds ~18.9s/chapter; quantify $/chapter-equivalent and throughput on the local LM Studio target.
3. **Then judge production-readiness** on precision-first criteria and either stop or write an improvement plan (candidate levers: better/smaller extractor, prompt-tightening with proper re-extraction measurement, cheaper filter, retrieval improvements, fixing the 2-hop bug which is pure correctness).

## Session 74 summary — cycle 74a-smoke + 74b: 73f live smoke + disable-semantics fix (D-CYCLE73F-LIVE-SMOKE)

**Result: 73f reload happy-path PASS (cross-service) + found & fixed a MED disable-semantics divergence (74b).**

**Setup gotcha:** deployed images PREDATED 73f/73h — both KS + worker-ai images were built ~2-5h before the 73f/73h commits (KS reload endpoint 404'd live; worker-ai had no `:8226` port). `compose up` doesn't rebuild. Had to `compose build knowledge-service worker-ai && up -d` first. (Lesson: `feedback_verify_deployed_image_matches_source` — caught before chasing a phantom bug.)

**73f happy-path smoke (PASS, cross-service):** `POST :8216/internal/admin/precision-filter/reload` (auth `X-Internal-Token: dev_internal_token`) with a custom config → 200 `redis_publish_status=published` + echoed config → Redis key `loreweave:precision-filter-config` written with `schema_version:1` envelope → worker-ai logged `WORKER_FILTER_RELOAD outcome=applied active=True` sub-ms later → `worker_ai_filter_reload_total{outcome=applied}` bumped → 73h `:8226/metrics` reachable (`startup=1`). Empty body → 422; auth works. **Note:** worker pubsub subscriber connects ~2s after boot (SDK resilient-backoff); POSTing within that window misses the signal (documented fire-and-forget limitation #1) — re-POST converges.

**74b fix — `disable=true` semantics were inconsistent (MED, found by the smoke):** the runtime pubsub path did `set(get_filter_config())` unconditionally → key-absent (after a `disable` DELETE) set the cache to **None (filter OFF)**, while startup hydrate did `if cached is not None: set(...)` → key-absent **kept env config (filter ON)**. So a runtime disable silently reverted to env-config on the NEXT restart — a cross-path divergence unit tests couldn't catch (they mock `get_filter_config` + assert `set(None)`). **Fix (user chose consistency-fix):** runtime now matches startup — on key-absent, reload `_load_precision_filter_config()` (env) instead of None, in all 3 paths: KS pubsub `_on_reload` ([pass2_orchestrator.py](../../services/knowledge-service/app/extraction/pass2_orchestrator.py)), worker pubsub `_on_reload` ([runner.py](../../services/worker-ai/app/runner.py)), KS endpoint local-apply ([internal_admin.py](../../services/knowledge-service/app/routers/internal_admin.py)) + docstrings. `disable=true` is now a **clear-the-override** op (reverts to env-config), NOT a force-off. Trade-off (accepted): can't fully disable the filter at runtime when env sets one; `_load` returns None when no filter env is set so a no-filter deployment still lands disabled.

**Re-smoke after 74b (PASS):** `POST custom` → worker `active=True model_ref=custom-uuid-2`; `POST disable` → worker `active=True model_ref=019e5650…` (env config, **NOT** active=False/None) + KS response returned env config not null. Counter `applied=2`, key absent.

**Tests:** KS `test_internal_admin.py` (50) + `test_pass2_orchestrator.py` — replaced the old `disable→None` lock with `disable→env-config` + added env-revert pubsub test; worker `test_runner.py` (59) — added env-revert consume test. All green on host.

**D-CYCLE73F-LIVE-SMOKE → CLOSED** (smoke ran + cross-service verified). 74b folded the finding inline.

## Session 74 summary — cycle 74a: c73e writer-autocreate realized-F1 eval (D-PASS2-WRITER-AUTOCREATE-F1-EVAL)

**Result: F1-NEUTRAL. Compose default stays OFF (SDK opt-in unchanged). Deferred row CLOSED.**

Ran the 3-judge ensemble re-judge (gemma + qwen-30b + claude-4.7-opus) on the saved `c73e-autocreate-on` dump that was blocked twice in session 73 by container OOM.

**Blocker permanently sidestepped — host orchestration.** The session-73 deaths happened because the re-judge ran *in* knowledge-service, and LM Studio JIT model-load → host memory pressure → Docker Desktop OOM-kills the heaviest container. Session 74 ran the orchestrator on **host Python** instead: `host → provider-registry (:8208) → LM Studio (:1234)`. knowledge-service is NOT in the re-judge path, so its OOM-killer can't reach the run. New reusable driver [`run_rejudge_resumable.py`](../../services/knowledge-service/tests/quality/run_rejudge_resumable.py) persists each judge's verdicts the instant it finishes (crash only loses the in-flight judge) and resumes by skipping already-complete judges. Run completed clean in ~23 min, all 3 judges `complete`, κ=0.738. **This makes D-DOCKER-RESTART-INVESTIGATION non-blocking for all future F1 cycles.**

**Measured F1 (3-judge ensemble):**

| Variant | gemma | qwen-30b | claude (median) | **3J median** | mean | κ |
|---|---:|---:|---:|---:|---:|---:|
| c73b-drop realized (SHIP) | 0.888 | 0.972 | 0.913 | **0.913** | 0.924 | 0.756 |
| c73e-autocreate-on | 0.901 | 0.979 | 0.911 | **0.911** | 0.930 | 0.738 |
| **Δ** | +1.3pp | +0.7pp | −0.2pp | **−0.2pp** | +0.6pp | −0.018 |

The locked metric (3J median) moved **−0.2pp (within noise)** — the expected +0.3-0.6pp lift did NOT materialize. gemma/qwen improved but the median pins to claude (flat). The +6 cascade-recovered relations are low-confidence (`≤0.3`, `kind=concept`) abstract subjects (`仙卿`, `大海`, `Bụt`, `cha Tấm`, `cung`); judges weight them near-indifferently — zero precision cost, zero median lift. Confound ruled out: claude judged 0/421 unjudged; the 190 truncation warnings (83% budget) all parsed cleanly. D10 clause (a) does not clear → keep default OFF. Detail in [`c73e_compare.md`](../../services/knowledge-service/tests/quality/eval_runs/c73e_compare.md).

**Deferred rows resolved:**
- **D-PASS2-WRITER-AUTOCREATE-F1-EVAL** → CLOSED (measured: F1-neutral).
- **D-PASS2-WRITER-CASCADE-GAP-CLOSE** → can CLOSE (gap measured as F1-immaterial; further closing chases a flat lever).
- **D-DOCKER-RESTART-INVESTIGATION** → de-prioritized for F1 work (host-orchestration bypass); still open for general stack stability if desired.

**Methodology note for next F1 cycle:** raise `KNOWLEDGE_JUDGE_BASE_TOKENS` above 3072 to clear the claude truncation warnings (harmless here — JSON recovered — but cleaner). Run from host with the exact env block in `run_rejudge_resumable.py`'s docstring; provider-registry host port is `:8208`, internal token `dev_internal_token`.

## Session 73 summary — cycle 73h Prometheus metrics infra for worker-ai

### Cycle 73h (L) — D-WORKER-AI-METRICS-INFRA

Worker-ai now exposes `worker_ai_filter_reload_total{outcome}` on `:8226/metrics` (host) → `:8094` (container). Closes cycle 73f r3 M4 log-only stopgap.

**What ships:**
- `prometheus-client>=0.20` worker-ai dep
- NEW `services/worker-ai/app/metrics.py` — dedicated CollectorRegistry + counter (4 outcomes: applied, failed, startup, startup_failed) + `start_metrics_server()` helper using built-in WSGI server (daemon thread, runs alongside asyncio)
- `config.py` `metrics_port` setting (default 8094; set 0 to disable)
- `main.py` starts metrics server at boot
- `runner.py` bumps counter on hydrate (startup/startup_failed) + on_reload (applied/failed)
- `docker-compose.yml` worker-ai ports `["8226:8094"]`

**Tests:** 12/12 worker-ai cycle 73f+73h pass (+4 cycle 73h regression-locks: counter bumps on applied/failed/startup + no-op when port=0). KS 94/94 unchanged.

### Cycle 73g (M) — D-CYCLE73F-r3-MEDLOW-CLEANUP

Batch fold of 4 MED + 2 LOW findings from cycle 73f r3 /review-impl:

- **M1** counter outcome=applied now ADDITIVE with failed (was mutually-exclusive, masked local-applied + redis-failed branch from dashboards). Matches cycle 73e M4 pattern.
- **M3** KS subscriber task cancel block added in lifespan shutdown (was leaking redis client + pubsub connection on container shutdown).
- **M4** worker-ai distinct structured log token `WORKER_FILTER_RELOAD` (later promoted to Prometheus counter in cycle 73h).
- **L1** added KS hydrate function tests (2 regression-locks; previously hydrate was wired but untested).
- **L2** added real-function mutation regression-lock for `set_precision_filter_config` (mock-only tests would have hidden a regression where the function early-returns without rebinding).
- **L3+L4** endpoint docstring expanded with pubsub-message-loss + redis-restart documented limitations.

**Tests:** 94/94 KS + 11/11 worker-ai pass after fold.

### Cycle 73f r3 fix (L/FIX) — `/review-impl` round 3 catches 2 HIGH that survived rounds 1+2

User invoked /review-impl r3 via slash command. Findings:

- **H1** worker-ai missing startup hydrate (asymmetric with KS r2 H1 fold) → worker restart silently dropped ops-override. Added `hydrate_precision_filter_config_from_redis()` in worker-ai/app/runner.py + wired into main.py before asyncio.gather. 2 new regression-lock tests.
- **H2** KS double-read of `_PRECISION_FILTER_CONFIG` (race window with concurrent pubsub) → AttributeError crash on `config.categories` access if reload swaps to None mid-call. Snapshot to local var at `_maybe_apply_precision_filter` entry. 1 new race-simulation regression-lock test.
- 4 MED + 5 LOW deferred to cycle 73g (now closed).

Lesson: r3 typically catches orphans from r1+r2 fixes — `feedback_review_impl_round_3_on_fix_delta` validated again.

## Session 73 summary — cycle 73f runtime filter reload (Redis-key + pubsub hybrid)

### Cycle 73f (L) — D-PASS2-FILTER-RUNTIME-FLAG ops endpoint for runtime config reload

Goal: ops can change Pass2 precision filter config (categories, partial_policy, model_ref) WITHOUT compose restart. Architecture: Redis-key as source of truth + pubsub for change notification + module-level cache in both KS + worker-ai. Bypasses container restart pattern that killed 73e ensemble 2x.

**Architecture:**

```
POST KS endpoint → SET Redis key + PUBLISH pubsub channel
                 → KS local cache swap (immediate)
                 → workers receive pubsub → re-read Redis → update cache
KS startup       → GET Redis key → seed cache (hydrate)
KS pubsub sub    → listen for cross-replica reload signals
```

**What ships:**
- NEW `sdks/python/loreweave_extraction/filter_config_store.py` (~220 lines, 10 tests) — duck-typed Redis helpers, schema_version envelope, defensive deserializer, subscriber loop with backoff
- KS `POST /internal/admin/precision-filter/reload` endpoint (body-based config, server-generated timestamp, model_validator catches disable+model_ref ambiguity + empty-body, Field validators, try/finally Redis cleanup)
- KS lifespan hydrate + subscriber task (r2 H1 fold — was missing, would have broken multi-replica)
- Worker-ai subscriber wired into `asyncio.gather`
- `set_precision_filter_config()` setter in both KS + worker-ai (atomic module-level swap via Python GIL)
- NEW Prometheus counter `knowledge_extraction_filter_reload_total{source, outcome}` (9 series)

**Tests:** 106/106 pass (90 KS + 10 SDK + 6 worker-ai incl. 2 new cycle 73f tests)

**3-round /review-impl:**
- r1 on DESIGN: 7H + 9M + 6L; 7H + 5M + 2L folded inline (server-timestamp, ge=1 validation, list→tuple, subscriber resilience, schema_version envelope, swap-then-publish order, metric counter, channel naming, connection cleanup, validation truth table)
- r2 on BUILD diff: 2H (1 critical) + 4M + 4L; H1 critical "KS never subscribes to own pubsub" folded (added hydrate + consume_filter_reload_signal in pass2_orchestrator + wired into main.py lifespan). H2 verified clean. M+L folded or deferred.

**Documented limitations (accepted):**
1. Pub/sub miss while worker restarting → ops re-reloads manually; monitor via metric counter
2. KS-local apply succeeds even when Redis publish fails → `redis_publish_status="failed"` surfaces drift via response field
3. Cross-service live smoke deferred to D-CYCLE73F-LIVE-SMOKE per container restart pattern (3x in this session)
4. In-flight job consistency: orchestrator reads `_PRECISION_FILTER_CONFIG` per call; reload mid-job means chapter N uses old, N+1 uses new (acceptable for ops-tooling)

**Deferred rows added:**
- **D-CYCLE73F-LIVE-SMOKE** — cross-service smoke (curl KS reload → tail worker logs → verify cache swap) when container stable
- **D-PASS2-FILTER-PER-JOB-OVERRIDE** — per-job override via StartJobRequest.filter_override field
- **D-PASS2-FILTER-PER-USER-UI** — FE surface (cycle 72 deferred)

### Cycle 73e (L) — Pass2 writer Tier-A name repair + Tier-B autocreate — closes 73c's writer-cascade gap WITHOUT LLM (no self-reinforcement risk)

## Session 73 summary — cycle 73e Pass2 writer Tier-A + Tier-B autocreate ship decision

### Cycle 73e (L) — Pass2 writer Tier-A name repair + Tier-B autocreate — closes 73c's writer-cascade gap WITHOUT LLM (no self-reinforcement risk)

Goal: close the baseline 10.7% writer-cascade gap (cycle 73c finding) by promoting unresolved relation subjects/objects via 3 mechanisms — all LLM-free, bypass-by-construction the self-reinforcement risk that blocked cycle 73d.

**Three tiers:**

- **Tier A.1** — chapter-local canonical-name map repair (free, always-on). Catches relation subject name matching extracted entity but with mismatched/missing IDs.
- **Tier A.2** — anchor index pre-check (free, always-on). Catches names that match a glossary anchor.
- **Tier B** — env-gated MERGE of new `:Entity` with `kind="concept"`, `auto_created=true`, `confidence=min(rel.confidence, 0.3)`. Per-chapter cap default 20.

**Cascade simulation (c73b-drop dump input, 73 relations):**

| Variant | Cascade-skip | Recovered | Verdict |
|---|---:|---:|---|
| c73e-autocreate-off | 13.7% (10/73) | 0 | baseline (≡ c73b-drop-realized) |
| **c73e-autocreate-on** | **5.5% (4/73)** | **+6 relations** | mechanism works |

Per-chapter detail: `journey_west_zh_ch01` recovers `仙卿` + `大海`; `tam_cam_vi` recovers `Bụt` + `cha Tấm` + `cung`; `little_women_ch01` correctly noise-skips 4 compound subjects ("fancy words and refined speech" etc.). Tier A.1 didn't fire on this fixture — all cascade-skips were due to LLM not extracting the relation subject as an entity (not ID-drift within chapter).

**Realized F1 (3-judge ensemble re-judge):** **DEFERRED to D-PASS2-WRITER-AUTOCREATE-F1-EVAL.** Two ensemble attempts both killed by knowledge-service container restart mid-run (gemma judge in flight; LM Studio JIT-load triggered host memory pressure → Docker Desktop killed container, /tmp wiped on restart). Same recurring pattern as cycle 73b first run (2026-05-30 06:14 UTC). Per CLAUDE.md "No Deadline · No Defer Drift," **D-PASS2-WRITER-AUTOCREATE-F1-EVAL is added to Naturally-next-phase deferred items** — re-run when container is stable for 30+ min uninterrupted.

**Ship decision: SDK ships opt-in (cycle 73d pattern); compose default OFF.** Mechanism validated via cascade simulation (+6 relations recovered, 5.5% cascade-skip vs 13.7% baseline, 0 noise false-positives). Quantitative F1 lift unevaluated. Power users can opt-in via `KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED=true` in `.env` to AB-test in their own deployments.

**Ship gate D10 5-clause:** unevaluable without realized F1 — deferred to F1 eval cycle.

**Deferred rows added:**
- **D-PASS2-WRITER-AUTOCREATE-F1-EVAL** (NEW) — re-run 3-judge ensemble on c73e-autocreate-on when container stable. Expected lift ~+0.3-0.6pp 3-judge median F1 based on cycle 73c proportionality (6 supported-cascade-recovered ≈ inverse of c73b's -0.3pp / c72c's -1.3pp realized loss).
- **D-PASS2-WRITER-CASCADE-GAP-CLOSE** (still OPEN) — mechanism shipped opt-in; activation pending F1 confirmation.

**What ships regardless of ship verdict:**
- ✅ `services/knowledge-service/app/db/neo4j_repos/entities.py` — `auto_created` property + ON MATCH promotion CASE
- ✅ `services/knowledge-service/app/extraction/entity_resolver.py` — `auto_created` kwarg plumbed
- ✅ `services/knowledge-service/app/extraction/pass2_writer.py` — Tier A.1 + A.2 + B logic + new `entities_autocreated` + `endpoints_repaired_by_name` Pass2WriteResult fields
- ✅ `services/knowledge-service/app/extraction/pass2_orchestrator.py` — `_load_writer_autocreate_config()` + TypedDict + spread into 3 writer call sites
- ✅ `services/knowledge-service/app/metrics.py` — NEW `knowledge_extraction_writer_autocreate_total{role, outcome}` counter (9 outcomes)
- ✅ Compose envs default OFF (`KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED=false`, `MAX_PER_CHAPTER=20`)
- ✅ Eval driver `run_c73e_writer_autocreate.py` + 2 eval fixture dirs + `c73e_compare.md`
- ✅ 28 new unit tests (7 entities + 18 writer + 3 orchestrator env-loader)

**`/review-impl` round 1 on DESIGN:** 5 HIGH + 7 MED + 5 LOW findings, all HIGHs + 6 MEDs + 4 LOWs folded inline before BUILD. Notable folds:
- H1: kind-collision in Tier A.1 chapter map → multi-kind triggers `kind_ambiguous` outcome, skip both A and B
- H2: word-count heuristic broken for CJK → combined char-budget(60) + word-budget(3)
- H3: hardcoded `confidence=0.0` defeats ON MATCH ratchet → use `min(rel.confidence, 0.3)`
- H4: anchor hit silently marked auto → pre-check separates `tier_a_anchor_repair` outcome from `tier_b_autocreated`
- M1: ON MATCH never clears `auto_created` → CASE clause clears on legit `auto_created=False` write (promotion)
- M7: ship gate too permissive → added clause (e) per-category regression cap

**`/review-impl` round 3 on FIX delta (post-r2 folds):** 2 real HIGH + 1 false-alarm HIGH + 3 MED + 3 LOW findings. Fold:
- H1: eval driver's `entity_names_set` raw-name shortcut bypassed fold logic → DELETED the shortcut; now every endpoint routes through fold map. **Effect:** revealed correct attribution (136 tier_a_name_repair across 9 chapters; previously under-counted as 0). Cascade-skip rate UNCHANGED (5.5% with autocreate-on, 13.7% off) — only the BOOKKEEPING was wrong, not the mechanism.
- H2: dead `cascade_dropped` inline bump in autocreate-disabled branch → removed (recompute formula at end was correct)
- H3: CONFIRMED OK (parity-correct, not a regression)
- M3 + L1: strengthened 2 tests with `evidence_edges` assertion (H3 fold proof) + create_relation kwargs verification (H2 fold proof)
- M1 + M2: deferred (SDK fallback in eval driver runs in container; evidence confidence semantic documented but not blocking)

**Re-framed cycle 73c finding (via r3 H1 discovery):** the "10.7% cascade gap" is mostly Tier A.1's job — relations have `subject_id=null` because the LLM-relation-extractor never resolves them, and the writer's name-to-ID Tier A.1 catches 93% (136/146 endpoints). Only ~5% (6/146) need Tier B autocreate. Cycle 73e's real contribution: providing the structured tier-resolution path + telemetry to attribute and tune the residual.

**`/review-impl` round 2 on BUILD diff (post-implementation):** 3 HIGH + 5 MED + 5 LOW findings. All HIGHs + 3 MEDs + 1 LOW folded inline before ensemble re-judge:
- H1: fold-key drift between Step 2 (sanitized) and Step 3 (raw) silently missed Tier A.1 → moved `_sanitize` before `_fold_name` in Step 3
- H2: `setattr(rel, ...)` mutated input Pydantic model, breaking retry semantics → refactored to use LOCAL `resolved_subject_id`/`resolved_object_id` vars
- H3: Tier A.2 anchor repair skipped `add_evidence` for the anchor entity → added evidence accrual after anchor repair
- M1: eval driver used SIMPLIFIED canonicalize (no honorific strip) → imported production `canonicalize_entity_name` from SDK
- M3: counter assertions break under pytest-xdist → added `pytestmark = pytest.mark.xdist_group("c73e-writer-autocreate-metrics")` module-level
- M4: cap_exhausted metric was mutually-exclusive with cap_exhausted_high_conf, diverging from eval driver → made additive (high_conf BOTH bumps cap_exhausted + cap_exhausted_high_conf)
- L3: added 2 regression-lock tests (self-reference relation Tier B→A.1 propagation, input-relation-id-not-mutated)

Final test count: **101 focused regression passes** (entity_auto_created 7 + entities_mutations 8 + entity_resolver 21 + pass2_writer pre-existing 19 + pass2_writer_autocreate 20 + pass2_orchestrator 26). +30 net new tests vs pre-73e baseline.

### Cycle 73d (M) — entity recovery (3-tier glossary→hints→LLM) — NEGATIVE; SDK ships opt-in, NOT activated

Goal: close the baseline 10.7% writer-cascade gap identified in cycle 73c by promoting unmatched relation subjects/objects as :Entity nodes via 3-tier resolution (glossary → optional author hints → LLM classifier fallback).

**Empirical 4-variant comparison** (all on c70a saved fixture, ensemble re-judged):

| Variant | Filter-output F1 | Cascade-skip rate | Realized F1 | Per-chapter latency |
|---|---:|---:|---:|---:|
| c70a baseline | 0.895 | 10.7% | ~0.88 (est) | — |
| c72c-drop realized (cycle-72 retired) | — | 22.5% | 0.904 | 42.5s |
| c73b-drop realized (current SHIP) | — | 12.3% | **0.913** | **18.9s** |
| c73d-recov-only | 0.898 | **0%** | 0.898 | **2.0s** |
| c73d-recov-plus-rel (proposed) | 0.922 | **0%** | 0.922 | ~30s |

3-judge median F1 lift of c73d-recov-plus-rel: **+0.9pp** vs c73b-drop-realized. But D10(c) self-reinforcement check catches it:

**Self-reinforcement check** (recompute median over judge-subset excluding the filter+classifier model):

| Variant | 3-judge median | **2-judge mean (no claude)** | Δ 2J vs c73b ship |
|---|---:|---:|---:|
| c73b-drop realized (SHIP) | 0.913 | 0.9300 | — |
| c73d-recov-plus-rel (proposed) | 0.922 | **0.9285** | **-0.15pp** |

The +0.9pp 3-judge lift came **entirely from the claude judge**. With claude removed, c73d-recov-plus-rel is **slightly WORSE** than c73b-drop. Classic self-reinforcement signature — claude classifier's output over-credited by claude judge.

**Ship decision: don't activate c73d as default.** SDK ships opt-in:
- ✅ `sdks/python/loreweave_extraction/entity_recovery.py` (~340 lines, 13 unit tests)
- ✅ `EntityRecoveryConfig` + env loaders (knowledge-service + worker-ai)
- ✅ New Prometheus counter `knowledge_extraction_recovery_decisions_total{source, verdict}`
- ✅ Compose envs default OFF
- ✅ Eval driver `run_c73d_recovery.py`
- ✅ Eval results `eval_runs/c73d-recov-only/` + `eval_runs/c73d-recov-plus-rel/`
- ✅ `eval_runs/c73d_compare.md` documenting the negative ship outcome

**Re-validation conditions** (re-evaluate when ANY of):
- Non-claude classifier model available (cloud claude-haiku-4-5 BYOK lands)
- 4th non-claude judge added to ensemble (e.g. cloud Claude judge)
- Author-hints API in book-service (Tier 2 use case grows, less reliance on Tier 3 LLM)

**Bonus finding (cycle 73d sub-result):** recovery successfully closes the c73c baseline cascade gap — 0% cascade-skip on c73d-recov-only (vs c70a's 10.7%, c73b's 12.3%). The mechanism works; the ship blocker is the self-reinforcement check, NOT the recovery itself.

**Memory lesson:** `feedback_anti_self_reinforcement_via_judge_subset_recompute` — when filter/classifier model is also in ensemble, recompute median over judge subset excluding that model; if lift disappears, it was self-reinforcement.

**Deferred rows added:**
- **D-ENTITY-RECOVERY-NON-CLAUDE-CLASSIFIER** (NEW) — re-validate c73d when a non-claude classifier model is available

### Cycle 73c (S→M scope-bump) — Neo4j-realized F1 cascade analysis + empirical re-judge

### Cycle 73c (S→M scope-bump) — Neo4j-realized F1 cascade analysis + empirical re-judge

**Question:** does the pass2_writer's relation-cascade-skip change the F1 numbers from cycle 72/73b ship decisions?

**Process:**
1. Analytics: simulated writer's cascade rule on saved filter dumps; computed supported-cascade rate per variant
2. Scope-bump (user approved): generated "realized" `actual.json` per variant (with cascade applied) → ran 3-judge ensemble re-judge on the realized dumps (~33 min total wall-clock)

**Empirical results:**

| Variant | Filter-output F1 | Realized F1 | Δ from cascade | Verdict |
|---|---:|---:|---:|---|
| c70a baseline | 0.895 | _not re-judged_ | est ~0.88-0.89 | Pre-existing writer-cascade gap (10.7% supported-relations cascade-skip) |
| c72c-drop (cycle-72 ship) | 0.917 | **0.904** | **-1.3pp** | Over-credited; cascade dropped supported relations |
| **c73b-drop (current ship)** | 0.916 | **0.913** | **-0.3pp** | Validated; near-negligible cascade impact |

**Key findings:**
- On realized basis, c73b-drop is **+0.9pp ahead of c72c-drop** (vs +0.1pp on filter-output) — much stronger ship case
- Pre-existing writer-cascade gap: even no-filter c70a has 13/121 (10.7%) judge-supported relations that would cascade-skip at write time. Root cause: LLM extracts relations with abstract/compound subjects ("civil practice", "home peace and comfort") that weren't extracted as entities
- Filtering entities (cycle-72 approach) MAKES the cascade worse (22.5% supported-cascade rate vs baseline 10.7%); filtering only relations (cycle-73b approach) doesn't make it worse (12.3% ≈ baseline)

**Ship recommendation: c73b-drop stays — now confirmed strictly better than c72c-drop on realized F1.**

**Deferred rows added:**
- **D-PASS2-WRITER-CASCADE-GAP-CLOSE** — close the baseline 10.7% cascade gap by extending entity extraction to abstract/compound subjects (option a), OR auto-creating entities at write time (option b), OR pre-filtering unresolved relations (option c). Recommend (a) for first pass.
- **D-PASS2-CASCADE-C70A-REALIZED-REJUDGE** — re-judge c70a on realized state to complete the realized-F1 picture; expected ~0.88-0.89.

**Memory lesson captured:** TBD pending RETRO.

### Cycle 73a (S-verify) — cycle 72 activation confirmed in dev stack

Rebuilt knowledge-service + worker-ai with cycle-72 SDK baked in; envs propagated, `_PRECISION_FILTER_CONFIG` loaded at module import in both services; end-to-end smoke filter call dropped fabricated entities + relations. No code or doc changes. Verified the cycle-72 SHIP commit actually works in production-shape compose stack.

### Cycle 73b (M) — relation-only filter SHIPPED — median F1 0.916, **44% latency reduction vs c72c-drop**

(see "Session 73 summary — cycle 73a verify CLEAN + cycle 73b SHIPPED relation-only filter (44% latency win)" — kept intact below)

---

## Session 73 summary (legacy header — kept for grep continuity) — cycle 73a verify CLEAN + cycle 73b SHIPPED relation-only filter (44% latency win)

### Cycle 73a (S-verify) — cycle 72 activation confirmed in dev stack

Rebuilt knowledge-service + worker-ai with cycle-72 SDK baked in; envs propagated, `_PRECISION_FILTER_CONFIG` loaded at module import in both services; end-to-end smoke filter call dropped fabricated entities + relations. No code or doc changes. Verified the cycle-72 SHIP commit actually works in production-shape compose stack.

### Cycle 73b (M) — relation-only filter SHIPPED — median F1 0.916, **44% latency reduction vs c72c-drop**

Hypothesis from c72c per-category analysis: relations carried virtually all of c72c-drop's +2.2pp F1 lift. Filtering entities + events added marginal κ improvement at significant latency cost.

**Empirical** (3-judge ensemble re-judge against c70a saved fixture):

| Variant | gemma F1 | qwen-30b F1 | claude F1 | Median F1 | Δ vs c70a | Per-chapter latency | 6-clause gate |
|---|---:|---:|---:|---:|---:|---:|---|
| c70a (baseline) | 0.848 | 0.955 | 0.895 | 0.895 | — | — | — |
| c72c-drop (cycle-72 ship) | 0.891 | 0.973 | 0.917 | 0.917 | +2.2pp | 42.5s | PASS 4/4 D10 |
| c73b-keep (rel-only, keep) | 0.855 | 0.964 | 0.907 | 0.907 | +1.2pp | 25.5s | FAIL (a)+(f) |
| **c73b-drop (rel-only, drop)** | **0.887** | **0.971** | **0.916** | **0.916** | **+2.1pp** | **18.9s** | **PASS 6/6** |

c73b-drop gate clauses (D10 + 2 cycle-73b-specific):
- (a) median F1 lift ≥ +1.5pp → +2.1pp PASS
- (b) min F1 lift ≥ -0.5pp → +1.6pp (qwen-30b) PASS
- (c) claude F1 lift ≤ 2× median → 2.1pp ≤ 4.2pp PASS
- (d) Fleiss κ ≥ 0.60 → 0.754 PASS (substantial; -0.022 from c72c-drop)
- (e) F1 within 1pp of c72c-drop (0.917) → 0.916, diff = 0.1pp PASS with margin
- (f) Per-chapter latency ≤ 21s (50% of c72c-drop) → 18.9s PASS with margin

**Hypothesis confirmed**: relation-only filter is **~2.2× more efficient** per second of latency (0.0485 F1/sec vs c72c-drop's 0.0216 F1/sec) with negligible F1 loss. Gemma still lifts +3.9pp on the relation-only filter, ruling out claude-self-reinforcement.

### Activation update

```yaml
# infra/docker-compose.yml — knowledge-service + worker-ai (cycle-73b default)
KNOWLEDGE_EXTRACTION_PRECISION_FILTER_CATEGORIES: ${...:-relation}  # NEW
WORKER_AI_PRECISION_FILTER_CATEGORIES: ${...:-relation}             # NEW
# (model_ref, partial_policy=drop, model_source unchanged from cycle-72 SHIP)
```

Override `CATEGORIES=entity,relation,event` to revert to cycle-72 full filter.

### SDK + service code changes

- `services/worker-ai/app/runner.py::_load_precision_filter_config` reads `WORKER_AI_PRECISION_FILTER_CATEGORIES` (default `"entity,relation,event"` for backward-compat)
- `services/knowledge-service/app/extraction/pass2_orchestrator.py::_load_precision_filter_config` reads `KNOWLEDGE_EXTRACTION_PRECISION_FILTER_CATEGORIES` (same default)
- Plus 3 new env-loader unit tests (2 worker-ai + 1 knowledge-service)
- Plus `run_c72_filter.py` accepts `KNOWLEDGE_C72_CATEGORIES` + `KNOWLEDGE_C72_PARTIAL_POLICY` for cycle 73b runs

### Eval artifacts shipped

- `services/knowledge-service/tests/quality/eval_runs/c73b-keep/` — filter dump + 3-judge ensemble
- `services/knowledge-service/tests/quality/eval_runs/c73b-drop/` — filter dump + 3-judge ensemble
- `services/knowledge-service/tests/quality/eval_runs/c73b_compare.md` — full D10+(e)+(f) gate evaluation + ship decision

### Operational note: knowledge-service container restart mid-ensemble

c73b-drop ensemble's first run was killed by a knowledge-service container restart at 06:14:20 UTC (clean exit, no OOM, no crash log). Cause unknown but only affected knowledge-service (worker-ai + provider-registry stayed up). Re-launched after re-copying `tests/` + dump back into container; second run completed cleanly in 17:24. Worth watching if pattern repeats — possibly Docker Desktop pause/resume artifact.

### Deferred items added/carried

- **D-PASS2-FILTER-NEO4J-REALIZED-F1** (carryover) — F1 post writer-cascade
- **D-PASS2-FILTER-FACTS-SUPPORT** (carryover) — filter facts
- **D-PASS2-FILTER-CLOUD-CALIBRATION** (carryover) — cloud Claude calibration
- **D-PASS2-FILTER-RUNTIME-FLAG** (carryover) — per-request header override
- **D-PASS2-FILTER-CACHE** (carryover) — verdict caching
- **D-PASS2-FILTER-PER-USER-UI** (carryover) — UI surface
- **D-PASS2-FILTER-CATEGORIES-AB-TUNE** (NEW from c73b) — re-validate relation-only ship after first month of production data; consider per-language or per-genre `categories` override

### Memory lessons captured this session

- **per-category-yield-attribution-via-ablation** — when a multi-component change ships positive, run an ablation to see which component carried the win. c73b-drop ablated c72c-drop down to just relations and confirmed entities + events added marginal value at significant latency cost.

### Session 73 entry point for the NEXT session

1. Verify cycle 73b activation similar to cycle 73a (rebuild already done in this session, env propagation confirmed)
2. Cycle 73c candidates from deferred list:
   - **D-PASS2-FILTER-NEO4J-REALIZED-F1** — post writer-cascade F1 measurement (most impactful — would let us distinguish filter-output gain from realized gain)
   - **D-PASS2-FILTER-FACTS-SUPPORT** — extend filter to facts (smaller scope)
   - **D-EVAL-FRAMEWORK-WIKINEURAL-MULTILINGUAL-ANCHOR** — multilingual NER anchor (predates cycle 71)
   - **C71 event prompt** revisit with the c70a lessons — events were never lifted by cycle 71/71-bis, are still the weakest extraction category

---

## Session 72.S2 summary — cycle 72 SHIPPED c72c (drop policy) — median F1 +2.2pp, κ +0.105, D10 4/4 PASS — historical

Ran the full BUILD + VERIFY + ship flow planned in S1. Filter `partial_policy="drop"` config (c72c variant) decisively cleared the D10 4-clause symmetric ship gate; activated by default in [`infra/docker-compose.yml`](../../infra/docker-compose.yml) for both knowledge-service and worker-ai. Filter is OFF in raw production envs (no compose; explicit env required) — dev compose ships it on by default to surface the F1 lift in routine use.

### Phases executed (S2)

| Phase | Commit | Output |
|---|---|---|
| CLARIFY-lite | — | c70a dump still in container; pass2.py / __init__.py / llm_judge.py unchanged since `1c0b2a08` baseline = no design drift |
| DESIGN | — | inherited from S1 spec; no re-litigation per `feedback_design_checkpoint_commit_separates_design_from_implementation` |
| REVIEW (design) | — | inherited from S1 round-1 fold (7 findings) |
| PLAN | — | inherited from S1 plan |
| **BUILD-1** SDK foundation | `f2d03c90` | 4 NEW SDK files (pass2_filter.py + precision_filter_prompts.py + precision_filter_system.md + c70a fixture dir) + 22 unit/integration tests; ships as dead code |
| **BUILD-2** orchestrator + caller wiring | `0211d3c3` | extract_pass2 kwarg + worker-ai env reader + knowledge-service orchestrator + metrics counter/gauge; 16 new regression tests; 288 tests pass cross-service |
| **BUILD-3** eval validation | `5f36802a` | c72b + c72c filter dumps + ensemble re-judge against c70a baseline; 2 bug fixes mid-Phase-3 (Pydantic model_construct for c70a-shape dump loading + messages[0].content extraction for production gateway response); c72_compare.md with full D10 4-clause evaluation |
| **SHIP** activation + handoff | pending | docker-compose.yml activation envs + this SESSION_HANDOFF update + RETRO lessons |

### Ship verdict — c72c (`partial_policy="drop"`)

| Variant | gemma F1 Δ | qwen-30b F1 Δ | claude F1 Δ | Median F1 Δ | Fleiss κ Δ | D10 4-clause |
|---|---:|---:|---:|---:|---:|---|
| c70a baseline | — | — | — | (0.895) | (0.671) | — |
| c72b (keep) | +0.5pp | +1.4pp | +1.4pp | +1.4pp | +0.019 | **borderline FAIL on (a)** by 0.1pp |
| **c72c (drop)** | **+4.3pp** | **+1.8pp** | **+2.2pp** | **+2.2pp** | **+0.105** | **PASS 4/4** |

D10 clauses:
- (a) median F1 lift ≥ +1.5pp — c72c +2.2pp PASS
- (b) min F1 lift ≥ -0.5pp — c72c +1.8pp (qwen-30b) PASS
- (c) claude F1 lift ≤ 2× median — c72c 2.2pp ≤ 4.4pp PASS (no self-reinforcement; gemma is the high outlier)
- (d) Fleiss κ ≥ 0.60 — c72c 0.776 PASS (substantial→strong)

**Anti-self-reinforcement signature absent**: filter uses claude-4.7-opus; gemma judge lifted MORE than claude (+4.3pp vs +2.2pp). The filter model is NOT getting an artificial boost from being the judge.

**Bonus signal**: gemma `language_bias` dropped 0.15 → 0.06, partially closing the EN-vs-CJK/VN judge bias concern from cycle 69's eval framework overhaul.

### Activation (default-on in dev compose, override to disable)

```yaml
# infra/docker-compose.yml — knowledge-service + worker-ai
KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF: ${...:-019e5650-eca7-78c2-985d-465aa3bce1ce}
KNOWLEDGE_EXTRACTION_PRECISION_FILTER_PARTIAL_POLICY: ${...:-drop}
KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_SOURCE: ${...:-user_model}

WORKER_AI_PRECISION_FILTER_MODEL_REF: ${...:-019e5650-eca7-78c2-985d-465aa3bce1ce}
WORKER_AI_PRECISION_FILTER_PARTIAL_POLICY: ${...:-drop}
WORKER_AI_PRECISION_FILTER_MODEL_SOURCE: ${...:-user_model}
```

To disable: set the model_ref env to empty string. Override in `.env` for ops who don't want the +30-90s/chapter latency cost.

### Bug fixes folded during Phase 3 sanity smoke (caught by ad-hoc diagnostic BEFORE the 19-min c72b ensemble launch — both saved from full-run waste)

1. **`load_candidates_from_dump` Pydantic strict-validate** ([sdks/python/loreweave_extraction/pass2_filter.py:570](../../sdks/python/loreweave_extraction/pass2_filter.py#L570)) — c70a eval dump format is a minimal projection `{name, kind, ...}`; full Pydantic candidates require more fields (`aliases`, `confidence`, `canonical_*`). Switched to `model_construct` + safe defaults. The eval dump format ↔ SDK candidate format is now bridged.

2. **`_call_filter_llm` content-extraction key wrong** ([sdks/python/loreweave_extraction/pass2_filter.py:_call_filter_llm](../../sdks/python/loreweave_extraction/pass2_filter.py)) — gateway returns `result["messages"][0]["content"]` per the chat-completion shape, NOT `result["content"]`. Filter was reading wrong key → empty content → all batches `unjudged` → 0% coverage on first smoke. Mirrored `llm_judge.py:443` pattern.

Both fixes verified by 16 cycle-72 unit tests + 1 single-chapter smoke (alice_ch01, 24.2s, 100% coverage) BEFORE launching the full c72b + c72c filter runs and ensemble re-judges.

### Cycle 72 close — 4 ship commits + 1 SHIP commit pending

| # | Commit | Phase |
|---|---|---|
| 1 | `32c251f1` | DESIGN spec + plan (session 72.S1) |
| 2 | `f2d03c90` | BUILD-1 SDK foundation |
| 3 | `0211d3c3` | BUILD-2 orchestrator + caller wiring |
| 4 | `5f36802a` | BUILD-3 eval validation + 2 bug fixes |
| 5 | _pending_ | SHIP — docker-compose activation + handoff + RETRO |

### Next session entry point

Cycle 72 closed POSITIVE. Filter is ON by default in dev compose. Next session's natural starting points:

1. **Verify filter activation in dev** — bring up the stack, run a chapter extraction, observe stage logs `pass2_precision_filter` events in [job_logs](../../services/knowledge-service/app/db/repositories/job_logs.py). Confirm Prometheus shows non-zero `knowledge_extraction_filter_decisions_total{verdict=*}`.
2. **D-PASS2-FILTER-NEO4J-REALIZED-F1** follow-up — measure F1 after pass2_writer cascade (separate from the filter-output F1 measured in c72_compare.md).
3. **Cycle 73 candidates** — per [docs/specs/2026-05-29-pass2-precision-filter.md](../specs/2026-05-29-pass2-precision-filter.md) deferred section. Top candidates:
   - **D-PASS2-FILTER-RELATION-ONLY-OPTIMIZATION** — relations contributed most of c72c's +2.2pp lift; relation-only filter saves 2/3 of the latency
   - **D-PASS2-FILTER-FACTS-SUPPORT** — extend filter to facts
   - **D-EVAL-FRAMEWORK-WIKINEURAL-MULTILINGUAL-ANCHOR** — multilingual NER anchor (predates cycle 71)
   - **D-CLAUDE-JUDGE-VS-GEMMA-JUDGE-DIVERGENCE-AUDIT** — partially-closed by c72c's improved κ + lower gemma language_bias, but not fully

### Deferred rows added this cycle (carry-over)

- **D-PASS2-FILTER-NEO4J-REALIZED-F1** — Neo4j-realized F1 measurement (after writer cascade)
- **D-PASS2-FILTER-FACTS-SUPPORT** — extend filter to facts (per spec D2)
- **D-PASS2-FILTER-RELATION-ONLY-OPTIMIZATION** — relations contribute most lift; latency-vs-yield tradeoff to validate (NEW from c72c analysis)
- **D-PASS2-FILTER-CLOUD-CALIBRATION** — cloud Claude calibration cycle
- **D-PASS2-FILTER-RUNTIME-FLAG** — per-request header override
- **D-PASS2-FILTER-CACHE** — verdict caching
- **D-PASS2-FILTER-PER-USER-UI** — UI surface

### Lessons captured to durable memory this cycle (per `feedback_review_impl_on_design_cycles`)

- **gateway-response-shape-messages-array-not-content-string** — gateway returns `result["messages"][0]["content"]`, not `result["content"]`. Any new gateway consumer in this codebase must mirror `llm_judge.py:441-443`.
- **pydantic-strict-validate-rejects-dump-projection-format** — eval dumps are a minimal projection of full Pydantic candidates; loading them back via `model_validate` fails on missing required fields. Use `model_construct` + safe defaults for loader paths.

---

## Session 72.S1 summary — cycle 72 pass2-precision-filter DESIGN-CHECKPOINT (spec + plan locked, no code shipped) — historical

XL cycle for the hybrid 2-pass extraction direction (30B recall → claude-4.7-opus precision filter) per cycle 71/71-bis pivot. This session ships ONLY the design artifacts; session 72.S2 will implement Phase 1 (SDK foundation) → Phase 2 (orchestrator wiring) → Phase 3 (eval validation against c70a saved-dump fixture).

### Phases executed (S1)

| Phase | Output |
|---|---|
| CLARIFY | [docs/specs/2026-05-29-pass2-precision-filter.md](../specs/2026-05-29-pass2-precision-filter.md) — 12 decisions D1-D12, 8 risks gradient, 3 OQs deferred to DESIGN |
| DESIGN | Same spec — D6 revised (operation=chat removes 10-pt cascade), 3 OQs resolved (OQ-1 separate model_source, OQ-2 Option B post-gather step, OQ-3 no Neo4j flag), module map 11 files, interfaces locked (PrecisionFilterConfig + Pass2Candidates extension + apply_precision_filter signature) |
| REVIEW (design) | /review-impl round 1: 7 findings (2 HIGH + 4 MED + 1 LOW substantive, 2 LOW deferred) — all folded inline; module count 11→12 with c70a saved-dump fixture added + precision_filter_prompts.py SOT |
| PLAN | [docs/plans/2026-05-29-pass2-precision-filter.md](../plans/2026-05-29-pass2-precision-filter.md) — 2-session split with natural seam at Phase 1/Phase 2; 8 sub-phases in S2; 23-test-case map; risk→mitigation→test cross-checked end-to-end |

### Key design decisions (locked, do not re-litigate in S2)

- **D1 (filter as SDK module, opt-in kwarg)** — `precision_filter: PrecisionFilterConfig | None = None` on `extract_pass2`; default None = zero behavior change
- **D2 (categories)** — all 3 (entity/relation/event); facts deferred (`D-PASS2-FILTER-FACTS-SUPPORT`)
- **D3 (filter model)** — `huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated` (UUID `019e5650-eca7-78c2-985d-465aa3bce1ce`)
- **D4 (partial policy)** — `keep` / `drop` runtime-configurable; `demote` reserved but raises in `__post_init__`
- **D5 (failure policy)** — filter NEVER raises; degrades to Pass A with `filter_status="degraded"` field
- **D6 (op enum)** — REUSE `operation="chat"` per `llm_judge.py` precedent; NO JobOperation enum change
- **D7 (telemetry)** — `knowledge_extraction_filter_decisions_total{category, verdict}` counter + `knowledge_extraction_filter_coverage_ratio{category}` gauge
- **D8 (caller envs)** — `WORKER_AI_PRECISION_FILTER_MODEL_REF` + `KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF`; unset = filter off
- **D10 (ship gate, 4-clause symmetric)**: median F1 lift ≥+1.5pp AND min ≥-0.5pp AND claude ≤2× median AND κ ≥0.60

### Round-1 fixes folded inline (no BUILD deferred work)

- **HIGH-1** — c70a saved dump (recoverable from `/tmp/eval_dump_cycle70/` in `infra-knowledge-service-1`) replaces nondeterministic re-extraction baseline; copy as repo fixture `services/knowledge-service/tests/quality/eval_runs/c70a/`
- **HIGH-2** — Promote BOTH `_NO_THINK_PREFIX` + `_PRECISION_SYSTEM` via `build_precision_prompt(suppress_thinking=...)` SOT helper in SDK
- **MED-1** — Pydantic→dict adapter at filter boundary (`model_dump(mode="json")`) pinned
- **MED-2** — D10 cross-judge gate revised from 3-clause asymmetric to 4-clause symmetric (anti-self-reinforcement + anti-recall-loss)
- **MED-3** — Measurement validity caveat: filter-output F1 ≠ Neo4j-realized F1; documented; deferred `D-PASS2-FILTER-NEO4J-REALIZED-F1` for future cycle
- **MED-4** — `apply_precision_filter` immutability contract via `dataclasses.replace`; 2 new tests pin it

### Session 72.S2 entry point (READ THIS FIRST in next session)

When you start S2:
1. **Re-read** [docs/specs/2026-05-29-pass2-precision-filter.md](../specs/2026-05-29-pass2-precision-filter.md) + [docs/plans/2026-05-29-pass2-precision-filter.md](../plans/2026-05-29-pass2-precision-filter.md) — verify no drift since this commit (per memory `verify-plan-prescriptions-against-code`)
2. **Re-classify** if scope changed (Phase 1 alone could be L if you slice the SDK foundation discretely)
3. **Verify c70a dump still exists** in `infra-knowledge-service-1:/tmp/eval_dump_cycle70/` — if container has been restarted, the dump is GONE and Session 72.S2 must re-run cycle 70 extraction first (~5 min on huihui-qwen3-30b)
4. **Phase 1 first** — pure SDK foundation, zero caller change, ships as dead code. Natural checkpoint after Phase 1 if session-2 budget runs short.
5. Phase 2 + Phase 3 = the actual filter activation + validation

### Files in this S1 commit

- [docs/specs/2026-05-29-pass2-precision-filter.md](../specs/2026-05-29-pass2-precision-filter.md) (NEW)
- [docs/plans/2026-05-29-pass2-precision-filter.md](../plans/2026-05-29-pass2-precision-filter.md) (NEW)

NOT in this commit (left for the author to commit separately or per their own cadence):
- `README.md` (modified, untouched by cycle 72)
- `docs/MILESTONE.md` (untracked, from earlier 17:40 session work)

### Deferred rows added (carry over to deferred items list)

- **D-PASS2-FILTER-NEO4J-REALIZED-F1** (MED-3 fold) — Neo4j-realized F1 measurement after writer cascade
- **D-PASS2-FILTER-FACTS-SUPPORT** (LOW-2 fold) — extend filter to facts
- **D-PASS2-FILTER-CLOUD-CALIBRATION** (spec non-goal) — cloud Claude calibration cycle
- **D-PASS2-FILTER-RUNTIME-FLAG** (spec non-goal) — per-request header override
- **D-PASS2-FILTER-CACHE** (spec non-goal) — verdict cache `(text_hash, model_ref, item_canonical) → verdict`
- **D-PASS2-FILTER-PER-USER-UI** (spec non-goal) — UI surface for filter toggle

---

# Session Handoff — Session 71 (specialized event prompt — NEGATIVE cycle, revert) — historical

> **Date:** 2026-05-29 (session 71, 1 M cycle attempted, A + B refinement both regressed, reverted).
> **HEAD:** `2b254e88` (cycle 71-bis NEGATIVE commit).
> **Branch:** `main`.

## Session 71 summary — cycle 71 + 71-bis BOTH reverted; pivoting to #2 hybrid 2-pass next

Both prompt-side event-extraction attempts (cycle 71 c71a/c71b + cycle 71-bis) regressed empirically. The cycle is decisively NEGATIVE for prompt-side event work — pivot direction confirmed.

### 71-bis attempt (Rule 10 isolated, English-only illustrative phrases)

Test: apply ONLY Rule 10 granularity to event prompt, no Examples B/C, English-only illustrative phrases (stripped overlap risk).

| Variant | Prompt size | gemma macro P/R | ch14 events | Script (ch14 EN/CJK) |
|---|---:|---:|---:|---:|
| c70a baseline | 4522 (event prompt unchanged) | 0.81 / 0.92 | not per-chapter measured by gemma | (c69 was 0/6) |
| **71-bis** Rule 10 only | 5101 | **0.79 / 0.91** | **0.91 / 1.00** (lifted from c71a's 0/0) | **8 / 3** (drift!) |

Empirical:
- 71-bis extraction completed in 279.92s; dump at `/tmp/eval_dump_30b_c71bis`
- 71-bis gemma judge completed in 348.11s; log at `/tmp/judge_gemma_c71bis.log`
- ch14 events: c71a 0/0 → 71-bis 0.91/1.00 (target chapter fixed via semantic match)
- BUT CJK script drift: journey_west_zh_ch01 3 EN / 0 CJK, ch14 8 EN / 3 CJK — judge tolerates semantic match but explicit prompt rule "Keep summary in ORIGINAL script of TEXT" is violated
- Relation regression replicated: alice_ch02 rel R=0, little_women rel R=0 (same pattern as c71a/c71b — adding any rule to event prompt seems to affect relation extraction)
- Revert: `git checkout HEAD --` restored 4522 chars

### Why 71-bis was rejected despite ch14 win

1. **Script drift is a hard rule violation.** Even if the judge accepts English summaries semantically, downstream consumers (Neo4j storage, multilingual retrieval, UI rendering) may struggle with English summaries on Chinese chapters. The prompt's explicit "Keep summary in ORIGINAL script of TEXT" rule is contract-level, not advisory.
2. **Relation regression pattern is consistent across all 3 prompt-side attempts.** c71a/c71b/71-bis all show alice_ch02 + little_women rel R=0. Adding ANY rule to the event prompt has hidden interaction with relation extraction (possibly shared context/budget at the model level).
3. **Macro P regression hits −2pp threshold exactly.** Marginal win on ch14 doesn't offset the −2pp macro + the script drift + the relation regression.
4. **The "ch14 win" comparison is apples-to-oranges.** c69/c70a never measured per-chapter event metrics via gemma judge; only rule-based attribution showed 0 TP. The clean comparison 71-bis vs c71a (within-cycle measurement) shows ch14 fixed; but vs c70a baseline we don't have the data.

### Combined lessons captured (cycle 71 + 71-bis)

- **Event prompts are intrinsically resistant to prompt-side improvements.** Three distinct attempts (c71a with overlapping examples, c71b with VN-only, 71-bis with rules-only English) all failed in different ways. The model's event extraction behavior is more stable than its relation behavior — adding signal to the event prompt creates side effects.
- **Pivot to structural levers.** Per cycle-70 commit's open follow-ups: cycle 72 should test **#2 Hybrid 2-pass extraction** (30B recall → claude-4.7-opus precision filter) — bigger lever, no prompt risk, F1 target ~0.88.
- **Script drift via English-only rule prose.** Adding instruction prose in English alone (no CJK/VN illustrative phrases) STILL caused CJK chapters to drift to English summaries. The presence of English illustrative content in the prompt biases the model toward English output, even when the chapter is in another script. Future multilingual prompts need symmetric language signal OR no language-specific signal at all.

### New deferred row (from 71-bis specifically)

- **D-EVENT-RULE-ENGLISH-PROSE-CJK-DRIFT** — adding ANY new rule with English-only illustrative phrases (Rule 10 had "after praying" / "happily" / "walked across the bridge") biased the model to emit English summaries on Chinese chapters. If a future cycle adds rules to the event prompt, use ONLY abstract phrasing (no concrete language-specific examples) OR symmetric multilingual examples sourced outside the fixture set.



Cycle 71 attempted to mirror cycle 70's pattern (Rule + CJK example + VN example + Lesson prose) onto the EVENT prompt. **Both variants regressed empirically vs c70a baseline; the prompt was reverted.** Event prompts are more sensitive than relation prompts to language-example presence — partial multilingual coverage creates failure modes that the relation cycle didn't surface.

### A/B/B' executed at user direction

| Variant | Prompt size | gemma macro P/R | ch14 events | Failure mode |
|---|---:|---:|---:|---|
| **c69 baseline** | 4522 | 0.83 / 0.94 | 6 evts CJK, 0/6 TP (granularity drift, but real extraction) | — |
| **c71a** (Rule 10 + Example B CJK + Example C VN + Lessons) | 7475 | **0.79 / 0.89** | **2 evts copying Example A English (regurgitation)** | Example B text overlaps ch14 narrative → model emits Example A as fallback |
| **c71b** (Rule 10 + remove Example B + keep Example C) | 6355 | not judged (script audit definitive) | 11 evts but 8 EN / 3 CJK | No CJK anchor example → Chinese chapters drift to English summary |

Empirical evidence:
- c71a extraction completed in 219.60s on huihui-qwen3-30b; dump at `/tmp/eval_dump_30b_c71a` inside `infra-knowledge-service-1`
- c71a gemma single-judge completed in 254.90s; per-chapter log: `/tmp/judge_gemma_c71a.log`
- c71b extraction completed in 249.91s; dump at `/tmp/eval_dump_30b_c71b`
- c71b CJK→EN drift: journey_west_zh_ch01 3 EN / 0 nonascii; ch14 8 EN / 3 nonascii — violates "Keep summary in ORIGINAL script of TEXT" rule
- Revert: `git checkout HEAD -- sdks/python/loreweave_extraction/prompts/event_extraction_system.md` restored 4522 chars

### Lessons captured

- **Event prompts ≠ relation prompts under the cycle-70 pattern.** Cycle 70 (CJK+VN examples + Lessons) worked for relations because it taught new VOCABULARY (predicates `disciple_of` / `stepchild_of`). Cycle 71 tried to teach STRUCTURAL granularity to events — the model resisted in two distinct ways.
- **Example text-overlap with eval fixtures triggers regurgitation.** Example B's "三藏揭壓帖" text overlapped journey_west_zh_ch14's actual narrative → model output Example A (the first example) as fallback for the overlapping chapter. **Future language-specific examples must source from text NOT in the eval fixture set.**
- **Asymmetric multilingual examples cause script drift.** c71b's EN + VN coverage left no CJK anchor → all Chinese chapters drifted to English summary. **For multilingual event prompts, need either symmetric coverage (1 example per supported language sourced from outside fixtures) OR no language-specific examples at all (rules-only).**
- **Rule 10 (granularity) MAY still have value isolated.** Most chapters showed clean per-category event metrics under c71a (≥0.86 P, ≥0.60 R) — the granularity-only signal wasn't isolated cleanly because the regurgitation + script-drift confounded it. Cycle 71-bis tests R10 alone.

### New deferred rows

- **D-CYCLE71-SYMMETRIC-CJK-EXAMPLE** — if attempting CJK event example again, source text from a chapter NOT in `tests/fixtures/golden_chapters/` (avoid the text-overlap trap). Pair with symmetric EN + VN examples sourced similarly.
- **D-EVENT-AGGREGATOR-FUZZY-MATCH** — judge-side fix for the granularity drift identified in cycle 69 (ch14 model extracts the same scenes as gold but folded/padded; matching at semantic level not literal). Alternative to prompt-side teaching.

### Cycle 72 candidates (post-cycle-71+71-bis revert)

| # | Candidate | Size | Status |
|---|---|---|---|
| 1 | ~~Specialized event prompt~~ | M | **TRIED, NEGATIVE — cycle 71 + 71-bis both reverted** |
| 2 | **Hybrid 2-pass extraction** (30B recall → claude-4.7-opus precision filter) | L (~half-day) | **RECOMMENDED NEXT — pivot to structural lever; no prompt risk; F1 target ~0.88** |
| 3 | **D-CLAUDE-JUDGE-VS-GEMMA-JUDGE-DIVERGENCE-AUDIT** | S (~1-2h) | Still pending from cycle 70 close; can run before #2 |
| 4 | **D-EVAL-FRAMEWORK-WIKINEURAL-MULTILINGUAL-ANCHOR** | M (~half-day) | Multilingual NER anchor; closes EN-vs-CJK judge bias question |
| 5 | **D-EVENT-AGGREGATOR-FUZZY-MATCH** | M (~half-day) | Judge-side fix for granularity drift; alternative to prompt-side event teaching |
| 6 | **Catalogue-driven extraction** (resume paused ADR) | XL (multi-session) | Architectural; defer until smaller cycles plateau |

Recommend cycle 72 = #2 (hybrid 2-pass) for the structural-lever bet. Session-end checkpoint advisable since 71/71-bis already burned this session's iteration budget; fresh session for #2 design + build.

---

# Session Handoff — Session 70 (specialized relation prompt — first recall-improvement cycle on the new eval framework) — historical

> **Date:** 2026-05-29 (session 70, 1 M cycle with A/B/B' refinement test).
> **HEAD:** pending final commit on top of `e9c5f3ff` (cycle 69 close).
> **Branch:** `main`.

## Session 70 summary — first recall-improvement cycle ships c70a (Lesson prose); refinement attempt c70b decisively rejected

First architectural-improvement cycle running on the new eval framework (cycle 69's anchor + 3-judge ensemble baseline). Goal: teach two new predicate canonicalization rules to lift relation precision on 30B's weak axis. Per session 67's "cheap-to-expensive" sequencing.

### A/B/B' executed at user direction "do 3 (refine + retest)"

| Variant | Prompt size | gemma P/R | qwen-30b P/R | claude P/R | Median | Fleiss κ | Disputed |
|---|---:|---:|---:|---:|---:|---:|---:|
| **c69 baseline** | 5100 | 0.834 / 0.937 | 0.980 / 1.000 | 0.983 / 0.879 | **0.93 / 0.94** | 0.708 | 6.6% |
| **c70a (Lesson prose, SHIPPED)** | 5872 | 0.809 / 0.921 | 0.959 / 1.000 | 0.955 / **0.924** | **0.96 / 0.92** | 0.671 | 5.4% |
| c70b (trimmed, no prose) — rejected | 5482 | 0.774 / 0.857 | 0.944 / 0.993 | 0.947 / 0.835 | 0.94 / 0.86 | 0.655 | 6.9% |

**Decision: ship c70a.** Rationale:
1. **claude-4.7-opus R lifted +4.5pp** (0.879 → 0.924) — the high-precision baseline judge accepts more correct extractions. Real value for high-recall use cases (Mode-3 chat retrieval).
2. **Predicate learning structural** — `disciple_of` (Chinese 拜...為師, journey_west_zh_ch14) + `stepchild_of` (Vietnamese con riêng, tam_cam_vi) emitted correctly in CJK/VN dumps for the first time.
3. **c70b monotonically regressed** all 3 judges — definitively rules out the "trim all prose" hypothesis. The Lesson prose blocks are scaffolding the model uses.
4. **Aggregate cost is small** — median R drop 0.02pp within Fleiss-κ-substantial noise; median P up 0.03pp.

### What the cycle did NOT achieve (honest report)

- **little_women_ch01 relation P stayed 0.08** (target was 0.30+). Rule-based metric unchanged. The new examples teach SPECIFIC kinship/mentorship rules that don't apply to little_women's parent-child-domestic narrative — they help Chinese mentorship + Vietnamese kinship fixtures specifically.
- **gemma judge regressed marginally** (P −0.025, R −0.016). Most-median judge penalizes the new predicates slightly; gemma's `language_bias` flagged at 0.16 (vs 0.138 baseline).
- **Fleiss κ dropped 0.708 → 0.671** (still substantial). Some judge disagreement on the new predicates — claude accepts readily, gemma is unsure.

### New deferred row

- **D-CLAUDE-JUDGE-VS-GEMMA-JUDGE-DIVERGENCE-AUDIT** — gemma flagged on language_bias post-cycle-70 (0.16 > 0.15 threshold); claude's R jump on the same dump suggests systematic disagreement on the new kinship/mentorship predicates. Worth a per-item audit of disputed verdicts to characterize the divergence.

### Lessons captured

- **Prompt prose can scaffold predicate canonicalization.** Cycle 1 lesson: don't compound the same lesson 3× across languages. Cycle 70 refinement lesson: trim-all-prose hypothesis is WRONG — the Lesson blocks help the model apply new predicates correctly. Goldilocks zone: ONE concrete lesson per example with ~30-50 char explanation.
- **Predicate learning ≠ aggregate metric improvement.** Model demonstrably learned new patterns but the ensemble median moved <0.05pp. Structural improvements take longer to translate into aggregate noise reduction.
- **Claude-as-judge is the high-recall barometer.** When new examples teach real-but-non-canonical patterns, claude updates its acceptance threshold first (R +4.5pp). Gemma is slower. For high-recall product features, prefer claude's verdict.
- **A/B/B' protocol is the right shape for marginal prompt changes.** The c70a-with-prose vs c70b-without-prose contrast gave a decisive signal. Without the refinement retest, "trim prose" would have shipped under the wrong hypothesis.

### Next session — Cycle 71 candidates (per cheap-to-expensive sequencing, updated with cycle 70 lessons)

| # | Candidate | Size | Status |
|---|---|---|---|
| 1 | **Specialized event prompt** | M (~3-4h) | Recommended — `journey_west_zh_ch14` events P=0 R=0 was cycle 69's biggest hole; targeted CJK/VN event-action examples should fill it |
| 2 | **Hybrid 2-pass extraction** (30B recall → claude-4.7-opus precision filter) | L (~half-day) | No prompt growth risk; combines ensemble bias profile; F1 expected ~0.88+ |
| 3 | **D-CLAUDE-JUDGE-VS-GEMMA-JUDGE-DIVERGENCE-AUDIT** | S (~1-2h) | Characterize the c70a-driven judge divergence; informs whether to weight judges or just track |
| 4 | **D-EVAL-FRAMEWORK-WIKINEURAL-MULTILINGUAL-ANCHOR** | M (~half-day) | Closes EN-vs-CJK/VN judge bias question |
| 5 | **Catalogue-driven extraction** (resume paused ADR) | XL (multi-session) | Architectural; defer until smaller cycles plateau |

Recommend cycle 71 = #1 (specialized event prompt) per cheap-to-expensive ordering. Same shape as cycle 70 (CJK + VN examples + Lesson prose) — pattern validated.

---

# Session Handoff — Session 69 (eval framework overhaul: anchor + 3-judge ensemble) — historical

> **Date:** 2026-05-27 → 2026-05-28 (session 69, 1 XL cycle)
> **HEAD:** pending final commit on top of `a8aa9fb0`.
> **Branch:** `main`.

## Session 69 summary — eval framework overhaul (anchor + ensemble), baseline relocked

The architectural meta-cycle session 68 (cycle 1 multilang-fewshot revert) pointed at: our single-judge bespoke eval has no inter-rater reliability check + no external anchor. Cycle 69 builds that framework. Spec: [`docs/specs/2026-05-27-eval-framework-overhaul.md`](../specs/2026-05-27-eval-framework-overhaul.md); plan: [`docs/plans/2026-05-27-eval-framework-overhaul.md`](../plans/2026-05-27-eval-framework-overhaul.md) — both committed pre-BUILD as a design-checkpoint artifact (8c7c0c9d) per `feedback_design_checkpoint_commit_separates_design_from_implementation`.

### 5 commits, sequenced per `feedback_xl_cycle_natural_checkpoint_pattern`

| # | Commit | Stage | Notes |
|---|---|---|---|
| 1 | `8c7c0c9d` | design checkpoint | spec (12 decisions D1-D12) + plan with all 15 /review-impl findings folded inline pre-BUILD |
| 2 | `d6478020` | sub-checkpoint 1a | pinned deps: deepeval==4.0.4 (langchain 1.x compat issue at 2.5.0 forced bump) + seqeval==1.2.2 + datasets==2.21.0 + krippendorff==0.7.0 |
| 3 | `28e1a3a4` | sub-checkpoint 1b | 5 foundation modules: anchor_runner.py + judge_ensemble.py + deepeval_metrics.py + test_anchor_eval.py + test_judge_ensemble_unit.py (19 unit tests covering Fleiss math + D11 failure handling + D12 bias formulas) |
| 4 | `ab5353b4` | integration | llm_judge.run_dump_judge + test_llm_judge_ensemble + test_eval_with_deepeval + MED-8 asyncio teardown fix (closes D-JUDGE-EVAL-ASYNCIO-TEARDOWN) |
| 5 | `a8aa9fb0` | bug fix at live VERIFY | chapter_judgement_to_verdicts moved to judge_ensemble.py + GoldVerdict.gold_idx (not .idx) + 2 regression-lock unit tests. Caught by the live ensemble run — 60 min of LM Studio compute wasted on the first attempt before the 1-line typo crashed every judge |

### Live VERIFY results (locked baseline for 30B extractor)

**Anchor benchmarks (informational, sanity-floor only per spec D2):**

| Anchor | Dataset | n | F1 | P | R | avg extracted / gold | Sanity floor |
|---|---|---:|---:|---:|---:|---|---|
| CoNLL-2003 NER | `tner/conll2003` test | 100 | 0.219 | 0.204 | 0.237 | 3.4 / 2.1 | ✅ PASS |
| DocRED unlabeled-triple | `thunlp/docred` validation | 50 | 0.127 | 0.110 | 0.149 | 15.0 / 10.4 | ✅ PASS |

~24-28% of SOTA — consistent ratio across both benchmarks; calibration signal not quality claim. Anchor sanity-floor (F1≥0.10 AND avg_extracted≥0.1×avg_gold) catches the false-negative trap that yesterday's "any F1 value" accepted.

**3-judge ensemble (locked default measurement):**

| Judge | Model | Macro P | Macro R | Strictness | Lang bias span |
|---|---|---:|---:|---:|---:|
| gemma | google/gemma-4-26b-a4b | 0.834 | 0.937 | 0.841 (median) | 0.138 |
| qwen-30b | huihui-qwen3-30b-instruct | 0.980 | 1.000 | 0.933 (outlier+0.09) | 0.049 |
| claude-4.7-opus | huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated | 0.983 | 0.879 | 0.845 (median) | 0.127 |

**Fleiss κ = 0.708 ("substantial" per Landis-Koch 1977)** over 461 items voted by all 3 judges. 487 total verdicts; 32 disputed (6.6%); 455 majority (93.4%). **Median over the 3 judges: P≈0.93 / R≈0.94.** No bias dimension exceeded its flag threshold (strictness_gap < 0.15, language_bias < 0.15).

Key bias signals captured:
- **qwen-30b is lenient** (strictness +0.09 over median, R=1.00) — confirms our prior suspicion that single-judge qwen overstates. Don't use it solo.
- **All 3 judges accept CJK + VN more readily than English** (87-96% vs 78-91%). Could be over-extraction reality OR judge under-rejection. English anchor can't disambiguate; defer until WikiNeural multilingual anchor lands.
- **All 3 judges favor recall over precision** (rp_bias negative across the board) — they accept gold items as "covered" more readily than they accept extracted items as "supported." For high-precision use cases, prefer claude-4.7-opus's narrower bias (−0.05) over gemma's (−0.13).

### New deferred rows

- **D-CYCLE1-ENSEMBLE-FORENSIC** — re-baseline the cycle-1 (multilang-fewshot) dump with the ensemble to apply spec D9 decision rule on extract-vs-scoring. Dump was wiped by mid-cycle Docker restart; recreating requires temporarily re-applying the reverted multilang prompts. Informational only — cycle-1's recall regression conclusion stands per single-judge data; the ensemble would refine the verdict's confidence interval. ~30 min next session.
- **D-EVAL-FRAMEWORK-WIKINEURAL-MULTILINGUAL-ANCHOR** — multilingual NER anchor (CJK + VN) to disambiguate the EN-vs-CJK/VN judge acceptance pattern. Currently the only signal we have is the ensemble itself; an external multilingual benchmark would corroborate or refute.
- **D-EVAL-FRAMEWORK-CLOUD-JUDGE** — 4th gold-standard cloud Claude judge for ground-truth calibration. Adds ~$1-3/run; defer until first ensemble run surfaces variance worth ground-truthing (this run shows κ=0.71 → currently sufficient).

### Default measurement methodology (effective 2026-05-28)

- **In-cycle iteration smokes:** single-judge gemma via `test_judge_eval.py::test_llm_judge_extraction_quality` (~20 min). Fast feedback.
- **Baseline-lock runs (every new model / every prompt-aggregator-scoring change / quarterly drift / pre-ship gate):** 3-judge ensemble via `test_judge_eval.py::test_llm_judge_ensemble` (~30 min after bug fix + budget bumps) + CoNLL-2003 + DocRED anchors (~10 min total). Full lock = ~40 min.
- **Single source of metric authority:** the ensemble's majority verdict + Fleiss κ. Per-judge numbers informational; ensemble is the lock.

### What's NEXT

Eval framework is the new measurement floor. Next session can confidently iterate on the architecture-improvement levers identified in cycle 67 / 68 / 69 with reliable scoring:

| # | Candidate | Size | Status |
|---|---|---|---|
| 1 | **Specialized relation prompt** (cycle 2 candidate from session 67) | M (~3-4h) | Pending; relations are 30B's weak axis (`little_women_ch01` 17% disputed mostly relation FPs) — targeted predicate vocab + few-shot per language could lift R+P together without compounding the cycle-1 omission lesson |
| 2 | **Hybrid 2-pass extraction** (30B recall → claude-4.7-opus precision filter) | L (~half-day) | Combines best of both per ensemble bias profile; F1 expected ~0.88+ |
| 3 | **D-CYCLE1-ENSEMBLE-FORENSIC** | XS (~30 min) | Definitive answer to "did cycle 1 regress extract or scoring" |
| 4 | **D-EVAL-FRAMEWORK-WIKINEURAL-MULTILINGUAL-ANCHOR** | M (~half-day) | Closes the EN/CJK/VN judge bias question; needs WikiNeural dataset wiring + new anchor_runner overload |
| 5 | **Catalogue-driven extraction** (resume paused ADR) | XL (multi-session) | Architectural; kind-specific extractors with closed vocabulary per genre |

Recommend **cycle 2's specialized relation prompt** as the next "cheap to expensive" lever, **bounded by the lessons from cycle 1 (multilang-fewshot revert)**:
- Keep prompt growth ≤ +500 chars to dodge concurrency × prompt-size limits
- Pair LANGUAGES with DIFFERENT lessons (don't compound a single high-pressure omission lesson 3×)
- VERIFY gate = ensemble re-baseline (not single-judge) per spec D10 cadence policy

---

## Session 68 summary — Track A model swap verified; SDK response_format LM Studio compat shipped

Single L cycle. User picked Track A from session 67's handoff (model swap + live extraction baseline). Loaded `huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated` at 40K context, thinking ON. Live smoke through `/internal/llm/jobs` async path hit LM Studio HTTP 400 on `response_format: {"type":"json_object"}` — newer LM Studio (post-2026-05-25) only accepts `json_schema` or `text`. The prior gateway normalization `normalizeResponseFormatForKind` only lives on the retired `/internal/proxy/*` path; the async-jobs adapter forwards the field verbatim, so every extractor was 400-blocked. Patched 5 extractor SDK files + the llm_judge.py to send `text` instead. Ran the full 9-chapter extraction eval + LLM-judge baseline on the new model. Cycle includes the patch, plan, regression-lock test, and adversarial `/review-impl` round confirming the patch root-causes correctly + a transient zero-extraction on `journey_west_zh_ch01` was concurrency-flake (isolated re-run yielded 10 entities), not patch-induced.

### Baseline result on `huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated`

| Metric | Value | vs qwen3.6 session-61 baseline |
|---|---|---|
| LLM-judge Precision (macro) | **0.93** | −0.04 pp |
| LLM-judge Recall (macro, as measured) | 0.71 | −0.10 pp |
| LLM-judge Recall (projected clean run) | **~0.81** | ±0 (one transient ch01 zero accounts for the gap) |
| Coverage P / R | 100% / 100% | +38 / +44 pp |
| Extraction wall clock (9 ch) | **7:04 min** | **−63% (≈2.7× faster)** |

Full per-chapter breakdown + reproducing commands in [`services/knowledge-service/eval/QUALITY_EVAL_BASELINES.md`](../../services/knowledge-service/eval/QUALITY_EVAL_BASELINES.md) (new section "2026-05-26 — huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated baseline").

### Files

| File | Change |
|---|---|
| `sdks/python/loreweave_extraction/extractors/{entity,relation,event,fact,summarize}.py` | `response_format: {"type":"text"}` (5 sites) |
| `services/knowledge-service/tests/quality/llm_judge.py` | same patch on the judge call |
| `services/knowledge-service/tests/unit/test_response_format_text_lock.py` (NEW) | regex-tolerant regression lock; runs in Dockerfile test stage line 33-37 |
| `services/knowledge-service/eval/QUALITY_EVAL_BASELINES.md` | new baseline section + comparison table row |
| `docs/plans/2026-05-26-response-format-text-for-lm-studio.md` (NEW) | L-cycle plan + 5 follow-ups |

### New deferred rows (filed during this session)

- **D-LM-STUDIO-RESPONSE-FORMAT-ASYNC-PATH** — port `normalizeResponseFormatForKind` to gateway adapter layer (`adapters.go::forwardOptionalChatFields`); defensive coverage so future extractors don't re-hit this regression
- **D-JUDGE-EVAL-ASYNCIO-TEARDOWN** — pytest-asyncio fixture-scope leak in `test_judge_eval.py`; `test_judge_discriminates_fabricated_items` breaks the subsequent quality test with closed-event-loop
- **D-EXTRACTION-PARALLEL-CONCURRENCY-FLAKE** — concurrency=4 eval produced a single transient zero on the same fixture that re-runs cleanly in isolation; needs a retry-on-zero defense
- **D-AGGREGATOR-REASONING-CONTAMINATION-GUARD** — `extractJSONObject` assumes reasoning is on a separate stream channel; loose-output models from `text` mode raise the priority of a defensive guard

### What's NEXT — pick from Track A or back to Track B/C from session 67

Track A primary deliverable (`D-P3-BASELINE-QWEN3.6-RERUN` / new-model baseline) is **achieved**. Remaining Track A items:

- `D-EXTRACTION-CONTEXT-FIX-STAGE-4-LIVE-SMOKE` — still open; user explicitly ran with thinking ON, so the gateway-forward `chat_template_kwargs={thinking:false}` path was NOT exercised. Verify when next iteration disables thinking.
- `D-P3-LLM-JUDGE-BASELINE-CHECK` + `D-P3-SHERLOCK-BASELINE` — open; today's baseline is on a DIFFERENT model (huihui-claude-4.7-opus, not qwen3.6-35b-a3b). qwen3.6 baseline check requires re-loading the original model.
- `D-P2-FULL-EXTRACTION-LIVE-SMOKE` + `D-P3-LIVE-SMOKE` + `D-P3-BOOK-SUMMARY-PERSIST-AUDIT` — fold in when next extraction kicks off (functional re-trigger).

Then back to **Track B** (M-L single-cycle items, no model dep) or **Track C** (small batchable polish) per session 67 handoff (see below).

---

# Historical handoff — Session 67 (10-cycle polish-debt burn-down)

> **Date:** 2026-05-24 (session 67 sub-sessions cont.4 through cont.13)
> **HEAD:** `b1b5cbef` — 10 commits ahead of session 67 cont.3 start; all pushed to `origin/main`.
> **Branch:** `main`.

## Session 67 summary (historical) — 10 cycles, 16 deferred items cleared

Pure deferred-row burn-down session. No new feature work; every cycle picked an open deferred row, scoped it, fixed/cleaned/tested it, committed. Five cycles were XS (≤1 LoC), five were S–M.

| # | Sub-session | Cycle | Size | Commit | Items cleared |
|---|---|---|---|---|---|
| 1 | cont.4 | D-EXTRACTION-CONTEXT-FIX-STAGE-4 | M | `590f22ce` | gateway-forward `chat_template_kwargs` + pre-flight `LLM_CONTEXT_OVERFLOW` 400 |
| 2 | cont.5 | D-P3-BOOK-SUMMARY-PERSIST-AUDIT | S | `18a64fb1` | Redis Stream `retry_at_epoch` burned budget in ms → inline-sleep fix |
| 3 | cont.6 | D-P3-INDEX-PRUNE-ENDPOINT | M | `2c0e405a` | `POST /internal/admin/summary-indexes/prune` with 3 orphan reasons |
| 4 | cont.7 | D-P2-MIGRATE-TO-PER-OP-EXTRACTOR-VERSION | XS | `98bbd931` | P2 task_id `v1-{op}-{hash}` instead of global hash |
| 5 | cont.8 | D-P2-STALE-CLAIM-LIFESPAN-HOOK | XS | `d90d5417` | `reset_stale_claims` wired into lifespan + 5 unit tests |
| 6 | cont.9 | 3-XS bundle | 3×XS | `3b610565` | worker-infra config test fix + prompts README + intent-classifier glossary-unavailable metric |
| 7 | cont.10 | D-PHASE6C-TRACE-ID-UNIFY | M | `35439e26` | NEW `loreweave_obs.current_otel_trace_id()`; 500 body emits both ids |
| 8 | cont.11 | D-PHASE6C-WORKERAI-JOB-SPAN | S | `f4dc68e1` | `@_with_job_span` decorator on `process_job` |
| 9 | cont.12 | D-PHASE6A-BETA-STREAM-RECORD | S | `9d2f1dac` | `streamGuard.settle` writes `usage_logs` row alongside reconcile |
| 10 | cont.13 | 5-item batch (6A polish + stale rows) | 2×S + 3 stale | `b1b5cbef` | EstimateNChunks overlap + affordableMaxTokens quantum headroom + 3 stale-row markup fixups |

**Cumulative impact:**
- Deferred-items table went from ~30 active to ~14 active (16 cleared).
- 4 new memory entries: `redis-streams-no-time-based-delivery`, `gateway-passthrough-must-forward-all-optional-fields`. Plus 2 reinforced (`feedback_batch_small_tasks`, `feedback_scope_audit_before_batching`).
- 1 latent test bug fixed during cont.12 (Settle_Dispatch was capturing last POST body across reconcile+record; would have silently broken when /record landed).
- 1 unexpected discovery during cont.13: 3 of 5 deferred rows were already-implemented but never-marked-cleared (D-PHASE6A-BETA-402-MESSAGE + D-K17.2a-02 + D-K4a-02). Saved the cycle from false implementation work.

## What's NEXT — three tracks open

### Track A: Model swap + live extraction baselines (USER-DRIVEN, blocking)

User said cont.4 they'd swap LLM model before resuming extraction (huihui-qwen3.6 ran at 7.6 tok/s parallel — too slow). Once the new model is registered, several deferred LIVE-SMOKE rows fold into one natural verification cycle:

- `D-EXTRACTION-CONTEXT-FIX-STAGE-4-LIVE-SMOKE` — verify `thinking_tokens` drops from 55-89% → ~0 with `chat_template_kwargs` now flowing through gateway; verify 400 `LLM_CONTEXT_OVERFLOW` fires on a fat prompt.
- `D-P3-LLM-JUDGE-BASELINE-CHECK` — verify P=0.97 / R=0.81 (9 golden chapters) holds post-P3.
- `D-P3-SHERLOCK-BASELINE` — sherlock_speckled_band joins baseline (P ≥ 0.85, R ≥ 0.70) thanks to P2 cache + P3 hierarchy enabling resumption.
- `D-P3-BASELINE-QWEN3.6-RERUN` — apples-to-apples baseline rerun on the new model.
- `D-P2-FULL-EXTRACTION-LIVE-SMOKE` + `D-P3-LIVE-SMOKE` + `D-P3-BOOK-SUMMARY-PERSIST-AUDIT` functional re-trigger naturally fold in (the unit-level fixes are shipped + deployed; live verification just confirms the deployed behaviour).

### Track B: Larger single-cycle items (no model dependency)

- `D-P1-IMPORT-PROCESSOR-INTEG-TESTS` [M-L] — 3 orchestrator tests (CallsParseEndpoint, TxRollbackOnSceneInsertFailure, ParseFailureMarksJobFailed). Needs Go testcontainer infra OR pgx.Pool interface refactor.
- `D-P3-MIXED-STATE-CONSOLIDATION` [M] — feature: one-click cleanup endpoint for mixed-state chapters (entities with `:EVIDENCED_BY` but no `:MENTIONED_IN` after partial P3 re-extraction).
- `D-PHASE6A-WORKER-SETTLE-IT` [M] — integration test for `worker.settleBilling` reconcile/release DB path; needs `jobs`-package DB harness.
- `D-PHASE6A-BETA-ACCOUNT-BALANCES-RETIRE` [M] — dead-code cleanup: remove `/record`'s `account_balances` deduction (ADR-superseded).
- `D-PHASE6C-DB-SPANS` [M-L] — OTel-instrument asyncpg/pgx/Neo4j calls monorepo-wide.
- `D-PHASE6B-RETRY-USAGE-DOUBLECOUNT` [M] — a retry can double-count usage tokens in `chatAggregator` / `jsonListAggregator`.
- `D-PHASE6B-MEDIA-DOUBLE-CHARGE` [M] — retrying media-gen after ambiguous transient error can double-generate.

### Track C: Small batchable polish (next batch candidates)

- `D-K21A-03` [S] — Redis `incr` rate-limit key leak (no TTL) in `memory_remember`.
- `D-K21A-04` [S] — `get_tools_redis()` singleton never closed.
- `D-PHASE6-REASONING-CONTENT` [S] — read `reasoning_content` from chat aggregator (DeepSeek-R1, o1 put answers there).
- `D-PHASE6-RERANK-CANCEL-ON-TIMEOUT` [S-M] — gateway job leaks when `wait_for(timeout=1.0s)` cancels SDK task.
- `D-P2-EXTRACTOR-VERSION-DEV-RECOMPUTE` — ✅ already cleared in cont.9 bundle (this row label is stale; remove next batch).

Per `feedback_batch_small_tasks`: next session can batch 3-4 of these into one workflow pass.

## Status snapshot — 5-phase hierarchical extraction

| Phase | Status |
|---|---|
| P1 Structural Decomposer | ✅ shipped (sessions 62-63) + live-smoked |
| P2 Cache + Leaf Core | ✅ MVP shipped (session 63) + per-op version migrated (cont.7) + stale-claim hook (cont.8) |
| P3 Hierarchical Reduce + Summaries | ✅ shipped (sessions 64-66 + cont.5 audit fix + cont.6 prune endpoint + cont.11 worker span) |
| P4 Semantic Chunking Escape Valve | not started — not critical-path |
| P5 Gated LLM Coref + Multi-res Refinement | not started — not critical-path |

**50MB local capability:** P1+P2+P3 shipped + all known correctness bugs from cascade smoke cleared. Pending: Track A model swap + baseline reruns.

## Status snapshot — observability (Phase 6c)

| Item | Status |
|---|---|
| 6c-α/β/γ baseline (W3C tracecontext across services) | ✅ shipped (sessions 53-57) |
| Trace-id unification (X-Trace-Id ↔ OTel trace_id) | ✅ shipped (cont.10) |
| Worker-ai per-job parent span | ✅ shipped (cont.11) |
| Mode-3 intent-classifier glossary-unavailable counter | ✅ shipped (cont.9) |
| DB-span instrumentation (asyncpg/pgx/Neo4j) | ❌ deferred — Track B |
| Tempo durability beyond dev | ❌ deferred — production polish |
| Metrics + log correlation (vs traces only) | ❌ deferred — production polish |

## Status snapshot — billing (Phase 6a)

| Item | Status |
|---|---|
| Subsystem A (user budget guardrail) for jobs | ✅ shipped |
| Subsystem B (platform free tier + credits) for jobs | ✅ shipped |
| Streaming guardrail (chat) | ✅ shipped + writes usage_logs (cont.12) |
| Subsystem A for stt-multipart | ❌ deferred (`D-PHASE6A-STT-MULTIPART-GUARDRAIL`) |
| `EstimateNChunks` accounts for chunk overlap | ✅ shipped (cont.13) |
| `affordableMaxTokens` reserves quantum headroom | ✅ shipped (cont.13) |
| `worker.settleBilling` integration test | ❌ deferred (Track B) |
| `account_balances` dead-code cleanup | ❌ deferred (Track B) |
| Retry double-count guard | ❌ deferred (Track B) |

## Recently cleared this session (cont.4 → cont.13)

D-EXTRACTION-CONTEXT-FIX-STAGE-4 · D-P3-BOOK-SUMMARY-PERSIST-AUDIT · D-P3-INDEX-PRUNE-ENDPOINT · D-P2-MIGRATE-TO-PER-OP-EXTRACTOR-VERSION · D-P2-STALE-CLAIM-LIFESPAN-HOOK · D-WORKER-INFRA-CONFIG-TEST · D-P2-EXTRACTOR-VERSION-DEV-RECOMPUTE · D-P3-INTENT-CLASSIFIER-GLOSSARY-METRIC · D-PHASE6C-TRACE-ID-UNIFY · D-PHASE6C-WORKERAI-JOB-SPAN · D-PHASE6A-BETA-STREAM-RECORD · D-PHASE6A-NCHUNKS-OVERLAP · D-PHASE6A-CAP-ROUNDUP · D-PHASE6A-BETA-402-MESSAGE (stale row) · D-K17.2a-02 (stale row) · D-K4a-02 (stale row).

## Operator notes

- All 10 commits pushed to `origin/main`. No local-only state.
- Knowledge-service + chat-service + provider-registry-service + worker-ai images rebuilt + deployed mid-session as their changes landed. All healthy at end of session.
- `extraction.summarize` Redis stream had 109 entries pre-cont.5 (the bug). Post-fix, future jobs should leave only the 3 logical messages per book in the stream. Worth monitoring on next extraction run.
- New `billing.UsdQuantum` constant is exported — other Go callers reasoning about USD precision can now import it instead of redefining `1e-8`.
- Test bug discovered + fixed in cont.12 (`TestStreamGuard_Settle_Dispatch` was last-body capture): pre-existing bug, would have failed silently if `/record` landed without the filter. Pattern worth remembering: when an httpest stub captures "the last body" and a feature adds a second POST, the test silently asserts on the wrong payload.

---

# Historical handoff — Session 66 (P3 Router MVP shipped)

> Content below preserved from the prior session's handoff. Refer to SESSION_PATCH.md for authoritative state.

> **Date:** 2026-05-23 (sessions 62-66 — P1+P2+P3 design+Foundation+Integration+Router MVP, pending P3 Router commit)
> **HEAD:** `faeb9b07` (P3 Integration) → pending P3 Router commit. **Branch 1 commit ahead of origin** after Integration push.
> **Branch:** `main`.

## What's NEXT — P3 BUILD across 3 sessions per design plan

### Pre-flight at session 64 start

- Push the 9 local commits to origin (user manual). Memory `feedback_verify_deployed_image_matches_source` reminds: confirm deployed image after push (we rebuilt + smoke-tested locally for P1+P2).
- Confirm `pytest services/knowledge-service/tests/unit/test_pass2_orchestrator.py` is green at HEAD (P3 BUILD will modify it).
- Confirm `loreweave_extraction.__extractor_version__` is `v1-6dce61b7` (current — to verify per-op extension doesn't break P2 cache baseline).

### Session 64 Foundation (DONE — committed 50ea6b46 + pushed)

11 files; 30 new tests; SDK 16/16 + KS 1721/1721 green.

### Session 65 Integration (DONE — committed faeb9b07 + pushed)

7 files; 20 new tests; KS 1741/1741 green.

### Session 66 Router MVP (DONE — pending commit)

4 files (2 NEW + 2 tests); 23 new tests; KS 1764/1764 green.

NEW: `abstract_query.py` (D5 heuristic: keyword + long-query+no-entity) + `summary_blend.py` (per-project per-level Neo4j vector index parallel query + score-weighted blend).

**Locked primitives ready for wire-up**:
- `is_abstract_query(message, glossary_entities) -> bool` — intent gate
- `select_summary_blend(session, project_id, embedding_model_uuid, query_embedding) -> list[LevelSummaryHit]` — multi-index retrieval

## What's NEXT — 2 wire-up tasks + live smoke to close P3

### D-P3-MODE3-ROUTER-WIRE-UP (~20 LoC, session 67)

In `app/context/modes/full.py`, add `_safe_summary_blend` parallel to `_safe_l3_passages`. Call it when `is_abstract_query(message, glossary_entities)` returns True. Merge results into the Mode-3 prompt builder (new `<summaries>` block similar to `<passages>`).

Files: 1 MODIFY (full.py) + maybe NEW renderer block. ~2-3h.

### D-P3-WORKER-AI-CONSUMER-WIRING (~3-4h, session 67-68)

NEW worker-ai task module that:
1. XREADs `extraction.summarize` Redis Stream with consumer group `worker-ai-summary`
2. For each message: `SummarizeMessage.from_redis_fields()` + dispatch `process_summarize_message(msg, deps)`
3. Wires `SummaryProcessorDeps`: knowledge_pool + neo4j_session + llm_client + embedding_client + summary_enqueue (for M4 re-enqueue)
4. XACK on success; let pending claim on failure (idle worker re-fetches)

Mirror existing `worker-ai/app/tasks/extraction_job_processor.py` pattern. Tests live in worker-ai.

### D-P3-LIVE-SMOKE + LLM-JUDGE-BASELINE + SHERLOCK-BASELINE (after wire-ups)

Cross-service smoke: full extraction → hierarchy nodes → per-chapter/part/book summaries → Mode-3 abstract query blend. Then LLM-judge baseline check + sherlock_speckled_band joining baseline.

## Status of 5-phase hierarchical extraction

| Phase | Status |
|---|---|
| P1 Structural Decomposer | ✅ shipped (sessions 62-63) |
| P2 Cache + Leaf Core | ✅ MVP shipped (session 63) |
| P3 Hierarchical Reduce + Summaries | ✅ primitives complete (sessions 64-66); 2 wire-ups pending |
| P4 Semantic Chunking Escape Valve | not started |
| P5 Gated LLM Coref + Multi-res Refinement | not started |

**50MB local capability**: P1+P2+P3 primitives ready; full integration requires the 2 wire-ups.

End-of-session-64 commit: "P3 Foundation [XL session 1/3]".

### Session 65 Integration (~5-6h)

Files:
1. MODIFY `pass2_writer.py` per M1 (hierarchy threading + `:MENTIONED_IN -> :Scene` edges in same Tx per D2a).
2. MODIFY `pass2_orchestrator.py` per M2 (summary message enqueue + `is_last_chapter` flag plumbing per D9).
3. EXTEND `SummaryRepo` with upsert methods + `UniqueViolationError` handling per M5.
4. NEW `services/knowledge-service/app/jobs/summary_processor.py` + worker-ai task registration + 5 unit tests + extractor tests.

End-of-session-65 commit: "P3 Integration [XL session 2/3]".

### Session 66 Router + live smoke (~3-4h)

Files:
1. NEW `app/context/intent/classifier.py` OR EXTEND `app/context/modes/full.py` per D5.
2. 5 router unit tests.
3. Live smoke per spec §4.6: full extraction → hierarchy nodes → summary indexes → Mode-3 abstract query blend.
4. SESSION_PATCH clears D-P3-LIVE-SMOKE + D-P3-LLM-JUDGE-BASELINE-CHECK + D-P3-SHERLOCK-BASELINE.

End-of-session-66 commit: "P3 Router + live smoke [XL session 3/3]".

### Step 2 (later): P4 + P5

Per ADR §6 roadmap. P3 + P2 caching + P1 structural decomp = **50MB local capability complete** per acceptance. P4 (semantic chunking escape valve) and P5 (gated LLM coreference + multi-resolution retrieval refinement) are quality polish; non-critical-path.

P1 (T1 structural decomposer) + P2 MVP (T3 cache + leaf core) are committed. **P3 is the critical-path next phase per ADR §6 roadmap.**

**Read first:** [`docs/03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md`](../03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md) §3 T4 + §6 P3 + §7 P3.

**P3 scope (ADR T4 + T7 stage 1):**
- Tree-merge bottom-up: scene KGs → chapter KGs → part KGs → book KG.
- Deterministic merge: canonical_id-keyed entity merge + alias union-find (Tarjan UF) + relation merge by (subject_canonical_id, predicate, object_canonical_id, polarity) + event merge by (name_norm, time_cue).
- Per-level summary embedding (NEW): LLM-generated 2-3 sentence summary per chapter/part/book node, embedded + indexed.
- Neo4j hierarchy nodes (`:Scene` / `:Chapter` / `:Part` / `:Book`) with `:HAS_CHILD` edges.
- P3 acceptance: tree-merge produces book-level KG identical (modulo summaries) to flat-dedup; legacy chapters join baseline (no longer skipped); `sherlock_speckled_band` joins baseline (achievable now with P2 cache+resume per spec).

**P3 also fulfils these P2 deferred rows:**
- D-P2-PER-SCENE-FANOUT: per-scene parallelism is natural at the reduce layer (each scene = independent leaf).
- D-P2-FULL-EXTRACTION-LIVE-SMOKE: hierarchical extraction live test is the natural smoke.

### Step 2 (later): P2 polish if hit at scale

If first 1MB+ novel extraction shows pain, address:
- D-P2-PER-SCENE-FANOUT (if intra-chapter parallelism needed)
- D-P2-STALE-CLAIM-LIFESPAN-HOOK (if extraction jobs crash mid-run)
- D-P2-PARENT-JOB-ID-PLUMBING (if per-leaf billing telemetry needed)

These are NOT blockers for P3 start.

## What's NEXT — D-P1-LIVE-SMOKE first, then start P2 (parallel map + checkpoint)

### Step 1 (must-do first): close D-P1-LIVE-SMOKE

Session 62 VERIFY hit a `docker compose build knowledge-service` failure — pip `JSONDecodeError: Unterminated string` during requirements.txt install, repeating across 3 retries. book-service Go rebuilt cleanly in parallel → confirmed **not** P1 code. Likely PyPI metadata cache corruption inside Docker buildkit.

**Run order:**
1. `docker compose build knowledge-service` — if it works now (pip cache cleared, metadata refreshed), proceed.
2. If still fails: try `docker compose build --no-cache knowledge-service`, OR pin a specific bs4 version, OR investigate which package is corrupting the install.
3. Once built, `docker compose up -d` and execute the live smoke per spec §4.5:
   - Upload `services/knowledge-service/tests/fixtures/golden_chapters/alice_*.txt` (or an EPUB) via book-service `/v1/books/{id}/import`.
   - Assert: `import_jobs.status='completed'`; `parts` row created; `chapters.part_id` + `structural_path` populated; `scenes` rows created with sane `leaf_text`.
   - Round-trip: query joined `leaf_text` for one chapter, compare to pandoc-stripped HTML — must match.
4. Clear D-P1-LIVE-SMOKE in SESSION_PATCH.

### Step 2: P2 (parallel map + checkpoint) — L-XL cycle

**Status (session 62, end-of-session):** D-P1-LIVE-SMOKE cleared in commit `2a7535b4` (knowledge-service + worker-infra rebuilds succeeded; cross-service `.txt` import end-to-end through `/internal/parse` → DB confirmed). **CLARIFY for P2 done in-session below — DESIGN starts session 63.**

**Read first:** [`docs/03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md`](../03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md) §3 T3 + §6 P2 + §7 P2 acceptance.

#### P2 CLARIFY answers (session 62 PO, locked)

| Q | PO choice | DESIGN implication |
|---|---|---|
| `extraction_leaves.result_jsonb` content scope | **Both — raw in cold storage + candidates hot** | Two tables: `extraction_leaves` (post-processed candidates, hot read path) + `extraction_leaves_raw` (full raw LLM response, cold; for re-judge/re-score without LLM re-call). DESIGN must address: retention policy (prune raw after N days? keep forever?), JOIN cost on re-judge, separate writes vs single Tx. |
| Cache invalidation when `scenes.parse_version` changes | **Explicit invalidation via DELETE** | P2 worker / new admin endpoint: when `parse_version` is bumped, DELETE FROM extraction_leaves + extraction_leaves_raw WHERE book_id IN (...). DESIGN must address: idempotent invalidation surface (CLI tool? `POST /internal/extraction/invalidate-cache/{book_id}`?), migration ordering with parse_version bump. |
| P2 worker placement | **Extend knowledge-service worker-ai** | Add `extraction-leaf-processor` consumer to existing worker-ai (Python). Reuse Redis Streams + DB pool + gather_relations_events_facts helper. No new compose service. |
| Glossary anchor failure mode | **Hard fail — leaf job 502** | Glossary-service uptime is now a hard dependency for extraction. If glossary 5xx → leaf marked failed (after retry budget). **PO accepted trade-off: brief glossary outage = paused extraction.** DESIGN must address: explicit health-check gate at job start (fail-fast vs fail-mid-leaf), retry budget interaction. |

#### P2 scope (consolidates ADR §3 T3 + the CLARIFY answers)

- NEW `extraction_leaves` table on knowledge-service DB: `(book_id, leaf_path, op) UNIQUE`, status, candidates_jsonb (post-processed), retried_n, started_at, completed_at, parse_version (FK semantic to scenes.parse_version).
- NEW `extraction_leaves_raw` table on knowledge-service DB: `(extraction_leaf_id) FK`, raw_response_jsonb, raw_token_usage, created_at. Cold table — separate write, indexed only by FK.
- Idempotent task ID: `sha256(leaf.normalized_text + extractor_op_name)` — re-submit same leaf → cache hit, skip LLM call. **Note: parse_version is NOT in the hash** (per PO choice 2: explicit invalidation, not composite-id).
- DAG over leaves bound by `LM_STUDIO_MAX_CONCURRENT` env (default 4).
- Per-chapter glossary anchor: fetch via glossary-service `/internal/books/{book_id}/extract-entities` (the existing bulk endpoint; confirm the contract). Per-chapter, not per-leaf. **Hard-fail if 5xx after retry budget.**
- Per-leaf retry budget (default 2); on exhaustion mark `failed`, reduce-step (P3 future) ignores.
- Resume on restart: skip `status='completed'` leaves; recompute everything else from scratch.
- NEW `POST /internal/extraction/invalidate-cache/{book_id}` endpoint for explicit invalidation when parse_version is bumped.
- **P2 fallback contract (M6 locked at P1 DESIGN — DO NOT SKIP):** when reading scenes for a chapter, if `scenes WHERE chapter_id=$1 AND lifecycle_state='active'` returns empty, fall back to `chapter_drafts.body` via `tiptap_json_to_text(body)` as one virtual scene. Legacy (pre-P1) chapters have NULL `structural_path` + zero scenes; this fallback is the bridge. **If P2 skips this contract, legacy chapters silently get zero extraction.**

**P2 reuses existing** `gather_relations_events_facts` extractor. No prompt change. No new ML.

#### Open questions for DESIGN phase (defer to next session)

- **OQ-P2-1**: `extraction_leaves_raw` retention policy. Keep forever (storage grows linearly with extraction runs)? Or prune after N days? Or per-book opt-in flag for "save raw" (debugging mode)? Recommend: **opt-in via project setting** so storage is bounded by user choice.
- **OQ-P2-2**: Glossary fetch granularity. Per-chapter is locked but the existing `/internal/books/{book_id}/extract-entities` endpoint returns all entities for a book. Should we cache that response in worker memory for the duration of one extraction run (book-scoped LRU)? Or refetch per-chapter (simpler but more glossary load)?
- **OQ-P2-3**: Concurrent extraction jobs on same book. If a user clicks "Build Graph" twice in succession, do we (a) reject the second job, (b) merge into the first, (c) let both run and dedupe via task_id hash? Recommend: (c) — task_id hash naturally dedupes; if same input, only one LLM call fires.
- **OQ-P2-4**: Cache invalidation triggers. Beyond `parse_version` bump, what else invalidates? Extractor prompt template change? LLM model change? Recommend: **add `extractor_version` column** to `extraction_leaves`; bump on any prompt/model change; invalidation DELETE filters on `extractor_version != current`.

Critical-path next session.

### Step 3 (later sessions): P3 (hierarchical reduce + per-level summaries) → P1+P2+P3 = 50MB capability complete

Per ADR §6: P3 is the third critical-path phase. P4 (semantic chunking escape valve) + P5 (gated LLM coref + multi-res retrieval) are independent quality polish that come after.

---

## Session 62 — what happened

Full 12-phase XL cycle for P1 (structural decomposer / T1 of the hierarchical extraction ADR). PO answered 3 CLARIFY questions, then "approve" repeated through DESIGN → REVIEW (design) → PLAN → BUILD → VERIFY → REVIEW (code) → QC → POST-REVIEW. P1 implementation **capability complete in code**; cross-service live smoke deferred via D-P1-LIVE-SMOKE.

### What changed

| Layer | Files | Test counts |
|---|---|---|
| Python SDK `sdks/python/loreweave_parse/` | 5 modules + `__init__.py` + parent `pyproject.toml` registration + `bs4>=4.12` dep | **38/38** SDK tests |
| knowledge-service `/internal/parse` | NEW router + tests + `max_parse_body_bytes` config + bs4 dep + main.py wire-up | **9/9** router tests; full suite **1654/1654** |
| book-service schema | parts + scenes tables + chapter.part_id/structural_path + 3 indexes (NO backfill — R-SELF-1 NULL sentinel for legacy) | **5/5** migrate regression tests |
| worker-infra integration | NEW `parse_client.go` + tests; REWROTE `import_processor.go` (3-level Tx D7); DELETED `splitChapters` + 4 helpers from `html_to_tiptap.go` | **6/6** parse_client contract tests + 4 splitChapters tests removed (replaced by SDK tests) |
| book-service `.txt` sync path | NEW `parse.go` (parseClientCall + processTxtImport) + tests; ADDED `.md` to `allowedImportFormats`; ROUTED `.txt` through `/internal/parse` per H1 | **6/6** parse tests |

### Review trail
- DESIGN: 3 self-review (R-SELF-1/2/3) + 10 /review-impl round 1 (3H + 7M + 4L + 1C) — all HIGH+MED folded inline; 2 MED deferred.
- /review-impl round 2 on BUILD: 0H + 4M + 5L + 3C — 5 fix-now batched (~25 LoC), 6 deferred rows queued.

### 6 deferred rows filed
- **D-P1-LIVE-SMOKE** — pip JSONDecodeError blocked knowledge-service image rebuild; must run first thing next session.
- **D-P1-IMPORT-PROCESSOR-INTEG-TESTS** — plan promised 3 processImport orchestrator tests; only HTTP-client unit tests written; rely on live smoke.
- **D-P1-CHAPTER-RAW-AUDIT** — `.txt` now writes per-chapter joined leaf_text to chapter_raw_objects.body_text (markers stripped vs pre-P1 full body); audit FE callers of `getChapterContent`.
- **D-P1-LEAF-TEXT-NESTED** — `html_to_leaf_text` direct-text fallback covers `<li>outer<ul>...</ul></li>` + `<div>loose<p>...</p></div>` but deeper edges may surface on real EPUBs.
- **D-P1-CONTRACT-DRIFT-TEST** — 3 mirrored schemas (Python `_types.py` + 2 Go) have no fixture-based drift test; consider extracting `sdks/go/lwparse/`.
- **D-WORKER-INFRA-CONFIG-TEST** — pre-existing `TestLoadDefaults` panic (predates P1, confirmed via git stash).

### Memory anchors validated / created
- `feedback_cheap_structural_before_expensive_semantic` — pandoc + structural walk handle every fixture without semantic chunking.
- `feedback_review_impl_on_design_cycles` — round 1 caught 3H+7M at DESIGN; round 2 caught 4M post-BUILD. Pattern continues to pay; invoke both rounds.
- `feedback_design_test_plan_is_a_checklist` — caught the M3 gap (promised processImport integration tests were missing).
- `feedback_mock_only_coverage_hides_crossservice_bugs` — parse_client_test.go explicitly asserts X-Internal-Token header per D-CHAT-BILLING-01 pattern.

### Lessons (candidate for agent memory)
- **PyPI metadata corruption inside Docker buildkit can fail an image build for 3+ retries.** Memory `feedback_host_env_drift_masquerades_as_code_bug` corollary: distinguish infra-flake from code-bug — try the OTHER service build in parallel (book-service Go rebuilt fine while knowledge-service Python failed) to confirm it's infra not code. Defer with `live infra unavailable: <reason>` per CLAUDE.md cross-service evidence rule.
- **2-round /review-impl is the right cadence for XL cycles introducing new abstractions + cross-service contracts.** Round 1 at DESIGN caught H1 (.txt bypass path I'd documented wrongly in D3), H2 (HTML→text algorithm not locked), H3 (body cap unspecified); round 2 at BUILD caught M1 (innermost-only block walker drops outer-text), M3 (missing promised integration tests). Each round costs ~$1-2 of subagent calls; net cost vs. landing those bugs post-release: trivial.

---

## Session 61 — what happened (for context, superseded by session 62)

[earlier session-61 cycle 1+2+3 details retained below in this file for archaeological reference; key takeaway: fence-fix cycle 1 unlocked P=0.97/R=0.81 on 9/10 golden chapters; cycle 2 idle-timeout safety net; cycle 3 ADR written; session 62 implemented P1.]

---

## Session 61 — what happened

Started as the CLARIFY of catalogue-driven extraction Stage 1 (XL, per session 60's ADR). The empirical gate the ADR mandated — capturing qwen3.6's raw `result.events` BEFORE any catalogue code — returned a **decisively different answer than the ADR assumed**, and the cycle pivoted to a small surgical fix.

### Root cause (CLARIFY)

Captured raw qwen3.6 output for alice_ch01 in two ways:
1. **Direct LM Studio chat completion** (bypassing the gateway aggregator) — returned **8 well-formed events**, all in-enum `kind` (action/travel/dialogue), all with named participants. JSON wrapped in markdown ` ```json … ``` ` fence.
2. **Through the production gateway path** — returned **0 events**, `chunk_errors: ["chunk 0: invalid character '`' looking for beginning of value"]`, despite the model emitting real `output_tokens`.

Diagnosis: `provider-registry-service/internal/jobs/aggregator.go:mergeChunkJSON` did `json.Unmarshal([]byte(raw), &parsed)` directly on the chunk content. The leading backtick of the markdown fence failed `Unmarshal`, the chunk's items went to `chunk_errors` instead of `merged`, and the job completed empty with no surfaced failure. **Silent across every extraction op** (`entity` / `relation` / `event` / `fact`) for **every reasoning model that wraps JSON in code fences**, since the aggregator shipped.

### Fix (S — 2 files, single service, single commit)

- NEW `extractJSONObject(raw) (string,bool)` in `aggregator.go` — first-`{`-to-last-`}` substring extractor. Strips markdown fences + any surrounding prose; returns `ok=false` when there is no balanced `{…}` so unrecoverable input still surfaces a `chunk_error` (no silent swallowing).
- `mergeChunkJSON` tries direct `json.Unmarshal` first, on failure recovers via `extractJSONObject` + retry-Unmarshal, on failure of that records the chunk_error. Clean-JSON path unchanged (zero-perf regression); chat aggregator untouched (different code path).
- 4 new tests: fenced, prose+fence, no-brace-still-errors (regression-lock against the recovery path swallowing real failures), helper unit.

### Verify (live smoke)

- `go test ./internal/jobs/` green, `go vet` clean.
- **Cross-service live smoke**: rebuilt provider-registry, re-ran extraction on alice_ch01 through the gateway → **event_extraction 0→8 events**, `chunk_errors` cleared, entity_extraction unaffected.
- **Full 9-chapter eval** (qwen3.6 extraction → gemma-4-26b LLM-judge): **P=0.97 R=0.81** macro, coverage P=62% R=56%. Raw counts: 65 entities + 49 relations + 60 events across the 9 chapters. The 10th chapter `sherlock_speckled_band` (1139 lines / 17 chunks) hangs the local 35B target under concurrent load — a perf concern orthogonal to the fence-fix; excluded.
- Updated `services/knowledge-service/eval/QUALITY_EVAL_BASELINES.md` with a "Post-fence-fix LLM-judge baseline (2026-05-23)" section.

### Empirical refutation of the catalogue-driven ADR's premise

Across the 9 golden chapters, **mechanism A (out-of-enum `kind`) and mechanism B (empty participants) — the two failure modes the ADR identified — did NOT trigger once**. The kind enum + the `_postprocess` participants filter are sufficient for the current fixture set. The "8/10 chapters → 0 events" observation session 60 measured against the rule-based scorer was 100% the fence bug; nothing about taxonomy.

**Status of catalogue-driven extraction ADR:** the design is still valid for genre fiction kinds (xianxia / cultivation realm / sect / technique — kinds the closed extractor enum cannot represent) but downgraded from "blocking R&D" to "**re-prioritise when a genre-fiction fixture set exists**". The ADR remains in `docs/03_planning/` as a future option.

### Baseline shift

| Run | Date | Extractor | Scorer | P | R |
|---|---|---|---|---:|---:|
| Session 59 pre-fence-fix | 2026-05-13 | gemma-4-26b | rule-based | 0.311 | 0.429 |
| Session 60 LLM-judge (broken pipeline) | 2026-05-22 | qwen3.6 | gemma judge | ~1.00 | ~0.46 |
| **Post-fence-fix LLM-judge** | **2026-05-23** | **qwen3.6** | **gemma judge** | **0.97** | **0.81** |

Recall jump 0.46→0.81 is the fence-fix payoff (the dropped chunks were the bulk of the chapter, not low-quality outliers).

## Session 61 cycle 2 — long-chapter perf idle-timeout safety net

The fence-fix cycle's full-9-chapter baseline run revealed `sherlock_speckled_band` (1139 lines / 17 chunks × 4 ops) hangs the local 35B target under sustained load. In-DB `llm_jobs` records confirmed: even SERIAL mode stalled with `event_extraction` stuck at 4/17 + a sibling `fact_extraction` failed mid-job with HTTP 400 `"Failed to load model qwen/qwen3.6-35b-a3b. Operation canceled."` — LM Studio's auto-eviction had unloaded the model mid-stream, the streamer (deliberately "No wall-clock timeout" per memory `feedback_no_timeout_on_llm_pipeline`) had no idle detection, so the chunk request waited forever.

**Fix (M, 6 files, primary in provider-registry-service):**
- NEW `idleTimeoutReader` + `wrapStreamBody` in `provider/streamer.go` — per-Read `time.AfterFunc` closes the body when no bytes arrive within `LLM_GATEWAY_STREAM_IDLE_TIMEOUT_S`. Atomic flag distinguishes idle-close from upstream-close → `ErrUpstreamTimeout`. Default 0 in code preserves the no-timeout memory principle; compose sets 300s prod default. **Idle vs wall-clock distinction**: only fires when NO bytes arrived in the window — a legitimately slow but progressing model never trips it.
- Wired at BOTH streamer entry points: `openCompletionStream` (OpenAI/LM Studio/Ollama) + `doStreamPOST` (Anthropic). No path bypasses.
- 5 new Go tests + `blockingReadCloser` helper.
- `infra/docker-compose.yml` sets `LLM_GATEWAY_STREAM_IDLE_TIMEOUT_S=300` env-tunable.
- `test_extraction_eval.py` adds `KNOWLEDGE_EVAL_LONG_CHAPTER_MAX_PARAGRAPHS=200` default skip (sherlock 252 → auto-excluded; set 0 to opt-in).
- `QUALITY_EVAL_BASELINES.md` "Run notes" section documents LM Studio TTL recommendation + the idle-timeout net.

**Verify:** all provider-registry packages `go test` green + `go vet` clean + live smoke (rebuilt provider-registry, sent chat job through SDK → status=completed, idle timer did not spurious-fire).

**Status of the long-chapter problem after this cycle:** the idle-timeout is a **band-aid that makes failures fail-fast** (chunk surfaces error, aggregator records `chunk_errors`, job completes with partial data). It does NOT make sherlock-class chapters succeed — that requires the architectural rework being researched next session (hierarchical semantic chunking + parallel map + tree-merge reducer, see top "What's NEXT").

## Lessons (for agent memory)

- **The CLARIFY empirical gate paid off.** The ADR explicitly mandated capturing the raw output before any catalogue code. That single step refuted the ADR's premise in one chapter, saving the XL refactor.
- **Memory `feedback_mock_only_coverage_hides_crossservice_bugs` strikes again.** Aggregator unit tests had fed clean JSON for years; the live model emits fences. The fix added a regression-lock test feeding a fenced input + a no-brace-still-errors guard against the recovery path swallowing real failures.
- **`feedback_no_timeout_on_llm_pipeline` corollary**: when a model "fails", audit the pipeline first. The fence bug had been masking real model quality across all 4 extraction ops since the aggregator shipped.
- **Concurrent load on a single LM Studio 35B is fragile** — saw repeated transient flakes (cold-model entity-extraction returning 0; mid-chapter event-extraction stuck) during the original concurrency=3 eval run. Serial (concurrency=1) was needed for two stragglers. The eval test should probably default to lower concurrency for the local target.
- **Idle timeout ≠ wall-clock timeout** (cycle 2). The memory principle "no wall-clock timeout on the LLM path" deliberately leaves long-running models alone, but does NOT prevent us from detecting an upstream that's gone *silent*. The cycle-2 `idleTimeoutReader` fires ONLY when no bytes have arrived in the window — a slow-but-progressing model never trips it. Reconciliation of these two principles is the right pattern for any cross-service stream where the upstream can die without protocol-level notification.
- **A safety net is not a cure.** Cycle 2's idle-timeout makes sherlock-class chapters *fail fast* instead of hanging. The architectural fix (semantic chunking + parallel map + tree-merge) is queued for the next session. Document the boundary so the safety net isn't mistaken for the solution.

---

## Session 60 — what happened (for context, superseded by the above)

The session set out to start the R&D extraction-quality track (session 59's "final work") and instead **redirected it**, because two foundations were broken:

1. **The measuring instrument was wrong.** The rule-based golden-set scorer matches by exact string/token equality — invalid for an interpretive task. Built an **LLM-as-judge** eval (`tests/quality/llm_judge.py` + `test_judge_eval.py` + 25 unit tests; judge routes through the SDK→provider-registry gateway; judge model = gemma-4-26b, different family from the Qwen extractor → no self-bias; **discrimination-probe-validated**, codified as a `--run-quality` test). **Finding: extraction precision ≈ 1.0** (the rule-based 0.60 was an artifact); **recall is the real gap, events ≈ 0**.
2. **Taxonomy rot.** Investigating events surfaced **three divergent kind vocabularies** — glossary `entity_kinds` catalogue (12 open, genre-aware) / extractor 6-enum / FE `KIND_OPTIONS` (7-set). None aligned. Extraction's closed enums drop data (event sub-type isn't even persisted) and can't represent genre kinds.

**Decision:** wrote **`docs/03_planning/KNOWLEDGE_SERVICE_CATALOGUE_DRIVEN_EXTRACTION_ADR.md`** (option A — glossary catalogue = taxonomy SSOT; keep `:Event` node + open subtype; entity-kind catalogue-driven; staged). `/review-impl` folded 3 MED + 4 LOW. **R&D + eval-dataset rebuild are DEFERRED behind the refactor.** Sequence: **(1) catalogue-driven extraction refactor → (2) eval dataset → (3) R&D.**

**3 commits on `main`** (origin at `2d56eb16`): `68291181` (LLM-judge), `f7510c3e` (judge hardening + `/review-impl` fixes), `5e1001a8` (ADR + session notes).

**Runtime gaps fixed in passing:** all LM Studio user_models lacked `pricing` → Phase 6a fail-closed ("model pricing not configured" 402); set `{"input_per_mtok":0,"output_per_mtok":0}` on qwen3.6 (`019e21cc-…`) + gemma-4-26b (`019dc3df-…`) in the provider-registry DB. `register_lm_studio_models.sql` still needs the same pricing patch.

## What's NEXT — Stage-1 of the catalogue-driven extraction refactor

**Read first:** `docs/03_planning/KNOWLEDGE_SERVICE_CATALOGUE_DRIVEN_EXTRACTION_ADR.md` (the full design + the folded review findings + acceptance criteria).

**Start at CLARIFY (the ADR says do this BEFORE any code):**
1. **Reload `qwen/qwen3.6-35b-a3b` in LM Studio** (session 60 left gemma-4-26b loaded for the judge) and **capture raw `result.events`** for a failing chapter (e.g. alice_ch01) → confirm whether events are lost to (a) out-of-enum `kind`, (b) the no-participants `_postprocess` filter, or (c) the model emitting none. Do NOT assume; the ADR's event-recall fix is unverified (MED#3).
2. **Resolve R4** — what writes `event_ref` / `preference` in the FE `KIND_OPTIONS`? They match neither catalogue nor extractor vocab; may be legitimate knowledge-only kinds that should NOT be forced into the glossary catalogue.

**Then BUILD (Stage 1):** glossary `GET /internal/books/{book_id}/entity-kinds` endpoint + `GlossaryClient.list_kinds` + `app/extraction/kind_catalogue.py` (cache + degradation fallback); remove the entity/event kind `Literal`s (never drop); `normalize_kind_to_catalogue` before anchor lookup + persist; persist `:Event.kind`; delete `_EXTRACTOR_TO_GLOSSARY_KIND` (audit all callers); reconcile the FE `EntitiesTab` filter to fetch dynamically. Measure before/after with the LLM-judge harness (judge-coverage ~68% caveat noted).

**Eval-dataset rebuild (after the refactor):** the conservative golden fixtures + exact-string scoring are being superseded by the LLM-judge; revisit the fixture philosophy (LLM-as-judge against source, not a hand-annotated subset) once extraction is catalogue-aligned.

**How to run the judge** (judge model loaded in LM Studio; an extraction dump already produced under `.eval_dumps/` — gitignored):
```
KNOWLEDGE_EVAL_JUDGE_MODEL=<judge_user_model_uuid> KNOWLEDGE_EVAL_USER_ID=<uuid> \
KNOWLEDGE_JUDGE_DUMP_PATH=.eval_dumps/<run> \
  pytest services/knowledge-service/tests/quality/test_judge_eval.py --run-quality -s
```
Extraction dump first via `test_extraction_eval.py` with `KNOWLEDGE_EVAL_DUMP_PATH` set. Stack: `docker compose up -d provider-registry-service` (pulls postgres/rabbitmq/minio/usage-billing) is enough for extraction+judge — Neo4j NOT needed (judge scores in-memory). LM Studio must serve the requested model (it serves whatever is LOADED regardless of model_ref → load the right one; `Max Concurrent Predictions=1` gives each request the full context at 32K).

---

## Session 59 — what happened (previous session)

Session 59 cleared the post-session-58 follow-up deferrals, then — on the user's call after a debt-vs-R&D discussion — added two **structural debt-prevention** fixes before the final R&D track, then cleared the three R&D-blocking prep items.

**10 commits on `main`:**

| Commit | Cycle | What |
|---|---|---|
| `3fd6e022` | 1 | **D-EMB-CLEANUP-01** — dropped dead `knowledge_projects.embedding_provider_id` column (the same-named col on `project_embedding_benchmark_runs` stays). |
| `dc78d3a3` | 2 | **D-EMB-EVAL-PKG-01** — moved K17.9 benchmark runtime into `app/benchmark/core.py` (+ `fixture_loader`/`mode3_query_runner`/`persist`/`metrics`/`golden_set.yaml`); `eval/run_benchmark.py` is now a thin CLI shell; Dockerfile no longer ships `eval/`. |
| `29955655` | 3 | **D-EMB-BENCHMARK-CAL-01** — per-dimension threshold overrides in `golden_set.yaml`; 1024 (bge-m3) `negative_control_max_score` 0.50→0.70. |
| `03424d43` | 4 | **D-EMB-MODEL-REF-04** — `patch_project` rejects 422 when changing `embedding_model` on a project with a graph (`extraction_status != 'disabled'`) → forces the destructive `PUT /embedding-model?confirm=true`. |
| `c2330176` | 5 | **D-CHAT-BILLING-01** — chat-service `BillingClient` now sends `X-Internal-Token` (was 401-rejected → per-model usage silently dropped since the service shipped). |
| `d5c2acbc` | A | **SESSION_PATCH archive** — file was 6030 lines / 1.3 MB (exceeds Read tool limit). Archived sessions 46-57c8 → NEW `SESSION_ARCHIVE.md`; SESSION_PATCH now **689 lines**. |
| `65b4b0e3` | B | **Live-smoke evidence soft-WARN** — `workflow-gate.py` warns at VERIFY when a cross-service change (≥2 `services/X/`) lacks a live-smoke acknowledgement token; CLAUDE.md Phase 6 documents it. Process guard against the recurring "mock-green but live-broken" pattern (4 hits sessions 58-59). |
| `a95d53eb` | DEF-03 | **C-PRED-ALIGN-DEF-03** — user confirmed LM Studio `Max Concurrent Predictions ≥4` + `Unified KV Cache ON` (RTX 4090 was at 20% util → single-request mode). |
| `39c3f261` | DEF-01 | **C-PRED-ALIGN-DEF-01** — extracted `gather_relations_events_facts` helper (single source of truth for Pass-2 R+E+F parallelism); eval test now mirrors production shape + adds the missing `extract_facts` + cross-chapter `asyncio.Semaphore(4)`. Also fixed a latent missing-`llm_client` `TypeError` in the eval test. |
| `26fd589e` | C18-DEF-01 | **C18-DEF-01** — `time_cue` now persisted on `:Event` nodes (was dropped at write time); also activates the previously-dead C18 `event_date_backfill` helper. |

**State now:** knowledge-service Tracks 1-3 + Track 2/3 Gap Closure (C1-C18) + K21 are all feature-complete. All post-session-58 follow-up deferrals cleared. SESSION_PATCH is navigable again. The eval harness is production-aligned + parallelized + LM Studio-tuned. knowledge-service unit suite **1620/1620**; chat-service **247/247**.

## Session 59 — what was next (SUPERSEDED by session 60 — R&D deferred behind the catalogue-driven refactor; see top)

**The only remaining knowledge-service work is the R&D extraction-quality track** (a.k.a. the gemma-eval track). Everything else is either done or a non-blocking polish/live-smoke deferral.

**Goal:** improve Pass-2 extraction quality (precision / recall / FP-trap-rate) on the **local** LM Studio target `google/gemma-4-26b-a4b` (per agent memory `feedback_local_llm_first_cloud_is_fallback` — cloud LLMs are calibration-only; token cost makes iterative cloud tuning prohibitive).

**Prior baseline** (`services/knowledge-service/eval/QUALITY_EVAL_BASELINES.md`): gemma-4-26b-a4b post-C-PRED-ALIGN scored **P 0.311 / R 0.429 / FP-trap 0.238** (pre-align was P 0.251 / R 0.356 / FP-trap 0.275). Gates (`P≥0.80 / R≥0.70 / FP-trap≤0.15`) are tuned for strict cloud LLMs + conservative fixtures; local-LLM runs fail them by design — the metric is *relative improvement per cycle*, not gate-pass.

**Readiness — all set up this session:**
- Eval harness mirrors production R+E+F parallelism (DEF-01) + runs chapters with `asyncio.Semaphore(4)` (env-tunable `KNOWLEDGE_EVAL_CHAPTER_CONCURRENCY`).
- LM Studio continuous batching confirmed ON (DEF-03) → expect 2-3× throughput vs the old serial runs.
- `time_cue` now persists on `:Event` (C18-DEF-01) → event-extraction quality is measurable + the `event_date_iso` backfill is tunable.
- 9 golden fixtures (5 English + 4 multilingual CJK/Vietnamese) in `tests/fixtures/golden_chapters/`.

**How to run** (needs the full stack + a registered LM Studio model):
```
docker compose --profile extraction up        # stack incl. neo4j (default-on)
KNOWLEDGE_EVAL_MODEL=<user_model_uuid> \
KNOWLEDGE_EVAL_USER_ID=<uuid> \
KNOWLEDGE_EVAL_PROJECT_ID=<uuid> \
KNOWLEDGE_EVAL_DUMP_PATH=/tmp/eval_dump \      # per-chapter actual/expected/attribution JSON
  pytest services/knowledge-service/tests/quality/test_extraction_eval.py --run-quality -s
```
The `--run-quality` flag + the `KNOWLEDGE_EVAL_MODEL` env are both required (the test skips otherwise). The dump path writes per-chapter diagnostics for semantic FP/FN analysis without re-running.

**Suggested first move (user-decided at session start):** capture a fresh **baseline** on the production-aligned + parallelized harness (no tuning) so the R&D track has a clean reference, THEN iterate. Each cycle: tweak prompt vocab / extraction rules → re-run → compare P/R/FP-trap per chapter via the dump.

**Non-blocking deferrals remaining** (none gate the R&D track — all explicitly targeted to their own phases in SESSION_PATCH "Deferred Items"):
- `D-K21B-07` — live-verify D12 Anthropic tool-calling (needs an Anthropic BYOK key).
- `C-PRED-ALIGN-DEF-02` — production events consumer in-process concurrency (Track 3 perf).
- ~6 LIVE-SMOKE items (Phase 6a/6c guardrail + OTel) — orthogonal to R&D paths; need a full live stack.
- ~20 polish-bucket items (K21 polish, 6a/6b/6c follow-ups, FE cosmetics) — see SESSION_PATCH. The strategic plan (user-agreed) is a periodic **"Gap Closure v2" debt-paydown arc** *after* the R&D track, not item-by-item now.

**Read in this order:** 1. `SESSION_PATCH.md` (top 10 bullets = session 59). 2. `services/knowledge-service/eval/QUALITY_EVAL_BASELINES.md` (prior P/R/FP-trap progression + per-chapter signal). 3. `docs/03_planning/KNOWLEDGE_SERVICE_TRACK2_3_GAP_CLOSURE_PLAN.md` §6 (roll-up). 4. This handoff.

**Recurring lesson (agent memory):** several knowledge-service phases shipped "complete" on unit-mock-only coverage and broke the first time they ran live (4 hits sessions 58-59). Cycle B's live-smoke WARN now flags this at VERIFY — but the judgment to actually live-smoke (or explicitly defer) is still the agent's. The R&D track runs the real LM Studio stack, so it IS the live smoke for the extraction pipeline.

---

## Session 57 cycle 2 — billing-model redesign ADR · /review-impl round 1 (3H+6M+3L all folded)

**Why this cycle exists:** the session set out to do Phase 6a ("quota enforcement at job submission"). Scoping it surfaced that the **billing model itself is broken**, so the 6a code cycle was abandoned mid-DESIGN and replaced with this ADR.

**The discovery chain:** (1) the gateway's `recordInvocation` is **unwired** — the gateway doesn't bill jobs; book/video/chat-service each call `/internal/model-billing/record` post-hoc. (2) `account_balances` meters a **token count** — wrong unit (models cost 10–30× different per token; the flat `0.000002`/token cost is fiction). (3) LoreWeave is **BYOK** — for `user_model` jobs the user pays their own provider, so a runaway loop drains the *user's* account; a platform-vs-BYOK quota gate does **not** protect them. Web research (LiteLLM/Bifrost/OpenRouter/Cloudflare AI Gateway) confirmed the norm: **USD per-user budgets, pre-flight worst-case estimate, `max_tokens` capped to remaining budget**.

**Deliverable:** [`docs/03_planning/BILLING_MODEL_REDESIGN_ADR.md`](../03_planning/BILLING_MODEL_REDESIGN_ADR.md) — billing split into **two subsystems**:
- **A — Spend Guardrail**: per-user **USD** budget (daily+monthly windows), applies to **every** job (BYOK + platform); pre-flight estimate → **402** before the provider call + `max_tokens` cap + estimate-based reservation. Protects the *user's* wallet.
- **B — Platform Resale Ledger**: `platform_model` only; config-driven free-tier USD + prepaid credits. Protects *LoreWeave's* wallet.
- Schema: `account_balances` → `spend_guardrails` + `token_reservations` + `platform_balances` (`NUMERIC(16,8)`).

**`/review-impl` round 1:** 3 HIGH + 6 MED + 3 LOW, all folded — fail-CLOSED on unpriced models, `NUMERIC(16,8)` (not 12,4 which rounds per-call cost to $0), per-operation pricing dimensions, `available = limit − spent − reserved` invariant, `FOR UPDATE`, `/record` `request_id` idempotency, streaming approach, leaked-reservation sweeper.

### What's NEXT for the next agent

**Phase 6a — Subsystem A (USD spend guardrail)** — a fresh **XL** cycle. Per ADR §4: `spend_guardrails` + `token_reservations` tables + migration; per-model USD pricing fields on `user_models` + platform-model config; gateway USD estimator; pre-flight 402 + `max_tokens` cap in `doSubmitJob`; terminal reconciliation in `worker.go finalizeAndNotify`; wire the gateway as job biller (`/record` idempotent by `request_id`). Then **6a-β** (Subsystem B, L) and **6a-γ** (FE guardrail config, M). 6b (retry — `worker.go:348` already marks it) and 6c (tracing — **greenfield OTel, L–XL not M**) follow.

ADR §6 open questions to settle at 6a CLARIFY: BYOK pricing-entry UX, per-unit estimate magnitudes (image/video/audio), window-reset policy, streaming tally cadence.

**Read in this order:** 1. `SESSION_PATCH.md` (top entry). 2. `BILLING_MODEL_REDESIGN_ADR.md`. 3. `LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` §6 (rows updated). 4. This handoff.

---

## Session 57 cycle 1 — Phase 5f · video-gen-service hardening · /review-impl rounds (DESIGN: 1H+3M+3L+1C; BUILD: 0H+1M+4L+2C — all fixed inline)

**Phase 5f was redefined.** The refactor plan listed 5f as "video-gen-service deletion + FE migration to call the gateway directly." CLARIFY killed that: video-gen-service is **not a pure proxy** — its `/generate` route downloads the gateway's result to MinIO + records billing, and the gateway's `video_gen` result is the raw upstream provider URL (Phase 5d, url-only), which a browser cannot fetch for a local ComfyUI backend. Deleting it would lose persistence + billing and break local video. **User decided (3 CLARIFY questions): keep video-gen-service as a permanent thin domain BFF** — the role book-service plays for chapter media — and harden it instead.

**What shipped — 3 audit gaps closed:**
- **G1** — removed the dead `/models` endpoint (zero FE callers; always-empty; had a `ModelsResponse(models=[])` wrong-kwarg bug) + `ModelInfo`/`ModelsResponse` schemas + FE `videoGenApi.listModels` + `VideoModel`.
- **G2+G4** — MinIO bucket bootstrap moved off the request hot path into a FastAPI `lifespan` handler, **and** video-gen-service now sets a public-read policy on `loreweave-media`. G4 was a real browser-breaking bug: it `make_bucket`'d with no policy, so winning the create-race vs book-service left the bucket private → generated video URLs 403'd. Added `_bucket_ready` flag + `ensure_bucket_ready()` per-request self-heal so a startup MinIO blip can't permanently break video serving.
- **G3** — incoming user JWTs are now HS256 signature-verified (`algorithms=["HS256"]` allow-list blocks `alg:none`); was an unverified base64 decode. Mirrors chat-service `auth.py`; `JWT_SECRET` was already wired in docker-compose.

**Files (13 — 2 NEW + 11 MOD):** NEW design doc + `tests/test_bucket_bootstrap.py`; MOD config/main/models/routers.generate/requirements + 3 test files + FE `video-gen/api.ts` + README + `infra/test-video-gen.sh`.

**Two `/review-impl` rounds, all findings fixed inline:**

| Round | Findings | Key fix |
|---|---|---|
| DESIGN | 1H + 3M + 3L + 1C | HIGH#1 — a one-shot best-effort bootstrap with no retry would itself reproduce G4 if MinIO is down at boot → adopted book-service `_bucket_ready`-flag + per-request self-heal |
| BUILD | 0H + 1M + 4L + 2C | MED#1 — `ensure_bucket_ready` (the HIGH#1 fix's own function) was untested → +2 tests; LOW PyJWT pinned, grep-lock hardened, conftest fixture promoted |

### Verify evidence
```
video-gen-service pytest:   25 passed (was 13; +12)
frontend tsc --noEmit:      exit 0
grep app/ list_models|ModelsResponse|ModelInfo:   0
grep generate.py urlsafe_b64decode:               0
bash -n infra/test-video-gen.sh:                  OK
```

### What's NEXT for the next agent

The **unified-gateway program is effectively complete** — every service's LLM/audio/image/video calls flow through `provider-registry`; video-gen-service is a permanent domain BFF, not a violation. Remaining planned work in [LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md](../03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md) is **Phase 6 — Hardening**: 6a rate-limit/quota enforcement at job submission, 6b job-level retry policy, 6c OpenTelemetry trace_id end-to-end. None are started. No open blockers from this cycle.

**Deferrals cleared this cycle:** `D-PHASE5E-MINIO-ASYNC-OFFLOAD` (G2), `D-PHASE5E-JWT-VERIFY-DEFENSE-IN-DEPTH` (G3). **Opened:** none.

**Read in this order:**
1. `docs/sessions/SESSION_PATCH.md` — full state (top entry = this cycle)
2. `docs/03_planning/LLM_PIPELINE_PHASE5F_DESIGN.md` — design + both /review-impl rounds folded
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — §5f updated + Phase 6 preview
4. This handoff file

---

## Session 56 cycle 3 — Phase 5e-β.2 · gateway audio_gen adapter + MinIO staging + Python/Go SDK + book-service audio.go migration · /review-impl rounds (DESIGN: 4H+11M+13L+3C; BUILD: C#1+5H+10M+7L; FIX DELTA: 1CRIT+2H+3M+2L — ALL critical+HIGH fixed inline across all 3 rounds)

**What shipped:** Gateway gains first-class `audio_gen` operation (batch TTS, 1..10 inputs, order-preserving). NEW `internal/storage/audio_cache.go` MinIO wrapper for URL-mode staging (public-read bucket + 1-day server-side lifecycle; mirrors book-service `loreweave-media` pattern). Both response modes: `b64_json` (default, inline) AND `url` (gateway-staged). book-service `audio.go` migrated off direct `/internal/credentials/` + `/v1/audio/speech` httpx path; uses batch SDK call → caller-side b64 decode → upload to its own MinIO. `PROVIDER_REGISTRY_SERVICE_URL` env DROPPED from book-service (audio.go was last consumer).

**Strategic significance:** After this cycle, book-service has ZERO direct provider httpx calls. The unified LLM gateway invariant is realized for: chat, completion, embedding, stt, tts (stream), tts (batch via audio_gen), image_gen, video_gen, entity_extraction, relation_extraction, event_extraction, fact_extraction, translation. Only Phase 5f remains (video-gen-service deletion + api-gateway-bff `/v1/video-gen/*` retirement + FE migration).

**Three review rounds, all critical+HIGH fixed inline:**

| Round | Findings | Resolution |
|---|---|---|
| DESIGN | 4H + 11M + 13L + 3C | URL mode redesigned (presigned-with-rewrite broke SigV4 → public-read static URLs); worker plumbing explicit; DB constraint name unversioned; dual-interface for book-service; SDK pointer pattern; MaxAudioGenInputs=10 (not 20) |
| BUILD | C#1 + 5H + 10M + 7L | C#1 substantially closed (+52 tests across 5 files); H#1 non-string text rejection; H#2 delete-defer (partial); H#4 LLM_GATEWAY_STORAGE_ERROR; H#5 Content-Type whitelist; M#4 format whitelist |
| FIX DELTA | 1CRIT + 2H + 3M + 2L | CRIT C#1 LLM_GATEWAY_STORAGE_ERROR was orphan code — registered in both SDKs + book-service writeAudioGenError; H#1 delete-defer race fully eliminated (DELETE only after all per-item ops succeed via `media_key != ALL($4::text[])`); H#2 LLMUpstreamError body kwarg added |

**~52 new tests this cycle** across adapter (9) / worker (5+10 subtests) / handler (9) / Go SDK (8) / Python SDK (11) + book-service helper tests.

**Files (~45 — 22 NEW + 23 MOD):**
- NEW gateway storage pkg + design doc + Python SDK test file + book-service audio_test.go
- MOD across gateway (adapter/worker/handler/server/main/config/migrate/go.mod) + Python SDK (errors/models/client/__init__/tests) + Go SDK (models/errors/client/tests) + book-service (audio/server/config/test) + docker-compose + openapi + notification

### Verify evidence
```
provider-registry-service go test ./...   ALL GREEN
  +9 audio_gen adapter tests (incl. order-preservation regression-lock)
  +5 worker tests (+10 classifyAudioGenError Matrix subtests)
  +9 jobs_router handler validation tests
sdks/python pytest:                       207 passed (was 196; +11)
sdks/go/llmgw go test:                    52 passed (was 44; +8)
book-service go test:                     api 0.24s + config 0.18s GREEN
grep audio.go:                            0 matches for /internal/credentials/, /v1/audio/speech, creds.*
grep audio.go:                            has s.audioGenClient.GenerateAudio(, llmgw.ErrAudioGenerationFailed, writeAudioGenError(
```

### What's NEXT for the next agent

**Phase 5f (M)** — `services/video-gen-service/` deletion + api-gateway-bff `/v1/video-gen/*` retirement + FE migration to call unified gateway directly. After 5f: unified gateway invariant FULLY realized for all platform LLM/audio/image/video. Estimated ~15 files.

**Open deferred items added this cycle:**
- `D-PHASE5E-BETA2-STORAGE-UNIT-TESTS` — AudioCache.Stage whitelist/0-byte tests need MinIO test instance
- `D-PHASE5E-BETA2-AUDIO-GEN-PARALLEL-ADAPTER` — sequential v1; future goroutine fan-out (order invariant locked by test)
- `D-PHASE5E-BETA2-AUDIO-GEN-PARTIAL-SUCCESS` — currently all-or-nothing batch
- `D-PHASE5E-BETA2-AUDIO-CACHE-FAST-TTL` — MinIO 1-day minimum vs ideal 1-hour
- `D-PHASE5E-BETA2-LIVE-SMOKE` — manual against real OpenAI BYOK + book chapter
- Plus ~12 lower-priority deferred items from review rounds 2 + 3

**Read in this order:**
1. `docs/sessions/SESSION_PATCH.md` — full state (top entry = this cycle)
2. `docs/03_planning/LLM_PIPELINE_PHASE5E_BETA2_DESIGN.md` — design + 4H+11M+13L review fixes folded
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — Phase 5e-β.2 ✅ + 5f preview
4. This handoff file

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` confirm closed
2. For Phase 5f: size M-L (~15 files). Mostly DELETE + FE migration. No new backend logic.
3. Reference impls: this cycle's audio_gen completes the gateway slot pattern (5b+5c-α+5d+5e-β.2); 5f is purely retirement.

---

## Session 56 cycle 2 — Phase 5e-β.1 · Go SDK + book-service media.go migration · /review-impl rounds (DESIGN: 6 HIGH + 5 MED + 6 LOW + 3 COSMETIC all actionable folded inline; BUILD: 3 HIGH + 6 MED + 7 LOW + 3 COSMETIC, 3 HIGH + 5 MED + 1 LOW fixed inline)

## Session 56 cycle 2 — Phase 5e-β.1 · Go SDK + book-service media.go migration · /review-impl rounds (DESIGN: 6 HIGH + 5 MED + 6 LOW + 3 COSMETIC all actionable folded inline; BUILD: 3 HIGH + 6 MED + 7 LOW + 3 COSMETIC, 3 HIGH + 5 MED + 1 LOW fixed inline)

**What shipped:** First Go SDK in the monorepo (`sdks/go/llmgw/` — module `github.com/loreweave/llmgw`, package `llmgw`) implementing the submit_job → poll → terminal-result flow modeled on Python SDK's `generate_image()`. book-service's `generateChapterMedia` migrated off direct `/internal/credentials/` + `/v1/images/generations` httpx path; uses `s.llmgw.GenerateImage()` with typed-error switch in extracted `writeImageGenError` helper. audio.go INTENTIONALLY unchanged (reserved for Phase 5e-β.2; needs audio_gen gateway adapter first).

**Strategic context (Path B step 4):** 5c-α + 5d shipped image_gen + video_gen gateway adapters; 5e-α migrated video-gen-service (first Python caller); this cycle migrates book-service (first Go caller). After 5e-β.2 (audio_gen adapter + audio.go migration) + 5f (video-gen-service BFF deletion + api-gateway-bff `/v1/video-gen/*` retirement + FE migration), unified gateway invariant fully realized.

**Scope-split decision:** handoff scoped "book-service migration" as one cycle; CLARIFY found (a) two LLM call sites (media.go image_gen + audio.go TTS), (b) audio_gen adapter doesn't exist on gateway yet, (c) full scope = 40-45 files / XXL. User chose split into 5e-β.1 (Go SDK + media.go) → 5e-β.2 (audio_gen adapter + audio.go). Per memory `feedback_scope_audit_before_batching`.

**First-ever Go SDK pattern decisions:**
- Filesystem `sdks/go/llmgw/` + module `github.com/loreweave/llmgw` + package `llmgw` (no underscore — `staticcheck ST1003` clean; Go-idiomatic short name)
- Sync API; context cancellation only (no `*http.Client.Timeout` traps for polling)
- Sentinel-based `errors.Is`/`errors.As` matching via unexported `inner` field
- Central `newErrorFromCode` constructor helper REQUIRED for all `*Error` construction — manual struct construction would silently break errors.Is
- Caller-defined consumer interface (`type imageGenerator interface { GenerateImage(...) }`) in book-service for mocking
- `replace ../../sdks/go/llmgw` in book-service go.mod; Dockerfile bumped to repo-root build context

**First-ever handler test for media.go:** book-service had NO tests for `generateChapterMedia`. 13 new tests added covering typed-error routing via extracted `writeImageGenError` helper + 1 real-SDK end-to-end test through `httptest.NewServer` + 2 grep-locks + 1 anti-bait. Full DB+MinIO+JWT integration test harness DEFERRED to Track 2 (HIGH#4 in design /review-impl).

**Files (22 — 11 NEW + 11 MOD):**
- NEW `docs/03_planning/LLM_PIPELINE_PHASE5E_BETA1_DESIGN.md` (status SHIPPED; DESIGN+BUILD review fixes folded)
- NEW `sdks/go/llmgw/{go.mod, doc.go, client.go, transport.go, models.go, errors.go, errors_test.go, transport_test.go, client_test.go}` (10 files)
- NEW `services/book-service/internal/api/media_test.go` (13 tests + grep-locks + anti-bait)
- MOD `services/book-service/internal/api/media.go` — drops ~110 LOC credential resolve + direct POST; uses SDK; extracted `writeImageGenError` helper
- MOD `services/book-service/internal/api/server.go` — `s.llmgw` field + ctor with `slog.Error` on NewClient failure
- MOD `services/book-service/internal/config/config.go` — +LLMGatewayInternalURL required env
- MOD `services/book-service/internal/config/config_test.go` — pre-existing broken test fixed (was missing required envs)
- MOD `services/book-service/go.mod` — replace directive for SDK
- MOD `services/book-service/Dockerfile` — repo-root build context
- MOD `infra/docker-compose.yml` — book-service build.context: .. + LLM_GATEWAY_INTERNAL_URL env

### `/review-impl` rounds

**Round 1 — DESIGN (BEFORE BUILD).** 6 HIGH + 5 MED + 6 LOW + 3 COSMETIC. All actionable folded inline.

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🔴 HIGH | `errors.Is` via `inner` was specified only at one construction site; rest left to implementer. Central `newErrorFromCode(code, msg, status)` helper + regression-lock test enforcing every `codeSentinels` entry round-trips. |
| 2 | 🔴 HIGH | Dockerfile + docker-compose build context bump missing from §4.1 scope. Promoted to in-scope; explicit Dockerfile diff. |
| 3 | 🔴 HIGH | `NewServer` signature change unflagged. Kept current `NewServer(pool, cfg) *Server` signature; SDK construction inline with nil-on-misconfig matching `s.minio` precedent. |
| 4 | 🔴 HIGH | §10.2 test plan claimed "SDK mock returns error EARLY" but ensureOwnerBook DB call comes BEFORE SDK call. Scope reduced to extracted-helper unit tests; full DB harness deferred. |
| 5 | 🔴 HIGH | `*http.Client.Timeout` injection trap (would silently cap each poll). SDK accepts `http.RoundTripper` only; internal `*http.Client` has no Timeout. |
| 6 | 🔴 HIGH | Test `TestGenerateImage_NonDefaultSize` would have been Phase 5e-α MED#1 trap recurring (gateway's "1024x1024" default = the asserted value). Use "1792x1024" + assert WIRE body not result. Add omitted-Size companion test. |
| 7 | 🟡 MED | Wire-body construction must use explicit `map[string]any` pattern (not struct + omitempty). |
| 8 | 🟡 MED | ErrImageGenerationFailed and ErrUpstream into SEPARATE switch cases. |
| 9 | 🟡 MED | Caller uses `errors.As` not type-assert. |
| 10 | 🟡 MED | Surface Retry-After header from `*Error.RetryAfterS`. |
| 11 | 🟡 MED | Package naming closure: `llmgw` (resolves staticcheck warnings). |

**Round 2 — BUILD output.** 3 HIGH + 6 MED + 7 LOW + 3 COSMETIC. 3 HIGH + 5 MED + 1 LOW fixed inline.

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🔴 HIGH | doc.go example showed `UserID: ownerID,` (would not compile — UserID is string but ownerID is uuid.UUID). Fixed to `ownerID.String()`. |
| 2 | 🔴 HIGH | FE `VersionTimeline.tsx:134-137` renders `ai_model` raw; design deferred this claiming FE resolves UUID → name but no such resolver exists. Real UX regression risk. Fix: store empty string in `ai_model` — FE conditional `{v.ai_model && ...}` naturally hides the line. New rows display without model line; legacy rows keep "dall-e-3". Graceful degradation. |
| 3 | 🔴 HIGH | `NewClient` failure in NewServer was silently swallowed. Added `slog.Error(...)` so a 503-forever loop is debuggable. |
| 4 | 🟡 MED | Test stub `wrappedSentinelError.Is()` bypasses the real Unwrap chain. Added `TestWriteImageGenError_RealSDKContentPolicy_RoutesTo400` that constructs a real `*llmgw.Error` through an httptest.NewServer-backed SDK call and routes it through `writeImageGenError`. |
| 5 | 🟡 MED | `LLM_AUTH_FAILED` → 502 PROVIDER_ERROR was wrong for the dominant case (BYOK key revoked upstream). Now → 402 NO_PROVIDER (FE prompts "configure provider"). |
| 6 | 🟡 MED | Dead `len(result.Data) == 0` check (SDK already guards). Removed; kept URL-mode `result.Data[0].URL == ""` check with future-b64-caller TODO comment. |
| 7 | 🟡 MED | `TestGenerateImage_HappyPath` doesn't assert wire `operation: "image_gen"`. Added wire-body assertions. |
| 8 | 🟡 MED | No regression-lock for zero-default poll interval. Added `TestWaitTerminal_ZeroIntervalDefaultsToHalfSecond`. |
| 9 | 🟢 LOW | Audio anti-bait test could be stronger. Added `creds.ProviderModelName` + `creds.APIKey` required-substrings. |
| - | 🔵 COSMETIC | gofmt across SDK + book-service touched files. |

**BUILD-time surprise:** REVIEW-CODE Stage 2 caught my custom `errAs` helper as redundant — replaced with stdlib `errors.As` + `errors.Is` for cleaner Go idiom.

### Verify evidence
```
sdks/go/llmgw pytest:                                  N/A (Go)
sdks/go/llmgw go test ./...:                           44 PASS (was 43; +1 zero-default regression-lock)
services/book-service go build ./...:                  CLEAN
services/book-service go vet ./...:                    CLEAN
services/book-service go test ./internal/api/:         19 PASS (12 writeImageGenError + 1 real-SDK E2E + 2 grep-locks + 4 existing)
services/book-service go test ./internal/config/:      3 PASS (incl. pre-existing broken test fixed)
grep -n "/internal/credentials/" media.go              no matches
grep -n "/v1/images/generations" media.go              no matches
grep -n "creds.ProviderKind" media.go                  no matches
audio.go retains: /internal/credentials/, /v1/audio/speech, creds.ProviderModelName, creds.APIKey  (anti-bait green)
```

### What's NEXT for the next agent

**Phase 5e-β.2 (XL)** — gateway `audio_gen` adapter + Python SDK + Go SDK extension + audio.go migration. Estimated ~25 files. Mirrors Phase 5c-α/5d patterns for gateway adapter work:

1. Gateway side (provider-registry-service):
   - openapi.yaml: +AudioGenInput + AudioGenResult + audio_gen JobOperation enum
   - migrate.go: ALTER block adding audio_gen to CHECK constraint
   - adapters.go: Adapter +GenerateAudio + types + sentinels
   - openai_audio.go (NEW): /v1/audio/speech impl (binary mp3 not URL — different from image/video URL response pattern)
   - adapters_audio.go (NEW): Anthropic/Ollama/LM Studio stubs (most lack TTS)
   - jobs/worker_audio.go + tests
   - api/jobs_handler.go validation + tests
   - notification-service consumer op-label

2. Python SDK: extend with `Client.generate_audio()` operation-based method (parallel to existing transparent-proxy TTS used by chat-service voice)

3. Go SDK: extend `sdks/go/llmgw/` with `GenerateAudio` method + `AudioGenResult` model

4. book-service `audio.go::generateAudio` migration: drop legacy credential resolve + use SDK; preserves per-block segment loop + MinIO upload + billing

5. Drop `PROVIDER_REGISTRY_SERVICE_URL` from book-service config (no longer needed once audio.go migrates)

**Phase 5f (M)** — `services/video-gen-service/` deletion + api-gateway-bff `/v1/video-gen/*` retirement + FE migration to call unified gateway directly.

**Open deferred items added this cycle:**
- `D-PHASE5E-BETA1-IMAGE-PROVIDER-MODEL-NAME-IN-RESULT` — extend SDK ImageGenResult to expose `provider_model_name` so the FE doesn't lose the human name (current empty-string workaround is graceful but suboptimal)
- `D-PHASE5E-BETA1-AI-MODEL-DB-MIGRATION` — backfill `block_media_versions.ai_model` if the empty-string-for-new-rows mixed-format becomes annoying (won't-fix unless FE complains)
- `D-PHASE5E-BETA1-LIVE-SMOKE` — manual POST /media-generate against actual provider after merge
- `D-PHASE5E-BETA1-INTEGRATION-TEST-HARNESS` — full DB+MinIO+JWT fixtures for handler integration tests (Track 2)
- `D-PHASE5E-BETA1-GO-SDK-LOGGING` — slog injection on Options for diagnostic events
- `D-PHASE5E-BETA1-GO-SDK-TRANSPORT-TUNING` — Transport.MaxIdleConnsPerHost for high-concurrency callers
- carry-over `D-PHASE5E-BILLING-PROVIDER-KIND-ANALYTICS`

**Read in this order:**
1. `docs/sessions/SESSION_PATCH.md` — full state (top entry = this cycle)
2. `docs/03_planning/LLM_PIPELINE_PHASE5E_BETA1_DESIGN.md` — design + 12 /review-impl fixes folded inline
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — Phase 5e row update + 5f preview
4. This handoff file

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` confirm closed
2. For Phase 5e-β.2: size XL (~25 files). Mirror 5c-α/5d gateway adapter cycle structure.
3. Reference impls: `sdks/go/llmgw/` for Go SDK pattern + Phase 5c-α/5d for gateway adapter + Phase 5e-α/5e-β.1 for caller migration shape

---

## Session 56 cycle 1 — Phase 5e-α · video-gen-service migration onto unified gateway · /review-impl rounds (DESIGN: 0 HIGH + 2 MED + 3 LOW + 1 COSMETIC all fixed inline; BUILD: 0 HIGH + 1 MED + 5 LOW + 2 COSMETIC, MED + 3 LOWs fixed inline)

## Session 56 cycle 1 — Phase 5e-α · video-gen-service migration onto unified gateway · /review-impl rounds (DESIGN: 0 HIGH + 2 MED + 3 LOW + 1 COSMETIC all fixed inline; BUILD: 0 HIGH + 1 MED + 5 LOW + 2 COSMETIC, MED + 3 LOWs fixed inline)

**What shipped:** First caller migration of Path B. video-gen-service `/v1/video-gen/generate` route now uses `loreweave_llm.Client.generate_video()` (shipped in Phase 5d) instead of direct httpx POST + manual credential resolution. SDK handles credential resolve + upstream POST + sync result decode internally. Per-call Client (matches chat-service voice precedent + sibling stream_service.py). Caller-side download + MinIO storage + billing PRESERVED (matches chat-service voice).

**Strategic context (Path B step 3):** 5c-α + 5d shipped the gateway adapters; this cycle migrates the FIRST production caller. After 5e-β (book-service Go migration) + 5f (video-gen-service BFF deletion + api-gateway-bff `/v1/video-gen/*` retirement + FE migration), the unified gateway invariant is fully realized for all external LLM/audio/image/video.

**First test suite for video-gen-service.** Service had NO `tests/` directory before this cycle. 13 tests added:
- 1 happy-path with SDK-wire-shape verification (kwargs captured + asserted)
- 5 error-class → HTTP status mappings (Quota→402, ContentPolicy→400, ModelNotFound→404, GenerationFailed→502, RateLimited→429)
- 1 non-default aspect_ratio regression-lock (QC MED#1: `aspect_ratio="9:16"` → asserts SDK kwargs `size=="1080x1920"`; catches hardcoded-default-bypass)
- 1 non-dict JWT payload returns 401 (QC LOW#4 edge case)
- 1 `_aspect_to_size` pure-function unit (LOW#3 from design)
- 4 grep-locks: negative (`/internal/credentials` absent + quoted `"PROVIDER_REGISTRY_URL"` absent strengthened per QC LOW#3 + `settings.provider_registry_url` absent) + positive (`loreweave_llm` import present + `Client(` construction present)

**Files (13 — 6 MOD + 7 NEW)**:
- NEW `docs/03_planning/LLM_PIPELINE_PHASE5E_ALPHA_DESIGN.md` (status SHIPPED; 5 DESIGN + 4 BUILD review fixes folded inline)
- NEW `services/video-gen-service/app/config.py` (pydantic-settings; legacy `PROVIDER_REGISTRY_URL` config dropped per /review-impl(DESIGN) MED#2)
- NEW `services/video-gen-service/app/llm_errors.py` (`map_llm_error_to_http_exception` helper with specific-before-generic ordering per memory `feedback_specific_sdk_exception_catches_before_generic`)
- MOD `services/video-gen-service/app/routers/generate.py` — drops `resolve_credentials` + direct httpx POST; uses `Client.generate_video()` per-call (try/except/finally ensures aclose() in all paths); `record_usage` signature widened to `provider_kind: str | None = None` per MED#1; download → MinIO → billing flow preserved
- MOD `services/video-gen-service/app/main.py` — settings import for fail-fast startup; dropped misleading `provider_configured` from `/health` per QC LOW#5
- MOD `services/video-gen-service/Dockerfile` — build context bumped to repo root; SDK install via `COPY sdks/python /sdk && pip install /sdk`
- MOD `services/video-gen-service/requirements.txt` — +pydantic-settings
- MOD `infra/docker-compose.yml` — video-gen-service `build.context: ..` + `dockerfile: services/video-gen-service/Dockerfile`; `PROVIDER_REGISTRY_URL` env REMOVED + `PROVIDER_REGISTRY_INTERNAL_URL` ADDED per MED#2
- NEW `services/video-gen-service/tests/__init__.py`
- NEW `services/video-gen-service/tests/conftest.py` (TestClient + JWT helper; env vars set BEFORE app import)
- NEW `services/video-gen-service/tests/test_generate.py` — 9 tests
- NEW `services/video-gen-service/tests/test_no_dead_resolution.py` — 4 grep-locks
- MOD `sdks/python/loreweave_llm/__init__.py` — extended exports (`LLMJobTerminal`, `LLMJobNotFound`, `LLMHttpError`, `LLMTransientRetryNeededError`) needed by the new `llm_errors.py` helper

### `/review-impl` rounds

**Round 1 — DESIGN (BEFORE BUILD).** 0 HIGH + 2 MED + 3 LOW + 1 COSMETIC. All 5 actionable folded inline.

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🟡 MED | `record_usage(provider_kind: str)` signature would break with None pass-through. Widened to `provider_kind: str | None = None` with rationale comment about JSON-null → Go-empty-string at usage-billing. |
| 2 | 🟡 MED | Legacy `provider_registry_url` config field would be dead after migration. Removed from config.py + compose. Mirrors Phase 5b chat-service precedent. |
| 3 | 🟢 LOW | `_aspect_to_size` helper had no unit test. Added `test_aspect_to_size_mapping`. |
| 4 | 🟢 LOW | "presumably broken against backend" → "untestable today" wording. |
| 5 | 🟢 LOW | JWT no-signature-verification: deferred `D-PHASE5E-JWT-VERIFY-DEFENSE-IN-DEPTH`. |
| 6 | 🔵 COSMETIC | proxy-routing.spec.ts mock — irrelevant to 5e-α. Skip. |

**Round 2 — BUILD output.** 0 HIGH + 1 MED + 5 LOW + 2 COSMETIC. MED + 3 LOWs fixed inline.

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🟡 MED | Happy-path used `aspect_ratio="16:9"` → `"1920x1080"` which is ALSO the fallback for unknown ratios; hardcoded-bypass regression wouldn't be caught. Added `test_generate_non_default_aspect_ratio_reaches_sdk` (uses `"9:16"` → asserts `"1080x1920"`). |
| 2 | 🟢 LOW | img2vid not exposed via GenerateRequest — accepted as `D-PHASE5E-IMG2VID-FE-INTEGRATION`. |
| 3 | 🟢 LOW | Grep-lock for `PROVIDER_REGISTRY_URL` was too specific (only `os.getenv` + `os.environ[]` forms). Strengthened to assert `'"PROVIDER_REGISTRY_URL"'` (quoted form) absent — catches all access idioms. |
| 4 | 🟢 LOW | Non-dict JWT payload (JSON array) → AttributeError on `.get()` → 401 untested. Added `test_extract_user_id_non_dict_payload_returns_401`. |
| 5 | 🟢 LOW | `/health` reported `provider_configured` based on a defaulted Settings field (always True). Dropped the misleading field. |
| 6 | 🟢 LOW | provider_kind=None analytics drift in billing — deferred `D-PHASE5E-BILLING-PROVIDER-KIND-ANALYTICS`. |
| 7 | 🔵 COSMETIC | get_minio() sync bucket check inside async route — deferred `D-PHASE5E-MINIO-ASYNC-OFFLOAD`. |
| 8 | 🔵 COSMETIC | record_usage logger pattern — standard best-effort; no action. |

**BUILD-time surprise (1):** SDK `__init__.py` was missing `LLMJobTerminal`/`LLMHttpError`/`LLMJobNotFound`/`LLMTransientRetryNeededError` exports needed by the new `llm_errors.py` helper. Extended exports.

### Verify evidence
```
video-gen-service pytest tests/:                     13 passed (first-ever test suite for this service)
SDK pytest sdks/python/tests/:                       196 passed unchanged
chat-service pytest:                                 180 passed unchanged
grep -rn "/internal/credentials" services/video-gen-service/app/routers/   no matches
grep -rn "PROVIDER_REGISTRY_URL" services/video-gen-service/app/           no matches (only PROVIDER_REGISTRY_INTERNAL_URL)
```

### What's NEXT for the next agent

**Phase 5e-β (L–XL)** — book-service (Go) migration. Currently calls `/v1/images/generations` directly from [internal/api/media.go:449](services/book-service/internal/api/media.go#L449). Needs a design decision BEFORE starting:

- **Option A: Build a Go SDK** (`sdks/go/loreweave_llm` parallel to Python). L-XL. Investment that pays off for future Go-service migrations (auth-service, sharing-service, glossary-service, catalog-service).
- **Option B: Inline Go HTTP shim** in book-service. M-L. 60-100 LOC throwaway specific to 5e-β. Faster but doesn't compound.

Recommend: revisit the decision AFTER 5e-α has run in production (live smoke confirmed). Phase 5b's voice path is a useful template even though it's Python.

**Phase 5f (M)** — `services/video-gen-service/` deletion + api-gateway-bff `/v1/video-gen/*` route retirement + FE migration to call unified gateway directly. After 5f: unified gateway invariant fully realized for chat + extraction + translation + audio + image + video.

**Open deferred items added this cycle:**
- `D-PHASE5E-JWT-VERIFY-DEFENSE-IN-DEPTH` — local JWT signature verification (defense-in-depth vs gateway-bff trust)
- `D-PHASE5E-IMG2VID-FE-INTEGRATION` — FE + GenerateRequest extension for image-to-video
- `D-PHASE5E-BILLING-PROVIDER-KIND-ANALYTICS` — backfill provider_kind at billing time if dashboards break on empty-string category
- `D-PHASE5E-MINIO-ASYNC-OFFLOAD` — move bucket bootstrap to lifespan startup (cosmetic; first-request-only)
- `D-PHASE5E-LIVE-SMOKE` — manual against local-image-generator-service:8700 (cross-validates 5d path dispatch)

**Read in this order:**
1. `docs/sessions/SESSION_PATCH.md` — full state (top entry = this cycle)
2. `docs/03_planning/LLM_PIPELINE_PHASE5E_ALPHA_DESIGN.md` — design + 8 /review-impl fixes
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — 5e-α row + 5e-β/5f preview
4. This handoff file

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` confirm closed
2. For Phase 5e-β: needs Go SDK decision FIRST; then size XL probably
3. Reference impl: 5e-α at HEAD `d276d0a7` + Phase 5b chat-service voice (Python caller pattern); for Go shim approach, see book-service media.go current state

---

## Session 55 cycle 3 — Phase 5d · video_gen adapter + SDK + openapi + 5-slot registration · /review-impl rounds (DESIGN: 1 HIGH + 2 MED + 4 LOW + 1 COSMETIC all fixed inline; BUILD: 0 HIGH + 1 MED + 5 LOW + 1 COSMETIC, MED + 3 LOWs fixed inline)
> **Branch:** `mmo-rpg/design-resume` (user pushes manually)

## Session 55 cycle 3 — Phase 5d · video_gen adapter + SDK + openapi + 5-slot registration · /review-impl rounds (DESIGN: 1 HIGH + 2 MED + 4 LOW + 1 COSMETIC all fixed inline; BUILD: 0 HIGH + 1 MED + 5 LOW + 1 COSMETIC, MED + 3 LOWs fixed inline)

**What shipped:** Gateway gains first-class `video_gen` operation on the unified contract via `POST /v1/llm/jobs operation=video_gen` → `adapter.GenerateVideo` → `VideoGenResult` (1 data entry; n=1 locked). Path dispatch `/v1/videos/generations/text-to-video` vs `/v1/videos/generations/image-to-video` based on init_image presence — matches actual local-image-generator-service routes (NOT singular `/v1/video/generations` per stale integration guide, per /review-impl(DESIGN) HIGH#1). Works against Wan, LTX Video, SDXL-derived video models. Caller-side URL→MinIO download. url-only response_format (b64 rejected per MED#3 — exceeds 8MB cap in practice). Image-to-video via `init_image` base64 field (NOT `image` per HIGH#1). `VideoGenJobTimeout=30min` (3× longer than image; ComfyUI multi-step workflows). Shared `isContentPolicyRejection` helper refactored from openai_image.go to NEW openai_content_policy.go.

**Strategic context (Path B step 2):** 5c-α activated image_gen; this cycle ships video_gen; 5e migrates callers (book-service Go + video-gen-service Python); 5f deletes video-gen-service BFF. After 5f: unified gateway invariant fully realized for chat + extraction + translation + audio + image + video.

**Files (23 — 15 MOD + 8 NEW)**:
- NEW `docs/03_planning/LLM_PIPELINE_PHASE5D_DESIGN.md` (status SHIPPED)
- MOD `contracts/api/llm-gateway/v1/openapi.yaml` — `video_gen` JobOperation enum + `VideoGenInput` + `VideoGenResult` + `VideoGenDataItem` schemas
- MOD `internal/migrate/migrate.go` — `video_gen` in CREATE TABLE inline + new ALTER block (Phase 4a-β idempotent pattern)
- MOD `internal/provider/adapters.go` — Adapter +GenerateVideo + 3 types + 3 sentinels (`ErrVideoGenerationFailed`/`ErrVideoContentPolicy`/`ErrVideoInvalidParams`) + `MaxImg2VidInputBytes=10MB`
- NEW `internal/provider/openai_content_policy.go` — refactored shared helper (was in openai_image.go); both image + video reference
- MOD `internal/provider/openai_image.go` — removed isContentPolicyRejection (now in shared file); bytes/json imports still legitimate
- NEW `internal/provider/openai_video.go` — full impl; path dispatch with **whitespace-trim before dispatch** (Fix LOW#2); adapter pre-checks; sync upstream mode; cross-ref comments
- NEW `internal/provider/adapters_video.go` — Anthropic/Ollama/LM Studio stubs
- NEW `internal/provider/adapters_video_test.go` — 13 tests (txt2vid + img2vid path dispatch + whitespace-init_image regression-lock + invariants + content-policy + oversize + typed upstream + stub-trio)
- NEW `internal/jobs/worker_video.go` — `processVideoGenJob` + `runVideoGenJob` + `classifyVideoError` + `videoJobOperations` + `VideoGenJobTimeout=30min`
- NEW `internal/jobs/worker_video_test.go` — 14 tests (2 whitelist + 1 3-way pairwise disjoint per Fix#2 + 1 5-place sync + 10 classify matrix)
- MOD `internal/jobs/worker.go` — image+video dispatch hook before chat-streaming
- MOD `internal/jobs/worker_test.go` — `TestIsStreamableOperation_RejectsNonStreamable` +video_gen + comment refresh
- MOD `internal/api/jobs_handler.go` — `validateVideoGenInput` + `validJobOperations` +video_gen + provider import + cross-ref comment (Fix LOW#6)
- MOD `internal/api/jobs_router_test.go` — +8 video_gen handler tests
- MOD `services/notification-service/internal/consumer/consumer.go` — opLabel docstring updated
- MOD `services/notification-service/internal/consumer/consumer_test.go` — +video_gen→"Video gen" fixture
- MOD `sdks/python/loreweave_llm/errors.py` — `LLMVideoContentPolicy` + `LLMVideoGenerationFailed` + `_CODE_TO_EXC` entries
- MOD `sdks/python/loreweave_llm/models.py` — `VideoGenDataItem` + `VideoGenResult` + JobOperation Literal +video_gen + max_length=1 inline comment (Fix LOW#4)
- MOD `sdks/python/loreweave_llm/client.py` — `Client.generate_video()` with `init_image` (NOT `image` per HIGH#1) + `Literal["url"]` only per MED#3
- MOD `sdks/python/loreweave_llm/__init__.py` — exports
- NEW `sdks/python/tests/test_video_gen.py` — 11 tests incl. /review-impl(BUILD) MED#1 regression-lock `test_generate_video_rejects_b64_format_server_side` + HIGH#1 regression-lock `test_generate_video_img2vid_includes_init_image_field`
- MOD `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — Phase 5d row ✅ shipped + 5e/5f preview

### `/review-impl` rounds

**Round 1 — DESIGN (BEFORE BUILD).** 1 HIGH + 2 MED + 4 LOW + 1 COSMETIC. All 8 folded inline.

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🔴 HIGH | Design's `/v1/video/generations` (singular) doesn't exist in actual local-image-generator-service (has `/v1/videos/generations/text-to-video` and `/image-to-video`). Field name was `image` per stale guide; backend uses `init_image`. Fixed by matching actual backend routes via path dispatch + renaming field to `init_image`. video-gen-service legacy path remains broken until 5e migrates it. |
| 2 | 🟡 MED | `init_image` input no size cap → DB bloat risk from 50MB base64 strings. Added `MaxImg2VidInputBytes=10MB` const + handler + adapter checks. |
| 3 | 🟡 MED | b64_json mode contract-symmetric with image_gen but realistic videos exceed 8MB cap. Handler rejects `b64_json` for video_gen with clear "use url mode" hint. Asymmetric with image_gen (intentional, documented). |
| 4 | 🟢 LOW | Contract asymmetry note (b64 image-only). Documented. |
| 5 | 🟢 LOW | Negative-N error message phrasing. Improved to "n must be >= 0". |
| 6 | 🟢 LOW | Dual-maintenance risk for video-gen-service legacy. Flagged in §9. |
| 7 | 🟢 LOW | 5-place sync test source-grep limitation. Accept (matches sibling tests). |
| 8 | 🔵 COSMETIC | Polling defaults. Accept. |

**Round 2 — BUILD output.** 0 HIGH + 1 MED + 5 LOW + 1 COSMETIC. MED + 3 LOWs fixed inline.

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🟡 MED | Design listed but missing: SDK test for b64_json rejection. Added `test_generate_video_rejects_b64_format_server_side` (verifies SDK sends caller's bypassed type-hint value on wire, gateway rejects, SDK propagates as LLMInvalidRequest). |
| 2 | 🟢 LOW | Whitespace-only init_image (`" "` or `"\n"`) routed to image-to-video → upstream parse error. Fixed: `strings.TrimSpace` before dispatch + adapter test `TestOpenAIAdapter_GenerateVideo_WhitespaceInitImage_RoutesAsTxt2Vid` (4 whitespace variants). |
| 3 | 🟢 LOW | SDK doesn't validate init_image is real base64. Accept-and-document as `D-PHASE5D-SDK-INITIMAGE-VALIDATION`. |
| 4 | 🟢 LOW | VideoGenResult max_length=1 not flagged for future relaxation. Added inline comment. |
| 5 | 🟢 LOW | Multi-error-collect (adapter first-fail). Carry-over to existing `D-PHASE5C-MULTI-ERROR-COLLECT`. |
| 6 | 🟢 LOW | No cross-reference comment between handler + adapter validation layers. Added mirror comments in both. |
| 7 | 🔵 COSMETIC | Test naming asymmetry. Accept. |

### Verify evidence
```
provider-registry-service: go build/vet/test ./...   ALL GREEN
  internal/api:                                       +8 video_gen handler tests
  internal/jobs:                                      +14 video_gen worker tests
  internal/provider:                                  +13 video_gen adapter tests
  internal/migrate:                                   no tests (compile-only) — DB CHECK additive ALTER
notification-service consumer:                        +video_gen op-label fixture, pass
SDK pytest sdks/python/tests/:                       196 passed (was 185; +11 new)
chat-service pytest:                                 180 passed unchanged
```

### What's NEXT for the next agent

**Phase 5e (XL)** — caller migration. **Two callers**, each needs a design decision:

1. **book-service** at [internal/api/media.go:449](services/book-service/internal/api/media.go#L449) — Go service. Currently calls `/v1/images/generations` directly via http.Client. Needs Go SDK OR thin Go HTTP shim to use `image_gen` via the unified gateway. **Decision needed**: build a full Go SDK (parallel to Python SDK; would also benefit future Go services like auth/sharing/glossary) vs. inline shim (60-100 LOC; throwaway for 5e only).

2. **video-gen-service** at [app/routers/generate.py:158](services/video-gen-service/app/routers/generate.py#L158) — Python service. Already uses httpx; migrating to `Client.generate_video()` is straightforward. Reference impl: Phase 5b's chat-service voice migration (same shape: drop httpx + use SDK + per-call Client instantiation pattern).

Phase 5e suggested order: video-gen-service first (smaller migration, exercises the new SDK), then book-service (larger Go decision).

**Phase 5f (M)** — `services/video-gen-service/` deletion + api-gateway-bff `/v1/video-gen/*` retirement. After this: unified gateway invariant fully realized for all external generation.

**Open deferred items added this cycle:**
- `D-PHASE5D-INTEGRATION-GUIDE-VIDEO-PATH` — cross-repo PR to update `G:\Works\local-image-generator-service\docs\EXTERNAL_AI_SERVICE_INTEGRATION_GUIDE.md` (stale singular path)
- `D-PHASE5D-LIVE-SMOKE` — manual post-merge: register local-image-generator-service:8700 + submit video_gen via curl + verify text-to-video and image-to-video dispatch
- `D-PHASE5D-SDK-INITIMAGE-VALIDATION` — client-side base64 format regex check

**Read in this order:**
1. `docs/sessions/SESSION_PATCH.md` — full state (top entry = this cycle)
2. `docs/03_planning/LLM_PIPELINE_PHASE5D_DESIGN.md` — design + 8 /review-impl fixes
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — 5d row ✅ + 5e/5f preview
4. This handoff file

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` confirm closed
2. For Phase 5e: probably L for video-gen-service migration alone, XL if also book-service (depends on Go SDK decision)
3. Reference impl: 5d at HEAD `b3f046ab` + Phase 5b chat-service voice migration for caller-side pattern

---

## Session 55 cycle 2 — Phase 5c-α · image_gen adapter + SDK + openapi · /review-impl rounds (DESIGN: 0 HIGH + 5 MED + 6 LOW + 1 COSMETIC all fixed inline; BUILD: 0 HIGH + 1 MED + 4 LOW + 1 COSMETIC, MED + 2 LOWs fixed inline)

**What shipped:** Gateway gains first-class `image_gen` operation on the unified contract via `POST /v1/llm/jobs operation=image_gen` → `adapter.GenerateImage` → `ImageGenResult` (1..4 data entries). OpenAI adapter only (Anthropic/Ollama/LM Studio return `ErrOperationNotSupported`). Works against OpenAI proper + sibling `local-image-generator-service` (ComfyUI at :8700; SD/SDXL/Illustrious/Flux/Wan/LTX Video) + any OpenAI-compat backend. Caller-side URL→MinIO download. Multi-image n=1..4. Both `response_format=url` AND `b64_json`.

**Strategic context (Path B):** first step of multi-cycle program to retire `services/video-gen-service/` BFF wrapper. After 5d (video_gen) + 5e (book-service + video-gen-service caller migration) + 5f (BFF deletion), every external generation flows through `POST /v1/llm/jobs` — unified gateway invariant fully realized.

**Files (18 — 11 MOD + 7 NEW)**:
- NEW `docs/03_planning/LLM_PIPELINE_PHASE5C_DESIGN.md` (design + plan + 12 /review-impl fixes inline; status SHIPPED)
- MOD `contracts/api/llm-gateway/v1/openapi.yaml` — `ImageGenInput` + `ImageGenResult` + `ImageGenDataItem` schemas (JobOperation enum already had `image_gen` from Phase 2b reservation)
- MOD `internal/provider/adapters.go` — Adapter interface +GenerateImage; +GenerateImageInput/Output/GeneratedImage types; +3 sentinels (`ErrImageGenerationFailed`, `ErrImageContentPolicy`, `ErrImageInvalidParams`); +2 consts (`MaxImagesPerJob=4`, `MaxImageResponseBytes=8MB`)
- NEW `internal/provider/openai_image.go` — full OpenAI implementation; **adapter-level invariant pre-checks** (Prompt empty + N>cap + N<0 + bad response_format → ErrImageInvalidParams per Fix #5); **JSON-first `isContentPolicyRejection`** per Fix #3 — avoids prompt-echo false-positive (substring fallback only when JSON parse fails)
- NEW `internal/provider/adapters_image.go` — Anthropic/Ollama/LM Studio stubs
- NEW `internal/provider/adapters_image_test.go` — 14 tests (happy URL/b64/multi-n/revised_prompt + 3 content-policy variants incl. prompt-echo-not-misclassified + 4 invariants + oversize-response + 2 typed-upstream + empty-data + 3 stub-locks)
- NEW `internal/jobs/worker_image.go` — `processImageGenJob` + `runImageGenJob` + `classifyImageError` (incl. ErrImageInvalidParams → LLM_INVALID_REQUEST per Fix #5) + `imageJobOperations` whitelist + `ImageGenJobTimeout=10min` (ComfyUI batch headroom)
- NEW `internal/jobs/worker_image_test.go` — 14 tests (2 whitelist + 1 disjoint per Fix #2 + 1 5-place-sync + 10 classify matrix)
- MOD `internal/jobs/worker.go` — image dispatch hook routes BEFORE chat-streaming whitelist, parallel to audio
- MOD `internal/jobs/worker_test.go` — `TestIsStreamableOperation_RejectsNonStreamable` comment updated per Fix #7
- MOD `internal/api/jobs_handler.go` — `validateImageGenInput` (handler-level chunking rejection + prompt 1..32K + n 1..4 + response_format url|b64_json)
- MOD `internal/api/jobs_router_test.go` — +7 image_gen handler tests
- MOD `sdks/python/loreweave_llm/client.py` — `Client.generate_image()` polymorphic over response_format; **/review-impl(BUILD) MED#1 fix**: `n: int | None = None` + `if n is not None` (was `int = 1` + `if n != 1`; prior code silently dropped explicit `n=1`)
- MOD `sdks/python/loreweave_llm/errors.py` — `LLMImageContentPolicy` + `LLMImageGenerationFailed` classes + `_CODE_TO_EXC` entries
- MOD `sdks/python/loreweave_llm/models.py` — `ImageGenDataItem` + `ImageGenResult` pydantic models
- MOD `sdks/python/loreweave_llm/__init__.py` — exports
- NEW `sdks/python/tests/test_image_gen.py` — 11 tests (3 happy/edge + **explicit-n=1 regression-lock** + 2 validation + 2 error-class mapping + 1 from_code regression-lock + 2 pydantic round-trip)
- MOD `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — Phase 5c-α row ✅ shipped + Phase 5c-β image_edit/variation deferred

### `/review-impl` rounds

**Round 1 — DESIGN (BEFORE BUILD).** Caught **0 HIGH + 5 MED + 6 LOW + 1 COSMETIC**. All 12 folded inline before any code was written.

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🟡 MED | Design implied schema/migration/SDK Literal additions; in reality `image_gen` already in 4/5 sync slots from Phase 2b reservation — only schemas new. Design §2.1 table now lists explicit state. |
| 2 | 🟡 MED | Disjoint test missing for image vs streamable + image vs audio. Added `TestImageJobOperations_Disjoint`. |
| 3 | 🟡 MED | Content-policy substring heuristic false-positive vector (prompt echo in error body). Switched to JSON-first `error.code` check; substring fallback only when JSON parse fails. +regression test for the prompt-echo case. |
| 4 | 🟡 MED | Canonical integration guide in sibling repo says "LoreWeave downloads"; we contradict. Accept-and-document as `D-PHASE5C-INTEGRATION-GUIDE-SYNC`. |
| 5 | 🟡 MED | Adapter-level n-cap missing (handler-only). Added `MaxImagesPerJob=4` + `ErrImageInvalidParams` sentinel + adapter pre-check + classifyImageError mapping + 3 invariant tests. |
| 6-11 | 🟢 LOW | Named 8MB cap const; stale test comment touchup; nullable-pointer concern accepted; sync-mode reservation deferred; concrete live-smoke curl block; SDK NEW-model clarity. |
| 12 | 🔵 COSMETIC | Sentinel naming inconsistency (inherited from 5a). Accepted. |

**Round 2 — BUILD output.** Caught **0 HIGH + 1 MED + 4 LOW + 1 COSMETIC**. MED + 2 LOWs fixed inline; 2 LOWs deferred.

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🟡 MED | SDK `if n != 1` silently dropped explicit `n=1` → caller asking for 1 image might get upstream-default-count (>1). Fixed: signature `n: int = 1` → `n: int | None = None`; wire-inclusion `if n is not None`. +regression-lock `test_generate_image_explicit_n_one_sends_on_wire`. |
| 2 | 🟢 LOW | `MaxImageResponseBytes` cap is on decompressed body size (Go auto-decompresses gzip); docstring didn't clarify. Updated comment. |
| 3 | 🟢 LOW | Adapter pre-check ordering collapses multi-error reports to first-fail. Accept-and-document as `D-PHASE5C-MULTI-ERROR-COLLECT`. |
| 4 | 🟢 LOW | Live-smoke `host.docker.internal` doesn't resolve on native Linux Docker. Added `extra_hosts` workaround note in design §7. |
| 5 | 🟢 LOW | 5-place sync test greps source files, not live DB constraint state. Same limitation as Phase 5a/4a-β siblings. Accept-and-document as `D-PHASE5C-LIVE-DB-CONSTRAINT-CHECK`. |
| 6 | 🔵 COSMETIC | Happy-path test asserted "n not in body" for n=1 default — pinned the MED#1 bug. Fixed alongside MED#1. |

### Verify evidence
```
provider-registry-service: go build/vet/test ./...   ALL GREEN
  internal/api:                                       +7 image_gen handler tests
  internal/jobs:                                      +14 image_gen worker tests
  internal/provider:                                  +14 image_gen adapter tests
SDK pytest sdks/python/tests/:                       185 passed (was 174; +11 new)
chat-service pytest:                                 180 passed unchanged (no regression)
grep -rn "operation.*image_gen" services/            wired through 4 callers + worker dispatch
NO DB MIGRATION NEEDED                               image_gen already in CHECK + enum + Literal
                                                     from Phase 2b reservation
```

### What's NEXT for the next agent

**Phase 5d (L)** — `video_gen` adapter + SDK + openapi. Same shape as 5c-α; POSTs to `/v1/video/generations` (singular video per existing video-gen-service contract). No multi-image; no b64_json (videos are too large). New `ImageGenJobTimeout`-equivalent for video (likely 20-30 min for Wan/LTX Video on local backend). Content-policy detection reusable. Reference impl: 5c-α `openai_image.go` + `worker_image.go` + `Client.generate_image` × 1:1 substitution.

**Phase 5e (XL)** — caller migration. Two callers:
- [book-service/internal/api/media.go:449](services/book-service/internal/api/media.go#L449) — Go; calls `/v1/images/generations` directly via http.Client. Needs Go SDK OR thin Go HTTP shim.
- [video-gen-service/app/routers/generate.py:158](services/video-gen-service/app/routers/generate.py) — Python; uses Python SDK (existing).

Phase 5e requires the Go SDK question to be settled (build full SDK vs. inline shim). Big decision.

**Phase 5f (M)** — `services/video-gen-service/` deletion. Remove BFF + compose entry + api-gateway-bff `/v1/video-gen/*` routes. FE switches to calling unified gateway via SDK or BFF facade. After this: unified-gateway invariant fully realized for chat + extraction + translation + audio + image + video.

**Open deferred items (5c-α):**
- `D-PHASE5C-INTEGRATION-GUIDE-SYNC` — cross-repo PR to update sibling guide
- `D-PHASE5C-NULLABLE-IMAGE-FIELDS` — Quality/Style/Background empty-string-omit semantics
- `D-PHASE5C-SYNC-IMAGE-GEN` — no `POST /v1/llm/jobs/sync` facade
- `D-PHASE5C-LIVE-SMOKE` — manual post-merge against local-image-generator-service:8700
- `D-PHASE5C-RESULT-SIZE-METRIC` — DB growth from b64_json results
- `D-PHASE5C-MULTI-ERROR-COLLECT` — adapter pre-checks fail-first (vs. collect-and-return)
- `D-PHASE5C-LIVE-DB-CONSTRAINT-CHECK` — source-grep doesn't verify live DB constraint
- `D-PHASE5C-DECOMPRESSED-CAP-DOCSTRING` — clarified inline; track if gzip-friendly upstream surfaces

**Read in this order:**
1. `docs/sessions/SESSION_PATCH.md` — full state (top entry = this cycle)
2. `docs/03_planning/LLM_PIPELINE_PHASE5C_DESIGN.md` — design + 12 /review-impl fixes
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — Phase 5c-α row + 5d/5e/5f preview
4. This handoff file

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` confirm closed
2. For Phase 5d: `python scripts/workflow-gate.py size L 12 7 1` then `phase clarify`
3. Reference impl: 5c-α at HEAD `12fe6273` — duplicate the pattern with `video_gen` operation

---

## Session 55 cycle 1 — Phase 5b · chat-service voice migration + audio proxy retirement + bytes-mode STT · /review-impl rounds (DESIGN: 3 HIGH + 7 MED + 5 LOW + 1 COSMETIC all fixed inline; BUILD: 0 HIGH + 2 MED + 4 LOW + 1 COSMETIC, 2 MED fixed inline)

**What shipped:** chat-service voice path migrated off `/internal/proxy/v1/audio/*` onto the unified LLM gateway via `loreweave_llm` SDK. Scope expanded during CLARIFY (M → XL) to add a bytes-mode multipart STT submit on `/v1/llm/jobs` so chat-service skips the MinIO+presigned-URL roundtrip; SDK `transcribe()` made polymorphic over `str|bytes|bytearray|memoryview`; 3 new SDK audio exception classes for the 3 audio gateway codes; audio paths now 410-Gone via `isDeprecatedProxyPath` deny-list; 3 proxy_integration_test.go placeholder-using tests rewritten to synthetic `v1/responses` path (preserves K17.2a + 4MiB cap + auth-header forward regression-locks).

**Files (20 — 18 MOD + 2 NEW)**:
- NEW `docs/03_planning/LLM_PIPELINE_PHASE5B_DESIGN.md` (DESIGN + PLAN doc, status SHIPPED after BUILD)
- MOD `contracts/api/llm-gateway/v1/openapi.yaml` — `SubmitSttBytesRequest` schema + `multipart/form-data` request body variant on both `/v1/llm/jobs` and `/internal/llm/jobs`; SttInput JSON-mode description cross-refs bytes mode; 413 + 415 responses added
- MOD `internal/provider/adapters.go` — `TranscribeInput +AudioBytes/+ContentType`; `ErrTranscribeInputInvalid` sentinel
- MOD `internal/provider/openai_audio.go` — exactly-one pre-check using `hasURL == hasBytes` with `hasBytes := len(input.AudioBytes) > 0` (treats zero-length non-nil slice as "not set"); bytes branch skips `fetchAudioURL`
- MOD `internal/provider/adapters_audio_test.go` — +6 tests (bytes happy + adapter-level oversize + ExactlyOne_BothSet + ExactlyOne_BothEmpty + ZeroByteSliceTreatedAsNotSet + ogg-content-type-ext)
- MOD `internal/jobs/worker_audio.go` — `Worker.ProcessAudioInline` bytes-mode entrypoint (goroutine-closure handoff; no DB persistence of bytes); `classifyAudioError` extended with `ErrTranscribeInputInvalid → LLM_INVALID_REQUEST`
- MOD `internal/jobs/worker_audio_test.go` — +2 tests (ErrTranscribeInputInvalid direct + wrapped)
- MOD `internal/api/jobs_handler.go` — `SttMaxAudioBytes`/`sttMultipartOverhead` consts; `mime.ParseMediaType` dispatch in `doSubmitJob`; new `doSubmitSttMultipart` handler with `http.MaxBytesReader` cap + `ParseMultipartForm` + chunking-field rejection + 0-byte audio reject + empty-Content-Type reject + explicit field-name diagnostic + goroutine spawn calling `ProcessAudioInline`
- MOD `internal/api/jobs_router_test.go` — +8 multipart tests (ValidationPasses + CaseInsensitiveContentType + Oversize → 413 + WrongOperation → 400 + ChunkingFieldRejected → 400 + WrongFileFieldName → 400 + ZeroByteAudio → 400 + EmptyContentType → 400); `buildSttMultipartRequest` helper
- MOD `internal/api/server.go` — `isDeprecatedProxyPath` deny-list extended with `v1/audio/transcriptions` + `v1/audio/speech`; docstrings updated
- MOD `internal/api/proxy_deprecation_test.go` — 3 audio cases flipped `false → true` + audio-dotdot-bypass + audio-suffix-not-prefix cases
- MOD `internal/api/proxy_integration_test.go` — 8 placeholder-using tests swapped to synthetic `v1/responses`; `TestDoProxyNonJSONPassthrough` DELETED; `TestDoProxyAudioPathsNotDeprecated` REMOVED (flipped audio rows added to `TestDoProxyDeprecatedPathsReturn410`)
- MOD `internal/api/proxy_router_test.go` — line 111 audio→responses path swap (disambiguated as route-mechanic test per Fix #10)
- MOD `sdks/python/loreweave_llm/client.py` — polymorphic `transcribe(audio: str|bytes|bytearray|memoryview, content_type=None)`; new `_submit_stt_url` + `_submit_stt_bytes` private helpers; `_submit_stt_bytes` coerces bytearray/memoryview → bytes (httpx multipart only accepts str/bytes); `_raise_http_error` consults `from_code` on 4xx so audio codes surface as their dedicated classes
- MOD `sdks/python/loreweave_llm/errors.py` — `LLMAudioTooLarge` + `LLMAudioFetchFailed` + `LLMAudioURLDisallowed` classes + 3 entries in `_CODE_TO_EXC`
- MOD `sdks/python/loreweave_llm/__init__.py` — exports
- MOD `sdks/python/tests/test_audio.py` — +7 tests (bytes_happy + bytearray + memoryview + bytes_without_content_type → LLMInvalidRequest + oversize → LLMAudioTooLarge + rejects_unsupported_type + regression-lock asserting audio codes have specific classes via `from_code`)
- MOD `services/chat-service/app/services/voice_stream_service.py` — drop `httpx` from voice path; `_new_llm_client(user_id)` per-call factory; `_transcribe_audio` uses SDK bytes mode; `_generate_tts_chunks` uses SDK `stream_tts` + re-emits `AudioChunkEvent` as existing FE envelope (sentenceIndex/chunkIndex/data/final); DELETE dead `provider.resolve()` calls in both `voice_stream_response` AND `generate_tts_for_message`
- NEW `services/chat-service/tests/test_voice_no_dead_resolution.py` — 3 grep-lock tests (provider.resolve banned + httpx import banned in voice path + SDK Client imported)
- MOD `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — Phase 5b row marked ✅ shipped with full final-shape description

### `/review-impl` rounds

**Round 1 — DESIGN doc (BEFORE BUILD).** Caught **3 HIGH + 7 MED + 5 LOW + 1 COSMETIC**. All 16 folded inline into design before any code was written.

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🔴 HIGH | 25MB cap mechanism unspecified — would produce 400 not 413. Spec'd `http.MaxBytesReader(w, r.Body, cap+overhead)` BEFORE `ParseMultipartForm` + catch `*http.MaxBytesError` → 413. |
| 2 | 🔴 HIGH | Adapter pseudocode contradicted "exactly one" rule — `switch case AudioBytes != nil` silently preferred bytes when both set. Added `hasURL == hasBytes` pre-check with new `ErrTranscribeInputInvalid` sentinel BEFORE the bytes-vs-URL branch. |
| 3 | 🔴 HIGH | SDK had no `LLMAudioTooLarge`/etc. classes — `from_code` was falling through to generic `LLMError` for the 3 audio codes. Added 3 classes + registered in `_CODE_TO_EXC`. |
| 4 | 🟡 MED | Content-Type dispatch needed `mime.ParseMediaType` (RFC-conformant) instead of naive `strings.HasPrefix`. |
| 5 | 🟡 MED | SDK isinstance must include `memoryview` for numpy/sounddevice idioms. |
| 6 | 🟡 MED | DELETE /v1/llm/jobs/{id} can't reach the worker goroutine; 25MB RAM pinned for up to SttJobTimeout=5min per cancelled job. **Accept-and-document** as `D-PHASE5B-CANCEL-NO-OP-AUDIO-RAM`. |
| 7 | 🟡 MED | Deleting `TestDoProxyRewritesJSONModelField` would silently retire K17.2a model-name-rewrite coverage. Rewrote to use synthetic `v1/responses` instead of delete. |
| 8 | 🟡 MED | Same for `TestDoProxyBodyTooLargeRejected` (4MiB body cap). Rewrote. |
| 9 | 🟡 MED | Per-call SDK Client instantiation pattern (matches sibling `stream_service.py:68`) not honored in design. Aligned. |
| 10 | 🟡 MED | proxy_router_test.go:111 disambiguation needed (route-mechanic vs audio-specific). Classified as route-mechanic → rewrote to synthetic path. |
| 11-15 | 🟢 LOW | Dead `tts_model_name` resolution; chunking-field rejection; field-name diagnostic; Q5 conditional phrasing; T18 SESSION_PATCH same-commit rule. All folded into design + build plan. |
| 16 | 🔵 COSMETIC | Sequence diagram path note (`/internal/llm/jobs` vs `/v1/llm/jobs`). Clarified. |

**Round 2 — BUILD output (post-coding).** Caught **0 HIGH + 2 MED + 4 LOW + 1 COSMETIC**. Both MEDs fixed inline.

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🟡 MED | 0-byte audio (non-nil empty `[]byte{}` from `io.ReadAll` on empty multipart part) silently passed through to OpenAI as 0-byte file → confusing LLM_UPSTREAM_ERROR. Added `if len(audioBytes) == 0 → 400` at handler; adapter `hasBytes` switched from `!= nil` to `len(...) > 0`. +1 handler test + 1 adapter test. |
| 2 | 🟡 MED | Empty per-part Content-Type silently defaulted to `audio.wav` filename → OpenAI Whisper misdecode. Added `if contentType == "" → 400` at handler. +1 handler test. |
| 3-6 | 🟢 LOW | Base64-string heuristic + cross-coded HTTP routing + panic-recovery + E2E closure test. All **accept-and-document** as `D-PHASE5B-*` deferred items. |
| 7 | 🔵 COSMETIC | JSON-mode vs multipart-mode chunking-decode ordering style divergence. Accept. |

### BUILD-time surprises (2 caught & fixed during BUILD)

- httpx's multipart writer (`_multipart.py::FileField.render_data`) only handles `str`/`bytes` natively — `bytearray`/`memoryview` fall through to its `.read()` branch and `AttributeError`. Coerce to bytes in `_submit_stt_bytes` (loses zero-copy for memoryview but the alternative is no support).
- SDK's `_raise_http_error` was raising generic `LLMInvalidRequest` for 4xx with audio codes (not using `from_code`). Routed via `from_code` on 4xx with defensive fallback when `from_code` returns base `LLMError`.

### Verify evidence
```
provider-registry-service: go build/vet/test ./...   ALL GREEN
  internal/api:                                       0.806s pass
  internal/chunker:                                   0.286s pass
  internal/jobs:                                      3.202s pass (+2 audio tests)
  internal/provider:                                  0.281s pass (+6 audio tests)
SDK pytest sdks/python/tests/:                       174 passed (was 167; +7 new)
chat-service pytest services/chat-service/tests/:    180 passed (was 177; +3 lock tests)
voice_stream_service.py httpx imports:               0 (was 1)
grep -rn "/internal/proxy/v1/audio" services/        only 2 docstring/comment refs
                                                     (no production code paths)
```

### What's NEXT for the next agent

**Phase 5c (deferred · sized TBD)** — `image_gen` adapter when the first caller arrives in monorepo. Likely candidates: video-gen-service or knowledge-service's wiki-illustration pipeline (per `docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md`).

**Phase 6a/b/c** — gateway rate-limit + quota enforcement (per refactor plan §6). Phase 6 worker-context hardening would close `D-PHASE5B-CANCEL-NO-OP-AUDIO-RAM`.

**Open deferred items added this cycle:**
- `D-PHASE5B-CANCEL-NO-OP-AUDIO-RAM` — DELETE /v1/llm/jobs/{id} doesn't cancel worker goroutine (25MB × 5min RAM)
- `D-PHASE2C-AUDIO-STAGING` — goroutine-closure breaks under RabbitMQ migration; need MinIO staging
- `D-PHASE5B-SSRF-GUARD-DEAD-CODE` — URL-mode STT has zero production callers; consider removing
- `D-PHASE5B-BASE64-STRING-HEURISTIC` — SDK could detect base64-encoded strings passed as `audio=` to improve error
- `D-PHASE5B-CROSSCODED-HTTP-ROUTING` — defensive cross-check from_code class vs HTTP status bucket
- `D-PHASE5B-E2E-CLOSURE-TEST` — wired-up integration test for handler→worker→adapter argument-passing
- `D-PHASE5B-EMPTY-CONTENT-TYPE-ACCEPTANCE` — consider auto-detect from magic bytes if caller demand surfaces
- `D-PHASE5A-LIVE-SMOKE` still open — pending manual post-merge live test with OpenAI BYOK whisper-1 + tts-1 against chat-service voice in browser

**Read in this order:**
1. `docs/sessions/SESSION_PATCH.md` — full state (top entry = this cycle)
2. `docs/03_planning/LLM_PIPELINE_PHASE5B_DESIGN.md` — design + plan + 7 final-shape sections
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — Phase 5b row marked shipped + Phase 5c/6 preview
4. This handoff file

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` confirm closed
2. For Phase 5c (when caller appears): `python scripts/workflow-gate.py size L 8 5 1` then `phase clarify`
3. Pre-flight: identify the new image_gen caller before writing the design

---

## Session 54 cycle 1 — Phase 5a · audio adapter (STT + TTS) · /review-impl caught 1 HIGH + 2 MED + 4 LOW (all HIGH/MED + 1 LOW fixed inline)

**What shipped:** Gateway gains first-class audio operations on the unified contract:
- **STT** via `POST /v1/llm/jobs` (`operation=stt` → `adapter.Transcribe` → `SttResult{text, language, duration_ms}`)
- **TTS** via `POST /v1/llm/stream` (`operation=tts` → `adapter.Speak` → SSE `audio-chunk` frames)
- OpenAI-only adapter — Anthropic/Ollama/LM Studio return `ErrOperationNotSupported`
- SDK gains `Client.transcribe()` + `Client.stream_tts()`
- `image_gen` DEFERRED to 5c (no caller); 410-Gone audio carve-out for `/internal/proxy/v1/audio/*` PRESERVED for 5b
- Backward-compat: omitted `operation` on `/v1/llm/stream` defaults to `"chat"` (regression-locked)

**Files (19 in feat commit + 1 in HEAD backfill commit)**:
- NEW `docs/03_planning/LLM_PIPELINE_PHASE5A_DESIGN.md` (DESIGN + PLAN doc)
- MOD `contracts/api/llm-gateway/v1/openapi.yaml` — StreamRequest `oneOf` [ChatStreamRequest, TtsStreamRequest] + AudioChunkEvent + Tts/Stt schemas
- MOD `internal/provider/adapters.go` — Adapter interface +Transcribe/Speak + types + sentinels (ErrOperationNotSupported, ErrAudioFetchFailed, ErrAudioTooLarge, ErrAudioURLDisallowed)
- NEW `internal/provider/openai_audio.go` — OpenAI Transcribe (multipart `verbose_json`) + Speak (4KB-streamed `/v1/audio/speech`); fetchAudioURL with 30s inner timeout + SSRF guard via injectable `audioURLResolver`
- NEW `internal/provider/adapters_audio.go` — Anthropic/Ollama/LM Studio stubs
- NEW `internal/provider/adapters_audio_test.go` — 17 tests (4 stub locks + 9 Transcribe + 4 Speak)
- MOD `internal/jobs/worker.go` — `audioJobOperations` map + tts defensive-reject + processAudioJob route
- NEW `internal/jobs/worker_audio.go` — processAudioJob + runSttJob with `SttJobTimeout=5min` + classifyAudioError with full typed-error matrix
- NEW `internal/jobs/worker_audio_test.go` — 17 tests (3 whitelist + 1 disjoint + 1 source-grep + 12 classify cases)
- MOD `internal/api/jobs_handler.go` — tts → 400 `LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS`; validation reordered before subsystem-503
- MOD `internal/api/jobs_router_test.go` — +2 tests (tts rejected + stt accepted)
- MOD `internal/api/stream_handler.go` — streamRequest.Operation + Input fields; doLlmStream branches on operation; streamTts + classifySpeakErrorCode helpers + ctx-canceled skip
- NEW `internal/api/stream_handler_test.go` — 10 tests (5 validation + 5 classifySpeakErrorCode)
- MOD `sdks/python/loreweave_llm/models.py` — AudioChunkEvent + Tts/Stt models + StreamEvent union widening
- MOD `sdks/python/loreweave_llm/client.py` — `_stream_inner` factor + `stream_tts` + `transcribe` + `_dispatch_event` audio-chunk wiring
- MOD `sdks/python/loreweave_llm/__init__.py` — exports
- NEW `sdks/python/tests/test_audio.py` — 7 tests
- MOD `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — 5a row ✅ shipped + 5c image_gen deferred
- MOD `docs/sessions/SESSION_PATCH.md` — cycle entry

### `/review-impl` round (Phase 5a) — caught 1 HIGH + 2 MED + 4 LOW; HIGH + 2 MED + 1 LOW fixed inline

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🔴 HIGH | runSttJob had NO timeout (worker spawned with `bgCtx := context.Background()`; `invokeClient` has no http.Timeout) — slow audio_url server could pin a goroutine indefinitely. Fixed via `SttJobTimeout = 5*time.Minute` + 30s inner `audioFetchTimeout` on DNS+fetch; `LLM_TIMEOUT` distinct from `LLM_CANCELLED` in classifyAudioError. |
| 2 | 🟡 MED | SSRF — only http/https scheme was guarded; `http://localhost:8080/admin` and `http://169.254.169.254/iam/...` were reachable. Fixed via `isDisallowedIP` (loopback + private + link-local + unspecified + multicast) + DNS pre-resolve via testable `audioIPLookuper` interface + `ErrAudioURLDisallowed` sentinel + LLM_AUDIO_URL_DISALLOWED code + 4 regression-lock tests. |
| 3 | 🟡 MED | Upstream non-2xx wrapped as opaque `fmt.Errorf("upstream status %d: %s")` losing retry-eligibility info. Fixed by routing both Transcribe and Speak through existing `ClassifyUpstreamHTTP` + `parseRetryAfter` (returns typed `*ErrUpstreamRateLimited`/`*ErrUpstreamPermanent`/`*ErrUpstreamTransient`); classifyAudioError + new classifySpeakErrorCode map typed errors → LLM_RATE_LIMITED / LLM_AUTH_FAILED (401/403) / LLM_UPSTREAM_ERROR. |
| 4 | 🟢 LOW | SDK stream_tts silently swallows unexpected events on tts stream. **Accepted + documented** as D-PHASE5A-SDK-TTS-EVENT-FILTER. |
| 5 | 🟢 LOW | streamTts wrote misleading SSE error frame on caller-disconnect (ctx canceled). Fixed: skip when `errors.Is(err, context.Canceled/DeadlineExceeded)`. |
| 6 | 🟢 LOW | openapi `AudioChunkEvent.required: [event,...]` but wire JSON omits `event` field. Pre-existing pattern (TokenEvent/UsageEvent same shape). **Accepted + documented** as D-PHASE5A-OPENAPI-EVENT-FIELD. |
| 7 | 🟢 LOW | SDK transcribe transient_retry_budget=0 hardcoded — caller can't override. Doc'd in docstring as "avoid double-charge BYOK". **Accepted + documented** as D-PHASE5A-SDK-TRANSCRIBE-RETRY-BUDGET. |

### Verify evidence
```
go build ./...:                       clean
go vet ./...:                         clean
go test -count=1 ./...:               ALL GREEN
  internal/api:                       2.6s pass
  internal/chunker:                   7.4s pass
  internal/jobs:                      4.5s pass (17 audio tests new)
  internal/provider:                  1.4s pass (17 audio tests new)
SDK pytest sdks/python/tests/:        167 passed (was 160; +7 new)
chat-service pytest:                  177 passed, 0 failed (regression baseline)
410-Gone audio carve-out regression:  TestDoProxyAudioPathsNotDeprecated still passes
```

### What's NEXT for the next agent

**Phase 5b (M)** — chat-service voice migration off `/internal/proxy/v1/audio/*` onto the new contract. Per [LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md §5](../03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md):

1. `services/chat-service/app/services/voice_stream_service.py`:
   - `_transcribe_audio`: upload audio bytes to MinIO + generate pre-signed URL (60s TTL) + call `Client.transcribe(audio_url, model_source, model_ref, language)` instead of httpx → `/internal/proxy/v1/audio/transcriptions`
   - `_generate_tts_chunks`: replace with `async for ev in Client.stream_tts(text, voice, ...)` → re-emit each AudioChunkEvent as the Vercel AI SDK envelope frame the FE consumes
2. Drop `httpx` import from voice path; tests mock SDK with `httpx.MockTransport`
3. After grep zero callers of `/internal/proxy/v1/audio/*`:
   - Remove audio carve-out from `isDeprecatedProxyPath`'s allowlist in `services/provider-registry-service/internal/api/server.go`
   - Drop the audio paths from `doProxy` whitelist
   - Drop `TestDoProxyAudioPathsNotDeprecated` (no longer guarding anything)
   - Replace with regression-lock asserting audio paths NOW return 410-Gone like the other deprecated paths

**Reference impl**: this cycle's `stream_tts` SDK pattern matches the existing `stream` chat pattern — Phase 5b is a 1:1 callsite swap with the FE wire-envelope re-emission as the only nuance.

**Pre-flight checks for 5b**:
- `grep -rn "/internal/proxy/v1/audio" services/` should show only chat-service + provider-registry-service (the migration target + the gateway-side handler)
- `python -m pytest services/chat-service/tests/ -q` baseline 177/177 must hold before any change

**Phase 5b est size**: M (files ≈5: voice_stream_service + tests + server.go + isDeprecatedProxyPath + audio fixture cleanup)

**Deferred items added this cycle**:
- D-PHASE5A-STREAM-INTEGRATION-TESTS — deeper /v1/llm/stream tests (auth+creds+adapter+SSE wire) need DB pool; defer to Phase 6 or whenever live smoke uncovers a gap
- D-PHASE5A-LIVE-SMOKE — manual post-merge: register OpenAI BYOK whisper-1 + tts-1 → curl stt + tts via `/internal/llm/*` → confirm `text` non-empty + audio bytes playable
- D-PHASE5A-LMSTUDIO-WHISPER — LM Studio whisper.cpp adapter optional follow-up if user requests
- D-PHASE5A-SDK-TTS-EVENT-FILTER — SDK stream_tts silently swallows unexpected events (accept+document)
- D-PHASE5A-SDK-TRANSCRIBE-RETRY-BUDGET — caller can't override hardcoded budget=0 (accept+document)
- D-PHASE5A-OPENAPI-EVENT-FIELD — wire omits `event` field that schema declares required (pre-existing pattern, accept)
- **5c image_gen adapter** — when first caller appears in monorepo

**Read in this order:**
1. `docs/sessions/SESSION_PATCH.md` — full state (top entry = this cycle)
2. `docs/03_planning/LLM_PIPELINE_PHASE5A_DESIGN.md` — Phase 5a design + plan + §8 preview of 5b
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — Phase 5 row + 5c deferral context
4. This handoff file

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` confirm closed
2. For 5b: `python scripts/workflow-gate.py size M 5 3 1` then `phase clarify`
3. Pre-flight: `grep -rn "/internal/proxy/v1/audio" services/` to baseline caller set

---

## Session 53 cycle 4 — Phase 4a-β · relation/event/fact extractors migrated · /review-impl caught 7 issues (all 6 actionable fixed inline)

## Session 53 cycle 4 — Phase 4a-β · relation/event/fact extractors migrated · /review-impl caught 7 issues (all 6 actionable fixed inline)

**What shipped:** All 3 remaining Pass 2 extractors (relation/event/fact) now route through unified LLM gateway with the same SDK + chunking + system+user prompt + tolerant-parser pattern as entity extractor. Gateway gains `fact_extraction` operation + `factKey` aggregator + 2 mid-cycle bug fixes (validJobOperations + DB CHECK constraint). **Phase 4a-α tier COMPLETE**: all 4 Pass 2 extractors uniformly migrated.

**24 files** across gateway/contracts/ks-svc/SDK/tests. Reference impl: this cycle's 3 extractor migrations follow entity extractor's 4a-α + followup pattern verbatim. Live smoke verified: `entities=5, relations=5, events=2, facts=2` — all 4 ops complete end-to-end against qwen3.6-35b-a3b.

### `/review-impl` round 4 — caught 7 issues, all 6 actionable fixed inline

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🟡 MED | factKey docstring claimed "polarity contradictions surface as separate rows" but actually merges → corrected docstring + test name + cross-ref to D-PHASE6-FACT-POLARITY-IN-KEY |
| 2 | 🟡 MED | mergeKnownKeys silently overwrote non-null with null when winner had null value (data loss for fact subject + entity evidence_passage_id) → fix prefers loser-non-null + 2 regression-lock tests |
| 3 | 🟡 MED | 5-place sync invariant (worker / API / DB CHECK / openapi / SDK Literal) only locked worker↔API → widened test to grep openapi.yaml + migrate.go + jobs_handler.go in one Go test |
| 4 | 🟢 LOW | Multi-chunk only verified at unit-test level for entity → 3 NEW per-extractor multi-paragraph chunking-invariant tests |
| 5 | 🟢 LOW | Null-enum cases not tested → `kind=None` / `type=None` added to drops_malformed tests |
| 6 | 🟢 LOW | Duplicate `import pytest` in appended sections → cleaned |
| 7 | 🔵 COSMETIC | Test naming clarity | Skip |

### Mid-cycle bugs caught + fixed during BUILD
- jobs_handler.go `validJobOperations` rejected fact_extraction → fixed + locked
- DB CHECK constraint on `llm_jobs.operation` rejected fact_extraction insert → additive ALTER migration

### Verify evidence
```
gateway:  go test ./internal/... → ALL GREEN
sdk:      pytest tests/ → 37 passed in 0.32s
ks-svc:   pytest tests/unit/ → 1633 passed in 10.99s (was 1611 cycle-3 baseline; +22)
live smoke: 4/4 ops completed (no chunk_errors)
```

### What's NEXT for the next agent

**4a-γ (L)** — migrate `regenerate_summaries.py` + `routers/public/summaries.py` + `routers/internal_summarize.py` to use SDK with `chat` operation (no chunking — summaries fit single call). Reference impl: 4a-β pattern × 3 sites.

ADR §6 Q7 to resolve in 4a-γ CLARIFY: does on-demand FE summarize benefit from `/v1/llm/stream` (P1) instead of `/v1/llm/jobs` (P2)? If yes, split 4a-γ into γ1 (regen scheduler → jobs) + γ2 (FE summarize → stream).

**Deferred items added in cycles 2-4:**
- D-PHASE6-XCHUNK-PRIMING — cross-chunk known_entities priming (cycle 3 MED#1)
- D-PHASE6-FACT-POLARITY-IN-KEY — adding polarity to factKey (cycle 4 MED#1)
- D-PHASE6-AGGREGATOR-NULL-MERGE — mostly mitigated by MED#2 fix; track residual for parallel-chunk aggregator design

**Read in this order:**
1. `docs/sessions/SESSION_PATCH.md` — full state
2. `docs/03_planning/KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md`
3. This handoff file
4. **Reference for 4a-γ**: Phase 4a-β at HEAD `<this-commit>` — extractor pattern; summaries are simpler (no `entities` param, no chunking)

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` confirm closed
2. For 4a-γ: `python scripts/workflow-gate.py size L 6 4 1` then `phase clarify`
3. Live smoke target: `019dc738-a6b7-7bff-b953-b47868ae7db0` (qwen3.6-35b-a3b for `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`)

---

## Session 53 cycle 3 — Phase 4a-α-followup · chunked entity extraction LIVE

## Session 53 cycle 3 — Phase 4a-α-followup · chunked entity extraction LIVE

**What shipped:** 5 files restructure entity prompt as system+user + re-enable `ChunkingConfig(strategy='paragraphs', size=15)`. Closes /review-impl cycle 2 HIGH#1 (chunking-shreds-combined-prompt) end-to-end. Live smoke on Speckled Band first 30 paragraphs (10854 chars) → gateway dispatches **2 sequential chunks** → **34 deduped entities** → no `chunk_errors[]`. **The original-complaint cycle (qwen3.6-35b-a3b on 13K-token chapters) is now FULLY supported.**

**Files (5)**:
- NEW `entity_extraction_system.md` — system-only template (instructions + KNOWN_ENTITIES + rules + examples) with chunking-self-contained directive; NO `{text}` placeholder
- MOD `llm_prompts/__init__.py` — PromptName Literal +'entity_system' + _load_raw mapping
- MOD `llm_entity_extractor.py` — SDK path now sends `[{role:system,content:system_prompt},{role:user,content:text}]` with chunking re-enabled; legacy K17.2 combined-template path preserved
- MOD `test_llm_entity_extractor.py` — assert chunking + 2-message structure + 2 new regression-lock tests
- MOD `test_llm_prompts.py` — TEXT_BEARING_PROMPT_NAMES skips entity_system + 2 entity_system-dedicated tests + 1 silent-drop regression-lock

### `/review-impl` round 3 — caught 1 MED + 3 LOW + 1 COSMETIC; all 4 actionable findings fixed inline

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| 1 | 🟡 MED | Cross-chunk discovered-entity priming gap — system message KNOWN_ENTITIES preserved across chunks but entities discovered in chunk N NOT propagated to chunk N+1 prompt; "Helen Stoner" in chunk 0 + "Miss Stoner" in chunk 1 → 2 distinct entities | NEW regression-lock test pins current behavior with explicit Phase 6 fix path; deferred D-PHASE6-XCHUNK-PRIMING |
| 2 | 🟢 LOW | Unit tests don't exercise multi-chunk dispatch | NEW test `test_extract_entities_via_llm_client_chunking_invariant_for_multi_paragraph_input` asserts extractor SENDS ChunkingConfig on 30-paragraph input |
| 3 | 🟢 LOW | System prompt's "Chunking note" misleading on single-call path | Wording softened: "may be a chunk OR the entire chapter" + explicit "do NOT caveat" |
| 4 | 🟢 LOW | `load_prompt("entity_system", text=...)` silently drops `text` kwarg | NEW regression test documents the silent-drop gotcha + cross-references intended use site |
| 5 | 🔵 COSMETIC | Example A KNOWN_ENTITIES literal | Skip |

### Verify evidence
```
ks-svc unit tests: 1611/1611 PASS in 10.63s (was 1608; +3 new)
LIVE SMOKE: Speckled Band 30 paragraphs (10854 chars)
  → 2 chunks dispatched sequentially (chunks_done 0→1/2→2/2)
  → 34 deduped entities returned
  → no chunk_errors[]
  → high-confidence proper nouns merged correctly across chunks
```

### What's NEXT for the next agent

**4a-β (L)** — migrate relation/event/fact extractors to the SDK pattern. Same surface as 4a-α (extractor signature + tolerant parser + orchestrator threading) × 3 extractors. Gateway changes:
- Add `fact_extraction` to `JobOperation` enum in [openapi.yaml](contracts/api/llm-gateway/v1/openapi.yaml)
- Add `factKey(subject + predicate + claim)` to gateway's `jsonListAggregator` switch + 5 new aggregator tests
- Worker whitelist already covers entity/relation/event_extraction; +`fact_extraction` to `streamableOperations` map

Knowledge-service changes:
- Restructure relation/event/fact prompts as system+user (mirror entity_extraction_system.md pattern) — system has rules + KNOWN_ENTITIES, user has chapter text only
- 3 extractors get `llm_client | None = None` param + new SDK path branch + tolerant parser
- `pass2_orchestrator` threads `llm_client` to all 4 extractors (legacy `client: ProviderClient` removed from extractor signatures only after 4a-δ)
- ~66 test mocks adjust (3 files × ~22 each)

**Reference impl:** Phase 4a-α at HEAD `6697d8d6` (entity migration) + this cycle's followup pattern. Each extractor follows the same shape.

**5 ADR §6 deferred questions still relevant:**
- Q3 cross-chunk known_entities priming (now D-PHASE6-XCHUNK-PRIMING; document only, fix in Phase 6)
- Q4 polling DB load profile (knowledge_llm_poll_total metric exists; needs measurement)
- Q5 gateway concurrency limit (knowledge_llm_inflight_jobs gauge exists; cap deferred to Phase 6a)
- Q6 fact_extraction prompt template (own vs share with event) — RESOLVE in 4a-β CLARIFY
- Q7 on-demand summarize: P1 stream vs P2 jobs (4a-γ)

**Read in this order to onboard:**
1. `docs/sessions/SESSION_PATCH.md` — full state with cycle metadata at top
2. `docs/03_planning/KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md`
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` §4 Phase 4a sub-cycle rows
4. This handoff file
5. **For 4a-β reference**: `services/knowledge-service/app/extraction/llm_prompts/entity_extraction_system.md` (the system+user split pattern to mirror)

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` to confirm prior cycle closed
2. For 4a-β: `python scripts/workflow-gate.py size L 8 5 1` then `phase clarify`
3. Infra: `docker ps --filter name=infra-` — provider-registry + knowledge-service + LM Studio reachable
4. Live smoke target: `019dc738-a6b7-7bff-b953-b47868ae7db0` (qwen3.6-35b-a3b user_model registered for `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`)

---

## Session 53 cycle 2 — Phase 4a-α BUILD live · /review-impl caught 9 issues all fixed inline

**What shipped:** Knowledge-service entity extraction now routes through the unified LLM gateway end-to-end. Live smoke against qwen/qwen3.6-35b-a3b returned `{Sherlock Holmes/Person, 221B Baker Street/Location, Dr. Watson/Person, Professor Moriarty/Person}` — **the original-complaint cycle that triggered the entire refactor is PROVEN end-to-end through the unified contract.**

**22 files** (gateway 6 + SDK 5 + ks-svc 9 + infra 1 + contracts 1) implementing ADR §5.1 Steps 0-5:
- **Step 0a — gateway worker op-whitelist** (`worker.go:140`): chat/completion/entity_extraction/relation_extraction/event_extraction now route past the gate; isStreamableOperation map + 3 routing tests
- **Step 0b — typed transient errors + gateway-side retry** (`provider/errors.go` NEW): ErrUpstreamRateLimited+Transient+Timeout+Permanent + IsTransientUpstreamError + RetryAfter + ClassifyUpstreamHTTP factory; openCompletionStream + anthropic_streamer classify HTTP status into typed shape; worker.streamWithRetry/streamWithBudget honor Retry-After + 1 retry per /review-impl MED#5 SHARED across chunks (not per-chunk)
- **Step 1 — SDK jobs API** (`sdks/python/loreweave_llm/`): submit_job/get_job/wait_terminal/cancel_job + multi-tenant per-call user_id on jobs AND stream methods; LLMTransientRetryNeededError raised when budget>0; httpx polling 250ms→5s
- **Step 2 — entity extractor migration**: `_extract_via_llm_client` routes via SDK when llm_client param supplied; `chunking=None` per /review-impl HIGH#1 — chunked extraction deferred to 4a-α-followup because current K17.1 prompt as single user message would shred under gateway's `\n\n` chunker; cancelled job RAISES ExtractionError(stage=cancelled) per /review-impl MED#3; tolerant parser drops items missing required fields with metric-bumped reasons
- **Step 3 — knowledge-service wrapper** (`app/clients/llm_client.py` NEW): LLMClient.submit_and_wait owns caller-side retry budget — fixed per /review-impl HIGH#2 to forward budget=1 to SDK so LLMTransientRetryNeededError actually fires + asyncio.sleep on retry_after_s + bumps outcome=transient_retry AND outcome=failed on exhaustion per LOW#7
- **Step 4 — orchestrator** threads llm_client to entity step ONLY; other 3 extractors stay on legacy provider_client until 4a-β
- **Step 5 — cancel-race regression test**: covered at SDK level (test_cancel_race_polling_observes_external_cancel) + extractor level (test_extract_entities_via_llm_client_cancelled_raises_with_stage)

### `/review-impl` round 2 — caught 9 issues, all fixed inline

| # | Sev | Issue | Fix |
|---|-----|-------|-----|
| 1 | 🔴 HIGH | Chunking shreds entity prompt (single user message contains instructions+rules+examples+text inline; gateway splits on `\n\n` → chunks 2..N have NO instructions → quality collapse on 13K-token chapters). My live smoke didn't trigger because input was 1 paragraph. | `chunking=None` + deferred 4a-α-followup that restructures prompt as system+user before re-enabling |
| 2 | 🔴 HIGH | Wrapper transient retry was DEAD CODE — passed budget=0 to SDK so LLMTransientRetryNeededError never fired; K17.3 quality contract (the entire reason ADR §3.3 D3c exists) NOT preserved | Forward budget=1 to SDK + new `test_llm_client_wrapper.py` (6 tests pin REAL retry-loop semantics; previous tests bypassed wrapper by mocking LLMClient directly) |
| 3 | 🟡 MED | Cancelled job conflated with "0 entities found" — orchestrator wrote empty Pass 2 + flipped extraction_jobs to completed, lying to user about cancel | Raise ExtractionError(stage='cancelled') instead of returning [] |
| 4 | 🟡 MED | Client.stream() didn't accept per-call user_id (multi-tenant pattern incomplete) | Mirror jobs methods; +2 SDK tests |
| 5 | 🟡 MED | Worker per-chunk retry budget (9 chunks × 2 attempts = 18 upstream calls under sustained transient errors) | Refactor to streamWithBudget shared-pointer; +2 budget regression tests |
| 6 | 🟢 LOW | openCompletionStream → typed error mapping not unit-tested directly (a regression to fmt.Errorf would silently disable streamWithRetry) | NEW open_completion_stream_test.go — 7 httptest tests pin status→type mapping |
| 7 | 🟢 LOW | knowledge_llm_job_total{outcome="failed"} didn't include exhausted-transient | Bump `outcome="failed"` ALSO on exhaustion |
| 8 | 🟢 LOW | openapi entity_extraction.input description claimed `{text, known_entities, language}` but real wire shape is chat-message | Updated description to clarify all extraction ops use chat-message wire; operation enum picks aggregator only |
| 9 | 🔵 COSMETIC | Unreachable `assert last_job is not None` | Auto-fixed by HIGH#2 refactor |

### Test deltas
- **Gateway:** +15 (8 worker_test.go: 3 whitelist + 5 retry + 2 shared-budget; 7 open_completion_stream_test.go httptest typed-error mapping)
- **SDK:** +21 (19 test_client_jobs.py: submit/get/wait/cancel/budget/cancel-race/multi-tenant; 2 test_client_stream.py: stream user_id)
- **knowledge-service:** +12 (6 test_llm_entity_extractor.py SDK-path; 6 test_llm_client_wrapper.py wrapper REAL retry semantics)

### Verify evidence
```
gateway:  go test ./internal/... → ALL GREEN
sdk:      pytest tests/ → 37 passed in 0.34s
ks-svc:   pytest tests/unit/ → 1606 passed in 10.53s
                              (19 pre-existing host-env failures unrelated; confirmed via git stash on b2f577e)
live smoke (post-fixes): qwen3.6-35b-a3b entity_extraction → 1 entity, status=completed
```

### What's NEXT for the next agent

**Two equally-valid next cycles** — pick based on quality-eval priority vs migration-velocity:

**Option A — 4a-α-followup (S/M)**: re-enable chunking by restructuring entity prompt as system+user. Touches `app/extraction/llm_prompts/entity_extraction.md` (split into a system block and a `{text}`-only user block) + `app/extraction/llm_entity_extractor.py` (build messages as `[{role:system, content:instructions}, {role:user, content:text}]` + set chunking=ChunkingConfig(strategy='paragraphs', size=15)). Re-run quality eval on Speckled Band (13K tokens) to validate chunked extraction matches single-call quality. **This is the cycle that finally fixes the original 13K-chapter complaint at production quality.**

**Option B — 4a-β (L)**: migrate relation/event/fact extractors to SDK pattern. Same surface as 4a-α (extractor signature + tolerant parser + orchestrator threading) × 3 extractors. Adds `fact_extraction` to openapi `JobOperation` enum + `factKey(subject+predicate+claim)` to gateway's jsonListAggregator + +5 aggregator tests. Includes the `_build_extraction_messages` consolidation decision (per ADR §5.1 LOW#10) when 3 extractors all need the same helper.

**Recommend Option A first** — closes the original-complaint loop end-to-end before scaling to 3 more extractors. 4a-β can ship after.

**5 ADR §6 deferred questions still open for 4a-β/γ/δ:**
- Q3 cross-chunk known_entities priming (still relevant once chunking re-enabled)
- Q4 polling DB load profile (knowledge_llm_poll_total metric exists; needs measurement)
- Q5 gateway concurrency limit (knowledge_llm_inflight_jobs gauge exists; cap deferred to Phase 6a)
- Q6 fact_extraction prompt template (own vs share with event)
- Q7 on-demand summarize: P1 stream vs P2 jobs (4a-γ)

**Read in this order to onboard:**
1. `docs/sessions/SESSION_PATCH.md` — full state with cycle metadata at top
2. `docs/03_planning/KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md` — 8 sections + 25 subsections + 9-item closing checklist
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` §4 Phase 4a sub-cycle rows
4. This handoff file (you're reading)
5. **For 4a-α-followup**: `services/knowledge-service/app/extraction/llm_prompts/entity_extraction.md` (~135 lines; needs system+user split)

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` to confirm prior cycle closed
2. For 4a-α-followup: size S/M (`size S 3 2 0` then `phase clarify`); for 4a-β: size L (`size L 8 5 1`)
3. Infra: `docker ps --filter name=infra-` — provider-registry + knowledge-service + LM Studio reachable
4. Live smoke target: `019dc738-a6b7-7bff-b953-b47868ae7db0` (qwen3.6-35b-a3b user_model registered for `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`)

---

## Session 53 cycle 1 — Phase 4a ADR DESIGN-first · /review-impl validated 3 HIGH gaps before commit

**Story:** Session opened on the natural Phase-4a-next path identified at session 52 close. Per CLAUDE.md "DESIGN-first cycle (like C16/C17/C18)", shipped a 394-LOC ADR pinning Path C (job-pattern + chunking) over Path A (surface-preserving) and Path B (SDK-direct). 4-cycle slicing 4a-α XL / 4a-β L / 4a-γ L / 4a-δ M bounds the ~407 mock-site test churn at <30% per PR. D1-D7 all resolved with rationale + 8 deferred Qs to BUILD-cycle CLARIFY.

**`/review-impl` paid for itself this cycle.** Initial ADR draft passed self-review and POST-REVIEW summary. User invoked `/review-impl` which re-read actual gateway code (`worker.go:140`, `repo.go Finalize`, `aggregator.go:72`) and caught **3 HIGH** that would have blocked 4a-α BUILD live smoke OR caused silent quality regression on local LLM:
- **HIGH#1**: `worker.go:140` hard-rejects non-chat operations TODAY — ADR §5.1 sketch was unrunnable; aggregator factory wires entity_extraction at line 72 but worker fails the job before reaching `NewAggregator(operation)`. Fix: §2.4 Gateway Gaps section + §5.1 Step 0 ships op-whitelist as 4a-α prereq.
- **HIGH#2**: D3 silently dropped HTTP-retry on transient upstream errors — gateway has zero retries, K17.3 absorbs 1 retry today. Without replacement, every transient LM Studio 502 = chapter-level failure. Fix: D3 split into D3a/b/c — preserve transient-retry via gateway-side single-retry on typed errors + SDK caller-side retry budget=1 bridge until Phase 6b ships proper retry.
- **HIGH#3**: D6 single `llm_job_id UUID NULL` column doesn't fit reality — each chapter extraction submits 4 LLM jobs (entity/relation/event/fact). Fix: revised to reverse-lookup via `llm_jobs.job_meta = {extraction_job_id, role}`; NO new column added.

Plus 6 MED + 3 LOW + 2 COSMETIC. All 12 actionable findings amended in ADR with explicit `/review-impl` cross-references (17 callouts total). 4a-α BUILD reclassified L→XL after gateway prereqs Step 0 added.

### Cycle 1 — C-LLM-PHASE-4A-ADR Phase 4a knowledge-service migration ADR [DOC XL DESIGN-first]

NEW `docs/03_planning/KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md` (394 LOC, 8 numbered sections + 25 subsections, 9-item closing checklist, 8 deferred Qs). MOD `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` §4 (Phase 4a single XL row replaced with 4 sub-cycle rows + ADR cross-link). Decisions baked in: Path C, 4-cycle slice, polling via SDK wait_terminal exp backoff 250ms→5s, sync-saga preserved B1, D3 split with caller-side single-retry bridge, fact_extraction added in 4a-β with factKey=subject+predicate+claim, prompts stay in knowledge-service, reverse-lookup via job_meta, worker-ai untouched. 4a-α Step 0 closes 2 gateway gaps before any consumer code touches new path.

### What's NEXT for the next agent

**4a-α BUILD cycle (XL)** is the immediate next BUILD. Per ADR §5.1 + closing-checklist:

1. **Step 0 gateway prereqs** (ship FIRST):
   - `services/provider-registry-service/internal/jobs/worker.go:140` — replace hard-reject with per-op switch allowing chat / completion / entity_extraction / relation_extraction / event_extraction
   - Adapter typed transient errors (`provider.ErrUpstreamRateLimited`, `ErrUpstreamTransient`, `ErrUpstreamTimeout`) for gateway-side single-retry honoring `Retry-After`
   - +5 worker_test.go tests (per-op routing + transient retry)

2. **Step 1 SDK changes** (`sdks/python/loreweave_llm/`):
   - `submit_job(operation, model_source, model_ref: str, input, chunking, callback, trace_id, job_meta)` — model_ref STAYS str, SDK validates UUID-shape
   - `get_job(job_id) → Job` with `httpx.Timeout(connect=5, read=10, write=5, pool=5)` per-poll
   - `wait_terminal(job_id, *, transient_retry_budget=1)` — exp backoff + raises `LLMTransientRetryNeededError` on `error.code IN {LLM_RATE_LIMITED, LLM_UPSTREAM_ERROR}` for caller-side retry
   - `cancel_job(job_id)`
   - ≥15 unit tests including transient-retry budget logic

3. **Step 2 Entity extractor migration** (`services/knowledge-service/app/extraction/llm_entity_extractor.py`):
   - New `llm_client: LLMClient | None = None` param — legacy `client: ProviderClient | None = None` retained for fallback
   - `for attempt in range(2):` retry loop catching `LLMTransientRetryNeededError`
   - `job_meta={"extraction_job_id": ..., "chapter_id": ..., "role": "entity"}` for D6 reverse-lookup
   - Tolerant parser fields per ADR §5.1 Step 3: required {name, kind, evidence_passage_id} optional {aliases→[], confidence→0.5}

4. **Step 3 pass2_orchestrator** threads `llm_client` to entity step ONLY in 4a-α; other 3 extractors stay on legacy.

5. **Step 4 deps.py** registers new SDK client lifespan singleton.

6. **Cancel-race regression test** mandatory (per ADR §5.5 + /review-impl MED#4): submit job + DELETE mid-flight + assert `extraction_jobs.status="cancelled"` + no Neo4j write.

7. **Live smoke**: Speckled Band 13K-token chapter through `extract_entities` returns N entities via gateway job. Verify against qwen3.6-35b-a3b (the original-complaint model).

**8 deferred Qs from ADR §6 — 4a-α CLARIFY MUST resolve Q1-Q5:**
1. Per-chunk paragraph size for entity_extraction (size=8 vs ~15)
2. wait_terminal per-poll httpx.Timeout shape under live load
3. Cross-chunk known_entities priming (recommend size=15 + measure)
4. Polling DB load profile (add metric `knowledge_llm_poll_total`)
5. Gateway concurrency limit (add metric `knowledge_llm_inflight_jobs{user_id}`)

**4a-β / 4a-γ / 4a-δ** scoped in ADR §5.2-5.4. Each independently green.

**Read in this order to onboard:**
1. `docs/sessions/SESSION_PATCH.md` — full state with cycle metadata at top
2. **`docs/03_planning/KNOWLEDGE_SERVICE_LLM_MIGRATION_ADR.md`** — 8 sections + 25 subsections + 9-item closing checklist + 8 deferred Qs
3. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` §4 Phase 4a sub-cycle rows
4. This handoff file (you're reading)
5. `contracts/api/llm-gateway/v1/openapi.yaml` — JobOperation enum, SubmitJobRequest schema (gateway gap §2.4 noted: enum lists ops the worker doesn't dispatch yet)

**Starting-cycle boilerplate:**
1. `python scripts/workflow-gate.py status` to confirm prior cycle closed
2. Start 4a-α with `python scripts/workflow-gate.py size XL N M K` then `phase clarify` (XL — gateway prereq + SDK + 1 extractor + tests + migration helpers ≥10 files; logic ≥6; 1 side-effect = new SDK API surface)
3. Infra check: `docker ps --filter name=infra-` — provider-registry + postgres + LM Studio reachable
4. For live smoke: `LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1` + qwen3.6-35b-a3b registered as user_model

---

## Session 52 — closed at HEAD `c0420d2` (20 cycles shipped · Phase 1+2+3 TIERS COMPLETE + Phase 1c-anthropic ✅ + Phase 3b-followup ✅)

> **Date:** 2026-04-26 (session 52, closed at 20th cycle / Phase 3b-followup per-op JSON aggregators)
> **HEAD:** `c0420d2` (Phase 3b-followup per-op aggregators; 1c-anthropic @ `2c7c9a2`; max_tokens-policy @ `1ae3158`; 3c worker chunked @ `842e1bf`; 3b multi-chunk agg @ `388d2ac`; 3a chunker @ `5c72133`; 2f FE EventSource @ `141fb01`; 2e SSE bridge @ `2b411a2`; 2d notif consumer @ `83a255a`; 2c RabbitMQ pub @ `9afb5bf`; 2b job lifecycle @ `64ff7d6`; 2a llm_jobs DDL @ `f28f4a3`; 1e lint rule @ `936724b`; 1c-ii chat-svc drops litellm @ `200a794`; 1c-i ReasoningEvent @ `d43d508`; 1b Python SDK @ `58b2024`; 1a Gateway streaming @ `aaff5e1`; 0a OpenAPI spec @ `4d1a1e0`; refactor plan @ `870b683`; pre-plan proxy fix @ `e63f90f`; session 52 prior demo-track HEAD `568cbfd`)

## Session 52 — 20 cycles shipped · **Pivot from extraction quality polish to LLM pipeline architecture refactor** · **Phase 1+2+3 TIERS COMPLETE**

**Pivot story:** session opened intending to "continue C19/C20 extraction quality cycles" against gemma-4-26b-a4b baseline. User asked to register + use `qwen/qwen3.6-35b-a3b` (their strongest local model). Eval timed out at 1500s × 2 retries — I incorrectly concluded "model not viable on this hardware". User pushed back firmly: timeouts on LLM pipelines are the wrong abstraction, system needs unified async + chunking + notification contract. Audit revealed 3 distinct LLM contracts in production (chat-service direct litellm bypass, knowledge-service transparent-proxy, translation-service typed invoke) plus 60s default timeout in knowledge-service mathematically incompatible with thinking-model workloads. Spent the rest of the session shipping the unified-contract refactor end-to-end.

**Highlights:**
- **🎯 Phase 1 tier COMPLETE** (1a Gateway streaming + 1b Python SDK + 1c-i ReasoningEvent + 1c-ii chat-service drops litellm + 1e lint rule). chat-service no longer imports `litellm` or `openai` — gateway invariant from CLAUDE.md restored for streaming code path.
- **🎯 Phase 2 tier COMPLETE** (2a llm_jobs DDL + 2b lifecycle handlers/worker + 2c RabbitMQ publisher + 2d notification-service consumer + 2e SSE bridge + 2f FE EventSource). Full async-job pipeline live end-to-end: provider-registry submit → goroutine streams → DB terminal → RabbitMQ user.<id>.llm.<op>.<status> → notification-service persist + api-gateway-bff SSE → FE bell badge bumps real-time.
- **🎯 Phase 3 tier COMPLETE** (3a chunker primitives + 3b multi-chunk aggregator + 3c worker chunked dispatch). Original user complaint (qwen3.6-35b-a3b on 13K-token chapters) technically unblocked — sequential per-chunk dispatch + JSON-merging aggregators ready for Phase 4a knowledge-service migration.
- **🚀 Deferred regression closed: Phase 1c-anthropic** — Anthropic SSE streamer with thinking_delta → ReasoningEvent for Claude 3.7+ extended thinking. Closes D-PHASE-1C-ANTHROPIC.
- **🚀 max_tokens=0 means omit** — caller policy enforcement at SDK + gateway-handler + adapter (3-layer defense-in-depth) so deep-reasoning tasks let the model decide token budget. Anthropic exception preserved (API requires max_tokens).
- **🚀 Phase 3b-followup per-op JSON aggregators** — final unblocker for Phase 4a. jsonListAggregator merges entity/relation/event JSON outputs across chunks with soft-fail on malformed chunks; without this Phase 4a was blocked because chatAggregator concatenates with `\n\n` producing invalid JSON.
- **18 commits new code + 1 commit refactor plan + 1 commit pre-plan proxy fix = 20 commits total**.
- **~6000+ LOC** new code across provider-registry-service (Go), api-gateway-bff (TS/NestJS), notification-service (Go), chat-service (Python), frontend (React/TS), sdks/python (NEW), contracts/api/llm-gateway (NEW).
- **NEW package `sdks/python/loreweave_llm/`** — first shared SDK in monorepo. Other services consume via `pip install -e ../../sdks/python` from their requirements.txt + Dockerfile multi-stage COPY pattern (chat-service Phase 1c-ii is the reference impl).
- **NEW contract `contracts/api/llm-gateway/v1/openapi.yaml`** — 17 schemas, 6 paths covering POST /v1/llm/stream + POST /v1/llm/jobs + GET/DELETE /v1/llm/jobs/{id} × public/internal pair. spectral lint clean.
- **NEW planning doc `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md`** — 8 sections covering principles, audit findings, target architecture, 7-phase migration plan, 8 user-decision questions Q1-Q8 (all approved with recommended defaults).

### Cycle 20 — C-LLM-AGG-PEROP Phase 3b-followup [BE M] — per-operation JSON aggregators

Final unblocker for Phase 4a. NEW `jsonListAggregator` in `internal/jobs/aggregator.go` parses per-chunk `{<list_field>:[...]}` JSON and merges items by caller-supplied keyFn. Three operation routes: `entity_extraction` (key = name+kind, aliases array gets union semantic on tie), `relation_extraction` (key = subject+predicate+object+polarity), `event_extraction` (key = name+time_cue). Higher confidence wins on tie; soft-fail per chunk so 1/N malformed output doesn't fail the whole job (errors captured in `result.chunk_errors[]`). Insertion-order preserved for deterministic results. **2 bugs discovered + fixed mid-cycle**: (a) `mergeKnownKeys` argument-order swap was making low-confidence existing rows win over higher-confidence new rows; (b) `chunkBuffer` not reset in EndChunk caused Finalize defensive-flush to re-parse already-handled chunks producing duplicate `chunk_errors`. **+8 tests**: Entity merge with alias union, Relation tuple-dedup, Polarity-distinct, Event by name+cue, malformed-chunk soft-fail, missing-list-field error, unchunked single-parse backward-compat. **Files: 2** (aggregator.go + test). **Verify**: jobs pkg 31 tests PASS (+8); api/chunker/provider all green.

### Cycle 19 — C-LLM-ANTHROPIC-STREAM Phase 1c-anthropic [BE M] — Anthropic SSE streamer

Closes deferred regression D-PHASE-1C-ANTHROPIC. Anthropic chat models now stream end-to-end through gateway's `/v1/llm/stream` instead of returning LLM_STREAM_NOT_SUPPORTED. NEW `internal/provider/anthropic_streamer.go` — streamAnthropicSSE parser dispatches per Anthropic event type: message_start captures input_tokens, content_block_delta with text_delta → TokenEvent + thinking_delta → ReasoningEvent (Claude 3.7+ extended thinking), message_delta emits UsageEvent + captures stop_reason, message_stop terminates emitting DoneEvent with mapped finish_reason, ping events filtered, error events surface as canonical StreamErrorEvent + stop. mapAnthropicStopReason translates end_turn|stop_sequence→stop, max_tokens→length, tool_use→tool_calls. openAnthropicStream POSTs `/v1/messages` with `x-api-key` + `anthropic-version: 2023-06-01` headers, forces stream:true. anthropicAdapter.Stream replaces the ErrStreamNotSupported stub; max_tokens 8192 default preserved (API requires). **Files: 3** (anthropic_streamer.go + adapters.go + anthropic_streamer_test.go). **Verify**: provider pkg PASS — 7 new Anthropic tests + existing AnthropicInvoke + adapters/streamer tests all green; live smoke deferred (needs Anthropic API key not configured in dev).

### Cycle 18 — C-LLM-MAXTOKEN-POLICY [BE+SDK M] — max_tokens=0 means omit

User-driven policy clarification: caller-omitted OR caller-zero `max_tokens` means "let the model decide" — must NOT appear in upstream payload. Critical for thinking models where reasoning + answer combined exceeds any reasonable arbitrary cap. **3-layer defense-in-depth**: (1) SDK `to_request_body` drops max_tokens when 0; (2) gateway `stream_handler.go` gate `if *MaxTokens > 0`; (3) adapters' Stream + Invoke methods drop unless > 0. Anthropic Invoke documented exception keeps 8192 default (API requires). **Files: 5** (SDK models.py + tests + stream_handler.go + adapters.go + new max_tokens_policy_test.go with 6 httptest-based tests verifying exact wire bytes).

### Cycle 17 — C-LLM-WORKER-CHUNK Phase 3c [BE L] — worker chunked dispatch

Phase 3 tier complete. Worker now reads chunking config from llm_jobs row, splits last user message via Phase 3a chunker, dispatches per-chunk adapter.Stream calls bracketed by aggregator StartChunk/EndChunk (Phase 3b), reports per-chunk progress. **Sequential dispatch** for MVP — chatAggregator state isn't goroutine-safe across chunks; parallel is Phase 3c-followup or Phase 6. **Files: 5** (chunked_input.go + tests + worker.go + jobs_handler.go + repo.go). **Verify**: live smoke 4-paragraph chunked job with size=2 → 2 chunks dispatched sequentially → progress 0/None → 1/2 → 2/2 → completed; content concatenated with `\n\n` separator; reasoning keeps last chunk per Phase 3b design.

### Cycle 16 — C-LLM-AGG-MULTICHUNK Phase 3b [BE M] — multi-chunk aggregator

chatAggregator gains StartChunk/EndChunk hooks. Per-chunk content+reasoning buffers reset on StartChunk, flushed on EndChunk with chunkSeparator='\\n\\n' between non-empty chunks (counter avoids leading sep + skips empty chunks). Reasoning-keep-last-chunk semantic. Usage SUMMED across chunks. Backward-compat: no Start/End calls = single-chunk Phase 2b behavior identical. **Files: 2**. **Verify**: 14 tests (+5 new) PASS.

### Cycle 15 — C-LLM-CHUNKER Phase 3a [BE M] — chunker primitives

Foundation for >8K-token inputs. NEW `internal/chunker/chunker.go` — Strategy enum (tokens/paragraphs/sentences/none), tiktoken-go cl100k_base for token counting, regex `(?:\\r?\\n\\s*\\r?\\n)+` for paragraphs, `[.!?。！？]+\\s*` for ASCII+CJK sentences. **CJK regex bug discovered + fixed mid-cycle** (original `\\s+|$` requirement failed for CJK which has no inter-sentence whitespace). **Files: 2 + tiktoken-go dep**. **Verify**: 15 chunker tests PASS.

### Cycle 14 — C-LLM-FE-STREAM Phase 2f [FE M] — EventSource subscriber

Phase 2 tier complete. `useNotificationStream` self-contained hook with EventSource + exponential-backoff reconnect (1s→30s cap) + ref-stable onEvent + accessToken-null teardown. NotificationBell drops 30s poll for live SSE; initial unread fetch becomes one-shot. **Files: 4**. **Verify**: vitest 8/8 PASS; tsc clean.

### Cycle 13 — C-LLM-SSE-BRIDGE Phase 2e [BE M] — api-gateway-bff SSE bridge

NEW NotificationsController @Sse('stream') at `/v1/notifications/stream` with JWT-via-query auth. Reuses existing AmqpService that consumes loreweave.events; routes by `event.user_id ?? event.owner_user_id` (back-compat with translation-service AND Phase 2c TerminalEvent). gateway-setup.ts excludes /stream path from upstream proxy filter. **Files: 7**. **Verify**: jest 5/5 PASS; live E2E full chain captured `id:1\\ndata:{full TerminalEvent JSON}` on FE-side curl.

### Cycle 12 — C-LLM-NOTIF-CONSUMER Phase 2d [BE L] — notification-service consumer

Closes the half between provider-registry's RabbitMQ publisher (Phase 2c) and FE EventSource subscription (Phase 2f). Notifications row created automatically for every LLM job terminal transition. NEW `internal/consumer/consumer.go` — durable queue `notification-service.llm-jobs` bound `user.*.llm.#`; `transformTerminalEvent` pure helper builds notifications row args; nack-no-requeue on malformed (poison-message guard) + requeue on transient DB error (at-least-once). **Files: 6**. **Verify**: 6 transform tests PASS; live E2E completed + cancelled flows produce notifications rows with category=llm_job.

### Cycle 11 — C-LLM-JOBS-NOTIFY Phase 2c [BE L] — RabbitMQ terminal-event publisher

Terminal-state events publish to `loreweave.events` topic exchange with exactly-once semantic via rowsAffected gate. NEW `internal/jobs/notifier.go` — Notifier interface + rabbitMQNotifier (amqp091-go) + NoopNotifier fallback. TerminalEvent envelope with RoutingKey = `user.<id>.llm.<op>.<status>`. Worker.finalizeAndNotify helper publishes IFF Repo.Finalize rowsAffected > 0 — race protection prevents duplicate event when cancel beats stream completion. **Files: 11**. **Verify**: live cancel-race regression — 25s wait after cancel confirms queue stays empty (no late completed event after cancel won).

### Cycle 10 — C-LLM-JOBS-LIFECYCLE Phase 2b [BE L] — async job handlers + worker

Submit → 202 with job_id → goroutine drives MarkRunning → adapter.Stream → Finalize → caller polls GET. NEW `internal/jobs/{repo,aggregator,worker}.go`; NEW `internal/api/jobs_handler.go` with 6 handlers (POST/GET/DELETE × JWT/internal pair). Phase 2b cuts: only chat/completion ops; non-chat → LLM_OPERATION_NOT_SUPPORTED. **Bug fixed in cycle**: Repo.Finalize originally had no status guard — goroutine could overwrite cancelled→completed when user cancels mid-stream. Fixed: `WHERE status='running'`. **Files: 7**. **Verify**: 13 new tests; live smoke happy path + cancel race regression.

### Cycle 9 — C-LLM-JOBS-DDL Phase 2a [BE M] — llm_jobs table foundation

NEW `llm_jobs` table appended to provider-registry schemaSQL. 23 columns mirroring openapi Job + SubmitJobRequest verbatim. operation enum (10 values), status enum default 'pending', `expires_at default now()+'7 days'` per Q8. **CHECK `llm_jobs_terminal_consistency` locks the invariant** `status terminal ↔ completed_at NOT NULL` at DB layer. 4 indexes including partial on expires_at WHERE terminal for future Phase 6 sweeper. **Files: 1**. **Verify**: live INSERT verifies CHECK rejects status='completed', completed_at=NULL.

### Cycle 8 — C-LLM-LINT-RULE Phase 1e [INFRA XS] — forbid direct provider-SDK imports

Enforcement gate locking in P3+P4. `scripts/lint-no-direct-llm-imports.sh` greps `services/`+`frontend/` for `(import|from) (litellm|openai|anthropic)` outside allowlist (`services/provider-registry-service/`, `sdks/python/`). Phase 1 COMPLETE. **Verify**: regression-tested by injecting `from litellm import acompletion` in chat-service path → exit 1 with offender output; cleanup → exit 0.

### Cycle 7 — C-LLM-CHAT-MIGRATE Phase 1c-ii [BE L] — chat-service drops litellm

Largest architectural deliverable of Phase 1. chat-service no longer bypasses gateway via direct provider SDK. CLAUDE.md gateway invariant restored for streaming chat. NEW `_stream_via_gateway` helper using SDK; title-gen migrates to SDK accumulation. Drop `_stream_openai_compatible`/`_stream_litellm`/`_resolve_model`. Dockerfile build context shifted to repo root for SDK COPY. requirements.txt drops `litellm>=1.40`. **Bug fixed in cycle**: passing `temperature=gen_params.get('temperature')` overrode pydantic StreamRequest default 0.0 with None → validation error. Fix: kwargs sparsity. **Files: 6 + 4 test files migrated**. **Verify**: chat-service pytest 177/177 PASS; live E2E `POST /v1/chat/sessions/{id}/messages` → 194 reasoning-delta + 6 text-delta = `'\\n\\n{"ok":true}'` zero litellm in path.

### Cycle 6 — C-LLM-REASONING-EVENT Phase 1c-i [BE+SDK M] — ReasoningEvent canonical

Closes silent Phase 1a regression. Discovered via direct LM Studio probe: thinking models stream `delta.reasoning_content` per-token but the parser was DROPPING those chunks (only emitting `delta.content`). NEW `StreamChunkReasoning` kind in canonical envelope. SDK adds ReasoningEvent pydantic class to discriminated union. **Files: 5**. **Verify**: live smoke against qwen3.6 — 146 reasoning chunks + 2 token chunks streamed separately end-to-end.

### Cycle 5 — C-LLM-SDK-PY Phase 1b [SDK L] — Python SDK loreweave_llm

First shared SDK in the monorepo. NEW `sdks/python/loreweave_llm/` package. Client.stream(StreamRequest) → AsyncIterator[StreamEvent]. 2 auth modes (jwt → /v1/llm/stream, internal → /internal/llm/stream + user_id query). httpx.Timeout(None, connect=5, read=120) — no wall-clock cap on whole stream. SSE parser handles event/data/comment lines. Error consistency: HTTP-level + SSE-frame `event: error` both surface as same typed exception via from_code factory. submit_job() stub raises NotImplementedError (Phase 2). **Files: 8**. **Verify**: pytest 14/14 PASS in 0.27s; live smoke against gateway+LM Studio qwen3.6 reconstructed `'\\n\\n{"ok":true}'`.

### Cycle 4 — C-LLM-STREAM-IMPL Phase 1a [BE L] — gateway streaming

First runtime piece of unified contract. NEW `POST /v1/llm/stream` (JWT) + `POST /internal/llm/stream` (X-Internal-Token + user_id query). SSE end-to-end with **no wall-clock timeout**. Closes the gap that forced chat-service to bypass via litellm. NEW `streamer.go` with canonical types + `streamOpenAICompat` parser shared by openai/lm_studio/ollama-compat. Anthropic stub returns ErrStreamNotSupported. NEW `stream_handler.go` with emit closure that JSON-marshals chunk + writes `event: <kind>\\ndata: <json>\\n\\n` + flushes. **Files: 5**. **Verify**: 9 streamer unit tests + live smoke through `/internal/llm/stream` against qwen3.6-35b-a3b emitted 6 token events + 1 done event.

### Cycle 3 — C-LLM-CONTRACT-OAS Phase 0a [DOC M] — OpenAPI spec

NEW `contracts/api/llm-gateway/v1/openapi.yaml` (~740 lines). 17 schemas covering streaming + async jobs + canonical SSE event envelope. Plan Q1-Q8 approved decisions baked in. spectral lint clean (initial run caught 4 nullable+$ref siblings + 1 unused ProviderKind, all fixed in-cycle). **Files: 2**.

### Cycle 2 — C-LLM-PIPELINE-PLAN [DOC XL] — refactor plan + audit

User-driven full-system architecture plan. Audit revealed 3 distinct LLM contracts in production, gateway-hardcoded `stream:false` forcing chat bypass, timeout-chain math fail. NEW `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — 8 sections covering principles (P1 streaming no-timeout, P2 async-jobs unified, P3 shared SDK, P4 gateway-only invariant), audit findings, target architecture (2 flavors at gateway), 7-phase migration plan, 8 open questions. **Files: 2**. User approved plan + Q1-Q8 defaults via "approve" reply.

### Cycle 1 — LM-STUDIO-PROXY-FIX [BE M] — transparent proxy strips trailing /v1

Pre-plan cycle. Closes the half that earlier LM-STUDIO-URL-FIX (commit 74da52c) missed: doProxy code path in api/server.go was still building `/v1/v1/chat/completions` for users who store endpoint as `http://host:1234/v1`. Discovered when running quality eval against qwen3.6-35b-a3b. Export NormalizeLmStudioBase + extract buildProxyTargetURL helper + 5 unit tests. **Files: 5**. **Verify**: live POST /internal/proxy/v1/chat/completions returns proper {choices, usage, stats} struct after rebuild.

### What's NEXT for the next agent

**Phase 4a is the natural next cycle but it is XL+ regardless of slice.** Knowledge-service has ~600 LOC `provider_client.py` business logic + ~1500 LOC test surface (test_provider_client.py 909 LOC + test_llm_json_parser.py 627 LOC). The migration target options:

1. **Surface-preserving rewrite (XL)**: chat_completion internals swap from JSON→SSE; ~30 test mocks need adjustment.
2. **Abandon provider_client.py (XL)**: 4 extractors use SDK directly; delete wrapper + tests; rewrite extractor mock pattern.
3. **Job-pattern + chunking (XL+)**: extractors become `submit_job + wait`; RabbitMQ subscriber inside knowledge-service or polling. **This is the cycle that actually fixes the original user complaint** (qwen3.6-35b-a3b on 13K-token chapters).

Phase 4a should open with a **DESIGN-first cycle** (like C16/C17/C18 of session 51) to choose the path + ADR before BUILD. Phase 3b-followup per-op aggregators + Phase 3c worker chunked dispatch are ready to consume.

**Other deferred items** (lower priority):
- Phase 3c-followup: parallel chunk dispatch (needs goroutine-safe aggregator) — Phase 6 hardening territory.
- Phase 4b/4c/4d: worker-ai/translation-service migrations + drop legacy invoke endpoints.
- Phase 5: Audio/STT/TTS migration to unified contract.
- Phase 6: rate-limit + retry + tracing + cancel-context propagation + crash-recovery.
- Phase 1c-anthropic-followup: Anthropic tool-use input_json_delta mapping (when tool-calling support lands).

**Read in this order to onboard:**
1. `docs/sessions/SESSION_PATCH.md` — full state with cycle-by-cycle metadata in header
2. `docs/03_planning/LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` — 8 sections + 7-phase plan + Q1-Q8 (user-approved)
3. This handoff file (you're reading) — cycle summaries with HEAD refs
4. `contracts/api/llm-gateway/v1/openapi.yaml` — canonical wire contract for the unified pipeline

**Session 52 closed at HEAD `c0420d2`. Session 53 opens fresh on Phase 4a DESIGN-first.**

---

## Session 51 — 14 cycles shipped (all Track 2/3 Gap Closure: C7..C16) · **P2 DONE (7/7)** · **P3 DONE (12/12)** · **P4 C14 DONE** · **P5 🏗 1/3 DESIGN-signed-off** · session closed

**Highlights:**
- **P2 tier closed at C9** (entity optimistic concurrency + unlock). All 7 P2 cycles shipped across sessions 50+51 (C3..C9).
- **🎉 P3 tier DONE 12/12** — opened at C10, fully closed at C12c-b. All Track 2/3 Gap Closure Priority 3 work shipped across 8 cycles (C10 + C11 + C12a + C12b-a + C12b-b + C13 + C12c-a + C12c-b).
- **🚀 P4 C14 fully shipped** in two cycles (C14a schedulers + C14b cursor state). User override of the P4 trigger criterion at C14b CLARIFY — plan-completion mindset. First session 51 cycle where "honest audit caught the plan understating scope" was applied BEFORE committing to size — saved a potential XL overrun.
- **🏗 P5 opened with C16** — first DESIGN-first cycle in plan history shipped clean. ADR for budget-attribution global-scope regen. Decision: Option B (`knowledge_summary_spending` table). Implementation sketch shovel-ready for next BUILD cycle. C15 honestly deferred per "fire when profiling shows pain" P4 trigger — opposite stance from C14b's user-override.
- **C12 split saga** — C12a (paired FS) + C12b-a/b-b (BE/FE split) + C12c-a/c-b (BE/FE split). Plan's single "C12 L" row bloomed into 5 honest-sized cycles. Memory `feedback_scope_audit_before_batching` applied each time.
- **C12c-a size reclassified** from plan-said-"S FE-only blocked" to workflow-gate-required FS L after audit caught: (a) no glossary-service list endpoint, (b) no worker branch handling scope='glossary_sync' (explicit TODO at runner.py:621 silently no-op'd), (c) scope='all' ALSO excluded glossary — user-approved flip makes the name honest.
- Back-end test coverage: **1466/1466 knowledge-service** (+61 over session 50's 1405) + **23/23 worker-ai** (+6 from C13's 17) + **12/12 glossary-service Go** at session 51 end.
- Front-end test coverage: **474/474** at session 51 end (unchanged since C12b-b — C13 stories are tsc-only, C12c-a is pure BE).

### Cycle 46 — Track 2/3 Gap Closure C16 🏗 [XL DESIGN-first] — budget-attribution ADR

**First P5 🏗 DESIGN-first cycle.** Shipped 280-line ADR
([`KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md`](../03_planning/KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md))
choosing **Option B** (`knowledge_summary_spending` table) over Option A (phantom-project pollution) and Option C (unified ledger XL refactor). Closes D-K20α-01's BUILD-blocker; the deferral itself stays partial until a BUILD cycle ships the implementation per §5/§7 checklist.

**Audit + decision rationale:** global L0 regen (`scope_type='global'`) bypasses the K16.11/K16.12 budget gate today because `record_spending` requires a `project_id`. Plan offered A vs B; audit + greenfield context (no production data) eliminated Option A's migration concerns and established C as overkill for the immediate problem.

**Implementation sketch covers:** DDL with composite PK + CHECK constraint + idx; `SummarySpendingRepo` (record + current_month_total); `check_user_monthly_budget` extension; `regenerate_global_summary` wire-in next to existing Prometheus increment; recording-order semantic (record AFTER provider success BEFORE guardrails); 15 enumerated test cases; DDL regression locks.

**4 open questions** explicitly deferred to BUILD-cycle CLARIFY: (1) project regen audit (does it ALSO bypass the gate?); (2) sanity caps; (3) FE wire shape; (4) auto-pause semantics.

**Closing checklist (§7)** gates D-K20α-01 fully-cleared: BUILD cycle ships migration + repo + budget extension + scheduler wire + DDL regression tests + 8 unit + 3 budget integration + 3 scheduler integration tests + plan row [x] AND `/review-impl` 0 unresolved HIGH/MED.

**Stage 2 self-fix:** added §5.4 recording-order paragraph clarifying record-after-provider-success rationale + recovery path via Prometheus/ledger divergence alert.

**Files: 3** (1 NEW ADR + SESSION_PATCH + plan row update). **Verify:** No code → no tsc/pytest. ADR doc-complete: 7 numbered sections, 5 subsections in §5, 4 explicit open questions, 9-item closing checklist.

---

### Cycle 45 — Track 2/3 Gap Closure C14b [BE L] — resumable scheduler cursor state

Closes **C14 fully** (C14a schedulers + C14b cursor). Second P4 cycle. User override of P4 trigger criterion at CLARIFY — plan-completion mindset.

**Three blocks:**
- **migrate.py** — NEW `sweeper_state` table (sweeper_name PK + last_user_id UUID + last_scope JSONB + updated_at). Per-sweeper resumable cursor, `last_scope` as escape hatch for future per-user-sub-scope sweepers. No FK on last_user_id (cross-DB forbidden).
- **NEW `SweeperStateRepo`** (4 methods: read_cursor / read_cursor_full / upsert_cursor with partial-UPDATE semantic / clear_cursor). Module docstring explains crash semantics.
- **Reconciler integration**: `SWEEPER_NAME` grep anchor; `_LIST_USERS_SQL` seek predicate `$1::uuid IS NULL OR user_id > $1::uuid` with ORDER BY user_id for deterministic resume; sweep_reconcile_once gains optional sweeper_state_repo (back-compat: None = C14a behavior); flow is read_cursor → fetch users with seek → per-user reconcile + upsert_cursor (BEFORE counter increment per /review-impl LOW#2) + counters → natural-completion clear; per-user raise leaves cursor at last successful user. Quarantine scheduler: docstring-only note (self-advancing filter, no natural per-user key).

**/review-impl caught 1 MED + 3 LOW + 1 COSMETIC; fixed MED + 1 LOW in-cycle, 1 LOW retracted (false finding), 2 accepted:**
- **MED#1** DDL regression test (3 new tests: table_present + schema_shape + no-cross-db-FK)
- **LOW#2** swapped upsert+counter order — cleaner semantics, both are safe (reconcile idempotent)
- **LOW#3 RETRACTED** — `idx_knowledge_projects_user_all ON knowledge_projects(user_id)` already exists from K16.12; my audit missed it

**Size reclassified** M→L at CLARIFY (7 files trips 6+ threshold). Honest-sizing memory applied — sixth reclassification this session.

**Closes D-K11.9-01 cursor-state + P-K15.10-01 cursor-state.** **C14 fully shipped.** Only C15 remains in P4 (trigger-gated).

**Files: 10** (6 code/test + 2 NEW — sweeper_state.py + test_sweeper_state_repo.py; 2 docs SESSION_PATCH/plan). **Verify:** pytest **1501/1501** (+17 from C14a baseline 1484: 10 repo + 4 scheduler integration + 3 DDL regression).

---

### Cycle 44 — Track 2/3 Gap Closure C14a [BE L] — reconciler + quarantine scheduler loops

**First P4 cycle.** Audit before CLARIFY caught that the plan's C14 row understated scope: K11.9 `reconcile_evidence_count` and K15.10 `run_quarantine_cleanup` are CALLABLE FUNCTIONS with no cron wiring — operators had to trigger manually. Split at user request into **C14a** (create missing schedulers, this cycle) + **C14b** (cursor hardening, deferred per P4 trigger criterion).

Two new scheduler modules mirroring K20.3 `summary_regen_scheduler` + K19b.8 `job_logs_retention` shape:

- **reconcile_evidence_count_scheduler.py** (NEW 210 LOC) — `sweep_reconcile_once` + `run_reconcile_loop`; advisory lock `20_310_004`; 24h cadence + 25min startup stagger; per-user iteration over DISTINCT user_id (NO is_archived filter post-LOW#4 fix — reconciler is cheap, archived projects still drift-prone). Per-user error isolation; Pydantic direct attribute access so schema drift crashes loudly.

- **quarantine_cleanup_scheduler.py** (NEW 200 LOC) — `sweep_quarantine_once` + `run_quarantine_loop`; advisory lock `20_310_005`; 12h cadence + 30min startup stagger; global sweep with /review-impl MED#1 inner-loop drain (10× throughput: 10k facts/sweep vs 1k original via `max_drain_iterations=10` safety cap + natural `count < limit` terminator).

- **metrics.py** (+2 Counter vecs with 3-outcome pre-seed + clarified Help strings per /review-impl MED#3 — `errored` is sweeps-with-≥1-error, not per-user-error count).

- **main.py** — 2 lifespan tasks + teardown cancellation mirroring K20.3/K19b.8. Advisory lock keys 001-005 now fully reserved.

**/review-impl caught 3 MED + 1 LOW + 2 COSMETIC; fixed 3 MED + 1 LOW in-cycle:**
- **MED#1** quarantine drain 10× (inner loop + safety cap + 3 regression tests)
- **MED#2** pool advisory-lock persistence on hard crash (pre-existing K20.3; documented in module docstring)
- **MED#3** metric `errored` semantics clarified in Help strings + derived-query examples
- **LOW#4** archived-only users now covered + source-scan regression lock

**Closes D-K11.9-01 partial + P-K15.10-01 partial (BE half).**

**Files: 10** (6 code/test + 2 docs SESSION_PATCH + plan + 2 scheduler NEW). **Verify:** pytest 1484/1484 (+18 from C12c-b baseline 1466: 9 reconciler + 9 quarantine).

---

### Cycle 43 — Track 2/3 Gap Closure C12c-b [FE L] — glossary_sync scope radio + retry fallback

Closes **D-K19a.5-06** completely (FE half paired with C12c-a BE). **P3 tier DONE 12/12.**

Pure FE additive on BuildGraphDialog: `ALL_SCOPES += 'glossary_sync'` (between chat and all); `availableScopes` memo extends book_id gate to cover both `chapters` AND `glossary_sync`; `openScope` falls back to `defaultScope` when `initialValues.scope` is a book-required scope but `project.book_id` is null — prevents orphaned state-but-not-rendered after book-unlink between job creation and retry (fixes pre-existing chapters bug for free). 4 locale JSON files + `BUILD_DIALOG_KEYS` drift-lock extended. 5 new tests (2 scope-radio + 3 /review-impl regression).

**/review-impl caught 3 LOW + 2 COSMETIC; all 3 LOWs fixed in-cycle:**
- **LOW#1** retry-fallback for book-unlinked projects (fixes chapters too) + 2 regression tests
- **LOW#2** retry pre-fill test for scope='glossary_sync'
- **LOW#3** Vietnamese `noBookHint` refined to "book-based scopes" grouping with examples

**Size reclassified** S→L at CLARIFY per workflow-gate (7 files trips 6+ threshold). Honest-sizing memory applied again — fifth reclassification in session 51.

**Files: 9** (7 code/test + 2 docs SESSION_PATCH + plan update). **Verify:** tsc clean; vitest 479/479 (+5 from C13 baseline 474). No BE touched — C12c-a's 422 guard is authoritative.

---

### Cycle 42 — Track 2/3 Gap Closure C12c-a [FS L] — glossary_sync BE unblock

3-service FS reclassified from plan-said "S FE-only blocked". Audit caught that **no glossary-service list endpoint existed**, **worker-ai had a TODO at runner.py:621 silently no-op'ing glossary_sync jobs**, and **scope='all' ALSO excluded glossary**. User approved flipping `all` to include glossary (making the name honest).

**Block A — glossary-service Go**: NEW `GET /internal/books/{book_id}/entities?cursor&limit` paginated endpoint with peek-ahead cursor logic, `alive=true AND deleted_at IS NULL` filter, short_description joined via LEFT JOIN on attribute_definitions. 5 tests (4 unit no-DB + 1 DB-gated cursor walk).

**Block B — worker-ai**: NEW `GlossaryClient` + `GlossaryEntity/Page` dataclasses with graceful-degrade → None. NEW `KnowledgeClient.glossary_sync_entity` + `GlossarySyncResult`. NEW `_enumerate_glossary_entities` returning `(list, complete: bool)` tuple + HARD_CAP=5000 + 200-page safety + UUID-ASC resume-skip. NEW `_GLOSSARY_SYNC_COST_PER_ITEM = 0.0` (through `_try_spend` for pause/cancel uniformity). NEW branch in `_process_job` for scope ∈ {glossary_sync, all} + book_id set. Bounded retry via `retry_glossary_<id>` cursor key mirroring chapters. `process_job`/`poll_and_run` sigs gain `glossary_client`.

**Block C — knowledge-service**: NEW `POST /internal/extraction/glossary-sync-entity` thin handler wrapping K15.11 helper (previously dead code). K15.11 helper ON MATCH SET now updates `project_id` (latest-sync wins, fixes first-call-wins drift for users with 2 projects sharing a book). `start_extraction_job` 422 guard for `glossary_sync + null book_id`.

**/review-impl caught 3 MED + 3 LOW + 1 COSMETIC; all 6 actionable findings fixed in-cycle:**
- **MED#1** start endpoint glossary_sync+null-book guard (422 with `error_code: 'glossary_sync_requires_book'`)
- **MED#2** K15.11 ON MATCH project_id drift (pre-existing; C12c-a activates helper)
- **MED#3** glossary branch bounded retry
- **LOW#4** opaque 502 boundary message
- **LOW#5** items_total drift on partial enumeration (enumerator returns `complete: bool`)
- **LOW#6** 5xx mid-enumeration test coverage
- **COSMETIC#7** 200-page ceiling kept as defense-in-depth

**Bonus:** during test Edit caught + restored a stray assertion in `test_start_job_active_job_exists_returns_409` (original test had 2 asserts; my first Edit only matched the first line, orphaning the second into a new test).

**Closes** D-K19a.5-06 BE half. **P3 tier 11/12 done** after C12c-a. Only **C12c-b** (FE scope radio, S) remains in P3.

**Files: 17** (14 code/test + 2 docs SESSION_PATCH/plan + 1 handoff). **Verify:** go test ok; worker-ai 23/23; knowledge-service 1466/1466.

---

### Cycle 41 — Track 2/3 Gap Closure C13 [FE L] — Storybook dialog stories via MSW

Pure FE infra. `msw@^2` + `msw-storybook-addon@^2` devDeps wired into `.storybook/preview.tsx` via `initialize({onUnhandledRequest:'warn'}) + loaders:[mswLoader]`. Service worker committed at `frontend/public/mockServiceWorker.js` (9KB, `msw init` output). 3 new infra modules under `.storybook/`: `fixtures/knowledge.ts` (14 typed factories), `msw-handlers.ts` (7 endpoint factories + `HandlerOptions`), `story-helpers.ts` (`findConfirmButton` / `findRunBenchmarkButton` / `waitForSelects` option-value-aware). 3 new story files × 19 stories (BuildGraph 11 + ChangeModel 5 + ErrorViewer 3). `@sb/*` Vite alias + tsconfig path collapses 4-level relative imports. MockAuthProvider.user reshaped from pre-existing `{id}` to production `{user_id, display_name: string|null, email}`.

**/review-impl caught 0 HIGH + 1 MED + 4 LOW + 2 COSMETIC; all 7 fixed in-cycle:**
- **MED#1** VERIFY was static-bundle-only — live-smoked via Chrome DevTools MCP (`npm run storybook`), confirmed MSW intercepts fire for all POSTed endpoints (estimate, start, benchmark-run, update-model) + play() interactions drive React state through the DOM. **DISCOVERED DURING SMOKE**: Radix Dialog portals to `document.body` so `canvasElement.querySelector*` misses dialog subtree entirely → extracted `story-helpers.ts` that queries `document`. Second-order: native `<select>` renders with placeholder-only while models useQuery pends → `waitForSelects` must gate on target-option-value or `selectOptions` throws "value not found in options".
- **LOW#2** `userModelsHandler` blind to `?capability=` query → split fixtures + query-param branch.
- **LOW#3** MockAuthProvider user shape mismatch (pre-existing K19a.8 latent) → renamed to match production `UserProfile`.
- **LOW#4** `benchmarkRunHandler` dead-on-arrival → NEW 11th BuildGraph story `BenchmarkRunFromCTA` consumes it via `findRunBenchmarkButton`.
- **LOW#5** `ambientHandlers` estimate-opt structural discriminator → explicit `{mode:'happy'|'loading'|'error'}` tagged union.
- **COSMETIC#6** `'../../../../.storybook/...'` imports → `@sb/*` Vite alias + tsconfig paths.
- **COSMETIC#7** `errorOr` blind cast to `JsonBodyType` → `isJsonSafe` recursive runtime narrow with fallback envelope.

**Closes** D-K19a.8-01. **P3 tier 9/9 DONE** after C13. **Files: 13** (6 MOD + 7 NEW). **Verify:** tsc clean + vitest 474/474 + `storybook build --test` success + live smoke Chrome DevTools MCP 4 story variants end-to-end.

### Cycle 40 — Track 2/3 Gap Closure C12b-b [FE L] — Run-benchmark CTA + error-code toast map

Pure FE. NEW `useRunBenchmark` mutation hook + inline `RunBenchmarkButton` rendered inside `EmbeddingModelPicker` — blast-radius = BuildGraphDialog + ChangeModelDialog + ProjectFormModal all inherit the CTA automatically. `runs=3` hardcoded (matches CLI + L-CH-09 methodology; BE validates 1..5). Gated on `projectId && value && !data.passed` so button shows for no-run AND failed, hides once passed. `runBenchmarkErrorMessage(t, code, detailMessage)` helper maps 6 codes (5 BE error codes + `'unknown'`) to localised toast copy. Success toast interpolates `{{model}}` from `resp.embedding_model` so model-swap mid-mutation can't render stale scope. 9-key i18n × 4 locales + placeholder drift lock.

**/review-impl** caught 0 HIGH + 1 MED + 3 LOW + 1 COSMETIC; fixed MED + 3 LOWs in-cycle, 2 accepted-with-doc:
- **MED#1**: toast didn't disclose which model the result belongs to — fixed by interpolating `{{model}}` from the response body (not the dropdown value, which may have changed).
- **LOW#2**: no placeholder-presence drift lock on new keys → 2 `it.each(LOCALES)` assertions mirroring C7's `jobs.detail.eta` pattern.
- **LOW#3**: `runs=null` explicit path untested → hook test pinning null pass-through so a future null→undefined coerce can't mask a BE 422 regression.
- **LOW#4 accept**: unmount-during-mutation drops toast (BE still completes + invalidates queryClient cache) — documented in hook docblock, matches `useRegenerateBio`.
- **LOW#5 accept**: button inside outer `<label>` is a structural smell (label-click forwarding no-ops on direct `<button>` target) — documented, matches BenchmarkBadge placement.
- **COSMETIC#6 accept**: rapid double-click race — `disabled={isPending}` updates synchronously within React's event tick; BE sentinel catches the edge.

**Closes** D-K19a.5-07 (FE half). **Files: 9**. **Verify:** FE knowledge+lib **474/474** GREEN (+9 from C12b-a baseline 465). `tsc --noEmit` clean.

### Cycle 39 — Track 2/3 Gap Closure C12b-a [BE L] — on-demand POST benchmark endpoint

NEW `app/benchmark/` module (230 LOC runner) + `POST /v1/knowledge/projects/{id}/benchmark-run`. Reuses K17.9 harness (AsyncBenchmarkRunner + fixture_loader + persist) so request-path is a thin sibling of the CLI's `_run_cli`. Typed exception hierarchy → 6 distinct error codes mapped to {404, 4×409, 1×502, 422}. Validation ladder: 404 cross-user/missing → 409 `no_embedding_model` → 409 `unknown_embedding_model` (dim-mismatched like `nomic-embed-text`) → 409 `not_benchmark_project` (empty-project guard via `KNOWN_SOURCE_TYPES` filter) → 409 `benchmark_already_running` (sentinel check-and-add) → 502 `embedding_provider_flake` (partial fixture load refuses to persist false-negative). Sync 120s default — background-task pattern rejected at CLARIFY (orphaned-failure UX worse than long request).

**/review-impl** caught 0 HIGH + 2 MED + 3 LOW + 1 COSMETIC; fixed all 5 non-cosmetic:
- **MED#1 source-scan drift lock**: `KNOWN_SOURCE_TYPES` correct today but silent risk if future PR adds a new producer. Fixed: regression test greps `passage_ingester.py` at test time for `source_type="..."` literals, asserts each is in the set.
- **MED#2**: initial `asyncio.Lock` + pre-check was atomic-only-in-single-threaded-asyncio + fragile to refactor (any future await-insert between check and acquire silently breaks serialization). Swapped to pure-sync `set[tuple[str,str]]` sentinel — check-and-add atomic-by-construction.
- **LOW#3**: no test pinned "benchmark_entity NOT in KNOWN_SOURCE_TYPES" invariant → added.
- **LOW#4**: partial fixture load silently persisted false-negative `passed=False` row (indistinguishable from real regression in FE badge) → NEW `FixtureLoadIncompleteError` → 502, refuses to persist. 2 tests: critical-contract + router.
- **LOW#5**: `_has_real_passages` Cypher literal had no direct assertion (all unit tests mocked it) → string-literal check for 3 safety clauses (`user_id`, `project_id`, `IN $real_types`).

**Closes** C12b (BE half). **Defers** C12b-b (FE) + C12c (glossary_sync, blocked). **Files: 5**. **Verify:** 28/28 new tests (15 runner + 13 router); 1405/1405 BE adjacent.

### Cycle 38 — Track 2/3 Gap Closure C12a [FS XL] — chapter-range picker + runner-side scope_range gate

Cross-service FS: NEW book-service `POST /internal/chapters/sort-orders` (mirrors `postInternalChapterTitles` shape verbatim — 200-cap, scan_error_count best-effort, rows.Err() fatal) + knowledge-service `BookClient.get_chapter_sort_orders` + NEW `ExtractionJobsRepo.list_active_for_project(user_id, project_id)` + event-handler runner gate in `handle_chapter_saved` + FE chapter-range inputs (From/To) in BuildGraphDialog gated on `scope='chapters'`.

**Disjoint union semantic** on the runner gate: ≥1 unbounded chapter-scope job → full ingest wins; otherwise `[10,20] ∪ [40,50]` excludes 30, includes 45. Graceful degrade on sort_order fetch failure → over-ingest (safer than silent skip). FE `chapterRange` useMemo declared BEFORE `estimateQuery` (TDZ fix during BUILD).

**/review-impl** caught 0 HIGH + 1 MED + 4 LOW + 0 COSMETIC; fixed MED + 1 LOW:
- **MED#1**: BE `_extract_chapter_range` accepted reversed `[50, 10]` — validator rejected wrong-length/non-int/negative but not `from > to`. Persisted, then runner gate `lo ≤ sort_order ≤ hi` vacuously false → silent skip with no error signal. Fixed: 3-line check raising 422; existing `test_estimate_scope_range_malformed_rejected` gains reversed-range case.
- **LOW#2**: `list_active_for_project` had no unit/integration test → 2 new integration tests (status filter + cross-user isolation) gated on `TEST_DATABASE_URL`.

**Closes** D-K19a.5-04 + D-K16.2-02b. **Defers** D-K19a.5-07 → C12b + D-K19a.5-06 → C12c (blocked). **Files: 16** (Go 2 + Python 5 + FE 4 + i18n 4 + docs 2). **Verify:** Go `TestPostInternalChapterSortOrders_*` 3/3; Python `test_event_handlers.py` 16/16 (+6 C12a); 247/247 BE adjacent. FE 444/444.

### Cycle 37 — Track 2/3 Gap Closure C11 [FS XL] — cursor pagination for extraction jobs history

Cross-service FS: NEW cursor codec + SQL row-value/NULLS-LAST predicate + response envelope + FE infinite query + Load more button. `_encode_cursor(c, r, j)` / `_decode_cursor(raw)` base64-urlsafe JSON, defensive against binascii/Unicode/JSON/field-shape errors. `list_all_for_user` signature returns `(list[ExtractionJob], str | None)` tuple + `cursor: str | None = None` kwarg. History path: 4-branch NULLS-LAST OR covering (cursor non-null + row non-null lower completed_at), (equal completed_at + lower tiebreak), (cursor non-null + row null — null always after), (both null + lower tiebreak). NEW `ExtractionJobsPage { items, next_cursor }` envelope; 422 on malformed cursor.

FE: `useInfiniteQuery` with `initialPageParam: ''` + `getNextPageParam: (last) => last.next_cursor ?? undefined`. `refetchInterval` conditional (function-form) gated on `pages.length ≤ 1` — single-page users keep 10s freshness, power users who Load more get a frozen view (explicit opt-in → explicit refresh). `ExtractionJobsTab` drops obsolete `COMPLETE_VISIBLE_LIMIT=10` slice.

**/review-impl** caught 0 HIGH (blocked early) + 1 HIGH + 1 MED + 3 LOW + 1 COSMETIC; fixed HIGH + MED + 1 LOW:
- **HIGH#1**: 9 integration-test call sites in `test_extraction_jobs_repo.py` treated return as list but the new tuple return `(rows, next_cursor)` silently broke them — would fail the moment the suite ran against live Postgres. Fixed: unpacked all 9 sites.
- **MED#2**: history polling was initially removed to avoid N-page refetch storm but created a UX regression → restored as function-form conditional gated on page count.
- **LOW#3**: no integration test exercised the novel 4-branch NULLS-LAST OR predicate → 2 new tests (walk-7-through-pages-of-3 + tied-completed_at-tiebreak).

**Closes** D-K19b.1-01 + D-K19b.2-01. **Files: 17**. **Verify:** BE unit 19/19 + cursor codec 7/7 = 26/26; FE 440/440.

### Cycle 36 — Track 2/3 Gap Closure C10 [FS XL] — timeline entity_id + chronological range filters

**First P3 cycle.** Cross-service FS: 3 new Cypher WHERE predicates (`participant_candidates`, `after_chronological`, `before_chronological`) + router entity_id resolution + FE TimelineFilters component (entity search dropdown + chronological range inputs).

Router resolution: `get_entity(user_id=str(jwt_user_id), canonical_id=entity_id)` with JWT-threaded user_id for cross-user safety. Missing entity → `participant_candidates=[]` (NOT `None`) so Cypher's `ANY(c IN [] WHERE ...)` = false → zero rows; collapses 404 path to empty timeline per KSA §6.4 anti-existence-leak. Reversed chronological range → 422.

FE TimelineFilters reuses `useEntities` (min-2-char + 250ms debounce matching EntityMergeDialog). **/review-impl MED#1**: chronological inputs fired BE call per keystroke → fixed by internal `afterInput`/`beforeInput` state + 400ms debounced commit effect + parent-reset sync effects. 2 regression tests (4-keystroke-coalesce + parent-reset-no-re-fire).

**Closes** D-K19e-α-01 + D-K19e-α-03. **Files: 16**. **Verify:** BE `test_timeline_api.py` 18/18 (+6 C10); 213/213 BE adjacent. FE 432/432.

### Cycle 35 — Track 2/3 Gap Closure C9 [FS XL] — entity optimistic concurrency + unlock endpoint — **P2 DONE 7/7**

Cross-service FS: `Entity.version: int = 1` field + coalesce backfill + atomic FOREACH Cypher + `POST /entities/{id}/unlock` + FE ifMatch threading + `useUnlockEntity` hook + Unlock CTA in detail panel. Atomic single-round-trip: `WITH e, coalesce(e.version, 1) AS current_version` + `FOREACH (_ IN CASE WHEN current_version = $expected_version THEN [1] ELSE [] END | SET ...)` + `RETURN e, current_version = $expected_version AS applied`. Version bumps at 4 user-facing sites (update / unlock / merge ON CREATE + ON MATCH / merge-update-target). System-internal writes (anchor recompute / archive / promote / unlink_glossary) deliberately NOT bumped to avoid spurious 412s.

**/review-impl** caught 1 HIGH + 0 MED + 4 LOW + 1 COSMETIC:
- **HIGH**: pre-C9 entities PERMANENTLY UNEDITABLE — `_node_to_entity` coalesced missing version to 1 but all 4 Cypher `coalesce(e.version, 0)` defaulted to 0, so FE's `If-Match: W/"1"` always 412'd against `current_version=0`. Unit tests mocked `run_write` and never hit this path. **Fixed** by aligning all 4 Cypher coalesce defaults to 1. **LOW#2**: added source-scan regression lock `test_cypher_version_coalesce_default_matches_read_path` that reads the 4 Cypher string literals at import time and asserts absence of `coalesce(.version, 0)`.

PATCH contract: 428 Precondition Required on missing If-Match, 412 Precondition Failed with `current.model_dump(mode="json")` body + fresh ETag header on mismatch. Unlock is idempotent (no If-Match) — `user_edited=true` entities become permanently alias-append-gated until user explicitly unlocks.

**Closes** D-K19d-γa-01 + D-K19d-γa-02. **P2 tier 7/7 — DONE.** **Files: 16**. **Verify:** BE entity 34/34 (+14 C9 + 2 regression locks); 163/163 BE adjacent. FE 422/422.

### Cycle 34 — Track 2/3 Gap Closure C8 [FS XL] — drawer-search source_type filter + in-card highlight + BE facet counts

Cross-service FS: NEW `count_passages_by_source_type` + Literal enum router param + response facet counts (user addendum) + NEW FE `highlightTokens` util + NEW `DrawerSearchFilters` component. Native `<input type="radio">` inside `<fieldset role="radiogroup">` for free WAI-ARIA keyboard semantics.

**/review-impl** caught 0 HIGH + 3 MED + 4 LOW + 2 COSMETIC; fixed 7 in-cycle:
- **MED#1**: cross-locale `sourceType.*` key presence test added.
- **MED#2**: `DRAWER_SOURCE_TYPES` tuple in api.ts as single source of truth — `EMPTY_COUNTS` + `OPTIONS` derive from it via `Object.fromEntries` / `.map`. BE adding a 4th type = ONE edit in api.ts, not 3.
- **MED#3**: filter reset on project change in `RawDrawersTab` — holding "Chapter" across projects hid hits in chat-only projects.

**Closes** D-K19e-γa-01 + D-K19e-γb-01. **Files: 16**. **Verify:** BE `test_drawers_api.py` 20/20 + new `test_passages_count.py` 4/4 = 24/24. FE 414/414.

### Cycle 33 — Track 2/3 Gap Closure C7 [FE XL] — humanised ETA formatter + stale-offset self-heal

**Reclassified from S to XL at CLARIFY** due to honest file count (10 files including locales). Pure FE: NEW `formatMinutes(minutes) → "<1min" | "{n}min" | "{h}h" | "{h}h {mm}min"` util + `useTimeline` optional `onStaleOffset` callback + consumer wiring.

Util pre-rounds to integer before branching so `59.6 → "1h"` (not naive `"0h 60min"`). Defensive NaN/Infinity/≤0 → `"<1min"` (dead code today, cheap future-safety). Hook fires callback when `total>0 && offset>0 && events.length===0 && !isLoading && !isFetching && !error` — all 6 guards. `events.length` dep (not identity) avoids re-fire on fresh-array fallback. After fire, parent sets offset=0 → guard `offset>0` fails → no loop.

**/review-impl** MED: collision with 5 existing local `formatDuration` helpers (ms/seconds semantics) → renamed `formatMinutes` for unambiguous unit. L4: inline `onStaleOffset` arrow churns effect deps → wrapped in `useCallback([])` in TimelineTab.

**Closes** D-K19b.3-02 + D-K19e-β-02. **Files: 12**. **Verify:** FE knowledge+lib 390/390 (+27 from 363 C6 baseline).

---

**What's next — Session 52 default path:**

🎉 **P1+P2+P3 all DONE + P4 C14 fully shipped + P5 C16 ADR signed off**. Remaining actionable: **C16-BUILD** (the implementation cycle for the ADR just shipped) OR **C17 + C18 DESIGN-first** ADRs. Next actionable default is **C16-BUILD** while ADR context is fresh.

Next cycle — **C16-BUILD (L)**: implement Option B per [the ADR](../03_planning/KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md). Files: migrate.py DDL append + NEW `SummarySpendingRepo` + budget.py extension + regenerate_summaries.py wire-in + 8 repo unit + 3 budget integration + 3 scheduler integration tests + DDL regression tests. CLARIFY MUST resolve §6's 4 open questions (especially #1: re-audit project regen budget path). Expect L-size; closing checklist in ADR §7 gates D-K20α-01 fully-cleared.

**Alternative next-cycle candidates:**
- **C17 🏗 (P5, XL DESIGN-first)** — Entity-merge canonical-alias mapping. KSA §3.4.E amendment + backfill story.
- **C18 🏗 (P5, XL DESIGN-first)** — Event wall-clock date. KSA §3.4 amendment + LLM prompt change + migration.
- **C15 (P4, S TRIGGER-GATED)** — Neo4j fulltext index. Fire ONLY when any user crosses ~10k entities.
- **User-gated ⏸** — C19 multilingual fixtures + C20 Gate-13 walkthrough.

**Session-51 stats**: 14 cycles shipped (C7→C16). Plan progress: 35 items / 23 cycles total; 33 items / 19 cycles done + 1 DESIGN-signed-off (C16 🏗). **P1+P2+P3 tiers fully closed; P4 C14 DONE; P5 opened with C16 ADR.** First session in LoreWeave history to close three plan tiers + fully ship a fourth's primary cycle + open the fifth via DESIGN-first in one continuous session.

**Session 51 aftermath — things to keep in mind:**

- **C9 HIGH (pre-C9 entities uneditable)** is a class lesson: when adding optimistic-concurrency to an existing model, audit EVERY coalesce/default-value site in read + write paths together. A read that defaults to 1 paired with a write that defaults to 0 creates a silent "permanently-stale" bug invisible to unit tests that mock `run_write`. Consider saving a feedback memory for coalesce-default symmetry if another cycle trips over this.
- **C11 HIGH (9 test sites tuple-breaks)** is a class lesson: when changing a repo method's return signature from `list[X]` to `(list[X], cursor)`, grep EVERY caller AND every test call site before VERIFY. The integration tests didn't run in CI (live-Postgres-gated) so the breakage would have surfaced only after the next stash baseline.
- **Source-scan regression locks** (C12b-a + C9 + C8) are now an established pattern for invariants that cross module boundaries and have no natural unit-test anchor: grep the source at test time + assert a predicate over the literal string. Cheap, zero Neo4j needed. Reuse whenever a new invariant spans 2+ files.
- **Pure-sync set-sentinel > asyncio.Lock** for check-and-add atomicity (C12b-a MED#2). Lock's pre-check-then-acquire is atomic only because no await sits between the two lines today — fragile to refactor. `set.add` returning True-if-new is atomic-by-construction and immune to future await-insertion.
- **Etag must fold every field in the response body** (C6 lesson reinforced via C9 ETag-in-412-mismatch behaviour). Adding a new field to a Pydantic response model without folding it into `_etag` lets stale data serve via 304. `hashlib.md5(..., usedforsecurity=False)` for the stable hash (NOT Python `hash()` which is PYTHONHASHSEED-randomized).
- **CLARIFY honesty > plan commitment**. C7 plan-said-S shipped as XL; C12 plan-bundled-L shipped as 3 cycles (C12a + C12b-a + C12b-b + C12c-blocked). Honest sizing at CLARIFY is worth more than hitting an initial classification — the workflow-gate tolerates reclassification.

**Starting-session boilerplate:**
1. Read [SESSION_PATCH.md](SESSION_PATCH.md) session-51 entries (cycles 33–46) + the plan file's §3 cycle table + the [C16 ADR](../03_planning/KNOWLEDGE_SERVICE_BUDGET_GLOBAL_SCOPE_ADR.md) §5–§7
2. `./scripts/workflow-gate.sh status` to confirm previous cycle closed
3. Start C16-BUILD with `./scripts/workflow-gate.sh size L 8 4 1` then `phase clarify` (L — DDL append + NEW repo + budget extension + scheduler wire + ~3 NEW + 2 MOD test files; 1 side-effect = new DB table). CLARIFY MUST resolve ADR §6's 4 open questions, especially #1 (re-audit project regen budget path).
4. Infra: `docker ps --filter name=infra-` — C16-BUILD wants live Postgres for integration tests; bring up infra-postgres at minimum
5. For future BE integration tests: `TEST_KNOWLEDGE_DB_URL=postgres://loreweave:loreweave_dev@localhost:5555/loreweave_knowledge` (port 5555 on host; DB name `loreweave_knowledge` NOT `knowledge`)
6. For Neo4j integration tests: `TEST_NEO4J_URI=bolt://localhost:7688 TEST_NEO4J_PASSWORD=loreweave_dev_neo4j`
7. Test account: `claude-test@loreweave.dev / Claude@Test2026` (Playwright smoke tests)

---

## Session 50 — 32 cycles shipped (24 Track 3 + 2 Track 2 close-out + 6 Gap Closure) · P1 done · P2 4/7 done · **session closed**

### Cycle 32 — Track 2/3 Gap Closure C6 [FS XL] — chapter-title resolution for Job + Timeline rows

Sixth Gap Closure cycle. Cross-service BE+FE via denormalization: book-service batched chapter-title endpoint + knowledge-service shared enricher + 4 enrichment sites + 2 FE consumer surfaces.

**Three blocks.**

1. **book-service** — new `POST /internal/chapters/titles` handler (inline in server.go per convention). SQL: `SELECT id, sort_order, title FROM chapters WHERE id = ANY($1::uuid[]) AND lifecycle_state='active'`. Format: `"Chapter N — Title"` (fallback `"Chapter N"` for whitespace-only titles). 200-id cap; missing/inactive chapters silently dropped. Path refined from plan's `/internal/books/chapters/titles` → `/internal/chapters/titles` since chapter_ids are cross-book.

2. **knowledge-service** — `BookClient.get_chapter_titles` + NEW `app/clients/chapter_title_enricher.py` with 2 in-place mutation helpers (events + jobs-cursor). `Event.chapter_title` + `ExtractionJob.current_chapter_title` additive optional fields. 4 enrichment sites: `/v1/knowledge/timeline`, `/jobs` list, `/jobs/{id}` single, `/{project_id}/extraction/jobs` per-project list. All 4 share the module-level BookClient singleton via `Depends(get_book_client)`.

3. **FE** — TimelineEventRow prefers `event.chapter_title ?? chapterShort(event.chapter_id)`; JobDetailPanel new "Current chapter" section gated on title presence. 2 new i18n keys × 4 locales.

**`/review-impl` caught 2 MED + 4 LOW; all 6 addressed in-cycle:**

- **M1** (critical): `_etag(job)` was `updated_at`-only → chapter title rename on book-side wouldn't bump etag, FE served 304 with stale title for up to staleTime. Fix folds `current_chapter_title` into etag via stable md5 (NOT Python's `hash()` which is PYTHONHASHSEED-randomized per-process). Regression test locks "same updated_at + different title → different etag".
- **M2**: happy-path SQL untested at Go level (s := &Server{}, pool=nil tests). Docstring documents the gap + recommends manual-curl smoke for future cycles. L5 partial-mitigation: `rows.Err()` turns silent empty-map SQL failures into 500s.
- **L3**: router tests silently skipped the enricher network path (cursor=None / invalid-UUID fixtures). Added 3 router-level enricher tests + `_setup_overrides` / `_make_client` now auto-override `get_book_client` so unit tests never touch real network.
- **L4**: UUID fallback wrapped in `<code>` → SRs announce character-by-character. Fix: `aria-label={t('timeline.row.chapterUnresolved', {id})}` + new i18n key × 4 locales.
- **L5**: handler silently skipped scan errors → schema drift would return empty map with no signal. Fix: `rows.Err()` check + scan_error_count in partial responses.
- **L6**: FE required type `chapter_title: string | null` doesn't match runtime `undefined` during rollout window. Kept required (matches codebase pattern) + added JSDoc noting the nuance + recommending `??` consumption pattern.

**Closes**: D-K19b.3-01 (JobDetailPanel current chapter) + D-K19e-β-01 (TimelineEventRow chapter title).

**Verify**:
- book-service Go tests 3/3 (non-DB only — M2 gap documented)
- knowledge-service BE unit **1379/1379** (+27 from 1352 C5 baseline: 6 book_client + 17 enricher + 3 router + 1 etag-bump)
- FE knowledge vitest **363/363** (+4 tests from C6 initial; L4/L6 additions didn't add new tests)
- `tsc --noEmit` clean
- No BE integration tests run; respx-mocked unit + the explicit Go-gap note are the safety nets

**Plan progress**: 11 items / 6 cycles · **P1 done · P2 4/7 done** (C3 ✅ + C4 ✅ + C5 ✅ + C6 ✅). Remaining P2: C7 (ETA formatter) · C8 (drawer-search UX) · C9 (entity concurrency+unlock).

---

### Cycle 31 — Track 2/3 Gap Closure C5 [FE M] — mobile polish: EntitiesTable + EntityDetailPanel + PrivacyTab

Fifth Gap Closure cycle. Pure FE responsive + a11y polish across 3 desktop-shared components.

**Three substantive deltas.**

1. **EntitiesTable dual render-tree**. Desktop 6-col grid table (~620px summed fixed cols) was overflowing 375px phones horizontally. Split into `hidden md:block` desktop tree (existing grid, preserved) + `md:hidden` mobile tree (card-per-row: Name + Kind primary line, flex-wrap secondary line with mentions/confidence/date/project). Shared `rowKeyHandler` helper dedup'd from the inline `onKeyDown`. Selected-state visual (`bg-primary/5 ring-1 ring-primary/30`) applied to BOTH trees via `cn()`. New testids `entities-table-desktop` / `entities-table-mobile` / `entities-row-mobile`; existing `entities-row` preserved on desktop (backward-compat with `EntitiesTab.test.tsx`'s 3 usages).

2. **EntityDetailPanel full-width on mobile**. One-word change `max-w-md` → `md:max-w-md`. Mobile: fills viewport. Desktop: 448px capped.

3. **PrivacyTab 4 buttons get `TOUCH_TARGET_MOBILE_ONLY_CLASS`**. Export / Delete / Dialog Cancel / Dialog Confirm wrapped in `cn(base, TOUCH_TARGET_MOBILE_ONLY_CLASS)`.

**`/review-impl` caught 1 HIGH + 3 LOW + 1 COSMETIC; all 5 addressed in-cycle:**

- **HIGH**: EntityDetailPanel's full-width mobile panel BLOCKS the overlay-dismiss path (overlay is covered by the panel), making the X close button the SOLE dismiss on touch. But X was `p-1 + h-4 w-4` ≈ 24×24px — well under the 44×44 iOS/Material minimum → fat-finger UX failure directly introduced by C5's width change. **Fix**: new `TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS = 'min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0'` export in `lib/touchTarget.ts` for icon-only buttons (needs BOTH axes because content doesn't fill width via padding); X button wrapped with `inline-flex items-center justify-center` to re-center the icon inside the expanded 44px box. Regression test locks all 4 class tokens + the flex-centering triple.
- **LOW2**: Mobile cards dropped `role="row"` — no columnheader context on mobile made SR announcement confused. Native `<button>` + `aria-label={e.name}` conveys the "activatable item" semantics cleanly. Desktop keeps `role="row"` for consistency with its columnheader row.
- **LOW3**: Added disabled-state PrivacyTab test — mocks `useAuth` with `accessToken: null`, asserts Export + Delete are `.toBeDisabled()` AND still carry `min-h-[44px]` + `md:min-h-0`. Guards against a regression like `className={cn(base, !disabled && TOUCH_TARGET_...)}` which default-enabled tests wouldn't catch.
- **LOW4**: Added inline comment on `entities-row` testid pointing at the `entities-row-mobile` sibling for future tests wanting cross-tree row counts via `findAllByTestId(/^entities-row/)`.
- **COSMETIC5**: Dialog cancel+confirm test rewrote `getAllByRole(...)[last]` DOM-order heuristic to `within(screen.getByRole('dialog'))` scoped query — no reliance on portal ordering.

**Closes**: D-K19d-β-01 (EntitiesTable mobile responsive + EntityDetailPanel full-width) + D-K19f-ε-01 (PrivacyTab sub-44px buttons).

**Verify**:
- 9/9 `mobilePolish.test.tsx` (7 initial + 2 post-/review-impl)
- 359/359 full FE knowledge vitest (+9 from 350 C4 baseline, zero regressions)
- `tsc --noEmit` clean
- No BE changes

**Plan progress**: 9 items / 5 cycles · **P1 done · P2 3/7 done** (C3 ✅ + C4 ✅ + C5 ✅). Remaining P2: C6 (chapter-title resolution) · C7 (ETA formatter) · C8 (drawer-search UX) · C9 (entity concurrency+unlock).

---

### Cycle 30 — Track 2/3 Gap Closure C4 [FE M] — useProjectState action-callback hook tests

Fourth Gap Closure cycle. Pure FE coverage debt closure: 1 new test file locks the runtime action-callback contract that K19a.7's compile-time `ACTION_KEYS` map couldn't reach.

**What the tests lock.** The hook exposes 14 callbacks: 8 BE-firing (`onPause` / `onResume` / `onCancel` / `onDeleteGraph` / `onRetry` / `onExtractNew` / `onRebuild` / `onConfirmModelChange`) + 6 no-op placeholders (K19a.5/K19a.6 dialog-owned). Before C4, a regression swapping `pauseExtraction` for `cancelExtraction` in `onPause` would have shipped undetected. After C4:

- Every BE-firing action asserts the correct `knowledgeApi` method + `(project_id, token)` arg shape
- `runAction` error path is locked: `toast.error` is called with `{label, error}` opts AND `invalidateQueries` does NOT fire (critical — else FE re-polls on bad state)
- `replayPayload`'s 4-branch `||` guard is fully covered: jobId / llm_model / embedding_model / scope null each trigger `noPriorJob` toast + no API call
- `onRebuild`/`onConfirmModelChange` guard's 2×2 matrix (action × missing-field) is fully covered
- `onExtractNew` forces `scope='chapters'` even when prior job was `chat`
- `accessToken=null` short-circuits all 8 actions
- 6 no-op placeholders are callable without throwing + leak to no API

**Plan divergence at CLARIFY.** Plan listed "11 actions" including `archive` / `restore` / `disable`. Audit showed archive/restore live at ProjectsTab/ProjectRow level (not the hook) and `disable` is one of the 6 no-op placeholders. Actual surface: 8 real + 6 placeholders = 14 callbacks.

**`/review-impl` caught 4 LOW + 2 COSMETIC; all 6 addressed in-cycle:**
- **L1** `beforeEach` per-mock reset → `Object.values(apiMocks)` loop (future API additions auto-reset)
- **L2** rebuild-guard 2×2 matrix was 2 of 4 cells → 4 tests fill the matrix
- **L3** `replayPayload`'s 4-branch null guard was 1 of 4 → 3 new tests for llm_model / embedding_model / scope null
- **L4** toast-opt-drop uncatchable with global raw-key i18n mock → **local** `react-i18next` mock encodes opts as `"<key>|<json>"`; error-path now asserts both outer template key AND `{label, error}` opts passed through
- **C5** batch no-token test doesn't isolate which action leaks → docstring explains density/isolation tradeoff
- **C6** error-path length-equality delta → explicit `calls.slice(before)` negative-slice

5 existing toast assertions tightened from `expect.stringContaining('<key>')` to `toHaveBeenCalledWith('<exact-key>')` since non-opt'd calls return bare key strings.

**Build-time fix:** unused `GraphStatsResponse` type import caught by tsc during VERIFY.

**Closes:** D-K19a.5-05 (action-callback runtime contract) + D-K19a.7-01 (partial super of D-K19a.5-05).

**Verify:**
- 20/20 `useProjectState.actions.test.tsx` (15 initial + 5 post-/review-impl)
- 350/350 full FE knowledge vitest (+20 from 330 C3 baseline, zero regressions)
- `tsc --noEmit` clean
- No BE changes

**Plan progress:** 9/33 item-closures · 4/20 cycles · **P1 done · P2 2/7 done** (C3 ✅ + C4 ✅). Remaining P2 cycles: C5 (mobile EntitiesTable + PrivacyTab tap audit) · C6 (chapter-title resolution) · C7 (ETA formatter) · C8 (drawer-search UX) · C9 (entity concurrency+unlock).

---

### Cycle 29 — Track 2/3 Gap Closure C3 [FS XL] — job_logs retention + pass2 stage producer + FE tail-follow

Third Gap Closure cycle, opens P2 tier. Three distinct deltas kept in one cycle at user request (explicit XL over C3a/C3b split).

**Block A — BE retention (D-K19b.8-01)**. NEW `app/jobs/job_logs_retention.py` close-mirror of K20.3 scheduler shape. Key differences: lock key `20_310_003` (unique across K13.1 + K20.3 keys), daily 24h cadence with 20-min startup delay (offsets K20.3's 10/15-min), `make_interval(days => $1)` parameterized DELETE, asyncpg `"DELETE N"` command-tag parse via defensive `_parse_delete_count`, release in try/finally. `main.py` wires create_task + cancel+await+suppress teardown. `migrate.py` adds `idx_job_logs_created_at` BTREE for the DELETE range predicate.

**Block B — Pass 2 stage producer (D-K19b.8-02)**. `pass2_orchestrator._run_pipeline` + 2 entry points accept optional `job_logs_repo: JobLogsRepo | None = None` kwarg (default None preserves ~20 existing test callers). 4 `info`-level events via `_emit_log` best-effort helper: `pass2_entities` (count + duration_ms), `pass2_entities_gate` (zero-entity early-exit marker), `pass2_gather` (R/E/F counts + gather-duration_ms), `pass2_write` (5 counters + write duration_ms added post /review-impl L2). Repo failures swallowed with WARNING log — extraction never dies for audit-write hiccups. `internal_extraction.py` constructs `JobLogsRepo(get_knowledge_pool())` inline, try/except for unit-test back-compat where pool isn't initialised.

**Block C — FE tail-follow (D-K19b.8-03)**. `useJobLogs.ts` swapped `useQuery` → `useInfiniteQuery` with cursor pagination + optional `jobStatus` opt gating 5s `refetchInterval` on `running/paused/pending`. `JobLogsPanel.tsx` gains `jobStatus` prop + listRef/nearBottomRef auto-scroll (100px threshold) + `max-h-80 overflow-y-auto` scroll container + Load-newer button disabled-during-fetching. `JobDetailPanel` passes `jobStatus={job.status}`.

**`/review-impl` caught 1 MED + 7 LOW + 1 COSMETIC; 6/7 fixed in-cycle + 2 accepted as Track 3 concerns**:
- **MED M1** `<details>` re-open left user at scrollTop=0 even when they'd been at bottom before collapse → `onToggle` handler with rAF-wrapped `scrollTo({top: scrollHeight})` + 2 regression tests (toggle-open fires / toggle-closed doesn't)
- **LOW L2** `pass2_write` event missing `duration_ms` (gather + entities had it) → wrapped `write_pass2_extraction` call in `time.perf_counter()` + context updated
- **LOW L3** `test_sweep_zero_row_delete_is_not_error` didn't assert unlock fires on zero-row path → assertion added
- **LOW L4** gather + write payload shapes untested at field-name level → 2 new parallel tests lock all counter/duration field names
- **LOW L6** browser resize left `nearBottomRef` stale → `ResizeObserver` on listRef (SSR-guarded) recomputes on container resize
- **COSMETIC C9** "Load more" ambiguous (cursor is ASC = newer) → i18n rename `loadMore`/`loadingMore` → `loadNewer`/`loadingNewer` across 4 locales
- **LOW L7** (accepted) cross-tenant retention not per-tenant configurable → module docstring documents Track 3 uplift
- **LOW L8** (accepted) log list not virtualized → component docstring documents `react-window` as Track 3 polish

**Build-time fixes**:
- `sinceLogId` camelCase vs `since_log_id` snake_case — tsc caught during build; hook + test assertions updated
- `internal_extraction.py` unit tests don't init the pool — wrapped `JobLogsRepo(get_knowledge_pool())` in try/except matching `_emit_log` repo=None contract
- `fireEvent.toggle` doesn't exist in react-testing-library — used `fireEvent(el, new Event('toggle', {bubbles: false}))`

**Closes**: D-K19b.8-01 + D-K19b.8-02 + D-K19b.8-03.

**Verify**:
- BE unit **1354/1354** (+24 from 1330 C2 end: 16 retention + 8 pass2 producer)
- BE integration retention 3/3 live + job_logs-adjacent 5/5 (8/8 against infra-postgres-1)
- FE knowledge vitest **330/330** (+10 from 320: 5 useJobLogs infinite-query + 5 JobLogsPanel toggle+Load-newer+auto-scroll)
- Worker-ai 17/17 (no regressions)
- `tsc --noEmit` clean

**Plan progress**: 7/33 item-closures · 3/20 cycles · **P1 done · P2 opened with C3** (14 items / 7 cycles remain in P2).

---

### Cycle 28 — Track 2/3 Gap Closure C2 [BE L] — scheduler trigger label + regen cooldown

Second cycle of the [Gap Closure Plan](../03_planning/KNOWLEDGE_SERVICE_TRACK2_3_GAP_CLOSURE_PLAN.md). Closes both remaining P1-tier observability items — **D-K20.3-α-02** (scheduler metrics) + **D-K20α-02** (regen cooldown). Reclassified S → L early in CLARIFY after audit (plan's "2 files" was optimistic; actual touch is 7 files + 3 test-file extensions).

**Two substantive code changes:**

1. **`summary_regen_total` gains `trigger` label** (`manual` | `scheduled`). Cardinality 12 → 24 pre-seeded series. `RegenTrigger = Literal["manual","scheduled"]` added to `regenerate_summaries.py`; threaded as `trigger` kwarg through `_regenerate_core`, `regenerate_global_summary`, `regenerate_project_summary` (default `"manual"` — back-compat). Scheduler passes `trigger="scheduled"`; public endpoints pass `trigger="manual"`. `/internal/summarize`'s `SummarizeRequest` gains a `trigger: RegenTrigger = "manual"` field (post /review-impl LOW#5). Duration/cost/tokens counters stay 2-label (MVP scope, documented).

2. **Redis SETNX cooldown** on both public regen endpoints. Key `knowledge:regen:cooldown:{user}:{scope_type}:{scope_id or '-'}`, 60s TTL. Per-target (scope_id in key), not per-user. Module-level lazy `aioredis` singleton with `asyncio.Lock` double-checked init + `close_cooldown_client` wired into lifespan teardown (both failure-cleanup tuple AND normal post-yield block). On 429: `Retry-After` header from `client.ttl(key)` with TTL-exception fallback to full budget + defensive floor-to-1 for the `-2`-race (key expires between SETNX=False and TTL read). Graceful degrade when `settings.redis_url` empty OR Redis raises.

**`/review-impl` caught 1 MED + 5 LOW + 1 COSMETIC; all 7 fixed in the same commit:**
- **MED#1** cooldown armed on 500-class server-side failures — live-verified via docker curl (Neo4j-not-configured 500 still armed key for 60s, punishing users for our own bugs). Fixed with `_release_regen_cooldown` helper called from `except ProviderError` AND `except Exception` in both endpoints. Business outcomes (user_edit_lock / concurrent_edit / no_op_* / regenerated) KEEP the cooldown armed — `test_regenerate_cooldown_stays_armed_on_business_outcomes` locks that primary anti-spam contract.
- **LOW#2** FakeRedis.ttl always returned the stored EX value so the defensive floor-to-1 branch never fired in tests → FakeRedis gains `expired_keys` mode returning `-2`; `test_regenerate_cooldown_retry_after_floor_when_ttl_expired_mid_race` asserts `Retry-After == 1`.
- **LOW#3** `client.ttl()` exception path had no test coverage (BoomRedis short-circuits at SET) → `_HalfBoomRedis` (SET/DELETE succeed, TTL raises) + `test_regenerate_cooldown_ttl_exception_falls_back_to_full_budget`.
- **LOW#4** `test_regenerate_project_cooldown_per_project_scope` missing `mock_regen.await_count == 2` → assertion added.
- **LOW#5** `/internal/summarize` didn't accept `trigger` → added as `SummarizeRequest.trigger` + 3 tests (default-to-manual, explicit-scheduled-forwards, Literal-validator-rejects-typo).
- **COSMETIC#7** `_check_regen_cooldown` + `_cooldown_key` used `scope_type: str` → tightened to `Literal["global", "project"]`.
- Accepted **LOW#6**: duration/cost/tokens still 2-label — documented in `_regenerate_core` docstring.

**Live manual-curl verify** (docker rebuild `infra-knowledge-service:latest` + hot-swap; Postgres/Redis/glossary healthy; Neo4j intentionally down = Track 1 mode):
- Call 1 to `/me/summary/regenerate` → 500 (Neo4j not configured); Redis key ABSENT (MED#1 release path fired)
- Call 2 → 500 not 429 (no stuck cooldown)
- Manually `redis-cli SET project:11111… EX 60` → endpoint → **429** with `Retry-After: 60` (cooldown still works for armed state)
- Endpoint to `project:22222…` → **422** guardrail (cross-user) NOT 429 (per-scope isolation holds)
- Post-422: both project keys armed independently (TTL 45s + 46s)
- `/metrics` scrape shows 24 pre-seeded series + `{scope_type="project",status="no_op_guardrail",trigger="manual"} 1.0` incremented by the 422 call

**Closes**: D-K20.3-α-02 (scheduler metrics) + D-K20α-02 (regen cooldown).

**Verify**: knowledge-service unit 1330/1330 (was 1322 at C1 end; **+8** = 5 cooldown regressions + 3 trigger-forwarding; existing-test updates: 3 metric assertions + 2 scheduler `await_args.kwargs["trigger"]` asserts + 1 `await_count == 2` assertion).

**Plan progress**: 4/33 item-closures · 2/20 cycles · **P1 tier 2/2 done** (C1 ✅ + C2 ✅); P2 tier opens with C3 next.

---

### Cycle 27 — Track 2/3 Gap Closure C1 [FS M] — merge_entities atomicity + ON MATCH union

**First cycle of the new [Track 2/3 Gap Closure Plan](../03_planning/KNOWLEDGE_SERVICE_TRACK2_3_GAP_CLOSURE_PLAN.md)** — a 20-cycle debt-drain (~32 open deferrals from Track 2 + K19/K20) the user asked for before opening further Track 3 feature work. C1 is P1 tier — the only backlog item with actual data-loss risk.

**Two changes to [`app/db/neo4j_repos/entities.py`](../../services/knowledge-service/app/db/neo4j_repos/entities.py):**

1. **Atomicity.** `merge_entities` steps 4–7 (rewire RELATES_TO / rewire EVIDENCED_BY / update target w/ glossary pre-clear / DETACH DELETE source) wrapped in `async with await session.begin_transaction() as tx:`. A Neo4j crash between glossary pre-clear and DETACH DELETE can no longer leave source orphaned with `glossary_entity_id=NULL`. Docstring added the contract: "session must be a fresh AsyncSession with no open transaction" — Neo4j async sessions don't nest tx.

2. **ON MATCH union.** `_MERGE_REWIRE_RELATES_TO_CYPHER` gained 4 CASE branches beyond the pre-existing `confidence`-MAX + `source_event_ids`-UNION: `pending_validation` via `coalesce(..., false) AND ...` (matches `relations.py`'s 8-site NULL=validated convention), `valid_from` earliest-non-null, `valid_until` NULL-wins (NULL = still-active sentinel per relations.py:13), `source_chapter` concat-when-distinct. Pass-2-validated source edge merging into quarantined target duplicate now correctly promotes to validated.

**+3 integration tests (live Neo4j):**
- `test_merge_entities_promotes_validated_edge_over_quarantined` — all 4 union branches incl. `valid_until` NULL-wins via raw-Cypher seed (`create_relation` doesn't accept the kwarg)
- `test_merge_entities_on_match_preserves_quarantine_and_validated` — both mirror AND cases a hardcoded `= false` regression would pass without
- `test_merge_entities_is_atomic_on_mid_flight_failure` — `monkeypatch`es `_MERGE_DELETE_SOURCE_CYPHER` → bad Cypher and asserts **3 rollback axes** (glossary + no rewired RELATES_TO + target aliases unchanged). Multi-axis defense against a regression moving ANY single step out of tx, not just the step the failure-injection point targets.

`/review-impl` caught **2 MED + 3 LOW + 1 COSMETIC; all 6 folded into same commit**:
- **M1** coalesce-to-true diverged from codebase NULL=false convention → switched both sides to `coalesce(..., false)`
- **M2** atomicity test proved only glossary-axis rollback → extended to 3 axes
- **L3** `valid_until` CASE never exercised → raw-Cypher seed on target
- **L4** AND-combine only tested promotion direction → new mirror test
- **L5** Python `bool(x or False)` NULL coercion — subsumed by M1 aligned defaults
- **L6** nested-tx contract undocumented → docstring updated
- Accepted #7: `source_chapter` concat bloat on repeated merges — hobby scale, in-code comment

**Closes**: D-K19d-γb-01 (ON MATCH union) + D-K19d-γb-02 (merge atomicity).

**Verify**: 26/26 `test_entities_browse_repo.py` (+3 new) + 105/105 adjacent integration + 86/86 entity unit.

**Plan progress**: 2/33 item-closures · 1/20 cycles · P1 tier: 1/2 done (C1 ✅, C2 next).

---

### Cycle 26 — K20.3 Cycle β [BE L] — Scheduled global L0 regen loop

Closes K20.3 by shipping the global-scope sweep that Cycle α deferred. Close-mirror of α with 3 substantive differences:

1. **UNION eligibility**: users with either an existing global summary OR any non-archived project — catches "keep my bio fresh" AND "will create on first successful regen once I have enough content". Locked by integration test against live Postgres.
2. **User-wide model resolution**: `SELECT llm_model FROM extraction_jobs WHERE user_id=$1 AND status='complete' ORDER BY completed_at DESC LIMIT 1` — picks the most-recent model used anywhere. Users who've never extracted get `no_model` skip.
3. **Distinct advisory lock** `_GLOBAL_REGEN_LOCK_KEY = 20_310_002` so project + global loops can run concurrently on different scopes.

Cadence: **weekly** (7d = 604800s) with 15-min startup delay (offset from project loop's 10-min).

`/review-impl` caught **2 LOW + 1 COSMETIC; all 3 addressed in-cycle**:
- **L1** UNION eligibility SQL untested at integration layer → NEW `test_summary_regen_scheduler_sql.py` with 2 tests hitting live Postgres: 5-user scenario matrix (summary-only / project-only / summary+archived / archived-only / dual-source) locks UNION dedup AND `is_archived=false` filter. Separate ordering test locks crash-resume determinism.
- **L2** no audit log showing which model was resolved per sweep → INFO log `K20.3: regen project|global user=... model=...` on both sweeps. Operators can now grep logs to trace "why did this user's regen fail?" back to the BYOK model choice (especially useful after provider model deprecations).
- **C3** FakeConn arg-count routing was fragile → SQL-text matching (`"project_id = $2" in sql`) ties the fake to the exact production code paths.

**Build-time catch**: initial integration test skipped with Postgres auth failure — container uses `loreweave:loreweave_dev@loreweave_knowledge` not `postgres:*@knowledge`. Corrected `TEST_KNOWLEDGE_DB_URL`.

**Cleared**: D-K20.3-α-01 (scheduled global L0 regen loop).

**Still deferred**: D-K20.3-α-02 (Prometheus metrics beyond logged outcome counters).

**Test deltas at K20.3 β end:**
- BE unit: **32/32 scheduler tests pass** (was 18; +14 global-sweep coverage)
- BE integration: **2/2 new SQL tests** against live `infra-postgres-1`
- BE regen-adjacent: **76/76** (no regressions)

---

### Cycle 25 — K20.3 Cycle α [BE L] — Scheduled project summary regen

Ships the scheduled auto-regen that K20α/β/γ intentionally deferred. Mirrors the K13.1 `anchor_refresh_loop` template: `sweep_projects_once` is the pure sweep function (pg_try_advisory_lock + iterate non-archived extraction-enabled projects + per-project call to `regenerate_project_summary`), `run_project_regen_loop` wraps it in an asyncio loop with 10-min startup delay + 24h interval.

**Model resolution**: scheduled regen has no caller to supply `model_ref`, so it subqueries `extraction_jobs` for the most-recent completed job per project and reuses its `llm_model`. Projects that never ran extraction are counted as `no_model` and skipped.

**Status mapping**: 6 `RegenerationStatus` Literal values collapse into 4 counter buckets on `SweepResult`:
- `regenerated` → `regenerated`
- `no_op_similarity`, `no_op_empty_source`, `no_op_guardrail` → `no_op`
- `user_edit_lock`, `regen_concurrent_edit` → `skipped`
- Unknown future status → `errored` + WARNING log (defensive branch)

**Advisory lock** via `try/finally: pg_advisory_unlock` guarantees release even on mid-sweep exception. Lock released before connection returns to pool — no orphaned state on recycled connections.

**Lifespan wire** in `main.py` matches K13.1: conditional on `settings.neo4j_uri` (Track 1 mode skips), teardown via `cancel+await+suppress CancelledError`.

`/review-impl` caught **1 LOW + 2 COSMETIC; all 3 addressed in-cycle**:
- **L1** inline `SummariesRepo(get_knowledge_pool())` vs async `get_summaries_repo()` factory → documented decision (matches K13.1 precedent; factory would make scheduler the odd one out in lifespan wire)
- **C2** `model_construct` test fixture bypass → 11-line docstring explaining forward-compat tradeoff
- **C3** sweep-complete INFO log untested → new test asserts exactly-one completion log + all 6 counter names present in message

**Build-time catches:**
- Pydantic Literal rejection on unknown status → `model_construct` bypass for the defensive-branch test
- Mock signature `**_kwargs` couldn't absorb positional args from real `sweep_projects_once(pool, session_factory, provider_client, summaries_repo)` → `*_args, **_kwargs`
- `startup_delay_s=0` guard skipped the first `asyncio.sleep` call, throwing off count expectations → tests use `startup_delay_s=1`

**Deferred to Cycle β**:
- D-K20.3-α-01 global L0 regen loop (needs cross-project model resolution)
- D-K20.3-α-02 scheduler run metrics (Prometheus counters beyond logged outcome)

**Test deltas at K20.3 α end:**
- BE unit: **18/18 scheduler tests pass** (new file)
- BE regen-adjacent: **62/62** (61 previous + 1 completion-log test)
- No regressions across all regen paths

---

### Cycle 24 — K19f Cycle ε [FE S] — Tap-target audit (K19f.5)

Closes the K19f cluster. Applied `TOUCH_TARGET_CLASS = 'min-h-[44px]'` to the 2 remaining mobile-shell links (MobileKnowledgePage privacy footer link + MobilePrivacyShell back link). Test assertions strengthened to import the constant and assert `className.toContain(TOUCH_TARGET_CLASS)` so a future refactor of the constant value (e.g. to Tailwind's `min-h-11` shorthand) stays lockable.

**Full tap-target inventory at K19f end**: GlobalMobile save (β) · ProjectsMobile toggle + Build (γ) · JobsMobile toggle + Pause/Resume/Cancel (δ) · MobileKnowledgePage privacy link (ε) · MobilePrivacyShell back link (ε). All interactive elements in mobile-rendered mobile-variant code ≥44px. Card spacing via `space-y-2` (8px), section spacing via `mb-8` (32px).

`/review-impl` caught **1 LOW + 2 COSMETIC; 1 COSMETIC fixed + 1 LOW deferred + 1 COSMETIC accepted**:
- **L1 → D-K19f-ε-01** PrivacyTab mobile audit gap. Renders on mobile via MobilePrivacyShell but its 4 buttons (Export, Delete, dialog Cancel, dialog Confirm) are ~26-30px tall. Deferred because PrivacyTab is desktop-shared — applying TOUCH_TARGET_CLASS unconditionally widens desktop buttons too. Future cycle picks between conditional (useIsMobile guard) or blanket (accept desktop cosmetic change).
- **C2** raw-string assertion in tests → import constant instead.
- **C3** no click-navigation test on Links → accepted as existing convention.

**K19f cluster 100% plan-complete** (α shell + β GlobalMobile + γ ProjectsMobile + δ JobsMobile + ε tap audit).

**Session 50 stats (final, session-closed state)**:
- **32 cycles shipped** (24 Track 3 + 2 Track 2 close-out + 6 Gap Closure: C1..C6)
- All Track 3 K19-series clusters (K19a through K19f) 100% plan-complete
- Track 2/3 Gap Closure Plan: P1 done · **P2 4/7 done** · 14 cycles remaining
- Front-end test coverage: **363 pass** at session 50 end (vs ~88 at session 47 end · +43 this session over C1–C6)
- Back-end test coverage: **1379 pass** at session 50 end (vs 1154 at session 47 end · +97 this session over C1–C6)

**What's next — Session 51 default path:** ✅ **Superseded.** Session 51 shipped C7 (as XL, not S — see aftermath note above for honest-sizing lesson) through C12b-b. See **Session 51** block at the top of this file for current status and the "What's next — Session 52 default path" pointing at **C13**.

**C6 aftermath — things to keep in mind for later cycles:**
- **BE denormalization > FE hook** when the data is cheap to look up at list-materialization time and both consumer surfaces share the root cause. Singleton `get_book_client` Depends + shared enricher helper (mutating in-place on Pydantic models) + 4 router wire sites was cleaner than a FE `useChapterTitles` hook would have been
- **Etag must include every field that feeds the response body** — the L6-pattern to watch for: if `_etag(x)` computes over `updated_at` only, any new `x.<field>` that flows into response JSON via enricher won't bump the etag, FE serves stale via 304. `hashlib.md5(...usedforsecurity=False)` for the stable hash (NOT Python's `hash()`, which is PYTHONHASHSEED-randomized per-process → different etag per worker)
- **Graceful-degrade chain has 4 layers, each needs its own test** — BE drops inactive/missing chapters → BookClient returns `{}` on HTTP failure → enricher short-circuits on empty dict → FE falls back via `chapter_title ?? chapterShort(chapter_id)`. Layer 1 Go test, layer 2 respx test, layer 3 enricher unit test, layer 4 vitest. Skipping any layer leaves a silent-degradation hole
- **Cross-service internal handlers with `requireInternalToken`** trust any service holding the shared token to query any IDs. knowledge-service only queries chapter_ids it already holds (from its own tenant-scoped Neo4j), so the leak surface is zero today. If a future service shares the token, this becomes a tenant-isolation concern — worth flagging in the internal-route review checklist
- **`rows.Err()` after pgx `for rows.Next()` loop** — without it, scan errors from schema drift (wrong column type, column dropped) silently return empty maps. With it, they surface as 500s. Cheap defense, high dividend

**C5 aftermath — things to keep in mind for later cycles:**
- **`TOUCH_TARGET_MOBILE_ONLY_CLASS` (`min-h-[44px] md:min-h-0`)** for padding-driven buttons on desktop-shared components; **`TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS` (`min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0`)** for icon-only buttons (X close, settings, kebab). Always pair the SQUARE variant with `inline-flex items-center justify-center` so the icon re-centers inside the expanded 44px box — otherwise sticks to top-left
- **Pure Tailwind `md:` class swaps** preferred over `useIsMobile()` for simple responsive CSS changes — no re-render, SSR-safe, class names are testable
- **Dual render-tree pattern** (`hidden md:block` desktop + `md:hidden` mobile) for components where the mobile layout is structurally different from desktop — cleaner than one tree with many `hidden md:inline` spans. `display: none` removes the other tree from the a11y tree in real browsers; jsdom sees both but className assertions catch class-drop regressions
- **Mobile cards that replicate desktop table structure** should drop `role="row"` for native `<button>` + `aria-label` — there's no columnheader context on mobile and SRs get confused. Desktop keeps `role="row"` for its columnheader context
- **Full-width mobile panels BREAK overlay-click-dismiss** — the panel covers the overlay entirely. Icon-only close buttons then become the sole dismiss and NEED the square tap-target treatment. Always audit mobile dismiss paths when moving from `max-w-*` to full-width

**C4 aftermath — things to keep in mind for later cycles:**
- **`vi.hoisted()` is the canonical hoist-beater** for mock vars in vitest — memory `feedback_vitest_hoisted_mock_vars.md` confirmed. First-attempt BUILD always hits the ReferenceError; always reach for `vi.hoisted()` from the start
- **Global `react-i18next` mock returns raw keys** — this MUTES toast-opt-drop regressions. For tests that need to verify `{label, error}` opts are passed through, write a **local** `react-i18next` mock override that encodes opts as `"<key>|<json>"`. Pattern now established in `useProjectState.actions.test.tsx`
- **Plan "N action" counts are often vibes** — C4's plan said "11 actions" but audit showed 8 BE-firing + 6 placeholders (archive/restore/disable not in the hook). Always audit the actual callback surface before committing to a test count
- **`Object.values(apiMocks)` loop** for `beforeEach` mock reset — future API additions auto-reset. Generalize this pattern for all future hook-test files with multiple API mocks

**C3 aftermath — things to keep in mind for later cycles:**
- `_emit_log` pattern (optional repo + best-effort try/except + UUID parse) is now established for BE→job_logs producers — any new extraction-pipeline stage that wants to surface progress to the FE JobLogsPanel should reuse the same contract
- Advisory lock key series `20_310_00{1,2,3}` is contiguous — next retention/scheduler loop should use `20_310_004`+ to stay in the K20.x/K19b.8 numbering family
- `useInfiniteQuery` refetchInterval refetches ALL loaded pages with their original pageParams — tail-follow is automatic because the last page's response grows as the server appends; NEW pages only appear when the last page fills (50 rows) and `hasNextPage` flips back to true
- `<details>` + `onToggle` + rAF scrollTo is the vetted pattern for "show latest on open" UX in collapsed panels — reusable in future collapsed-viewer components
- FakeConn + FakePool convention lives in `test_job_logs_retention.py` and `test_summary_regen_scheduler.py` — if a 4th scheduler lands, consider hoisting to a shared `tests/unit/_fake_pool.py` fixture module
- Two /review-impl cycles in a row caught `<details>`-style defensive branches that unit tests don't exercise (C2's MED-1 cooldown-on-5xx; C3's MED-1 toggle-open scroll). Pattern: **when a component has state that persists across visibility changes (collapsed/closed panels, route changes, tab switches), the first-open/first-visible path is a coverage hole** — any future component with similar lifecycle should get an explicit toggle/open regression test

Remaining cycles after C2 (grouped by tier):
- **P2 (C3–C9)** — 14 items / 7 cycles: job_logs observability trio · useProjectState hook tests · mobile polish · chapter-title resolution · ETA formatter · drawer-search UX · entity concurrency+unlock
- **P3 (C10–C13)** — 7 items / 4 cycles: timeline gaps · cursor pagination · scope+benchmark dialog · Storybook dialogs via MSW
- **P4 (C14–C15)** — 3 items / 2 cycles: resumable scheduler cursor state · Neo4j fulltext index (fire only at >10k entities)
- **P5 🏗 (C16–C18)** — 3 items / 3 cycles, all DESIGN-first: budget attribution · entity-merge canonical-alias mapping · event wall-clock date
- **User-gated ⏸ (C19–C20)** — multilingual fixtures (user provides text) + Gate-13 human walkthrough

**NOT the default path but possible if user redirects:**
- Continue Track 3 feature cycles (K19g-h, K21 tool calling, K22 privacy page)
- Gate-13 T2-close-2 walkthrough (user-attested BYOK run)
- Data re-engineering ([101_DATA_RE_ENGINEERING_PLAN](../03_planning/101_DATA_RE_ENGINEERING_PLAN.md))

**Starting-session boilerplate:**
1. Read [SESSION_PATCH.md](SESSION_PATCH.md) cycle-32 entry + the plan file's §3 cycle table
2. `./scripts/workflow-gate.sh status` to confirm previous cycle closed
3. Start C7 with `./scripts/workflow-gate.sh size S 3 2 0` then `phase clarify` (S — pure-FE ETA formatter utility + ~2 consumer surfaces + tests; no BE change, no cross-service contract. Side effects = 0)
4. Infra: `docker ps --filter name=infra-` — C7 is FE-only unit tests + no integration path; services can stay up or down
5. For Postgres integration tests (if needed in a subsequent cycle): `TEST_KNOWLEDGE_DB_URL=postgres://loreweave:loreweave_dev@localhost:5555/loreweave_knowledge` (port 5555 on host; container maps to 5432; DB name `loreweave_knowledge` NOT `knowledge`)
6. For Neo4j integration tests: `TEST_NEO4J_URI=bolt://localhost:7688 TEST_NEO4J_PASSWORD=loreweave_dev_neo4j`
7. For manual-curl verify, JWT gen one-liner: `python -c "import jwt,uuid,datetime; print(jwt.encode({'sub':str(uuid.uuid4()),'exp':datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=10)},'loreweave_local_dev_jwt_secret_change_me_32chars',algorithm='HS256'))"` → `curl -H "Authorization: Bearer $TOKEN" http://localhost:8216/...` (if Neo4j is down, extraction-path tests will 500/503 — known Track 1 limitation)

---

### Cycle 23 — K19f Cycle δ [FE L] — JobsMobile (K19f.3)

Ships the third simplified mobile variant. Merged active+history sorted list (`STATUS_SORT_ORDER: running → paused → pending → failed → cancelled → complete`, within-status newer-first) with **Map-based dedup by job_id** (active wins on conflict — handles the 2s/10s poll transition race). Per card: project_name + colored status badge + progress bar (running/paused only) + Intl-formatted started_at. Tap → inline expand with items counters, timestamps, error message (failed only), action buttons per status. Actions: `pauseExtraction / resumeExtraction / cancelExtraction` with `stopPropagation` + `invalidateQueries(['knowledge-jobs'])` on success. **Dropped** per plan: CostSummary, per-status sections, JobDetailPanel, JobLogsPanel, retry-with-new-settings.

`/review-impl` caught **3 MED + 6 LOW + 1 COSMETIC; 3 MED + 5 LOW fixed in-cycle**:
- **M1** duplicate `key` React warning when same job_id appears in both active (2s poll, stale) + history (10s poll, fresh) during running→complete transition → Map dedup with active-wins-on-conflict + regression test.
- **M2** Resume + Cancel API paths completely untested — only Pause was exercised, so runAction's if/else-if/else branch swap would pass → 2 new tests clicking each + asserting correct mock called.
- **M3** `queryClient.invalidateQueries` contract untested (same gap class as ProjectsMobile refetch) → `vi.spyOn(QueryClient.prototype, 'invalidateQueries')` + assertions on all 3 actions + NOT-called on failure.
- **L4** stopPropagation batch coverage on Resume + Cancel · **L5** action-failure toast · **L6** project_name null fallback · **L7** same-status sort tiebreaker · **L9** historyError branch — all added.
- Accepted: **L8** progress-bar edge cases (BE data-error territory) · **C10** memoization `?? []` dep instability (minor perf).

**5th cycle in a row** `/review-impl` paid meaningful dividends. **M1 is notable** — it's a real production bug (React key collision + potential render drop), not just a coverage gap. The pattern of active+history merging should carry a dedup step any time the caller flattens them.

**What Cycle ε / final cycle inherits:**
- All 3 mobile variants (Global / Projects / Jobs) live
- `lib/touchTarget.ts` with `TOUCH_TARGET_CLASS` applied across mobile variants
- `components/mobile/` convention stable
- Stub pattern proven: data-testid buttons inside stubs expose swallowed callbacks
- `vi.spyOn(QueryClient.prototype, 'invalidateQueries')` pattern for verifying react-query contract

**Remaining K19f work:**
- **K19f.5** full tap-target audit across existing desktop components — sweep `grep -r 'py-1\|py-1.5\|h-6\|h-7'` for sub-44px interactive elements. Deferrals D-K19d-β-01 (EntitiesTable mobile grid) + D-K19e-β-02 (Timeline responsive) remain open but are hidden behind the desktop-only banner on mobile, so fixing them is not a K19f gate.

**Test deltas at δ end:**
- FE knowledge+pages vitest: **320 pass** (was 303 at K19f γ end; **+17** = 10 initial + 7 /review-impl regression)
- `tsc --noEmit` clean

---

### Cycle 22 — K19f Cycle γ [FE L] — ProjectsMobile (K19f.2)

Ships the second simplified mobile variant. Stacked card list reusing `useProjects(false)`: name + project_type badge + extraction_status badge (5-value raw status, NOT the 13-state machine) + description preview. Tap card toggles inline expand showing full description + Intl-formatted last_extracted_at + embedding_model + Build button (reuses existing BuildGraphDialog with `stopPropagation` keeping the card expanded). Dropped per plan: Create/Edit/Archive/Delete dialogs + all 13-state-machine action buttons.

`/review-impl` caught **1 MED + 4 LOW; all 5 fixed in-cycle**:
- **M1** `onStarted` → `refetch()` contract completely untested — initial BuildGraphDialog stub didn't expose the callback. Fixed by expanding stub with `simulate-build-started` button + regression test asserting `refetch` called.
- **L2** raw ISO `last_extracted_at` (same pattern K19e γ-b fixed for drawer created_at) → `Intl.DateTimeFormat` helper.
- **L3** empty-description fallback branch untested → test with `description: ''` asserts `noDescription` renders.
- **L4** truncate long-path untested → 200-char description test asserts `…` present + full 200-A's not present.
- **L5** `onOpenChange(false)` dialog-close path untested → stub exposes `simulate-close` button + regression test asserts dialog unmounts.

**Retro — 4th cycle in a row where /review-impl caught a stub-test coverage pattern.** The pattern is now clearly documented: test stubs for complex children should expose the callback props the parent contracts with, not just the render shape. A "happy div" stub that swallows callbacks hides the contract.

**What Cycle δ (JobsMobile) inherits:**
- `components/mobile/` convention established
- `lib/touchTarget.ts` with `TOUCH_TARGET_CLASS` constant applied to all interactive elements
- Stub pattern: expose callback props via `data-testid` buttons inside the stub so tests can drive them
- Keep desktop dialogs as-is (cramped but functional) unless mobile UX becomes painful
- i18n pattern: `mobile.<variantName>.*` sub-block + MOBILE_KEYS iterator extension per cycle

**Test deltas at γ end:**
- FE knowledge+pages vitest: **303 pass** (was 291 at K19f β end; **+12** = 8 core + 4 /review-impl regression)
- `tsc --noEmit` clean

---

### Cycle 21 — K19f Cycle β [FE L] — GlobalMobile (K19f.4) + tap-target utility

Ships the first simplified mobile variant. 150-line `GlobalMobile` keeps textarea + save + char count + unsaved badge; drops per plan: Reset, Regenerate, Versions, PreferencesSection, token estimate, version counter. **Keeps If-Match conflict handling** — dropping would let a mobile save silently stomp a desktop edit. NEW `lib/touchTarget.ts` exports `TOUCH_TARGET_CLASS = 'min-h-[44px]'` constant as K19f.5 audit groundwork; save button is first consumer. NEW `components/mobile/` directory (future home for ProjectsMobile + JobsMobile). MobileKnowledgePage swaps `<GlobalBioTab />` → `<GlobalMobile />`. 8 i18n keys × 4 locales.

`/review-impl` caught **1 HIGH + 2 LOW + 1 COSMETIC; all 4 fixed in-cycle**:
- **H1** 412 "regression test" used a plain-object mock error that failed `isVersionConflict`'s `err instanceof Error` type guard → took generic-error else branch, passed for wrong reason. Fixed via `makeConflictError` helper building a proper `Error` with `.status=412` and `.body={content,version}`, plus 2-click pattern asserting `expectedVersion` advances 3→4 on retry (STRONG signal the baseline absorbed).
- **L2** no assertion that `TOUCH_TARGET_CLASS` is applied to save → regression could ship 32px button; fixed with `expect(save.className).toContain('min-h-[44px]')`.
- **L3** whitespace-only save branch untested → added test verifying `"   "` → `{content: ''}` payload.
- **C4** `UseSummariesReturn = ReturnType<typeof useSummariesMock>` resolved to `undefined` → replaced with explicit `HookReturn` interface.

**Retro — third cycle in a row where /review-impl caught a test that passed for the wrong reason.** Pattern is now clear: any regression test that claims to lock a defensive branch must PROVE the branch ran (via observable downstream state change), not just that "the error path didn't crash."

**What Cycle γ (next) inherits:**
- `lib/touchTarget.ts` available — apply `TOUCH_TARGET_CLASS` to every interactive element in ProjectsMobile
- `components/mobile/` directory convention established
- i18n pattern: `mobile.<variantName>.*` sub-blocks + MOBILE_KEYS iterator extensions per-cycle
- MobileKnowledgePage swap pattern: replace desktop tab import with mobile variant, update test stub

**Test deltas at β end:**
- FE knowledge+pages vitest: **291 pass** (was 286 at K19f α end; **+5** = 4 GlobalMobile tests + 1 whitespace test; HIGH fix strengthened existing test without adding one)
- `tsc --noEmit` clean

---

### Cycle 20 — K19f Cycle α [FE L] — Mobile shell (K19f.1 MVP)

Opens the K19f Mobile UI cluster. NEW `useIsMobile` hook via `window.matchMedia('(max-width: 767px)')` with synchronous first-render read (no FOUC) + live `change` listener + SSR-safe guards + listener cleanup. NEW `MobileKnowledgePage` single-column shell: 3 stacked sections (Global bio / Projects / Extraction jobs) **reusing existing desktop tab components inline** + "use desktop for Entities/Timeline/Raw" banner + Privacy footer link. NEW `MobilePrivacyShell` renders just PrivacyTab body + back link — avoids the 7-tab desktop nav overflowing on <768px. KnowledgePage guard: `if (isMobile) { if (privacy) <MobilePrivacyShell /> else <MobileKnowledgePage /> }`.

`/review-impl` (user-invoked) caught **2 MED + 1 COSMETIC; both MEDs fixed in-cycle**:
- **M1** mobile + /knowledge/privacy fell through to desktop render shipping the 7-item tab nav → added `MobilePrivacyShell` component + dedicated mobile-privacy branch + `mobile.backToKnowledge` i18n × 4 + regression test asserting `queryByRole('tablist') === null`
- **M2** KnowledgePage had zero test coverage for the new mobile guard → created `pages/__tests__/KnowledgePage.test.tsx` with 4 branch tests (desktop / mobile-non-privacy / mobile-privacy / desktop-privacy) mocking `useIsMobile`
- **C3** mid-effect `setIsMobile(mql.matches)` is defensive-only no-op in production → accepted as documented

Scope-trim deferrals (from CLARIFY):
- **K19f.2/.3/.4** separate `ProjectsMobile/JobsMobile/GlobalMobile` simplified variants — MVP reuses existing tabs inline; build variants when the cramp becomes a real UX problem
- **K19f.5** tap-target audit (44px minimum) — do during Cycle β when mobile variants land
- **D-K19d-β-01 + D-K19e-β-02** mobile-responsive EntitiesTable + Timeline grids — those tabs are **hidden** on mobile via the desktop-only banner, so fixing their grids waits for mobile variants for those tabs

**What Cycle β (next) inherits:**
- `useIsMobile` hook + `MobileKnowledgePage` / `MobilePrivacyShell` components exist and are stable
- Embedded desktop tabs render inside sections — if ProjectRow / JobRow feel cramped at 375px, swap those for simpler mobile card variants
- Dialog `max-w-md` (448px) overflows on 375px phones — Radix pads the viewport but content may be squished; candidate for dialog-level responsive tweaks
- No automated tap-target coverage — K19f.5 audit is manual or via Playwright

**Test deltas at K19f α end:**
- FE knowledge vitest: **286 pass** (was 271 at K19e γ-b end; **+15** = 3 hook + 4 mobile-page [incl MobilePrivacyShell M1 regression] + 4 KnowledgePage + 4 iterator assertions)
- `tsc --noEmit` clean

---

### Cycle 19 — K19e Cycle γ-b [FE XL] — RawDrawersTab consuming γ-a endpoint

Ships the user-facing Raw drawers tab on top of γ-a's BE. NEW `useDrawerSearch` hook (userId-scoped queryKey per K19d β M1, disabled-gate via `project_id + query.length >= 3`, retry:false). NEW `DrawerResultCard` presentational with colored source-type badge (chapter/chat/glossary) + amber hub badge + Intl-clamped match-% + full a11y. NEW `DrawerDetailPanel` Radix slide-from-right mirroring K19d β EntityDetailPanel pattern with full text + metadata grid + `Intl.DateTimeFormat` on `created_at`. NEW `RawDrawersTab` container with **8 render branches** (no-project / no-query / short-query / loading / retryable-error+Retry / non-retryable-error+fix-config / not-indexed / empty / results) + 300ms debounce + retry-invalidates-prefix + `disabled={isFetching}` anti-double-fire.

**KnowledgePage swaps** `<PlaceholderTab name="raw" />` for `<RawDrawersTab />` **and removes PlaceholderTab + PlaceholderName entirely** — **every knowledge tab is now live**. The whole `placeholder.*` i18n block is deleted from all 4 locales, with a regression test asserting `bundle.placeholder === undefined`.

`/review-impl` (user-invoked) caught **3 LOW + 2 COSMETIC; ALL 5 fixed in-cycle**:
- **L1** no test proved 300ms debounce actually debounced rapid keystrokes (a regression to 0ms would have passed all 6 initial tests) → new test fires 5 rapid onChange events, asserts calls=1 with final query="bridge"
- **L2** `is_hub` field came over the wire but was never rendered → amber "Summary" badge on card + hub metadata row on detail panel + 4 new i18n keys × 4 locales
- **L3** raw ISO string in `created_at` → `formatCreatedAt` using `Intl.DateTimeFormat`
- **C4** redundant `&& queryActive` guard on `isLoading` (react-query's `enabled:false` already keeps it false) → removed
- **C5** error-banner could render empty string on oddly-shaped payloads → `?? t('drawers.unknownError')` fallback + new i18n key × 4 locales

Build-time catches: `jsx-a11y/button-name` lint on `<Dialog.Close asChild><button><X/></button></Dialog.Close>` (Radix merges props but lint doesn't see it) → moved `aria-label` + added `title` directly on the inner `<button>`; **fake-timers** for debounce test broke react-query's internal `setTimeout` causing cross-test cascade timeouts → switched to real timers + `waitFor`; initial project-dropdown tests fired `fireEvent.change` before `useProjects` options rendered (silent no-op) → added `selectProject` helper awaiting `findByRole('option')` first.

**What K19e Cycle γ-c / δ would inherit (if ever built):**
- Source-type filter UI on search — blocked on D-K19e-γa-01 BE fix
- Term highlighting in preview — D-K19e-γb-01
- Delete drawer (K19e.6), facts list + edit (K19e.7/.8) — separate BE work

**Test deltas at γ-b end:**
- FE knowledge vitest: **271 pass** (was 253 at K19e β end; **+18** = 3 hook + 7 tab incl debounce + 8 iterator assertions)
- `tsc --noEmit` clean

**K19e cluster 100% plan-complete** (K19e.1/.2/.3/.4/.5 shipped; K19e.6/.7/.8 deferred; K19e.9 i18n covered per-cycle; K19e.10 empty/loading states shipped).

---

### Cycle 18 — K19e Cycle γ-a [BE L] — Drawer search endpoint (K19e.5)

Opens the Raw-drawers sub-cluster. Ships the public `GET /v1/knowledge/drawers/search?project_id=&query=&limit=` endpoint — semantic search over `:Passage` nodes reusing proven K18.3 machinery 1-to-1 (no new Cypher). Server-side flow:

1. `ProjectsRepo.get(user_id, project_id)` → 404 on cross-user/missing
2. If project has no `embedding_model` → 200 `{hits:[], embedding_model:null}`
3. If `embedding_dimension` not in `SUPPORTED_PASSAGE_DIMS` → 200 empty
4. `embedding_client.embed(model_source="user_model", model_ref=project.embedding_model)` → 502 `{error_code:"provider_error", retryable:bool}` on `EmbeddingError`
5. Empty provider response (outer OR inner empty) → 200 empty
6. `find_passages_by_vector(include_vectors=False)` → `DrawerSearchHit[]`
7. 502 `{error_code:"embedding_dim_mismatch"}` if live-vs-stored dim disagree

CLARIFY-time scope trim:
- **D-K19e-γa-01** source_type filter (chapter/chat/glossary) — plan K19e.4 mentioned for FE tab layout; needs K18.3 `find_passages_by_vector` extended with new WHERE branch.
- **D-K19e-γa-02** drawer-search embed cost not tracked toward K16.11 monthly budget — hobby-scale $0.00002/search, real at scale.

`/review-impl` (user-invoked) caught **4 LOW + 1 COSMETIC; 3 fixed in-cycle + 1 deferred + 1 accepted**:
- **L1** mutable default arg in test helper (`_project_stub()` called at module load shared instance) → sentinel-guarded conditional assignment
- **L3** `retryable` flag on `EmbeddingError` was discarded → propagated onto 502 detail + paired regression tests for both True/False paths
- **L4** empty inner vector (`embeddings=[[]]`) fell through to `find_passages_by_vector` ValueError surfacing misleading `dim_mismatch` 502 → extended empty-short-circuit guard to `not result.embeddings or not result.embeddings[0]` + regression test
- **C5** no explicit test for `include_vectors=False` forwarding → added kwargs assertion
- **L2** deferred as D-K19e-γa-02

Build-time catches (all collection-error on first pytest run): `EmbedResult → EmbeddingResult` (wrong class name), `ProjectType.original → "book"` Literal (not enum), `ExtractionStatus.idle → "disabled"` Literal.

**What K19e Cycle γ-b (next) inherits:**
- `GET /v1/knowledge/drawers/search?project_id=&query=&limit=` → `{hits: DrawerSearchHit[], embedding_model: string | null}` (`hits` carries `id / project_id / source_type / source_id / chunk_index / text / is_hub / chapter_index / created_at / raw_score`)
- FE can render "not indexed yet" banner when `embedding_model === null`
- 502 `retryable: true` means show retry button; `false` means show "fix config" messaging
- `source_type` filter is UI-only today (client-side filter the returned `hits[].source_type`) OR pair with D-K19e-γa-01 BE fix
- Cycle γ-b scope: `useDrawerSearch` hook + `RawDrawersTab` container + `DrawerResultCard` (text preview + full-text slide-over click) + i18n + KnowledgePage swap for PlaceholderName='raw'

**Test deltas at γ-a end:**
- BE unit knowledge-service: **1282 pass** (was 1268 at K19e-α end; **+14** drawers)
- 63/63 router-adjacent unit pass (no regressions)

---

### Cycle 17 — K19e Cycle β [FE XL] — TimelineTab consuming α endpoint

FE consumer on top of Cycle α's BE. Ships the user-facing Timeline tab. New hook `useTimeline` (userId-scoped queryKey per K19d β M1, 30s staleTime, `enabled: !!accessToken`). New presentational `TimelineEventRow` with inline expand — event_order / title / chapter-short / up-to-3 participants chips + `+N more` overflow / confidence clamped to [0,100]. New container `TimelineTab` with project filter + prev/next pagination + loading/error/empty states + past-end escape hatch ("Back to first page" button when `total>0 && events=[] && offset>0`). KnowledgePage swaps PlaceholderTab for TimelineTab and narrows PlaceholderName to `'raw'` only. 20 i18n keys × 4 locales + `placeholder.bodies.timeline` removed from all 4 locales + TIMELINE_KEYS iterator locks both additions AND removal.

`/review-impl` caught **1 MED + 3 LOW + 2 COSMETIC, all fixed in-cycle:**
- **MED** pagination prev/next were untested — added 3 tests: Next advances offset, Prev re-disables at offset=0, Prev/Next both disabled when total fits one page.
- **L2** no `enabled: !!accessToken` regression test — added `renderHook` with `accessToken: null` asserting mock never called.
- **L3** `formatConfidence` didn't clamp to [0,100] — `Math.max(0, Math.min(100, pct))` defense vs data drift.
- **L6** stale-offset race when total shrinks below offset — added escape-hatch button + new `timeline.pagination.backToFirst` i18n key × 4 locales.
- **COSMETIC #4** duplicate `data-testid="timeline-event"` on outer `<li>` — removed.
- **COSMETIC #5** `_eventStub` underscore prefix misleading — renamed `EVENT_STUB`.

Build-time catches: `aria-expanded={boolean}` lint → switched to explicit `'true'|'false'` string; pagination tests initially used `mockClear()` + call-count assertions that raced with react-query's in-flight resolution → rewrote to assert DOM state transitions (Prev button disabled/enabled) which tests the actual user-visible contract.

**What Cycle γ (the next K19e piece) now inherits:**
- Range inputs for `after_order` / `before_order` can drop straight into TimelineTab — the hook already accepts them.
- Entity-scope drill-down requires BE work first (D-K19e-α-01 deferral).
- Chapter title resolution still shows raw UUID short form (D-K19e-β-01).
- Raw drawers tab is the next FE-only big piece (K19e.4+).

**Test deltas at K19e Cycle β end:**
- FE knowledge vitest: **253 pass** (was 232 at K19d γ-b end; **+21** = 4 hook + 9 tab + 8 iterator/placeholder-removal)
- `tsc --noEmit` clean

---

### Cycle 16 — K19e Cycle α [BE L] — Timeline list endpoint (K19e.2)

Opens the K19e Timeline + Raw-drawers cluster. BE foundation only; β ships the FE TimelineTab consuming this endpoint. CLARIFY-time scope trim:

- Shipped: `GET /v1/knowledge/timeline?project_id=&after_order=&before_order=&limit=&offset=` → `{events, total}`. JWT user-scoped, archived excluded, 2-query count+page split (O(limit) memory), stable pagination via `title ASC, id ASC` tiebreaker, 422 on reversed range.
- **D-K19e-α-01** `entity_id` filter deferred — `:Event.participants` stores display names; needs entity lookup. Natural fit for Cycle β/γ when FE drill-down lands.
- **D-K19e-α-02** ISO wall-clock `from`/`to` deferred — :Event has no date field; narrative `event_order` is the MVP axis.
- **D-K19e-α-03** `chronological_order` range deferred — let Cycle β FE decide if two-axis toggle is worth the UX.

`/review-impl` (user-invoked before COMMIT) caught **3 LOW** findings, all fixed in-cycle:
- **L1** integration test `_limit_clamped_to_max` seeded only 5 events so a removed clamp would still pass — replaced with 2 unit tests patching `run_read` to assert the exact `$limit` kwarg forwarded to Cypher (both clamp-fires and pass-through branches).
- **L2** no `event_user_project (user_id, project_id)` composite index on :Event even though `entity_user_project` exists — added to `neo4j_schema.cypher`, cleared **P-K19e-α-01**.
- **L3** unused `logger = logging.getLogger(__name__)` in `timeline.py` (read-only endpoint) — removed.

**What Cycle β (FE) now inherits:**
- `knowledgeApi.listTimeline({ projectId, afterOrder, beforeOrder, limit, offset })` wrapper to write.
- `{events: Event[], total: number}` response shape.
- `Event` type mirrors the BE Pydantic — re-use the K19d `Entity` pattern (fields: id, title, chapter_id, event_order, participants, summary, confidence, evidence_count, mention_count).
- 422 on reversed range → surface as toast + clear range input.
- No entity drill-down on BE yet — FE table can list entity names but can't filter by them.
- Schema index exists; project-scoped browse is cheap.

**Test deltas at K19e Cycle α end:**
- BE unit knowledge-service: **1268 pass** (was 1258 at K19d γ-b end; +10 net = 11 timeline - 1 weak integration test deleted)
- BE integration timeline: **11/11 live** against `infra-neo4j-1`
- 23/23 K11.7 events adjacent no regressions
- 49/49 router-adjacent no regressions from `main.py` change

---

## Session 50 — 15 cycles shipped (13 Track 3 + 2 Track 2 close-out) · K19b + K19c + K20 + K19d all 100% plan-complete

```
Track 3 K19b progress (session 50)

Cycle 1  K19b.1 + K19b.4    User-scoped jobs endpoint + hook + JobProgressBar    1c208ce + c79ea90
                            BE: list_all_for_user repo + GET /v1/knowledge/extraction/jobs
                            FE: listAllJobs, useExtractionJobs hook (2s/10s dual-poll),
                                JobProgressBar (6 statuses, indeterminate, Intl USD format)

Cycle 2  K19b.2 + K19b.7-    ExtractionJobsTab + project_name + jobs.* i18n      4fb8b62
         partial             BE: ExtractionJob +project_name + LEFT JOIN
                             FE: ExtractionJobsTab (4 sections, native <details>,
                                 per-group error banners, JobRow with fallback),
                                 jobs.* keys × 4 locales, KnowledgePage wired

Cycle 3  K19b.3 + K19b.5 +   JobDetailPanel (slide-over) + Retry + ETA           5e00f7b
         ETA                 FE-only. NEW useJobProgressRate (EMA hook, α=0.3,
                             60s stale-reset, module-scoped Map<jobId> shared
                             across hook instances). NEW JobDetailPanel (Radix
                             slide-from-right, metadata grid, Pause/Resume/Cancel
                             actions, error block, conditional Retry CTA). MOD
                             BuildGraphDialog +initialValues prop for retry
                             pre-fill. MOD ExtractionJobsTab wires row click
                             (role=button + Enter/Space), panel + retry state
                             (R1 single retryIntent, R2 close panel on retry,
                             R3 retry only for status=failed). +17 i18n keys
                             × 4 locales. Clears D-K19b.4-01 (ETA).

Cycle 4  K16.12 completion   Track 2 close-out. User-wide budget API.            b313c1b

Cycle 5  K19b.6 + D-K19a.5-03 CostSummary card + monthly-remaining hint           32a9a18

Cycle 6  D-K16.11-01         Wire budget helpers into production                 c9f7064
         [BE M]               extraction.py step 2.6 calls can_start_job +
                              check_user_monthly_budget with estimated_cost =
                              max_spend_usd ?? 0; 409 structured detail
                              (monthly_budget_exceeded / user_budget_exceeded).
                              worker-ai runner.py +_record_spending inline
                              helper (CASE-on-current_month_key rollover) +
                              called after every successful chapters / chat
                              extraction. Production current_month_spent_usd
                              now populates as jobs run → CostSummary card
                              finally shows real prod spending.

Cycle 7  K19b.8               Extraction-job log viewer MVP                       526533d

Cycle 8  K19c Cycle α          BE preload: user-scope entities endpoint           a619b5f

Cycle 15 K19d Cycle γ-b        Merge endpoint + FE edit/merge dialogs             c9aaf95
         [FS XL]                BE: merge_entities helper + MergeEntitiesError
                                with 4 codes (same_entity/entity_not_found/
                                entity_archived/glossary_conflict) + 6 Cypher
                                blocks (load/validate, collect both-direction
                                edges, UNWIND batch MERGE with Python-driven
                                relation_id recomputation, EVIDENCED_BY
                                rewire on job_id, target metadata update with
                                glossary pre-clear to dodge UNIQUE constraint,
                                DETACH DELETE source, Python post-dedupe).
                                NEW POST /v1/knowledge/entities/{id}/
                                merge-into/{other_id} with 400/404/409 error
                                envelope. FE: NEW useUpdateEntity + useMerge
                                Entity hooks with closed-union error codes +
                                source detail cache eviction on merge. NEW
                                EntityEditDialog (name/kind/aliases textarea
                                with trim+dedupe + no-op skip). NEW
                                EntityMergeDialog with search-to-select
                                target picker (reuses useEntities, filters
                                out source, FE min-2-char). EntityDetailPanel
                                gets Edit/Merge icon buttons + mounted child
                                dialogs. 37 i18n keys × 4 locales + ENTITIES
                                _KEYS iterator +148 cross-locale assertions.
                                /review-impl caught H1 (source self-relation
                                silently dropped — rewired then cascade-
                                deleted) fixed in-cycle with regression test.
                                M1/M2/M3 deferred (D-K19d-γb-01 ON MATCH
                                union gap, D-K19d-γb-02 non-atomic multi-
                                write, D-K19d-γb-03 post-merge canonical_id
                                mismatch — fundamental architectural).
                                Build-time fix: UNIQUE(glossary_entity_id)
                                violation when both source and target
                                transiently held same anchor → clear source
                                first in same SET statement. BE unit 1258
                                (+5 merge routes). Integration 23/23 live
                                (+9 merge scenarios). FE knowledge 232 (+14
                                = 5 hook + 5 edit + 4 merge dialog). tsc
                                clean; no unhandled rejections after wrapping
                                mutation calls in try/catch. K19d cluster
                                100% plan-complete. K19d.8 graph viz stays
                                optional per plan.

Cycle 14 K19d Cycle γ-a        PATCH entity + user_edited lock [BE half of γ]    5d42afd + db405f6
         [BE L]                 Entity.user_edited: bool = False + _MERGE_ENTITY_
                                CYPHER ON CREATE user_edited=false + ON MATCH
                                aliases CASE coalesce(user_edited,false)=true
                                gate (coalesce handles pre-γ-a nodes as
                                un-edited so existing extraction preserved).
                                NEW update_entity_fields helper + _UPDATE_ENTITY
                                _FIELDS_CYPHER per-field CASE (null=leave,
                                else overwrite) + canonical_name recomputed on
                                name change. NEW PATCH /v1/knowledge/entities/
                                {id} endpoint with EntityUpdate Pydantic:
                                at-least-one model_validator + per-alias
                                non-empty + ≤200 char + max 50. 404 on
                                cross-user/missing. Merge (K19d.6) split to
                                γ-b because RELATES_TO edges carry deterministic
                                IDs derived from subject_id → per-edge MERGE-
                                new+DELETE-old surgery is complex enough for
                                its own cycle. /review-impl L1 fixed (inline
                                // Cypher comments were first-in-codebase →
                                moved to Python #); M1 (no If-Match optimistic
                                concurrency, D-K19d-γa-01) + M2 (no unlock
                                mechanism for user_edited, D-K19d-γa-02)
                                deferred. Build-time catch: "The Phoenix" test
                                variant didn't hit ON MATCH branch because
                                "the" isn't in HONORIFICS strip list → switched
                                to "Master Phoenix" (master is stripped →
                                same canonical_id). BE unit 1253 (+4).
                                Integration entities browse 14/14 live (+4
                                γ-a scenarios incl user_edited-lock regression
                                + pre-γ-a regression). K19d γ-b (merge + FE
                                edit/merge dialogs + CTAs + i18n, ~12 files XL)
                                is the only K19d work remaining.

Cycle 13 K19d Cycle β          Entities tab FE (table + detail panel)            aeb008b + c920d95
         [FE XL]                NEW useEntities + useEntityDetail hooks (userId-
                                scoped queryKeys per review-impl M1, 30s/10s
                                staleTime). NEW EntitiesTable presentational
                                (a11y: role=row + tabIndex + onKeyDown for
                                Enter/Space). NEW EntityDetailPanel Radix Dialog
                                slide-from-right (metadata grid + aliases chips
                                + relations partitioned outgoing/incoming with
                                per-row ↗/↙ arrows + truncation banner +
                                pending-validation badge). NEW EntitiesTab
                                container with debounced search (300ms + FE
                                min-2-chars matching BE 422) + prev/next
                                pagination capped at maxOffset + offset-reset
                                on filter change. KnowledgePage replaces
                                PlaceholderTab with EntitiesTab. 38 i18n keys
                                × 4 locales (placeholder.bodies.entities
                                removed everywhere — same pattern as K19b.2
                                jobs removal). ENTITIES_KEYS iterator +152
                                cross-locale assertions. /review-impl caught
                                M1 (cross-tenant cache flash — 30s window
                                where logout→login swap shows prior user's
                                cached entities before refetch); fixed with
                                userId-prefixed queryKey + regression test.
                                M2 (mobile grid breaks <800px) deferred as
                                D-K19d-β-01 (K19f scope). Build-time fixes:
                                useDebounced with useMemo (leak) → useEffect;
                                useProjects.items not .projects. FE knowledge
                                218 (+15). tsc clean. K19d γ (edit/merge)
                                remains the only K19d work left.

Cycle 12 K19d Cycle α          Entities browse + detail BE [α of β/γ split]      96f9b6b + e0fbd21
         [BE L]                 NEW entities_router at /v1/knowledge prefix +
                                2 JWT-scoped endpoints: GET /entities (filters:
                                project_id/kind/search min-2ch/limit/offset) +
                                GET /entities/{id}. New neo4j repo funcs:
                                list_entities_filtered (2-query count+page split
                                per review-impl M1 for O(limit) memory) +
                                get_entity_with_relations (OPTIONAL MATCH +
                                collect-inside-subquery for 0-relations case).
                                EntityDetail Pydantic reuses existing Relation
                                subject/object projection. Anti-leak: cross-user
                                detail 404 per KSA §6.4. /review-impl caught
                                M1 (pagination materialized full tenant row-set
                                in memory to count) + L1 (entity_id Path had
                                no length cap); both fixed in-cycle with
                                regression tests. Build-time bug: plain CALL
                                subquery with MATCH drops outer row when inner
                                has 0 rows — fixed with OPTIONAL MATCH + collect
                                inside. BE unit 1249 (+10). Integration entities
                                browse 10/10 live. β (FE EntitiesTab + detail
                                panel) + γ (edit/merge) pending. P-K19d-01
                                logged (Neo4j fulltext index when entity count
                                crosses ~10k per user).

Cycle 11 K20 Cycle β+γ         FE consumer + metrics + dup check [K20 complete]   9289ded + 166c9e1
         [FS XL]                BE: metrics.py +4 series (regen_total{scope_type,
                                status}×12 pre-seeded labels + duration histogram
                                + cost_usd + tokens). regenerate_summaries.py
                                split into outer metrics wrapper + inner logic
                                (every status branch bumps counter once); +step
                                6b past-version dup check via list_versions(
                                limit=20) + same 0.95 jaccard threshold;
                                +_compute_llm_cost_usd helper + happy-path
                                cost/token recording. +8 unit tests. FE: NEW
                                useRegenerateBio hook with parseRegenerateError
                                closed-union errorCode from body.detail
                                .error_code + invalidates [SUMMARIES_KEY +
                                VERSIONS_KEY]; NEW RegenerateBioDialog reusing
                                BuildGraphDialog's ['ai-models', 'chat']
                                queryKey for cache share + inline banner for
                                user_edit_lock + distinct toasts for
                                concurrent/guardrail/provider/unknown + info
                                toast for similarity/empty-source. api.ts
                                +RegenerateRequest/Response + regenerateGlobalBio
                                wrapper. GlobalBioTab +Regenerate button
                                disabled={dirty} per review-impl H1 (without
                                guard the existing dirty-protection useEffect
                                would silently preserve local buffer over a
                                successful server regen). 21 new i18n keys ×
                                4 locales + GLOBAL_KEYS extension (+84 cross-
                                locale assertions). /review-impl caught H1
                                (dirty-textarea race), M1 (queryKey
                                fragmentation with BuildGraphDialog), L1
                                (dialog test coverage gap on 3 error paths);
                                all fixed in-cycle. BE unit 1239 (+8). FE
                                knowledge 203 (+13 = 5 hook + 8 dialog).
                                Drift integration 6/6 still live. K20 cluster
                                effectively complete — only K20.3 scheduler
                                + D-K20α-01 budget-integration half +
                                D-K20α-02 per-scope cooldown remain deferred.

Cycle 10 K20 Cycle α           BE regen helpers + public edge [unblocks K19c.2]   71530a1 + 5faaf08
         [BE L]                 NEW app/jobs/regenerate_summaries.py with 6-status
                                RegenerationResult (regenerated / no_op_similarity
                                / no_op_empty_source / no_op_guardrail /
                                user_edit_lock / regen_concurrent_edit) per KSA
                                §7.6. Drift rules: reads raw :Passage text not
                                current summary; 30-day manual-edit lock;
                                diversity check via word-set jaccard > 0.95; K20.6
                                MVP guardrails (empty / token_overflow / K15.6
                                injection) rejecting LLM output. NEW internal
                                endpoint `POST /internal/summarize` +
                                public edges `POST /v1/knowledge/me/summary/
                                regenerate` + `POST /v1/knowledge/projects/{id}/
                                summary/regenerate` (both JWT-scoped; 200/409/
                                422/502 HTTP mapping). /review-impl caught:
                                **H1** every regen wrote history as edit_source=
                                'manual' which would trip the 30-day edit lock
                                on the NEXT regen (fixed: EditSource Literal +
                                migration CHECK + SummariesRepo.upsert kwarg all
                                gain 'regen'; regen helper passes it); **M1** no
                                upfront ownership check on project scope (fixed:
                                `_owns_project` SELECT before LLM call).
                                Deferred: K20.3 scheduler, K20.5 rollback
                                endpoint, K20.7 metrics, D-K20α-01 cost
                                tracking, D-K20α-02 per-scope cooldown.
                                BE unit 1231 (was 1195; +36). Drift integration
                                6/6 live against infra-postgres-1 + infra-neo4j-1.

Cycle 9  K19c Cycle β          FE K19c-partial: reset + diff + preferences        8baa670 + 79503f2
         [FE XL]               Installed diff@^9 + @types/diff@^7. api.ts +Entity
                               type + list/archive wrappers. NEW useUserEntities
                               hook. NEW PreferencesSection (list + confirm +
                               archive + prefix-match invalidation with
                               docstring per review-impl L7). GlobalBioTab:
                               +token estimate (chars/4) + Reset button + confirm
                               dialog + <PreferencesSection/> wire below editor.
                               VersionsPanel preview modal: "Show diff vs current"
                               toggle rendering diffLines() chunks with
                               added/removed/context colour classes; useEffect
                               resets toggle per preview. +global.* i18n (26 new
                               keys × 4 locales). GLOBAL_KEYS iterator added
                               (104 cross-locale assertions). Mid-verify fix:
                               static vi.mock factory for useAuth tripped
                               vitest-2 unhandled-rejection detection on one hook
                               error test; switched to dynamic vi.fn() pattern
                               (matches useUserCosts working pattern). Review-impl
                               L7 fixed in-cycle (queryKey prefix-match docstring).
         [BE L]                 list_user_entities(scope='global') Neo4j helper +
                                GET /v1/knowledge/me/entities?scope=global +
                                DELETE /v1/knowledge/me/entities/{id} (reuses
                                archive_entity, idempotent per RFC 9110). Unblocks
                                K19c.4 FE in Cycle β. Prior audit found:
                                K19c.2 still BLOCKED on K20.x; K19c.1/.3 have
                                partial Track 1 coverage (GlobalBioTab +
                                VersionsPanel); this cycle strictly scopes to the
                                missing BE surface. /review-impl L6 caught
                                DELETE docstring lie about non-idempotent 404
                                (fixed + integration test locks contract).
         [FS XL]               BE: NEW job_logs table (BIGSERIAL + CHECK level +
                               FK CASCADE) + JobLogsRepo (append + cursor list)
                               + GET /v1/knowledge/extraction/jobs/{id}/logs
                               with since_log_id/limit pagination + 404 on
                               cross-user. Worker: _append_log inline helper +
                               5 lifecycle call sites (chapter_processed,
                               chapter_skipped, retry_exhausted, auto_paused,
                               failed). FE: listJobLogs API + useJobLogs hook
                               (staleTime 10s single-page) + NEW JobLogsPanel
                               collapsible inside JobDetailPanel. jobs.detail.
                               logs.* × 4 locales. 3 follow-up deferrals:
                               D-K19b.8-01 retention cron, D-K19b.8-02
                               orchestrator-side logs, D-K19b.8-03 tail-follow.
         [FE XL]              FE-only. NEW useUserCosts hook (staleTime 60s,
                              user_id-scoped queryKey). NEW CostSummary.tsx
                              with inline EditBudgetDialog (decimal regex
                              matches BE NUMERIC(10,4), progress bar colors
                              at 80%/100% thresholds). NEW shared
                              lib/formatUSD.ts after /review-impl caught
                              inconsistent formatting between CostSummary +
                              BuildGraphDialog. Wired into ExtractionJobsTab
                              top. BuildGraphDialog renders monthly-remaining
                              hint near max_spend via useUserCosts (clears
                              D-K19a.5-03). +17 costSummary.* keys + 1
                              maxSpend.monthlyRemaining × 4 locales.
         [BE L]              NEW user_knowledge_budgets table + UserBudgetsRepo
                             (get+upsert). Extended UserCostSummary response
                             with monthly_budget_usd + monthly_remaining_usd
                             (clamped >=0). NEW PUT /v1/knowledge/me/budget
                             endpoint (ge=0, null clears). NEW
                             check_user_monthly_budget helper in budget.py
                             (aggregates across user's projects, stale-month
                             filter). NEW idx_knowledge_projects_user_all
                             covering index for archived-inclusive scans.
                             Unblocks D-K19a.5-03 (monthly budget remaining
                             context in BuildGraphDialog). K19b.6 now has
                             everything it needs on the BE side.

Remaining K19 residuals: K19b.7-rest (other tabs' strings); K19c
                        partial (Cycle α shipped BE; Cycle β ships FE
                        deltas); K19d Entities tab (can reuse entities
                        endpoint pattern from Cycle α); K19e Raw tab.
                        K19b 100% PLAN-COMPLETE.
                        K19c.2 Regenerate still BLOCKED on K20.x.
```

**Test deltas at session 50 end (after 9 cycles):**
- Frontend knowledge: **190 pass** (was 112 at session 49 end; +78 over 6 FE cycles)
- Backend unit knowledge-service: **1195 pass** (was 1154 at session 49 end; +41 — no BE in Cycle 9)
- Backend unit worker-ai: **17 pass** (was 13 at K19b.6 end; +4 across Cycles 6+7)
- Backend integration: 30 extraction_jobs_repo + 5 user_knowledge_budgets + 5 job_logs + **6 list_user_entities** (new this cycle, against live Neo4j)
- Cycle 1 /review-impl: 5 LOW all fixed + 1 MED via review-code
- Cycle 2 review-code: 1 LOW fixed; /review-impl: 4 LOW all fixed
- Cycle 3 review-code: 2 LOW fixed; /review-impl skipped per human approval
- Cycle 4 review-code: 3 LOW accepted; /review-impl: 3 LOW all fixed
- Cycle 5 review-code: 1 LOW fixed; /review-impl: 1 LOW fixed
- Cycle 6 review-code: 10 LOW all accepted; /review-impl skipped per human approval
- Cycle 7 review-code: 1 LOW fixed; /review-impl skipped per human approval
- Cycle 8 review-code: 4 LOW accepted; /review-impl: 1 MED-doc fixed (DELETE idempotent-docstring lie + integration lock-in)
- Cycle 9 review-code: 6 LOW accepted; /review-impl: 1 LOW fixed (prefix-match queryKey invalidation docstring)

**What shipped in Cycle 3 (10 files, FE-only):**
- NEW `useJobProgressRate.ts` hook (EMA rate tracker, 6 tests)
- NEW `JobDetailPanel.tsx` (Radix slide-over with metadata grid + Pause/Resume/Cancel + conditional Retry, 6 tests)
- MOD `BuildGraphDialog.tsx` (+`initialValues` prop for retry pre-fill, +1 test)
- MOD `ExtractionJobsTab.tsx` (selectedJobId + retryIntent state, JobRow role=button + Enter/Space, retry getProject useQuery with error toast, +3 tests)
- MOD 4 locales (+17 `jobs.detail.*` + `jobs.retry.button` keys each)
- MOD `projectState.test.ts` (JOBS_KEYS +17 paths → 31 × 4 = 124 cross-locale assertions)

### What K19b.8 (next cycle candidate) can assume

**K19b.8 Log viewer** — standalone cycle, not blocked. Scope:
- BE schema: `job_logs(log_id BIGSERIAL PK, job_id UUID FK, user_id UUID, level TEXT, message TEXT, context JSONB, created_at TIMESTAMPTZ)` + index `(user_id, job_id, log_id DESC)` + retention cron (N days).
- Extraction-worker instrumentation at every chunker/extractor/error-path in `services/worker-ai/app/runner.py` keyed by `(user_id, job_id)`. Likely easiest via a custom Python logging handler that writes to the table.
- Public endpoint: `GET /v1/knowledge/extraction/jobs/{id}/logs?since_log_id=&limit=50` with cursor pagination.
- FE: `JobLogsPanel` inside `JobDetailPanel` (or new tab). Tail-follow with auto-scroll toggle. Virtual list for 1000+ lines.
- Size estimate XL; doable as a single cycle or split into BE + FE halves.

### What K19c Cycle β now ships (and what's still blocked)

K19c cluster is plan-complete except K19c.2 (regenerate). GlobalBioTab now
exposes token estimate + Reset button (server-side clear with confirm +
If-Match conflict handling). VersionsPanel preview modal has a diff-vs-current
toggle. New PreferencesSection component below the editor lists global
entities with delete-via-archive flow. See [SESSION_PATCH.md §Current Active
Work](SESSION_PATCH.md#current-active-work) for the detailed file list.

**K19c.2 still blocked on K20.x** — regenerate dialog can't land until K20
ships the `POST /internal/summarize` endpoint plus a public edge for it.

### Historical note — What K19c Cycle β initially assumed (now shipped)

Cycle α shipped the BE. Cycle β consumes:
- **GET** `/v1/knowledge/me/entities?scope=global&limit=50` → `{entities: Entity[]}` (Pydantic from `app/db/neo4j_repos/entities.py::Entity` — fields include `id`, `user_id`, `project_id: null`, `name`, `canonical_name`, `kind`, `aliases`, `confidence`, `updated_at`).
- **DELETE** `/v1/knowledge/me/entities/{entity_id}` → `204` on archive; `404` on cross-user / missing entity. **Idempotent** per RFC 9110 — second DELETE also returns 204.
- Query params validated: `scope: Literal['global']` (422 on invalid), `limit: int` ge=1 le=`ENTITIES_MAX_LIMIT=200`.

Cycle β scope (previously estimated XL, now trimmed by α):
- FE `api.ts`: `Entity` type + `listMyEntities` + `archiveMyEntity` wrappers
- NEW `hooks/useUserEntities.ts` with react-query staleTime pattern
- `GlobalBioTab.tsx`: +Reset button (confirm → clear to empty) + token estimate under char count (simple `content.length / 4` heuristic)
- `VersionsPanel.tsx`: diff viewer in preview modal (install `diff` npm ~4KB or inline line-diff)
- NEW `components/PreferencesSection.tsx`: renders global entities with delete confirm; wires into GlobalBioTab
- Tests + i18n × 4 locales

Cycle β is still ~L-XL; splitting it further if needed.

### K19b 100% plan-complete status

All 8 K19b tasks shipped this session:
- **K19b.1** ✅ (Cycle 1) — user-scoped jobs endpoint + hook
- **K19b.2** ✅ (Cycle 2) — ExtractionJobsTab layout
- **K19b.3** ✅ (Cycle 3) — JobDetailPanel slide-over
- **K19b.4** ✅ (Cycle 1) — JobProgressBar
- **K19b.5** ✅ (Cycle 3) — Retry with different settings
- **K19b.6** ✅ (Cycle 5) — CostSummary card
- **K19b.7-partial** ✅ (all cycles) — jobs.* i18n keys × 4 locales
- **K19b.8** ✅ (Cycle 7) — extraction-job log viewer MVP

**Integration state of the Jobs tab:**
- CostSummary reads real production `current_month_spent_usd` (wired in Cycle 6 via worker `_record_spending`).
- Budget-cap pre-check blocks jobs that would exceed per-project or user-wide monthly caps (Cycle 6).
- JobDetailPanel surfaces 5 lifecycle events via JobLogsPanel (chapter_processed, chapter_skipped, retry_exhausted, auto_paused, failed) alongside progress bar, metadata grid, error block, actions, and conditional retry CTA.
- ETA rendered via client-side EMA (Cycle 3).

**Follow-up polish deferrals** (none block shipping the Jobs tab):
- D-K19b.1-01 cursor pagination when user has >200 historical jobs
- D-K19b.2-01 "Show more" on Complete section
- D-K19b.3-01 human-readable "current item" from cursor
- D-K19b.3-02 humanised ETA formatter for >60min jobs
- D-K19b.8-01 retention cron for job_logs
- D-K19b.8-02 orchestrator-side pipeline logs (chunker/extractor stages)
- D-K19b.8-03 tail-follow auto-polling + load-more in JobLogsPanel

### What K19b.3 (detail panel) already ships — for future cycles consuming it

- `ExtractionJobsTab` rows are presentational, no click handler yet. Add `onClick` to `JobRow`, wire `role="button"` + `tabIndex={0}` + `onKeyDown` for Enter/Space.
- Single-job BE endpoint exists: `GET /v1/knowledge/extraction/jobs/{job_id}` (K16.5, session 47). Supports If-None-Match for 304. Returns `ExtractionJobWire` shape (including `project_name` — **wait**, no: K19b.2's `project_name` only populates via `list_all_for_user`'s LEFT JOIN. The single-job route still returns NULL for it). K19b.3 either (a) passes project_name through from the parent row (simplest, already fetched), (b) enhances the single-job endpoint to JOIN too, or (c) fetches the Project separately. Option (a) is zero-BE.
- `useExtractionJobs` exposes active + history lists. K19b.3's slide-over can look up the clicked job from that list without a second fetch (until poll staleness matters; within 2–10s the list data is fresh enough).
- Slide-over pattern: reuse shadcn `Sheet` component if present; else adapt the `Dialog` pattern from K19a.5 BuildGraphDialog. Keep state in `ExtractionJobsTab` (selectedJobId + onClose), not global.
- Retry CTA (K19b.5) goes INSIDE the slide-over on failed/cancelled jobs: button "Retry with different settings" opens BuildGraphDialog with the failed job's scope/model pre-filled. K19a.5's dialog accepts `initialValues` — verify shape matches.

### What the hook `useExtractionJobs` provides (unchanged from Cycle 1)

- Returns `{ active, history, isLoading, error, activeError, historyError }`.
- Polling: 2s active / 10s history (not-in-background via React Query default). Tab owns no timer logic.
- queryKey scoped `['knowledge-jobs', userId, 'active'|'history']` so logout→login on a shared QueryClient doesn't leak cross-user cache.
- Brief ≤10s transition gap when a job flips `running → complete` between the 2s active poll and the 10s history poll — job temporarily absent from both lists. Acceptable; `ExtractionJobsTab` doesn't mask today but K19b.3 could invalidate `['knowledge-jobs', userId, 'history']` from actions that transition jobs to terminal states.

### K19b.2 i18n boundary

- `knowledge.json` under `jobs.*` holds all K19b.2 strings (`loading`, `error.{active,history}`, `sections.*.{title,empty}`, `row.{started,completed,unknownProject}`).
- JOBS_KEYS iterator in `projectState.test.ts` neutralises the global `react-i18next` mock bypass: 14 paths × 4 bundles = 56 runtime assertions that each locale has the key populated. Any new jobs.* key needs to be appended to `JOBS_KEYS` at test-authoring time.
- `placeholder.bodies.jobs` removed from all 4 locales (the jobs tab is live; placeholder no longer reached). If someone re-introduces a placeholder state for jobs, add the key back.

### Schema-recovery lesson (session 50 Cycle 2)

The `test_k19b_2_list_all_project_name_null_when_join_misses` test initially used `ALTER TABLE DROP CONSTRAINT ... / ADD CONSTRAINT ...` to orphan a row. A mid-test failure left the DB with the FK removed AND orphan extraction_jobs rows, which meant the pool fixture's `TRUNCATE knowledge_projects CASCADE` couldn't cascade-clean extraction_jobs (no FK to cascade through), and the next run tried to re-ADD the FK against orphan data and failed. Manual recovery: `TRUNCATE extraction_jobs CASCADE` + `ALTER TABLE extraction_jobs ADD CONSTRAINT extraction_jobs_project_id_fkey FOREIGN KEY (project_id) REFERENCES knowledge_projects(project_id) ON DELETE CASCADE`. Rewritten test uses `SET LOCAL session_replication_role = 'replica'` in a transaction — skips FK triggers for writes inside that transaction only, never touches schema, auto-reverts on commit/rollback, zero leak on failure. **Takeaway for future cycles:** avoid DDL (ALTER) in tests when DML-level bypass is available. `session_replication_role`, `DEFERRABLE INITIALLY DEFERRED` constraints, and `DISABLE TRIGGER` (within a transaction) are all safer.

### FS-cycle audit lesson (K19b.1)

The CLARIFY-phase BE audit (per `feedback_fe_draft_html_be_check.md`) caught the user-scoped-list gap before any FE was drafted. Options presented were:
- (a) Reclassify to FS, add new endpoint — chosen
- (b) Expose `list_active` at HTTP layer only, defer history
- (c) Pure-FE N-fanout across `listProjects` + per-project `listExtractionJobs`

Option (a) won because K19b.2's layout sections (Running/Paused/Complete/Failed) map 1:1 to the `status_group` binary, so pushing the filter down to SQL is both cheaper (O(1) query per group) and less code-complex than any FE merging. The option-(c) N-fanout would have worked for a demo but broken at ~10 projects per account. This is exactly the class of call the `feedback_fe_draft_html_be_check.md` rule exists to force before CLARIFY is closed.

### Still deferred after K16.12 completion

- **D-K19b.1-01** → Track 3 polish: cursor pagination for history once users cross ~150 historical jobs.
- **D-K19b.2-01** → Track 3 polish: "Show more" CTA on Complete section (BE ships 50, FE slices 10).
- ~~D-K19b.2-02~~ — **Cleared in K19b.3**.
- ~~D-K19b.4-01~~ — **Cleared in K19b.3**.
- **D-K19b.3-01** → Track 3 polish: human-readable "current item" from cursor. Needs BE cursor enrichment OR FE chapter-title lookup.
- **D-K19b.3-02** → Track 3 polish: humanised ETA formatter for >60min jobs.
- ~~K19b.8~~ — **Cleared in Cycle 7** (MVP shipped). D-K19b.8-01/02/03 tracked below for polish.
- **D-K19b.8-01** → Track 3 polish: retention cron for job_logs (no auto-cleanup today).
- **D-K19b.8-02** → Track 3 polish: orchestrator-side pipeline logs in knowledge-service extract_item handler.
- **D-K19b.8-03** → Track 3 polish: tail-follow auto-polling + load-more in JobLogsPanel.
- **D-K19c.4-01** (new, Cycle 8) → K17/K18 entity-management surface: rename-aware `user_archive_entity` variant that preserves `glossary_entity_id` on archive. Current `archive_entity` clears the FK per its K11.5a scope; fine for user-MVP but imperfect for the "hide now, restore later" flow.
- ~~D-K19a.5-03~~ — **Cleared in K19b.6** (BuildGraphDialog monthly-remaining hint shipped).
- ~~D-K16.11-01~~ — **Cleared in Cycle 6.** Budget helpers wired into production; CostSummary will now populate real figures as jobs run.
- **D-K19a.5-04 + D-K16.2-02b** → Track 3 (paired): chapter_range picker + runner-side enforcement.
- **D-K19a.5-06** → Track 3 polish: `glossary_sync` scope option in BuildGraphDialog.
- **D-K19a.5-07** → Track 3 polish: "Run benchmark" CTA in BuildGraphDialog.
- **D-K19a.7-01** → naturally-next: hook-level action smoke tests for `useProjectState`.
- **D-K19a.8-01** → Track 3 polish: MSW-backed dialog stories.

---

## Session 49 — 4 Track 3 cycles shipped (K19a.5 + K19a.6 + K19a.7 + K19a.8)

```
Track 3 K19a progress (session 49)

Cycle 6  K19a.5  BuildGraphDialog + ErrorViewerDialog          3148751
         + session_handoff HEAD backfill                        1156193
Cycle 7  K19a.6  ChangeModelDialog + destructive confirms +     2226283
                 BE POST /extraction/disable (FS)
         + HEAD backfill                                        7cf394f
Cycle 8  K19a.7  i18n polish (runAction + PrivacyTab + 4        2cbcc7c
                 locales + ACTION_KEYS typo defence)
         + HEAD backfill                                        c6ee80a
Cycle 9  K19a.8  Storybook 10 install + 13 ProjectStateCard     TBD
                 stories (Vite alias @/auth → MockAuth)

Track 3 K19a cluster: 100% complete (8 non-optional + 1 optional)
```

**Test deltas at session 49 end:**
- Frontend knowledge (+ shared ConfirmDialog): **112 pass** (was 75 at session 48 end; +37 content across K19a.5/6/7)
- Storybook: 14 stories build clean; `npm run build-storybook` 10.7s
- BE: +5 new tests (POST /extraction/disable — happy + 404 + 409 active + 409 paused + idempotent no-op)
- /review-impl across all 4 cycles caught **6 MED + 13 LOW + 5 COSMETIC**; every code finding fixed in-cycle except 2 accepted silently (K19a.7 F4 vitest stub churn + K19a.8 F3 Playwright binaries one-time cost); 10 D-K19a.*-* deferrals logged, 2 cleared in K19a.6 (D-K19a.5-01 change-model, D-K19a.5-02 disable-without-delete)

**What shipped:**
- `BuildGraphDialog.tsx` — scope selector (chapters/chat/all, `chapters` hidden when `!book_id`), chat-model dropdown, embedding picker (reuses K12.4), max_spend decimal-validated input, debounced auto-fetch estimate preview, benchmark pre-flight gate, BE-detail error extractor (`readBackendError` exported for unit test).
- `ErrorViewerDialog.tsx` — shared viewer for `failed` + `building_paused_error`. Job metadata grid + pre-wrapped error text + Copy button.
- Wired via `ProjectRow` dialog-state lifting + `useProjectState` stubs becoming silent no-ops. Merge deps narrowed to `errorPayloadKey` so actions don't re-create on poll tick.

### What K19b can now assume

- All 14 `ProjectStateCardActions` callbacks are wired: 9 fire BE APIs (pause/resume/cancel/retry/extractNew/delete/rebuild/confirmModelChange/ignoreStale), 5 open parent-lifted dialogs/confirms (buildGraph/start/viewError/changeModel/disable).
- `ProjectRow` is the canonical merge point for dialog-dependent actions — lift dialog/confirm state, spread `baseActions`, override the relevant callbacks. For destructive actions, route through `runDestructive(PROJECT_ACTION_KEYS.xxx, op, close)` so ConfirmDialog's `loading` prop shows in-dialog spinner + toast carries the right translated label.
- `readBackendError` lives at `frontend/src/features/knowledge/lib/readBackendError.ts` (K19a.6 F7). Any new dialog surfacing 4xx errors should import from there — `apiJson` only reads top-level `.message` but FastAPI wraps as `{detail: ...}`.
- `ChangeEmbeddingModelResponse` is a discriminated union (warning / noop / result); future callers must narrow before treating as success — K19a.6 F2 fixed the silent-success-on-no-op bug.
- `ConfirmDialog` now disables Cancel + X buttons while `loading=true`. Pattern is consistent across all destructive flows.
- `useProjectState` exports `PROJECT_ACTION_KEYS` (K19a.7 F1) — a compile-time map of action → i18n key. Consumers wanting to surface BE errors as localised toasts should import this rather than repeating string literals; typos become build errors.
- Zero hardcoded toast/label/body strings remain in `frontend/src/features/knowledge/` — `grep -r "toast\.(error\|info\|success\|warning)\(['\"]"` confirms. New dialogs should use `useTranslation('knowledge')` from the start.
- Storybook (K19a.8) is installed with 14 stories covering all 13 `ProjectMemoryState` kinds. `npm run storybook` dev-serves at port 6006; `npm run build-storybook` produces a static catalog. `.storybook/main.ts` aliases `@/auth` → `MockAuthProvider` so any future story can render real components that call `useAuth` without wiring it explicitly.
- BE endpoints now cover all Track 3 K19a surfaces:
  - `DELETE /extraction/graph` — destructive delete
  - `PUT /embedding-model?confirm=true` — destructive change-model (deletes graph + disables)
  - `POST /extraction/disable` — **non-destructive** disable (preserves graph)
  - `POST /extraction/rebuild` — destructive rebuild (delete + start fresh job)

### Still deferred after K19a.7

- **D-K19a.5-03** → K19b.6: Monthly budget remaining context in BuildGraphDialog max-spend field (needs BE `/v1/me/usage/monthly-remaining` endpoint).
- **D-K19a.5-04** → paired with D-K16.2-02b: FE chapter_range picker (BE preview honours, runner doesn't — ship both together).
- **D-K19a.5-05** → superseded by D-K19a.7-01: half closed (F1 typo prevention via `ACTION_KEYS` const); other half now tracked as D-K19a.7-01.
- **D-K19a.5-06** → K19a.7 (NOT done in this cycle): `glossary_sync` scope option in BuildGraphDialog (BE accepts, FE doesn't expose). The "K19a.7" polish cycle focused on string i18n, not scope-list expansion. Re-target to Track 3 polish or K19b as convenient.
- **D-K19a.5-07** → Track 3 polish: "Run benchmark" CTA in BuildGraphDialog when `has_run=false` (needs POST endpoint for eval harness).
- **D-K19a.7-01** → naturally-next: hook-level action smoke tests (inherits action-fire-path coverage from D-K19a.5-05).
- **D-K19a.8-01** → Track 3 polish: dialog stories for BuildGraphDialog / ChangeModelDialog / ErrorViewerDialog. Needs MSW handlers for `knowledgeApi` interception. Mock auth already wired via K19a.8 Vite alias.

### FS-cycle payload-audit lesson — response-side variant

K19a.5 F1 surfaced the BE `{detail: {message}}` body-extraction gap. K19a.6 F2 added another class: **response shape ambiguity under idempotent/no-op paths**. The BE `PUT /embedding-model?confirm=true` returns three different shapes — warning (confirm=false), no-op (same-model, either direction), result (confirm=true, different model). FE must narrow the discriminated union before treating as success; otherwise a cross-device race turns a silent no-op into a false "success" UX. For future FS cycles with idempotent BE endpoints: **list every BE response branch at CLARIFY time**, not just the happy path.

### i18n silent-fallback lesson (K19a.7)

i18next silently falls back to the raw key path when a key is missing, so a callsite typo like `t('projects.state.actions.pauze')` doesn't crash — it renders `"projects.state.actions.pauze: rate limit"` in the user-visible toast. Runtime JSON-resource iterators catch missing resources but NOT typos at the callsite. Defence: a compile-time constant map (`ACTION_KEYS` in `useProjectState.ts`) turns every callsite into a TypeScript literal lookup so typos become build errors. For any future i18n-heavy module, introduce the const map up front rather than threading string literals.

### Storybook-init quirks (K19a.8)

`npx storybook@latest init --type react` is aggressive: it modifies `vite.config.ts` to inject `@storybook/addon-vitest` plumbing AND downloads ~200 MB of Playwright browser binaries for that addon — even on a no-install run. For a minimal Storybook-only setup:
1. Use `--skip-install` to avoid committing to deps before review.
2. Edit `package.json` to REMOVE `@storybook/addon-vitest`, `@chromatic-com/storybook`, `addon-onboarding`, `@vitest/browser`, `playwright` before `npm install`.
3. `git checkout HEAD -- vite.config.ts` to undo the vitest-addon workspace plumbing (it adds a `test: {workspace: [...]}` block that references the removed addon).
4. Ctrl-C the prompt that asks to install Playwright browser binaries — it comes AFTER addon config, not at the start.
5. Delete the `src/stories/` example directory (Button/Header/Page scaffold) and `vitest.shims.d.ts` shim file.
6. `fn()` for action spies lives in `storybook/test`, not `@storybook/test` (Storybook 10 moved it).

---

## Session 48 — 5 Track 3 cycles shipped (archived for reference)

> Previous session handoff content preserved below.

---

### Previous Session 48 Header

**Date:** 2026-04-19 (session 48 END)
**HEAD:** `5a726be` (K19a.4)
**Branch:** `main` (ahead of origin by sessions 38–48 commits — user pushes manually)

## Session 48 — 5 Track 3 cycles shipped

```
Track 3 K19a progress (session 48)

Cycle 1  K19a.1-rename           /memory → /knowledge end-to-end     d14d71b
Cycle 2  K19a.1-placeholders     4 Coming-soon tabs                   bab8829
Cycle 3  K19a.2 + K19a.7-skel    13-state TS types + i18n labels     70a3136
Cycle 4  K19a.3                  dispatcher + 13 state subcards      af4cefa
Cycle 5  K19a.4                  hook + BE graph-stats + ProjectRow  5a726be
```

**Final test counts at session 48 end:**
- Frontend (knowledge): **75 pass** (26 projectState + 23 useProjectState + 26 ProjectStateCard)
- Backend (new this session): **6 pass** (test_graph_stats.py)
- Track 2 regression tests: still green per last session 47 runs
- /review-impl caught **1 HIGH + ~15 MED/LOW findings** across the 5 cycles; every code finding fixed in-cycle, 3 LOW documented as known issues (see F4/F7/F8 below)

**User feedback adopted this session:**
- Cycle 3 onwards: batch small related tasks into one workflow cycle (rule saved to memory `feedback_batch_small_tasks.md`)
- FE draft HTML → BE audit at DESIGN phase, reclassify to FS if BE is missing (rule saved to memory `feedback_fe_draft_html_be_check.md`) — K19a.4 validated this: the graph-stats endpoint gap was caught pre-CLARIFY, user picked `(c) add BE now` rather than defer

**Cycle 1 (K19a.1-rename, d14d71b):** pure `/memory` → `/knowledge` rename + nav retranslation (24 files).

**Cycle 2 (K19a.1-placeholders, bab8829):** 4 placeholder tabs added. Navigation shell complete (7 tabs: Projects / Jobs / Global / Entities / Timeline / Raw / Privacy). Each new tab renders "Coming soon" + localized function description.

**Cycle 3 (K19a.2 + K19a.7-skeleton, 70a3136):** **First batched cycle** per user feedback. Foundation types for the 13-state memory-mode UI: `ProjectMemoryState` discriminated union + supporting types (BE-aligned per review-impl F1) + `VALID_TRANSITIONS` map + `canTransition` helper + all state/action i18n keys × 4 locales. 22/22 tests passing including runtime i18n cross-locale checks that neutralize the vitest i18n mock bypass (identified as L2 in cycle 1 review-impl).

**Cycle 4 (K19a.3 full, af4cefa):** `ProjectStateCard` dispatcher + all 13 subcomponents + shared primitives + 26-test component test file. Pure presentational (callback-prop pattern, TS exhaustive switch). `ProjectStateCardActions` union of 14 callbacks. /review-impl caught 7 more findings (3 MED dispatcher/prop drops + 1 MED i18n-coverage regression + 3 LOW polish), all fixed in-cycle. i18n runtime coverage now tracks 48 key paths × 4 locales (192 assertions).

**Cycle 5 (K19a.4 hook + BE graph-stats endpoint, 5a726be):** First FS cycle of Track 3. New `GET /v1/knowledge/projects/{id}/graph-stats` endpoint (Cypher UNION-ALL aggregation, 6 BE unit tests). New `useProjectState(project)` hook: derives `ProjectMemoryState` from `(Project, jobs, stats)`, polls `/extraction/jobs` at 2s while active, wires 11 of 14 callbacks to real endpoints (pause/resume/cancel/retry/extractNew/delete/rebuild/confirmModelChange + 3 that stay toast-stubs pointing to K19a.5 + 4 that stay toast-stubs pointing to K19a.6). `ProjectCard.tsx` deleted, replaced by `ProjectRow.tsx`. /review-impl caught 9 findings (1 **HIGH** — missing `embedding_model` on `/start` + `/rebuild` payloads would 422 at runtime; 2 MED — no error handling, no scopeOfJob tests; 5 LOW + 1 cosmetic). All code findings fixed in-cycle; 3 LOW documented as known issues.

**User feedback captured mid-session:** future small tasks should be batched into single cycles (saved to memory `feedback_batch_small_tasks.md`). Cycle 3 is the first application. Worked well — review-impl caught 9 findings in the batched scope that all got fixed in one pass.

### What K19a.5 can now assume

- `useProjectState(project)` hook returns `{ state, actions, isLoading, error }` — the dialog can import it to trigger estimate → confirm → start. When the Build button eventually opens the dialog, the dialog's Start button REPLACES `actions.onStart` (currently a toast-stub).
- `knowledgeApi.estimateExtraction(projectId, {scope, llm_model, embedding_model}, token)` returns a `CostEstimate`. `knowledgeApi.startExtraction(projectId, {scope, llm_model, embedding_model}, token)` returns an `ExtractionJobWire`. Both are ready to call.
- `EmbeddingModelPicker` (from K12.4) handles embedding-model selection UI; the dialog can reuse it.
- Call `queryClient.invalidateQueries({queryKey: ['knowledge-project-jobs', projectId]})` after starting a job to flip the ProjectStateCard from DisabledCard → BuildingRunningCard on the next poll.

### Known issues deferred from K19a.4 review-impl

- **F4 (polling scale):** 2 queries × N projects. Bounded today by the 100-item pagination cap in ProjectsTab. If pagination is ever removed, consider a `/v1/knowledge/projects/active-jobs` aggregator.
- **F7 (multi-device race):** polling stops for paused/complete/failed states. External state changes on another client aren't auto-refreshed. Future: always-on 30 s low-cadence poll OR SSE.
- **F8 (action-API test gap):** the 11 real-action callbacks have no hook-level tests. `renderHook` + mocked `knowledgeApi` would cover them. Medium lift, future hardening.

### What K19a.5 will replace

- `actions.onStart` stub — becomes the dialog's Start button calling `knowledgeApi.startExtraction`.
- `actions.onBuildGraph` stub — becomes the dialog-opener trigger on DisabledCard.
- `actions.onViewError` stub — becomes the error-viewer modal trigger on Failed/BuildingPausedError cards.

### Retro note — lesson for future FS cycles

Review-impl HIGH F1 (missing `embedding_model` on /start + /rebuild payloads) was a real 422-at-runtime trap that NO test layer could have caught: vitest doesn't hit BE, pytest doesn't hit FE, and Playwright smoke was blocked by BE not running. For FS cycles, review-impl MUST explicitly audit FE payload shape against the BE Pydantic schema — it's the only layer that catches this class of bug.

### FS cycle checklist going forward

1. **At CLARIFY:** enumerate every FE action → BE endpoint pair in a table.
2. **At DESIGN:** read the BE Pydantic request model for each endpoint; confirm every required field has a source in the FE state/props.
3. **At /review-impl:** re-read the Pydantic models; trace every payload construction call site; flag any optional-on-FE / required-on-BE mismatches as HIGH.

## Session 48 — K19a.1-rename (first Track 3 cycle) ✅

Pure `/memory` → `/knowledge` rename + nav retranslation.

**What shipped:**
- URL path + page file + component + i18n namespace all renamed to `knowledge`; hard-cut on `/memory` (old URLs 404)
- 5 product-name-referring locale strings retranslated to Knowledge / ナレッジ / Tri thức / 知識; functional/state-machine references (`staticMemory` badge, `indicator.popover.projectHeading`, `picker.*`, body text) deliberately kept as "Memory" — they describe the AI's memory function, not the product name
- `nav.memory` common-namespace key renamed + retranslated
- `tMemory` local alias renamed to `tKnowledge` in SessionSettingsPanel
- Playwright runtime evidence captured

**What still says "Memory" intentionally:**
- `projects.card.staticMemory` badge — technical state label from the 13-state memory-mode machine; backend `session.memory_mode` contract uses `"static"` / `"degraded"` / `"no_project"`
- `indicator.popover.projectHeading` / `globalHeading` / `body text` / `picker.*` — describe the AI's memory function
- Component names `MemoryIndicator`, `MemoryPage`-turned-history are a concept, not the URL — `MemoryIndicator` component kept; file renamed to `KnowledgePage.tsx`

**Test-coverage gap (important for the NEXT i18n-touching cycle):** the vitest setup at [frontend/vitest.setup.ts:24-41](../../frontend/vitest.setup.ts) globally mocks `react-i18next` such that `useTranslation(anyNamespace)` returns keys verbatim. Unit tests provide **zero** evidence of namespace correctness. Future i18n renames must rely on exhaustive grep (including `<Trans ns=>`, `useTranslation([])` array form, `t('ns:key')` prefix form, `i18n.t`, `getFixedT`) + `tsc --noEmit` + `vite build` + Playwright. Do not over-trust vitest green.

**Review-impl caught & fixed:** M1 (misleading `tMemory` alias post-namespace-rename), M2 (option c was half-shipped — retranslated 5 product labels per locale but kept functional descriptions), L1 (no runtime evidence — added Playwright smoke), L3 (2 stale "Memory page" comments).

---

## (Archived for reference) Session 47 END handoff

> Previous session handoff content preserved below for context.

---

## 1. TL;DR — what shipped this session

**20 commits. Track 2 code-complete.** Session 47 executed the full Track 2 close-out extended plan the user negotiated mid-session. All T2-close-* and T2-polish-* cycles shipped; the only remaining Track 2 item is the Gate 13 human-interactive checkpoint loop (T2-close-2), which can't be automated and is waiting on the user.

```
Track 2 close-out (26 cycles total, sessions 46 + 47)

Session 46  (12 commits, shipped first)
  Cycles 1–6 of the original Track 2 close-out roadmap

Session 47  (20 commits, extended-plan close-out)
  Cycle 7a   P-K18.3-02 MMR embedding cosine              ✅  7c666c9
  Cycle 7b   K18.9 Anthropic prompt cache_control         ✅  8f282c3
  Cycle 8a   D-K18.3-02 generative rerank                 ✅  e5aeb96
  Cycle 8b   D-T2-04 cross-process cache invalidation     ✅  239b021
  Cycle 8c   D-T2-05 glossary breaker half-open probe     ✅  2732462
  Cycle 9    K17.9.1 benchmark-runs migration             ✅  e0a94a7
  test-hygiene one-active-job-per-project fixes            ✅  609de2b
  Gate-13-report doc                                       ✅  95d336e
  T2-close-1a   K17.9 golden-set harness core wiring      ✅  525eaa5
  T2-close-1b-BE   benchmark gate + status endpoint       ✅  849be7f
  T2-close-1b-FE   picker badge + public endpoint         ✅  a484e25
  scope-out docs T2-close-1b-CI + T2-polish-4              ✅  34a4d8f
  T2-close-5   D-K16.2-01 per-model USD pricing           ✅  ed9f13d
  T2-close-6   D-K16.2-02 scope_range.chapter_range       ✅  01b8eda
  T2-close-7   P-K2a-02 + P-K3-02 glossary trigger perf   ✅  02067e2
  T2-close-3   scripted C05/C06/C08 chaos harness         ✅  fae8ce1
  T2-polish-1  test-isolation audit + 2 Go test fixes     ✅  8e3410d
  T2-polish-2a /metrics for glossary-service              ✅  0464919
  T2-polish-2b /metrics for book-service                  ✅  98623aa
  T2-polish-3  D-K18.9-01 cache_control on system_prompt  ✅  ff9ef11
  T2-close-4   Track 2 acceptance pack (doc)              ✅  e694e44
```

**Test execution at session END:**
- knowledge-service unit: **1154 pass** (up from 1049 at session 46 end)
- chat-service unit: **177 pass** (up from 169)
- glossary-service api: **100% green in 3.0 s** (was 2 persistent failures — both stale test bugs fixed in polish-1)
- book-service api: **green + new `parseSortRange` / `buildSortRangeFilter` tests**
- provider-registry-service: green

**Scoped out by user decision (not deferred):**
- T2-close-1b-CI — GitHub Actions benchmark job (no CI/CD at this stage)
- T2-polish-4 — CI integration-test wiring (same reason)

---

## 2. Where to pick up — Track 2 sealing + Track 3 onramp

### Option A — Close Gate 13 (recommended first)

The only code-path-adjacent Track 2 task remaining is **T2-close-2**: the 12-step Gate 13 human-interactive checkpoint walkthrough in [GATE_13_READINESS.md §5](GATE_13_READINESS.md). Requires:

1. BYOK credentials for one LLM provider (Anthropic / OpenAI / LM Studio) + one embedding model (bge-m3 on LM Studio or text-embedding-3-small on OpenAI).
2. A test project with 2–3 real chapters loaded via book-service API.
3. Driving the UI: enable extraction → wait for job → open chat → ask broad / specific / relational queries → inspect chat-service logs for `<memory mode="full">` → send 25+ messages to prove only last 20 in history → ask a contradiction-of-negation question → disable/re-enable extraction → check cost against provider invoice.
4. Optionally run the chaos scripts live for extra confidence: `./scripts/chaos/c0{5,6,8}_*.sh`.

Outcome: append a §10 Gate 13 attestation to [TRACK_2_ACCEPTANCE_PACK.md](TRACK_2_ACCEPTANCE_PACK.md) with captured evidence (log excerpts, screenshots, invoice line).

This is the **only** remaining step before Track 2 is formally closed. Code-wise nothing else blocks Track 3.

### Option B — Start Track 3 planning

If the Gate 13 loop is being deferred, Track 3 can start anytime because all Track 2 surfaces are shipped. The Deferred Items table in SESSION_PATCH has a "Track 3 preload" list with specific target phases — open that table and pick the cluster that fits the next session's scope.

Track 3 preload clusters (each has a target phase listed in Deferred Items):
- **D-K16.2-02b** — runner-side `chapter_range` enforcement (dormant today; frontend doesn't send `scope_range` yet).
- **D-K11.9-01 + P-K15.10-01 (partial)** — cursor-state for resumable reconciler + quarantine sweep. Paired with a job-state table. Target: K19/K20 scheduler cleanup.
- **D-K8-02 (remaining)** — project card stat tiles (entity / fact / event / glossary counts). Needs FE wiring on top of already-shipped BE surfaces.
- **D-K17.10-02** — xianxia + Vietnamese K17.10 fixtures.
- **P-K3-01 / P-K3-02 (full path)** — per-row short_description backfill → set-based SQL. Blocked on `shortdesc.Generate` ported to SQL; same port unblocks full P-K3-02.

### Resume recipe (either option)

1. **Read [SESSION_PATCH.md](SESSION_PATCH.md) + [TRACK_2_ACCEPTANCE_PACK.md](TRACK_2_ACCEPTANCE_PACK.md)** — the acceptance pack is the single-page view; SESSION_PATCH has everything else.
2. **Check Deferred Items "Naturally-next-phase" table** — any row whose Target equals the phase you're entering is in scope.
3. **Use the workflow gate:** `python scripts/workflow-gate.py reset` then `size <XS|S|M|L|XL> <files> <logic> <effects>` before each cycle; phase-by-phase through RETRO.

---

## 3. What changed in the Deferred Items table this session

### Cleared this session (moved to Recently cleared)

| ID | Cycle | Summary |
|---|---|---|
| **D-K16.2-01** | T2-close-5 | Per-model USD pricing table (`app/pricing.py`) for cost preview — replaces legacy ~$2/M fallback. |
| **D-K16.2-02** | T2-close-6 | `scope_range.chapter_range` threaded through estimate endpoint → `BookClient.count_chapters(from_sort=, to_sort=)` → book-service `parseSortRange` + `buildSortRangeFilter`. |
| **D-K18.3-02** | 8a | Generative listwise rerank on top of MMR, opt-in via `extraction_config["rerank_model"]`, inner timeout 1s, fail-safe fallback. |
| **D-T2-04** | 8b | Cross-process L0/L1 cache invalidation via Redis pub/sub. |
| **D-T2-05** | 8c | Glossary circuit-breaker half-open single-probe guarantee. |
| **D-K18.9-01** | T2-polish-3 | `cache_control` on session `system_prompt` — second Anthropic cache breakpoint used. |
| **K17.9 (harness core + BE gate + FE badge + migration)** | T2-close-1a/1b-BE/1b-FE + Cycle 9 | Golden-set benchmark end-to-end live. `project_embedding_benchmark_runs` table + gate in `/extraction/start` + picker badge + `GET /v1/knowledge/projects/{id}/benchmark-status`. |
| **P-K18.3-02** | 7a | MMR embedding cosine + `top_n` early-exit (21× perf win on dim=3072 pool=40). |
| **K18.9** | 7b | Anthropic prompt caching: structured system content with `cache_control: ephemeral` on stable memory prefix. |
| **P-K2a-02 + P-K3-02 (partial)** | T2-close-7 | Glossary trigger watch-list rewrite; pin toggle 1→0 recalcs, description PATCH 3→1 (no-op) / 2 (real). |
| **Chaos C05/C06/C08 (scripted)** | T2-close-3 | `scripts/chaos/{c05,c06,c08}_*.sh` authored + smoke-tested. |
| **T2-polish-1 test-isolation audit** | T2-polish-1 | Python suite audited clean; 2 pre-existing broken Go tests fixed. |
| **T2-polish-2a /metrics glossary** | T2-polish-2a | 4 counter vecs + 8 call sites pre-seeded; review-impl caught + killed 16 dead labels. |
| **T2-polish-2b /metrics book-service** | T2-polish-2b | 3 counter vecs, cross-service label divergence documented. |
| **T2-close-4 acceptance pack** | T2-close-4 | `TRACK_2_ACCEPTANCE_PACK.md` consolidates Track 2 evidence. |

### Still deferred (explicit Track-3-preload, no re-deferrals this session)

| ID | Target |
|---|---|
| D-K8-02 (remaining stat tiles) | Track 2 Gate 12 or Track 3 |
| D-K11.9-01 (partial, cursor state) | K19/K20 scheduler cleanup |
| P-K15.10-01 (partial, cursor state) | Paired with D-K11.9-01 |
| D-K17.10-02 | K17.10-v2 after threshold stabilisation |
| D-K16.2-02b (runner-side chapter_range) | Track 3 (when FE range-picker ships or batch-iterative runner lands) |
| D-K18.3-02b (if any — none currently) | — |
| P-K3-01 (backfill Go→SQL port) | Track 3 |
| P-K3-02 full path (same port) | Track 3 |

No new deferrals added this session besides **D-K16.2-02b** (review-impl catch during T2-close-6 — runner is event-driven and doesn't honour `chapter_range`; preview filters but runner doesn't, dormant until FE sends `scope_range`).

---

## 4. Important context the next agent must know

### Workflow enforcement unchanged (v2.2 · 12-phase)

```
CLARIFY → DESIGN → REVIEW-DESIGN → PLAN → BUILD → VERIFY → REVIEW-CODE → QC → POST-REVIEW → SESSION → COMMIT → RETRO
```

State machine: `.workflow-state.json` + `scripts/workflow-gate.py` from repo root. Pre-commit hook blocks commits without VERIFY + POST-REVIEW + SESSION completed.

**POST-REVIEW is a human checkpoint, NOT self-adversarial re-read.** Deep review is on-demand via `/review-impl`. Every cycle this session had a `/review-impl` pass and several caught HIGH issues the initial self-review missed (examples: T2-close-3 found 3 HIGH blockers in chaos scripts; T2-close-6 found 6 findings including a shared-validator bypass; T2-close-7 found a soft-delete regression from the initial trigger-rewrite).

### Key semantic changes this session

1. **`entity_snapshot.updated_at` semantics changed (T2-close-7).** Pin toggle no longer bumps `updated_at`, and the self-trigger dropped `updated_at` from its watch list. `snapshot.updated_at` now tracks last-**semantic**-change, not last-**touch**. Callers wanting last-touch should read `glossary_entities.updated_at` directly.
2. **`scope_range.chapter_range` is preview-only (T2-close-6).** The estimate endpoint filters; the event-driven extraction runner does not yet honour the range. Dormant today because no frontend sends `scope_range`. Tracked as D-K16.2-02b.
3. **Anthropic 2 of 4 cache breakpoints used (7b + polish-3).** parts[0] = stable memory (cached), parts[1] = volatile memory (uncached, changes per-message), parts[2] = session system_prompt (cached).

### Observability surfaces — all 3 Go services on knowledge-service hot paths

| Service | Endpoint | Counters |
|---|---|---|
| provider-registry | `/metrics` (session 46) | 4 (proxy / invoke / embed / verify) |
| glossary-service | `/metrics` (T2-polish-2a) | 4 (select_for_context / bulk_extract / known_entities / entity_count) |
| book-service | `/metrics` (T2-polish-2b) | 3 (projection / chapters_list / chapter_fetch) |

Outcome label sets differ intentionally between glossary (`invalid_body`) and book (`not_found`). Cross-ref comments in both metrics.go files explain why. Do NOT "normalize" them.

### Chaos scripts — live-run when needed

`scripts/chaos/` contains `lib.sh` + `c05_redis_restart.sh` + `c06_neo4j_drift.sh` + `c08_bulk_cascade.sh` + `README.md`. Each exits `0` on PASS, dies with `FAIL <reason>` on failure, and uses `trap cleanup EXIT` so a failed run still sweeps test data. Test UUIDs prefixed `00000000-0000-0000-c0XX-...` for manual sweep. Prereqs: the `infra-*` compose stack running.

### Benchmark harness is live and gate-active

`python -m eval.run_benchmark --project-id=<uuid> --embedding-model=<model>` runs the K17.9 golden-set harness. A passing row in `project_embedding_benchmark_runs` is now required to start an extraction job — the `POST /extraction/start` endpoint returns 409 with structured `{error_code: benchmark_missing | benchmark_failed, ...}` otherwise. The K12.4 embedding-model picker shows a 3-state badge (green passed / red failed / grey no-run) that drives the CTA.

### Caches + breakers shipped this session (all per-worker-process unless noted)

- `_anchor_cache` TTLCache(256, 60s) — `internal_extraction.py` (session 46).
- `_query_embedding_cache` TTLCache(512, 30s) — `selectors/passages.py` (session 46).
- L0/L1 TTLCache + **cross-process pub/sub invalidation** via `CacheInvalidator` on Redis channel `loreweave:cache-invalidate` (Cycle 8b this session). Settings-gated on `redis_url`.
- Glossary breaker with half-open single-probe guarantee (Cycle 8c this session).

### Pre-existing failing tests (not this session's fault)

- `book-service/internal/config TestLoadValidation` — missing `INTERNAL_SERVICE_TOKEN` env in test setup; the validation requirement was added later. Confirmed via `git stash`.
- `translation-service/tests/test_glossary_client.py` + `test_pipeline_v2.py` — module-import pydantic Settings validation errors (pre-existing before session 46).

### New deps this session

- `github.com/prometheus/client_golang v1.23.2` on **both** glossary-service and book-service (from T2-polish-2a/2b). Session 46 already added it to provider-registry. `go.mod` + `go.sum` committed.

### Infra & test invocation (unchanged)

- Compose: `cd infra && docker compose up -d`; Neo4j profile: `docker compose --profile neo4j up -d neo4j`.
- Neo4j port: **7688**, Postgres port: **5555**, Neo4j creds `neo4j / loreweave_dev_neo4j` (note the `_neo4j` suffix — chaos scripts default to this).
- pytest from `services/knowledge-service/` (unit: `-q tests/unit/`; integration needs `TEST_KNOWLEDGE_DB_URL` + `TEST_NEO4J_URI`).
- Go tests from `services/<svc>/` (`go test ./...`); glossary-service integration needs `GLOSSARY_TEST_DB_URL`.

---

## 5. Session 47 stats

| Metric | Before session 47 | After session 47 | Delta |
|---|---|---|---|
| Total knowledge-service unit tests | 1049 | **1154** | **+105** |
| chat-service unit tests | 169 | **177** | **+8** |
| glossary-service api test status | 2 failing (stale) | **100% green** | 2 fixed |
| book-service api test status | green | **green + new tests** | new units |
| Deferred items open | ~6 naturally-next + 4 re-deferred + 2 partial | **~6 naturally-next / partial only (no re-deferrals)** | ~4 cleared |
| Cycles complete (original Track 2 roadmap) | 6/9 | **9/9** | +3 |
| T2-close extended plan cycles | 0 | **9/9** (1 scoped out) | +9 |
| T2-polish extended plan cycles | 0 | **4/4** (1 scoped out) | +4 |
| Session commits | 0 | **20** | +20 |
| Review-impl follow-up catches | — | ~20 HIGH/MED/LOW findings across cycles | — |
| New deps | — | `prometheus/client_golang v1.23.2` on glossary + book | +1 dep × 2 services |
| New env knobs | — | — | stable |
| Services with /metrics | 1 (provider-registry) | **3** (+ glossary + book) | +2 |
| Chaos scripts (scripted live runs) | 0 | **3** (C05/C06/C08) | +3 |

---

## 6. Housekeeping note

This file is the single, unversioned handoff. **Future sessions MUST update this file in place — do NOT create a `_V48.md` or similar.**

Track 2 is **code-complete**. The repo is in a clean state to either (a) execute the Gate 13 human loop to formally seal Track 2, or (b) begin Track 3 planning — neither blocks the other. All deferrals have explicit target phases; no "we'll come back to it" rows remain.

When the Gate 13 human loop is run, append §10 attestation to [TRACK_2_ACCEPTANCE_PACK.md](TRACK_2_ACCEPTANCE_PACK.md) with the captured evidence, and move the T2-close-2 row out of "remaining" in SESSION_PATCH's header metadata.
