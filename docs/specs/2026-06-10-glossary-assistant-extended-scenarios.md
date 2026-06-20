# Glossary-Assistant — Extended Scenarios Deep-Dive (S9–S26)

> **Date:** 2026-06-10. **Status:** CLARIFY / design analysis. **Companion to** [`2026-06-10-glossary-assistant-scenario-coverage.md`](2026-06-10-glossary-assistant-scenario-coverage.md) (the 8 core scenarios + 3-layer model).
> **▶ 2026-06-20 status:** S9–S26 verdicts are re-assessed in the companion doc's **"STATUS UPDATE — 2026-06-20"** table (post Tiered-MCP-Tools epic). Summary: the ontology CRUD is now agent-reachable; the L1-complete/L2-missing theme below **still holds** for the pipeline + read ops (merge S9, triage S12, evidence S16, chapter-link S17, plus extract/translate/research) — those remain agent-blind and are the next campaign.
> **Purpose:** go deep on the *additional* scenarios surfaced during analysis — the management ops (S9–S14), read/QA ops (S15–S18), and the cross-cutting concerns (S19–S26). For each: intent, test script, what L1 backend already exists (verified, with file refs), the L2 agent-tool gap + a concrete proposed tool signature, the L3 surface, security/edge cases, dependencies, and an effort/risk estimate.
> **Recurring theme:** almost every management op is **L1-complete / L2-missing** — the backend can do it, the agent can't reach it. The exceptions (S15, S18, S5) need genuinely new capability.

---

## Conventions

**Tool types** (the only three shapes that satisfy the MCP-first invariant):
- **MCP-read** — Go MCP tool on glossary-service, returns data, no write.
- **MCP-write-proposal** — Go MCP tool that **mints a confirm-token or a draft** (never a silent canonical write); the actual write is human-gated.
- **FE-suspend** — chat-service frontend-tool that suspends the run → renders a card → user Applies → resumes with the real outcome (H6). This is the pattern for any write that needs a visual review/diff.

**Effort:** S (tool + reuse existing endpoint/card) · M (new endpoint or new card) · L (new subsystem / async).
**Verified L1** below = confirmed against `services/glossary-service/internal/api/server.go` route table + handlers.

---

# Group 1 — Management ops (L1-complete, L2-missing)

These are the **highest-leverage, lowest-risk** additions: the endpoints, guards, and (often) manual UI already exist and are battle-tested. We only add an agent tool + a confirmation card.

---

## S9 — Merge duplicate entities

**Intent.** "tìm và gộp các nhân vật trùng" / "gộp '焰魔' và 'Diễm Ma' thành một".

**Test script.**
- Given two entities that are the same character under name variants, When I ask the assistant to merge them, Then it shows me which is the winner, what gets archived, and the consequences (chapter-links/evidence consolidated, wiki article archived-in-place), I approve once, and a **revert handle** exists.

**L1 (verified).**
- `POST /v1/glossary/books/{book_id}/entities/{entity_id}/merge` (`mergeEntities`, R5 destructive merge, merge-journal recorded).
- `GET /merge-candidates` (`listMergeCandidates`) + `POST /merge-candidates/{candidate_id}/dismiss` — the dedup inbox.
- `POST /merge-journal/{journal_id}/revert` (`revertMerge`) — symmetric un-merge.
- `POST /internal/books/{book_id}/merge-candidates` (`internalProposeMergeCandidates`) — pipeline proposes clusters.
- FE: `MergeCandidatePanel`, `useMergeCandidates` (list/confirm/dismiss/revert).

**L2 gap → proposed tools.**
- `glossary_list_merge_candidates` *(MCP-read)* — `{book_id}` → ranked duplicate clusters (so the assistant can *find* dupes, not just act on a pair the user names).
- `glossary_propose_merge` *(FE-suspend)* — `{book_id, winner_entity_id, loser_entity_id[], rationale?}` → suspends → **MergeConfirmCard** showing winner/losers + consequence summary → Apply POSTs `/merge` → resume `merged | merge_conflict | merge_error | cancelled`.

