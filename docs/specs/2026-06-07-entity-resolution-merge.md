# Spec — Entity Resolution / Coreference Merge (mui #1c)

- **Date:** 2026-06-07
- **Branch:** `glossary/ai-pipeline-v2`
- **Phase:** CLARIFY ✅ (PO locked 2026-06-07) → DESIGN.
- **Parent architecture:** `docs/03_planning/GLOSSARY_AI_PIPELINE_V2_ARCHITECTURE.md` (mui #1c).
- **Size:** **XL** — knowledge + glossary + frontend; **schema change** (merge_candidates + merge_journal); **destructive op** (merge/un-merge). Workflow: v2.2 human-in-loop (PO declined /amaw); proactively run `/review-impl` at POST-REVIEW on the merge-execution + un-merge paths.

---

## 1. Problem

One real entity is referred to by many names (姜子牙 / 姜尚 / 太公望 / 子牙 / 飞熊). Because the canonical id is name-derived (`sha256(user:project:kind:canonical_name)`), each name becomes a separate entity in the KG, and glossary likewise accumulates duplicates that exact-name/alias dedup can't catch. Nothing detects or merges them. The asymmetry (verified 2026-06-07): **knowledge already has merge** (`POST /entities/{id}/merge-into/{other}` + repo `merge_entities` in `neo4j_repos/entities.py:2066` + `entity_alias_map` anti-resurrection); **glossary has none** (no merge route — the big new build, R5).

## 2. CLARIFY locks (PO 2026-06-07)

| # | Decision | Locked |
|---|---|---|
| **L1 (TP3)** | Risk posture | **Human-confirms every merge.** No auto-merge in v1 (destructive + homonym risk e.g. two 李靖). Detect+rank+suggest only; the merge fires on explicit user confirm. |
| **L2 (SP2/SP3)** | DETECT signals v1 | **Name + KG-structural co-occurrence first** (works with the current data — dev KG has **0 entity-embeddings**). Embedding-cosine signal added later when the K11.5b pipeline produces vectors. |
| **L3** | Scope v1 | **Full DETECT + REVIEW + EXECUTE.** |
| **L4** | Workflow | v2.2 human-in-loop (no /amaw); `/review-impl` at POST-REVIEW for merge/un-merge. |

## 3. Design — three layers, glossary-as-curation

Consistent with the branch invariant (glossary = SSOT/curation; knowledge = AI compute; knowledge proposes INTO glossary; human approves). Merge candidates surface in glossary (like mui #1 suggestions); the human confirms in glossary; glossary executes the merge on canon (SSOT-first), then the event drives the KG.

### 3.1 DETECT (knowledge) — coreference candidate pass
- **Blocking** (avoid O(n²)): only compare entities of the **same kind** within the **same project**; bucket candidates by shared signal (shared alias token, shared chapter, shared relation neighbor) so each entity is compared to a bounded neighbor set.
- **Score (v1, no embedding):**
  - *name signal* — shared alias, substring/containment, normalized-name edit distance, honorific-stripped equality (reuse `canonical.py` canonicalization).
  - *KG-structural signal* — co-occurrence: shared chapters (EVIDENCED_BY same source), shared relation neighbors, appears-in same events. This is what catches 太公望↔姜子牙 (no shared characters in the name, but they co-occur in the same scenes).
  - (later) *embedding cosine* — when entity vectors exist.
- **LLM verify** for candidates above the score floor: prompt with evidence (mentions of A and B + their relations) + 封神 naming-convention hint → "same entity? consider 名/字/号/title; beware two different people sharing a name." Returns {same: bool, confidence, rationale}.
- **Output:** merge-candidate clusters `{entity_ids: [...], score, evidence: [...], rationale}`.
- **Where:** a new detect module (`app/extraction/coref_detect.py`) + an internal trigger (job or endpoint). Candidates are **proposed to glossary** (knowledge → glossary, best-effort) — not stored in knowledge.

### 3.2 REVIEW (glossary) — merge-candidate inbox
- **New table `merge_candidates`**: candidate_id, book_id, kind_id, member_entity_ids (UUID[]), suggested_winner_entity_id, score, evidence_json, rationale, status CHECK ('proposed'|'dismissed'|'merged'), created_at. UNIQUE on a normalized member-set key (idempotent re-propose).
- **New glossary internal endpoint** `POST /internal/books/{book_id}/merge-candidates` (knowledge calls) — upsert proposed clusters.
- **FE surface** (reuse the AI-Suggestions inbox pattern, second tab/type): list proposed clusters → show members (name/aliases/kind/chapter counts) + evidence + suggested winner → **Confirm merge** (pick/confirm winner) / **Dismiss** (status=dismissed; re-propose suppressed). Public list + actions (JWT).

### 3.3 EXECUTE (glossary) — the merge endpoint (R5, the big build)
- **New endpoint** `POST /v1/glossary/books/{book_id}/entities/{winner_id}/merge` body `{loser_ids: [...]}` (JWT, owner). Transactional:
  1. **Validate**: all in same book + same kind; winner ≠ loser; none already deleted.
  2. **Write merge_journal row(s)** (for un-merge) BEFORE mutating: `{journal_id, winner_id, loser_id, book_id, repointed: {table: [pk...]}, loser_snapshot_json, merged_by, merged_at}`.
  3. **Repoint FKs** loser→winner across: `chapter_entity_links` (ON CONFLICT (entity_id,chapter_id) → keep/merge), `entity_attribute_values` (+cascade `evidences`,`attribute_translations`) — attribute conflict policy: keep winner's value, append loser's as alias/evidence where sensible, **TP2**, `entity_enrichments` (repoint), `extraction_audit_log` (repoint).
  4. **`wiki_articles` UNIQUE(entity_id) conflict (TP2):** if both winner+loser have an article → policy: keep winner's article, archive loser's (revision-preserved) — do NOT silently drop. If only loser has one → repoint to winner.
  5. **Fold loser names → winner aliases** (so future extraction/dedup resolves the loser name to winner).
  6. **Soft-delete loser** (`deleted_at`), set `merged_into_entity_id = winner_id` (new column) for audit + un-merge.
  7. **Emit `glossary.entity_merged{book_id, winner_glossary_id, loser_glossary_id}`** to the outbox.
  8. Set merge_candidate status='merged'.
- **Un-merge** `POST .../merge-journal/{journal_id}/revert`: replay the journal (repoint back, restore loser from snapshot/recycle, clear merged_into), emit a compensating event. Reversible until purge.

### 3.4 KG sync (knowledge) — new event handler
- knowledge consumes `glossary.entity_merged` → calls the **existing** repo `merge_entities(winner, loser)` (rewires RELATES_TO/EVIDENCED_BY, unions aliases/counts) keyed by `glossary_entity_id` + writes `entity_alias_map` (anti-resurrection: future extraction of the loser name routes to winner). Idempotent (re-delivery = no-op). The compensating un-merge event → best-effort KG note (full KG un-merge is hard; record + log — acceptable since KG is derived and re-extraction reconverges).

## 4. Acceptance criteria
- AC1: 3 entities that are one character (e.g. 姜子牙/太公望/子牙 co-occurring) surface as ONE merge candidate; two different 李靖 (distinct contexts) do NOT (or surface low + human dismisses).
- AC2: no merge happens without explicit user confirm (L1).
- AC3: merge repoints ALL loser FKs to winner; no orphan rows; loser soft-deleted with `merged_into_entity_id` set.
- AC4: `wiki_articles` UNIQUE conflict resolved per policy (no 500, no silent data loss).
- AC5: un-merge restores pre-merge state (FKs repointed back, loser live again).
- AC6: `glossary.entity_merged` → KG `merge_entities` + alias_map; re-delivery idempotent.
- AC7: detection runs without entity-embeddings (name + KG-structural only) and is bounded (blocking, no O(n²)).
- AC8: every destructive path degrades safely (validation rejects bad merges with 4xx, never corrupts on partial failure — transactional).

## 5. Schema changes
- glossary: `merge_candidates` table; `merge_journal` table; `glossary_entities.merged_into_entity_id UUID NULL`.
- (knowledge `entity_alias_map` already exists.)
- **Migrations are L+ / destructive-adjacent** — additive tables + one nullable column; no data backfill. Reversible.

## 6. Phasing (verify each; the merge path is the load-bearing risk)
1. ✅ **G-merge (glossary):** merge_journal + `merged_into_entity_id` migration; the merge endpoint (FK repoint + wiki policy + journal + soft-delete + event); un-merge endpoint. **Heaviest + riskiest — DB-integration tests for every FK + wiki conflict + un-merge round-trip.** *(DONE + /review-impl: MED-1 alias-fold, MED-2 TOCTOU lock, MED-3a chain-guard, MED-3b per-loser results.)*
2. ✅ **K-sync (knowledge):** `glossary.entity_merged` event handler → repo merge_entities + alias_map. Unit + event-replay idempotency test. *(DONE + /review-impl: MED-1 orphan-relink compensation, MED-2 alias_map project_scope.)*
3. ✅ **G-cand (glossary):** merge_candidates table + `POST /internal/.../merge-candidates` (knowledge→glossary) + public list/dismiss + best-effort mark-merged. *(DONE 2026-06-07 + /review-impl: MED-1 mark-merged subset semantics — partial merge of a larger cluster no longer closes it. 12/12 glossary api + 19/19 knowledge glossary_client. Cross-service smoke → DEFERRED 062, after K-detect.)*
4. ✅ **K-detect (knowledge):** coref_detect (name + KG-structural blocking/score) + config-gated LLM verify + propose to glossary. *(DONE 2026-06-07 + /review-impl: HIGH-1 per-kind clustering — combined multi-kind scoring produced mixed clusters glossary rejects wholesale, losing valid same-kind pairs; MED-2 verdict-coerce — `bool("no")`==True inverted string rejects. 17/17 coref unit tests. Endpoint `POST /internal/coref/detect` + default-OFF auto-hook.)*
5. ✅ **FE:** merge-candidate review surface (AI-Suggestions inbox pattern) — list clusters + member detail + rationale → winner radio (defaults to suggested) → Confirm (R5 merge) / Dismiss + Undo toast (un-merge via journal_id). *(DONE 2026-06-07 + /review-impl: MED-1 — toast count now reflects actual merges, info-toast on no-op. 13/13 vitest + tsc clean. 4 locales × 2 namespaces.)*
6. **VERIFY:** cross-service live smoke (DEFERRED 062) — propose a candidate, confirm merge, assert loser soft-deleted + FKs repointed + KG merged; then un-merge round-trip. Token mandatory (≥2 services). **← ONLY REMAINING — needs a rebuilt stack + a duplicate-bearing project.**

**mui #1c is FEATURE-COMPLETE** (G-merge · K-sync · G-cand · K-detect · FE) — only the end-to-end live-smoke (062) remains, which is a data+infra condition, not code.

## 7. Risks (from architecture eval)
- **R5 (biggest):** glossary merge-execution is all-new; FK repoint across 6+ tables must be transactional + complete (AC3/AC8). Mitigation: journal-first, transaction, exhaustive per-FK tests, reuse knowledge's merge as a reference for edge-handling.
- **TP2:** `wiki_articles` UNIQUE under merge — explicit policy (§3.3.4), no silent loss.
- **R2/reversibility:** un-merge depends on the journal being complete; test the round-trip (AC5).
- **R3/homonym:** false-merge — mitigated by L1 (human-confirm always) + LLM verify + kind-aware.
- **Detection without embeddings (L2):** lower recall than embedding-based (won't catch purely-semantic coreference with no name/structural overlap); acceptable v1, embedding-signal is the documented upgrade.

## 7b. G-cand DESIGN (phase 3 — locked 2026-06-07)

Storage + plumbing only; the **scorer/detector is K-detect (phase 4)**. G-cand makes the candidate surface real so K-detect has a sink and the FE has a source.

- **Table `merge_candidates`** (additive migration `UpMergeCandidates`): `candidate_id`, `book_id`, `kind_id` FK→entity_kinds, `member_entity_ids UUID[]`, `member_set_key TEXT` (sorted-distinct member ids joined by `,` — the idempotency key), `suggested_winner_entity_id UUID NULL`, `score DOUBLE PRECISION`, `evidence_json JSONB`, `rationale TEXT`, `status` CHECK('proposed'|'dismissed'|'merged'), `created_at`, `updated_at`. **UNIQUE(book_id, member_set_key)**; INDEX(book_id, status).
- **Idempotent re-propose:** `INSERT … ON CONFLICT (book_id, member_set_key) DO UPDATE SET score/evidence/rationale/winner/updated_at **WHERE merge_candidates.status='proposed'**`. A conflict on a `dismissed`/`merged` row updates nothing → **re-propose suppressed** (spec §3.2). Returns the existing `candidate_id` either way.
- **Internal propose** `POST /internal/books/{book_id}/merge-candidates` (X-Internal-Token). Body `{candidates:[{member_entity_ids, suggested_winner_entity_id?, score?, evidence?, rationale?}]}`. Per candidate: require ≥2 distinct members; resolve `kind_id` from the winner (or first member) and require **all members live + same book + same kind** (else `skipped` with reason — a candidate spanning kinds/books is incoherent). Returns per-candidate `{candidate_id?, status:'proposed'|'suppressed'|'skipped', reason?}`.
- **Public list** `GET /v1/glossary/books/{book_id}/merge-candidates?status=proposed` (JWT, owner). Returns each candidate with **member detail** (entity_id, name, aliases, chapter_link_count) + kind_code + score + rationale + evidence + suggested_winner + status + created_at, so the FE inbox renders without N round-trips. Default status filter `proposed`.
- **Public dismiss** `POST /v1/glossary/books/{book_id}/merge-candidates/{candidate_id}/dismiss` (JWT, owner): proposed→dismissed. 404 wrong book/missing; 409 if already `merged` (can't dismiss a done merge); dismissing an already-`dismissed` row is idempotent 200.
- **No new "confirm" endpoint** — confirm == the existing R5 merge endpoint. Closing the loop (spec §3.3.8): on a successful `mergeOne`, best-effort post-commit mark any `proposed` candidate that contains BOTH winner and that loser as `status='merged'` (so the inbox doesn't show a resolved cluster). Best-effort: a failure is logged, never fails the merge.
- **knowledge `propose_merge_candidates(book_id, candidates)`** on `GlossaryClient` — mirrors `propose_entities` (best-effort, returns dict|None). K-detect will call it; G-cand ships it + a unit test.

**Files (L):** glossary `migrate.go` (+`UpMergeCandidates`), `cmd/.../main.go` (register), `merge_candidates_handler.go` (new: propose/list/dismiss + mark-merged helper), `server.go` (routes), `merge_handler.go` (best-effort mark-merged call); knowledge `glossary_client.py` (+method). Tests: `merge_candidates_test.go` (DB-integration), `test_propose_merge_candidates.py`.

## 7c. K-detect DESIGN (phase 4 — locked 2026-06-07)

The coref detector. **CLARIFY locks (PO 2026-06-07):** trigger = **on-demand internal endpoint + opt-in auto-hook (default OFF)**; LLM-verify = **config-gated, on by default with score-only fallback** when no judge model is configured. Signals = name + KG-structural (spec §3.1, no embeddings). **Candidate members are glossary-anchored entities only** — the propose endpoint (G-cand) validates glossary membership, and unanchored KG discoveries flow through mui#1 writeback first.

**Module split for testability** — `app/extraction/coref_detect.py`:
- **Pure scorer** (no I/O, the unit-test target):
  - `CorefEntity` record: `entity_id` (glossary_entity_id), `canonical_id` (KG node id), `name`, `canonical_name`, `aliases`, `mention_count`, `neighbor_ids: frozenset` (RELATES_TO neighbor KG ids).
  - `_name_signal(a,b)` = max(exact alias/name overlap, substring containment, honorific-stripped equality, normalized edit-distance similarity) — reuses `canonicalize_entity_name`.
  - `_structural_signal(a,b)` = Jaccard over `neighbor_ids` (catches 太公望↔姜子牙 — co-occur, no shared name chars).
  - `score_pair(a,b)` = weighted blend `name_weight·name + struct_weight·struct`, ∈[0,1].
  - `block_and_score(entities, …)` — **blocking** (bound O(n²)): bucket by shared exact alias/name token, shared neighbor id, and name char-bigram (drop buckets > MAX_BUCKET to avoid common-char explosion). Score only within-bucket pairs, dedup, filter ≥ floor, sort, cap at `max_pairs`. Returns `CandidatePair{a_id,b_id,score,name_score,struct_score,evidence}`.
  - `cluster_pairs(pairs)` — union-find → clusters of ≥2 glossary ids (transitive A-B,B-C ⇒ {A,B,C}).
- **Orchestrator** (`detect_from_records(records, llm, glossary, …)` — testable with fakes): score → LLM-verify above-floor pairs (kept only if `same==true`; **LLM failure degrades to score-only per-pair**, never drops a scored candidate) → cluster → suggested_winner = max `mention_count` → `glossary.propose_merge_candidates(book_id, candidates)`. Returns `DetectResult{clusters, proposed, suppressed, skipped}`.
- **Neo4j loader** (`_load_coref_entities`, thin, covered by live-smoke not unit) — one `run_read` Cypher per kind: anchored entities (`glossary_entity_id IS NOT NULL`) for the project + their RELATES_TO neighbor ids, `LIMIT max_candidates_per_kind`.
- **LLM verify** (`_verify_pair`) mirrors the Q4b online-judge call (`llm_client.submit_and_wait`, model from `coref_judge_model`/`_user`/`_model_source`); prompt = names + aliases + shared-neighbor evidence + 封神 naming-convention hint ("consider 名/字/号/title; beware two different people sharing a name") → JSON `{same, confidence, rationale}`.

**Endpoint** `POST /internal/coref/detect` (`app/routers/coref.py`, internal-token) body `{user_id, project_id, kinds?}` → `ProjectsRepo.get` resolves `book_id` → orchestrator. **Auto-hook**: gated `if settings.coref_auto_on_extraction` at the end-of-book branch in `internal_extraction.py` (reuses the mui#1 is-last-chapter gate; best-effort, default OFF).

**Config:** `coref_enabled=True`, `coref_auto_on_extraction=False`, `coref_score_floor=0.5`, `coref_name_weight=0.6`, `coref_struct_weight=0.4`, `coref_min_mentions=2`, `coref_max_pairs=200`, `coref_max_candidates_per_kind=500`, `coref_llm_verify=True`, `coref_judge_model=""`, `coref_judge_user=""`, `coref_judge_model_source="platform_model"`.

**Files (L):** knowledge `app/extraction/coref_detect.py` (new), `app/routers/coref.py` (new), `app/config.py`, `app/main.py` (register router), `app/routers/internal_extraction.py` (auto-hook); tests `tests/unit/test_coref_detect.py`. Cross-service live-smoke = the mui#1c phase-6 VERIFY (DEFERRED 062) once a real duplicate-bearing project exists.

## 7d. FE DESIGN (phase 5 — locked 2026-06-07)

Reuses the mui#1 **AI-Suggestions inbox** pattern (panel + hook + badge in GlossaryTab; gateway auto-proxies `/v1/glossary/*` — no gateway change). Surface = spec §3.2: list proposed clusters → member detail + evidence + suggested winner → **Confirm** (pick winner → R5 merge) / **Dismiss** (G-cand dismiss). Un-merge affordance = an **Undo toast** after a confirm (the merge response carries `journal_id`s → revert), so no journal-list endpoint is needed.

- **`api.ts`**: `listMergeCandidates(bookId, token)` GET `.../merge-candidates?status=proposed`; `confirmMerge(bookId, winnerId, loserIds, token)` POST `.../entities/{winner}/merge`; `dismissMergeCandidate(bookId, candidateId, token)` POST `.../merge-candidates/{id}/dismiss`; `revertMerge(bookId, journalId, token)` POST `.../merge-journal/{id}/revert`.
- **`types.ts`**: `MergeCandidateMember{entity_id,name,aliases,chapter_link_count}`, `MergeCandidate{candidate_id,kind_code,score,rationale,evidence,suggested_winner_entity_id,status,created_at,members[]}`, `MergeCandidateListResponse{candidates[]}`, `MergeResult{winner_id,results[{loser_id,journal_id,status,reason}]}`.
- **`hooks/useMergeCandidates.ts`**: query `['glossary-merge-candidates',bookId]`; actions `confirm(candidate, winnerId)` (losers = members − winner → confirmMerge; returns journal_ids for undo), `dismiss(candidate)`, `undo(journalId)`. All invalidate the inbox + `['glossary-entities',bookId]`.
- **`components/MergeCandidatePanel.tsx`** (+ a compact `MergeCandidateCard` sub-component to respect the ~100-line rule): per cluster — member rows with a winner radio (defaults to `suggested_winner_entity_id`), evidence/score summary, Confirm + Dismiss. Confirm success → `toast.success` with an **Undo** action calling `undo(journal_id)`.
- **`GlossaryTab.tsx`**: `['glossary-merge-candidates',bookId]` count query → conditional button (badge) → `setView('merge_candidates')` → `<MergeCandidatePanel>`.
- **i18n**: `books.json` `glossary.merge_candidates` (button) + `glossaryEditor.json` `merge_candidates.*` (panel), all 4 locales (en/vi/ja/zh-TW).
- **Tests**: `useMergeCandidates.test.tsx` (load/confirm-losers-computed/dismiss/invalidate) + `MergeCandidatePanel.test.tsx` (render cluster, winner-pick, confirm→undo-toast, dismiss).

**Files (L):** `api.ts`, `types.ts`, `hooks/useMergeCandidates.ts` (new), `components/MergeCandidatePanel.tsx` (new), `pages/book-tabs/GlossaryTab.tsx`, i18n (8 files), 2 tests. Confirm triggers the destructive R5 merge via API — covered by component test + the existing G-merge DB tests.

## 8. Confirm-at-BUILD
- Exact glossary FK inventory + ON DELETE/UPDATE (chapter_entity_links, entity_attribute_values+evidences+attribute_translations, entity_enrichments, wiki_articles, extraction_audit_log) — re-read `migrate.go` before the repoint.
- knowledge repo `merge_entities` signature + whether it's safely callable from an event handler (not just the JWT route).
- glossary outbox event emission helper (reuse `insertEntityOutboxEvent` shape) + a new `glossary.entity_merged` event type the knowledge consumer registers.
- KG-structural co-occurrence query shape (shared EVIDENCED_BY source / shared relation neighbor) in Neo4j.