**L3.** New **MergeConfirmCard** (destructive variant of the card family: red, lists what's archived, "revertable from merge inbox").

**Security / edge cases.** Merge is **destructive + cross-entity** — ownership check on *both* entities; winner/loser must be same book; concurrent edit during merge; the wiki archive-in-place rule (Bug-1 fix on `wiki/llm-building`) must hold. Revert path must be surfaced in the card copy.

**Deps.** Card family generalization (shared with S10). **Effort: M.** **Risk: med** (destructive).

---

## S10 — Delete / deprecate (entity, kind, attribute)

**Intent.** "xóa nhân vật phụ này" / "bỏ kind không dùng" / "gỡ attribute thừa khỏi kind".

**Test script.**
- Given an entity I no longer want, When I ask to delete it, Then it soft-deletes (recoverable from recycle-bin), the assistant confirms it's recoverable. For a **kind**, deletion is blocked if it has active entities (the assistant explains why) and cascades wiki on confirm.

**L1 (verified).**
- Entity: `DELETE .../entities/{entity_id}` (`deleteEntity`, **soft-delete**); recycle-bin `GET /recycle-bin`, `POST /{entity_id}/restore`, `DELETE /{entity_id}` (purge).
- Kind: `DELETE /kinds/{kind_id}` (`deleteKind`) — guards: can't delete `is_default`; can't delete with active entities; cascades wiki + emits `wiki.deleted`.
- Attribute: `DELETE /kinds/{kind_id}/attributes/{attr_def_id}` (`deleteAttrDef`) — guard: can't delete `is_system`.

**L2 gap → proposed tools.**
- `glossary_propose_delete_entity` *(FE-suspend)* → **DeleteConfirmCard** (emphasize: soft + recycle-bin recoverable) → Apply `DELETE` → resume.
- Kind/attr delete → fold into the **schema change-set** tool (Group 2 / S3) since "remove attribute" is a schema op; standalone kind-delete is rare and high-impact (prefer manual UI, or a guarded FE-suspend with the active-entity-count surfaced).

**L3.** **DeleteConfirmCard** (recoverable framing for entities; hard-stop explanation when a kind delete is blocked).

**Security / edge cases.** Destructive; the **guards must be reported, not bypassed** (kind with active entities → the assistant explains, doesn't force). Purge (hard-delete) should **not** be assistant-driven (manual recycle-bin only). Idempotency on double-delete.

**Deps.** Card family (S9). **Effort: S–M.** **Risk: med.**

---

## S11 — Reassign kind / resolve the "unknown" bucket

**Intent.** "nhân vật này bị xếp nhầm loại Item → đổi sang Character" / "xử lý đống entity 'unknown' do extraction tạo".

**Test script.**
- Given entities parked under `unknown` with a `source_kind_code`, When I ask the assistant to resolve them, Then it suggests a target kind per cluster (or an alias mapping), I approve, and the entities are re-keyed onto the target kind (attributes mapped by code, display value preserved).

**L1 (verified).**
- `GET /unknown-entities` (`listUnknownEntities`).
- `POST .../entities/{entity_id}/reassign-kind` (`reassignEntityKind`) — single entity.
- `POST /kind-aliases` (`createKindAlias`, optional `reassign=true`) — maps `alias_code → kind_id` and bulk-re-keys all unknowns with that source code (`rekeyEntityToKind`).
- FE: `ResolveKindModal`, `UnknownEntitiesPanel`, `useUnknownReview`.

**L2 gap → proposed tools.**
- `glossary_list_unknown_entities` *(MCP-read)* — `{book_id}` → unknown entities grouped by `source_kind_code`.
- `glossary_propose_reassign_kind` *(FE-suspend)* — `{book_id, entity_id | source_kind_code, target_kind_code, create_alias?}` → **ReassignConfirmCard** (shows attribute-mapping preview: which attrs carry over, which drop) → Apply → resume.

**Security / edge cases.** Re-keying **drops non-matching attributes** (`rekeyEntityToKind` lines) — the card MUST preview data loss. `create_alias` writes a **global** alias (affects future extractions) — flag that. Source-code-bulk vs single-entity must be explicit.

**Deps.** Card family. **Effort: M.** **Risk: med** (silent attribute drop if not previewed).

---

## S12 — Triage the AI-suggestions inbox (approve / reject drafts)

**Intent.** "duyệt các entity mà AI vừa đề xuất, chấp nhận cái đúng, loại cái sai".

**Test script.**
- Given draft entities tagged `ai-suggested` (from extraction writeback), When I ask the assistant to help me triage, Then it lists them, recommends approve/reject per item (with reasoning from the source text), I confirm, approved → `active`, rejected → `inactive` + `ai-rejected` tombstone (so it's never re-proposed).

**L1 (verified).**
- Inbox = entities with `status='draft'` + tag `ai-suggested`; listed via the entity list filter.
- **Approve** = `PATCH .../entities/{id}` `{status:'active'}`.
- **Reject** = `PATCH .../entities/{id}` `{status:'inactive', tags:[...,'ai-rejected']}` — the tombstone gate in `bulkExtractEntities`/`entityHasTag` then skips that name in future AI batches (H9).
- FE: `AiSuggestionsPanel`, `useAiSuggestions` (`promote`/`reject`).

**L2 gap.** The assistant **cannot change `status` or `tags`** today — `glossary_propose_entity_edit` only targets `short_description` + attribute `original_value`. So the agent literally cannot promote/reject its own drafts.
**Proposed tools.**
- `glossary_list_ai_suggestions` *(MCP-read)* — `{book_id}` → draft+ai-suggested entities with their attributes/evidence so the agent can reason about quality.
- `glossary_propose_status_change` *(FE-suspend)* — `{book_id, changes:[{entity_id, action: approve|reject, reason?}]}` (**batch-capable** — triage is inherently many) → **TriageCard** (a checklist of recommendations) → Apply loops the PATCH calls → resume with per-item outcome.

**L3.** **TriageCard** — multi-row approve/reject checklist with the agent's recommendation pre-filled, user toggles, one Apply.

**Security / edge cases.** Batch → **partial-failure reporting** (S19/S20). Reject must preserve `ai-suggested` for audit AND add `ai-rejected` (the hook does this — replicate exactly). Approving promotes to canon → triggers the glossary→KG sync; that's intended.

**Deps.** Batch pattern (S19), card family. **Effort: M.** **Risk: low–med** (well-understood ops; batch is the new bit). Note: a generic `glossary_propose_status_change` also covers ad-hoc activate/deactivate, subsuming part of S1's CRUD gap.

---

## S13 — Revision history / undo

**Intent.** "khôi phục nhân vật này về bản trước" / "gần đây ai/cái gì đã sửa entity này?".

**Test script.**
- Given an entity with revision history, When I ask "có gì thay đổi gần đây" then "khôi phục về bản hôm qua", Then the assistant lists revisions (who/when/what) and, on approval, restores the chosen revision.

**L1 (verified).**
- `GET .../entities/{id}/revisions` (`listEntityRevisions`), `GET .../revisions/{rev_id}` (`getEntityRevision`), `POST .../revisions/{rev_id}/restore` (`restoreEntityRevision`).
- FE: `EntityHistoryPanel`, `useEntityRevisions`.

**L2 gap → proposed tools.**
- `glossary_list_revisions` *(MCP-read)* — `{book_id, entity_id}` → revision list.
- `glossary_propose_restore_revision` *(FE-suspend)* — `{book_id, entity_id, rev_id, base_version}` → **RestoreConfirmCard** (diff current↔target) → Apply → resume. Reuses the H5 version guard (restore is a write).

**Security / edge cases.** Restore is a write → version-guard against concurrent edits; the diff must show what the restore changes (it's "edit backwards"). Merge-journal revert (S9) is a sibling — same card family.

**Deps.** Card family. **Effort: S–M.** **Risk: low.**

---

## S14 — Genre management via the assistant

**Intent.** "tạo nhóm genre 'Tiên Hiệp' màu xanh, rồi gắn cho các kind PowerSystem, Species, PlotArc".

**Test script.**
- Given a book, When I ask the assistant to create a genre group and tag relevant kinds, Then the genre is created and the kinds' `genre_tags` updated, reviewed in one approval.

**L1 (verified).**
- Genre: `GET/POST .../genres`, `PATCH/DELETE .../genres/{genre_id}` (`genres_crud.go`). Unique per book.
- Kind genre-tagging: `PATCH /kinds/{kind_id}` updates `genre_tags`.
- FE: `GenreGroupsPanel`, `GenreFormModal` (incl. cascade rename).

**L2 gap → proposed tools.**
- `glossary_propose_genre` *(FE-suspend)* — create/update/delete a genre group + optionally tag kinds → **GenreConfirmCard**.
- (Kind genre-tagging overlaps with the schema change-set tool, S3.)

**Security / edge cases.** Genre delete leaves `genre_tags` on orphaned kinds (existing behavior) — surface that. Unique-name conflict → report. Cascade-rename is a FE concern today; if the assistant renames, it must replicate the cascade or call the same path.

**Deps.** Card family. **Effort: S–M.** **Risk: low.** *(Lowest-value of Group 1 unless genre work is active.)*

---

# Group 2 — Read / QA / consistency (new capability)

These need genuinely new read/aggregate logic — not just exposing an endpoint.

---

## S15 — Coverage / consistency audit

**Intent.** "nhân vật nào chưa có mô tả?" · "ai được nhắc trong chương nhưng chưa có trong glossary?" · "attribute nào mâu thuẫn giữa các chương?".

**Test script.**
- Given a book, When I ask "kiểm tra glossary còn thiếu/sai gì", Then the assistant returns a structured report: entities missing required attributes, names appearing in chapter text but absent from the glossary, and flagged contradictions — each with a jump-to-source.

**L1.** Partial building blocks: `enrichment-coverage` internal endpoint exists; raw-search (lexical/semantic over chapters) exists; glossary list/search exists. **No single "audit" endpoint.**

**L2 gap → proposed tools.**
- `glossary_audit_coverage` *(MCP-read)* — `{book_id, checks?: [missing_required|orphan_mentions|contradictions]}` → a findings list. Implementation composes glossary data + raw-search ("mentioned-but-absent" = chapter terms ∉ glossary names/aliases) + (for contradictions) an LLM pass — which itself must be an agentic sub-step, not a raw prompt.
- "Orphan mentions" leans on the **raw-search** subsystem (already shipped) for chapter-term coverage.

**Security / edge cases.** Contradiction detection is LLM-judgement → false positives; frame as "candidates to review," never auto-fix. Cost: a full-book audit is expensive → cost gate (S21) + bounded scope.

**Deps.** Raw-search; LLM-judge sub-step; async (S20) for whole-book. **Effort: L.** **Risk: med** (precision of "contradiction").

---

## S16 — Evidence / citation (read + write)

**Intent.** "đoạn văn nào chứng minh nhân vật này có sư phụ là X?" · "thêm trích dẫn nguồn cho attribute 'môn phái'".

**Test script.**
- Given an entity, When I ask "dẫn chứng cho thuộc tính này ở đâu", Then the assistant returns the evidence quotes (chapter + location). When I ask to add a citation, it proposes an evidence row I approve.

**L1 (verified).**
- `GET .../entities/{id}/evidences` (`listEntityEvidences`).
- `POST/PATCH/DELETE .../attributes/{attr_value_id}/evidences[/{id}]` (`evidence_handler.go`).
- **But `glossary_get_entity` does NOT return evidence** (returns attributes/aliases/kind/short-description only — verified in `mcp_server.go`).

**L2 gap → proposed tools.**
- `glossary_get_entity_evidence` *(MCP-read)* — `{book_id, entity_id}` → evidence per attribute. (Or extend `glossary_get_entity` with an `include_evidence` flag — cheaper, but watch output size / SO-3 bound.)
- `glossary_propose_evidence` *(FE-suspend)* — `{book_id, entity_id, attr_value_id, evidence_type, original_text, chapter_id?, ...}` → **EvidenceCard** → Apply.

**Security / edge cases.** Evidence is append-friendly (low risk). Output-size bound on read (an entity can have many evidences). When web-search (S5) lands, web sources become evidence → the `chapter_id` becomes optional `source_url`.

**Deps.** Card family. **Effort: M.** **Risk: low.**

---

## S17 — Chapter-link queries / linking

**Intent.** "X xuất hiện ở những chương nào?" · "liên kết entity này với chương 12 (vai trò: major)".

**Test script.**
- Given an entity, When I ask where it appears, Then the assistant lists chapter-links with relevance; When I ask to link it to a chapter, it proposes a link I approve.

**L1 (verified).** `GET/POST .../entities/{id}/chapter-links`, `PATCH/DELETE .../chapter-links/{link_id}` (`chapter_link_handler.go`). *(Note: FE `api.ts` doesn't even expose these — manual UI gap too.)*

**L2 gap → proposed tools.**
- `glossary_list_chapter_links` *(MCP-read)* — `{book_id, entity_id}`.
- `glossary_propose_chapter_link` *(FE-suspend)* — `{book_id, entity_id, chapter_id, relevance, note?}` → card → Apply.

**Security / edge cases.** Unique `(entity_id, chapter_id)` → upsert/duplicate handling. Largely additive/low-risk.

**Deps.** Card family. **Effort: S–M.** **Risk: low.**

---

## S18 — Relationship / graph queries

**Intent.** "ai là sư phụ của X?" · "vẽ quan hệ giữa các nhân vật chính".

**Test script.**
- Given a book with relationships, When I ask about an entity's relationships, Then the assistant answers from the knowledge graph / relationship entities, with sources.

**L1.** Partial: knowledge-service `memory_recall_entity` (federated MCP) returns "entity details + relationships"; a `Relationship` system kind exists in glossary. **Cohesion between the two layers is unclear** (glossary SSOT vs knowledge derived graph — the two-layer pattern in CLAUDE.md).

**L2 gap.** `memory_recall_entity` is already reachable. The gap is **product clarity**: is relationship truth in glossary (a `Relationship` kind/entities) or in knowledge (Neo4j-derived)? Define which the assistant queries for which question, and whether it can *propose* relationships.

**Security / edge cases.** Spoiler horizon (S23) is acute for relationships (reveals plot). Cross-layer consistency.

**Deps.** Knowledge-service graph maturity; spoiler model. **Effort: L** (mostly design/product). **Risk: med.**

---

# Group 3 — Cross-cutting concerns (affect many scenarios)

These aren't single features — they're **patterns/guards** that several scenarios above depend on. Decide them early; they shape every tool's design.

---

## S19 — Batch / bulk operations

**Problem.** "dịch tất cả nhân vật", "re-extract tất cả chương cho kind này", "duyệt 30 draft", "backfill attribute mới cho mọi entity". Today each = **N sequential tool calls** → slow, token-heavy, and the LLM loses track at scale.

**Design.** A **batch-proposal** shape reused across S4/S8/S12: one tool call carries a list (`changes[]`), the card renders the whole list, one Apply iterates the underlying per-item endpoint server-side (or in the FE Apply handler) and returns **per-item outcomes** (`{id, status, error?}[]`). Crucially the **agent loop is NOT iterated** — the batch is one suspend/resume, not N.

**Edge cases.** Partial failure (some succeed, some 412/error) must be reported truthfully (H6 at batch granularity). Idempotency on retry. A size cap (don't let the LLM propose 5000 edits unbounded — SO-3 analogue).

**Deps.** Underpins S4, S8, S12. **Effort: M** (pattern + one reference card). **Risk: med** (partial-failure correctness).

---

## S20 — Long-running / async operations in chat

**Problem.** Extraction (S7/S8), deep-research (S5), whole-book audit (S15), large batch (S19) take **seconds-to-minutes** — a single chat turn can't block on them. Extraction is already a RabbitMQ **job** with a WebSocket progress channel.

**Design.** A **job-handle pattern**: the write-proposal tool *starts* the job and returns `{job_id, status:'queued', estimate}` immediately; chat surfaces a **JobProgressCard** that subscribes to the existing job WebSocket; on completion the assistant can read results via a `*_job_status` MCP-read tool and continue. The chat turn ends after starting the job — results arrive as a later turn / card update.

**Edge cases.** Turn boundaries (the LLM must not "pretend" the job finished — H6); job failure surfaced; user navigates away then back (job state is server-side, recoverable). Cancellation.

**Deps.** Prerequisite for S5, S7, S8, S15, large S19. **Effort: L** (the hardest cross-cutting piece). **Risk: high** (new interaction model; truthful-resume across turns).

**DECISION (2026-06-10) — Path B (application-level job-handle), NOT MCP-native Tasks.**
- MCP *does* now have a first-class async primitive — **Tasks** (call-now/fetch-later: `tasks/get`/`result`/`list`/`cancel`, durable handle, progressToken), but it landed in the **2025-11-25** spec revision and is **experimental** (SEP-1686 Tasks, SEP-1391 LRO).
- **Our Go SDK `modelcontextprotocol/go-sdk` v1.6.1 is the LATEST published version and has NO Tasks support** (verified 2026-06-10 against the module cache — no `tasks/*` methods). TS SDK `^1.29.0` has experimental Tasks; Python `mcp>=1.9,<2` unconfirmed. So a version bump can't unblock it — Go simply hasn't shipped it.
- MCP Tasks would also fight our **federation model**: ai-gateway uses per-call fresh clients (INV-7/H14); a stateful task spanning requests would force task-proxying through the gateway across all three SDKs.
- We **already have durable async infra** (RabbitMQ + `extraction_jobs` table + WebSocket progress) that is *more* durable than in-protocol Tasks.
- **Therefore S20 = Path B:** a write-proposal MCP tool returns `{job_id}` immediately (mapping onto the existing job + `extraction_jobs` row); a separate MCP-read `*_job_status` tool polls; chat renders a **JobProgressCard** on the existing WebSocket. Works on all current SDKs, no experimental features, doesn't disturb federation. Conceptually identical to Tasks → cheap to migrate later. See deferred **`D-MCP-TASKS-MIGRATION`**.

---

## S21 — Cost confirmation gate

**Problem.** Extraction, deep-research, batch-translate cost real money/tokens. Extraction already computes a **cost estimate** at L1 (`estimate_extraction_cost`); the assistant path has no gate.

**Design.** Any expensive write-proposal returns a **cost estimate** in its preview; the confirm card shows it; Apply is the consent. Reuse the SchemaConfirmCard pattern with a cost line. A per-request ceiling (config) hard-stops runaway asks.

**Deps.** Pairs with S20 (jobs) and S5 (research). **Effort: S** (once estimates exist). **Risk: low.**

---

## S22 — Field-type-aware editing

**Problem.** Attributes have types (`text|textarea|select|number|date|tags|url|boolean`, with `options[]` for select). The diff/propose tools must render and **validate** per type — a `select` edit must be within `options`; `tags` is an array; `number/date/boolean` must parse. Today `propose_entity_edit` passes `old/new_value` as preserved JSON but type-validation rigor is partial.

**Design.** The propose tool fetches the attribute's `field_type`+`options` (via `glossary_list_kinds` / get_entity) and validates before minting; the card renders the right control (dropdown for select, chips for tags, date-picker). Server-side validation already exists for some paths — make it authoritative.

**Deps.** Touches every entity-edit scenario (S1/S3/S4). **Effort: M.** **Risk: low–med** (correctness/UX).

---

## S23 — Spoiler / capture-horizon awareness

**Problem.** When the assistant *describes* an entity or relationship, it can leak plot the reader hasn't reached. The wiki feature already designed a **capture-horizon + reader-gate** concept (spec v3, `wiki/llm-building`).

**Design.** When the assistant summarizes lore for a reader context, bound the source material to the reader's current chapter (a `max_chapter` parameter on read tools). Authoring context (the glossary editor) is unrestricted; reader-surface context is gated. Align with the wiki spoiler model — don't invent a second one.

**Deps.** Reader position (book-service); wiki spoiler model. **Effort: M.** **Risk: med** (product-sensitive; easy to get wrong).

---

## S24 — Indirect prompt-injection from untrusted text

**Problem.** INV-6 already treats glossary/chapter text as DATA-not-instructions. This becomes **load-bearing** the moment S5 (web search) ingests arbitrary external HTML, which is far more adversarial than the user's own novel text.

**Design.** Keep the INV-6 boundary; for web content add explicit provenance framing ("the following is untrusted external content"), strip/escape, never let fetched text alter tool-selection. A separate review before any web-sourced content becomes a proposal. Test with injection payloads.

**Deps.** Gates S5. **Effort: M** (mostly within S5). **Risk: high if S5 ships without it.**

---

## S25 — Shared-book / non-owner permissions

**Problem.** Ownership is fail-closed today (`checkBookOwnership`, positive-only cache). If sharing-service grants a non-owner *edit* rights, can they use the assistant on that book? Untested.

**Design.** Decide whether assistant write-tools honor **share-grants** (not just ownership). If yes, the ownership check must consult sharing-service; if no, document that the assistant is owner-only. Don't silently allow/deny.

**Deps.** sharing-service contract. **Effort: M.** **Risk: med** (security boundary).

---

## S26 — Conversation language vs content/target language

**Problem.** The user converses in Vietnamese; entity names are Chinese; the desired translation target might be English. The assistant must not conflate "language I'm chatting in" with "target translation language," and must echo names in the right script.

**Design.** Translation tools (S4/S6) take an explicit `target_language`; the skill prompt clarifies the distinction; never assume target = conversation language. UI shows source + target side by side.

**Deps.** S4/S6. **Effort: S** (mostly prompt + explicit params). **Risk: low.**

---

# Consolidated view — dependency order

```
S20 (async jobs) ─────────────┬─> S5 (web/deep research) ──> needs S24 (injection), S21 (cost)
                              ├─> S7/S8 (assistant extraction)
                              └─> S15 (whole-book audit)

S19 (batch) ──────────────────┬─> S4/S6 (translate many)
                              ├─> S12 (triage inbox)
                              └─> S8 (re-extract many)

Card-family generalization ───┬─> S9 merge, S10 delete, S11 reassign, S13 restore,
(destructive + multi-row +     │   S14 genre, S16 evidence, S17 chapter-link, S12 triage
 cost + field-type)           └─> (this is the real Group-1 enabler)

S22 (field-types), S23 (spoiler), S25 (perms), S26 (lang) = guards woven into the above.
```

**Recommended sequencing (if we build):**
1. **Card-family generalization** + **Group 1 read tools** (S9/S11/S13/S16/S17 reads) — cheap, unlocks visibility.
2. **Group 1 write-proposals** (S10 delete, S12 triage, S9 merge, S11 reassign, S13 restore) — reuse cards, reuse endpoints. Big coverage jump.
3. **Batch pattern (S19)** — then S12-batch, S4-batch.
4. **Schema change-set (S2/S3)** + **field-types (S22)**.
5. **Translation tooling (S4/S6)** after the alias data-model decision.
6. **Async jobs (S20)** → **assistant extraction (S7/S8)**.
7. **Web/deep research (S5)** + **injection hardening (S24)** + **cost gate (S21)** — the net-new subsystem, last.
8. **Audit (S15)**, **relationships (S18)**, **spoiler (S23)**, **perms (S25)** — as product priorities dictate.

---

## LOCKED architecture decisions (2026-06-10)

All open questions resolved by the user. These are binding for the build campaign.

| # | Decision | Implication |
|---|---|---|
| **D1 — Sequencing** | **Cover ALL scenarios**, built **easy→hard** (by dependency), not a chosen subset. | The order below (Foundational → Group 1 → batch → schema → translation → async/extraction → web research) is the *path to full coverage*, not a menu. |
| **D2 — Alias model** | **First-class alias table** with a `language` column (NOT translations-of-the-`aliases`-attribute). | Migration + refactor every alias read/write — incl. extraction dedup `findEntityByNameOrAlias` (today reads the `aliases` *attribute*). **Foundational, touches the writeback path.** |
| **D3 — Async (S20)** | **Path B** job-handle on existing RabbitMQ/WebSocket infra. MCP-native Tasks deferred (`D-MCP-TASKS-MIGRATION`). | See S20 decision block. Standard for all expensive ops (S5/S7/S8/S15/large-S19). |
| **D4 — Destructive ops** | **Single confirm card + undo** (recycle-bin / revisions / merge-journal). | Generalize the card family with a destructive variant showing consequences + recoverability. |
| **D5 — Relationships (S18)** | **Glossary SSOT + KG derived** (two-layer, CLAUDE.md). | Author relationships as glossary `Relationship` entities; knowledge graph is the derived view via the event pipeline. |
| **D6 — Web research (S5)** | **Staged**: simple web-search MCP tool first → deep-research agent loop later (after async + injection-hardening mature). | Build last. Deep-research depends on D3 (async) + S24 (injection) + S21 (cost gate). |
| **D7 — Permissions (S25)** | **Honor share-grants now** (not owner-only). | Every assistant write-tool's ownership guard (`checkBookOwnership`) must consult **sharing-service** and distinguish **view-grant vs edit-grant** (a viewer must not write/delete). **Foundational, security-critical** — verify the sharing-service contract first; this is a `/review-impl` / AMAW candidate. |
| **D8 — Kind scope = 3-TIER (owner's original design)** | **System library** (platform-owner-only edit) + **per-user library** (a user's own kinds, shared across THEIR books) + **per-book derived** (selection/override/addition). | The current single global-mutable catalog is a **mis-implementation to repay** (see review H-A) — an early AI impl collapsed system+per-user into one global-shared catalog (`requireUserID`-only). **S2** "new kind" → per-user library (+ enable for book); **S3** "optimize for this book" → per-book override; neither touches system tier or other users. Repaying this is folded into **F3**. |

### Refinements (D9–D12, 2026-06-10 — second-round decisions)

| # | Decision | Implication |
|---|---|---|
| **D9 — Per-book derivation depth (refines D8)** | The per-book layer covers **kind enablement AND attributes** — each book selects which kinds are on, which attributes apply, and may **add/hide attributes per-book**. | F3 grows: an "**effective schema for book**" = global kind defs + per-book selections/overrides/additions. "Optimize kind for this book" (S3) **never** mutates the global kind. Touches entity-create attribute seeding + extraction profile (both must read the effective schema, not the raw global kind). |
| **D10 — Manage-grant tier (refines D7)** | Writes split by grant: **edit-grant** → create/edit; a **separate `manage`/owner grant** → destructive (delete/merge/reassign/purge). | **New cross-service dependency:** sharing-service must expose a `manage` permission tier distinct from `edit`. **Verify the sharing-service contract first — if absent, sharing-service work precedes F1.** The ownership guard returns the grant level; destructive tools assert `manage`. |
| **D11 — Alias migration = hard cutover (refines D2)** | One-release migration: move aliases `tags`-attribute → first-class table, switch **all** readers/writers together. | **Risk: high** — mandates a *complete* inventory of alias touch-points (`findEntityByNameOrAlias` extraction dedup, `cached_aliases`, entity read/write, search, wiki, translation-glossary) changed in one shot. **Real-PG tests + cross-service live-smoke REQUIRED before merge** (cross-service evidence rule). No compat window → no margin for a missed reader. |
| **D12 — Branch strategy** | **Merge PR #26 first** (arc P0–P6, done+verified), then open `feat/glossary-assistant-coverage` **from main**. | Campaign is a clean new branch off post-#26 main. The 4 analysis/decision doc commits currently on `feat/glossary-extracting-assistant` ride along with #26. |
| **D13 — Collaboration epic FIRST (resolves the D7/D10 gap)** | The platform has **no collaborative-permission model** (verified 2026-06-10: book = single `owner_user_id`; sharing-service = visibility only — `private`/`public`/`unlisted`, read-only). Honoring share-grants (D7/D10) requires building that model. **Decision: build the collaboration-permissions epic (E0) BEFORE the glossary Foundational phase.** | **New platform-wide prerequisite epic, not glossary-specific.** Rough shape: a `book_collaborators` table `(book_id, user_id, role ∈ {edit, manage})`; owner-only grant/revoke endpoints; a book-service permission-check (`grant level` for a user×book); ownership-guard + JWT/claims propagation; UI for the owner to invite/grant/revoke. **This gates F1 and therefore the whole campaign** — scope it as its own spec+plan (likely `/loom` L/XL + AMAW, security-critical). |

### Foundational prerequisites (must precede Group 1)

D2, D7, D8 each introduce a **load-bearing schema/guard change** that Group 1 tools will build on. Per D13, a **platform Collaboration epic (E0) precedes everything**, then a glossary **Foundational phase**, before the cheap Group-1 tooling:

0. **E0 — Collaboration-permissions epic (D13, platform-wide, gates F1):** `book_collaborators(book_id, user_id, role ∈ {edit, manage})`; owner-only grant/revoke; a book-service permission-check returning a user×book **grant level**; claims/guard propagation; owner UI to invite/grant/revoke. Its own spec+plan; security-critical (AMAW). **Until E0 lands, assistant writes are owner-only by necessity.**
1. **F1 — Share-grant ownership guard (D7+D10, depends on E0):** extend `checkBookOwnership` to consult E0 and return the **grant level** (`view`/`edit`/`manage`); fail-closed. Edit-tools assert ≥`edit`; destructive tools assert `manage`. *Security-critical — /review-impl or AMAW.*
2. **F2 — First-class alias model (D2+D11):** alias table + `language`; **hard-cutover** migrate the `aliases` attribute; rewire **every** reader/writer in one release (`findEntityByNameOrAlias` extraction dedup, `cached_aliases`, entity read/write, search, wiki, translation-glossary). **Real-PG + cross-service live-smoke before merge.**
3. **F3 — 3-tier kind/attribute scoping + per-book derivation (D8+D9, incl. repaying H-A defect):** **(a)** lock system-library mutation to platform-owner/admin; **(b)** add per-user scoping (`owner_user_id`) so user customizations never touch system/other-users — *this repays the early-impl global-mutable defect*; **(c)** per-book selection/override/addition tables + an "**effective schema for book**" read. **Every schema reader** must consume the effective schema: entity-create seeding, extraction profile, AND the `glossary_list_kinds` MCP tool. *Bigger than originally framed — it's a scoping correction, not just additive.*
4. **F4 — Card-family generalization (D4):** destructive variant + multi-row + cost line + field-type-aware controls (S22) — the real Group-1 enabler.
5. **F5 — Job-handle async pattern (D3):** the `{job_id}` + `*_job_status` + JobProgressCard scaffold on existing infra.

Only F1–F4 gate Group 1; F5 gates the extraction/research/batch scenarios.

### Revised build order (full coverage, easy→hard)

```
Phase -1 Collaboration:  E0 book_collaborators + roles (edit/manage) + grant/revoke + UI  [PLATFORM EPIC, gates F1]
Phase 0  Foundational:  F1 share-grants · F2 alias table · F3 per-book kinds · F4 card family
Phase 1  Group-1 reads: list merge-cands / unknowns / revisions / evidence / chapter-links / ai-suggestions
Phase 2  Group-1 writes: delete · triage-inbox · merge · reassign · restore · genre · evidence · chapter-link
Phase 3  Batch (F-batch, S19) → triage-batch, status-change-batch
Phase 4  Schema change-set (S2/S3) — bundled kind+attributes, add/edit/remove, per-book (D8)
Phase 5  Translation tooling (S4/S6) — on the new alias model (D2); batch translate
Phase 6  Async jobs (F5) → assistant extraction (S7/S8) with fill/overwrite/merge modes
Phase 7  Audit (S15) · relationships (S18, D5)
Phase 8  Web research (S5, D6) staged: web-search → deep-research; + injection-hardening (S24) + cost gate (S21)
```

Cross-cutting guards (S22 field-types, S23 spoiler, S24 injection, S26 language) are woven into the phases that need them, not separate phases.

### Clarification ledger — campaign-level is CLOSED; remaining questions are phase-scoped

Campaign architecture is fully decided (D1–D13, H-A reframe, S32). The questions below are **deliberately deferred to each phase's CLARIFY** (open them then, not now — they need that phase's context):

- **E0 CLARIFY (Phase -1):** which service owns `book_collaborators` (book-service vs sharing-service vs new)? grant propagation = JWT claims vs per-request permission-check endpoint? role set (just `edit`/`manage`, or more)? revoke semantics + cache lag? can a `manage`-grantee re-grant?
- **F3 CLARIFY (Phase 0, 3-tier repayment H-A):** per-user library = **copy** system kinds on customize, or **layered reference** (system + user-override)? **migration/attribution of existing global kinds** when per-user scoping is introduced (who owns the kinds an early impl created globally)? is a user's per-user library private, or shareable across a series (S27)?
- **Phase 5 (translation, S4):** which engine produces suggested names (existing translation-service 2-pass vs an assistant LLM call)? supported target-language set?
- **Phase 6 (async, post H-C spike):** the delivery mechanism (server-push turn vs poll-on-ask) — decided by the spike; plus job cancellation + result retention/TTL.
- **Phase 8 (web research, S5/D6):** which provider (Tavily/Brave/SerpAPI/…)? BYOK per-user vs platform-config? does it route via provider-registry (the invariant covers LLM/embedding/image/audio/STT — web-search is not listed) or a new integration? per-request cost ceiling.

**Design-internal (no user clarification needed — resolved during DESIGN):** MCP tool naming/namespacing; the change-set confirm mechanism redesign (H-D); the in-chat Undo affordance (D4); field-type-aware card controls (S22).
