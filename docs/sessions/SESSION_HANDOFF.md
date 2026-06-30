# ▶▶ NEXT SESSION STARTS HERE — **Temporal Knowledge Architecture — substrate + merge/split + KG side DONE; F4 KAL service NEXT** · branch `feat/temporal-knowledge-architecture` · HEAD `f52e50f7`+ · 2026-06-30

> **What this branch is:** implementing the Incremental Temporal Knowledge Architecture
> ([spec](../specs/2026-06-29-incremental-temporal-knowledge-architecture.md) §12/§12.7.8 govern;
> [plan](../plans/2026-06-30-temporal-knowledge-architecture-impl.md)). Append-only bi-temporal facts as the
> sole SSOT (INV-FACTS §12.0); everything else a rebuildable cache. Execution = **serial foundation → parallel
> fanout** (user-directed: build foundation serially, checkpoint, then fan out consumer migrations).
>
> **▶ Shipped this session — the SSOT substrate spine, all real-DB verified on `loreweave_glossary`:**
> - **F0** `fc4c9a80` — froze the **KAL v1 contract** (`contracts/api/knowledge-gateway/kal.v1.yaml`), the keystone
>   every consumer binds to; `knowledge-gateway: missing` row in `language-rule.yaml` (→ typescript at F4 scaffold).
> - **F1a** `ae6f17fd` — `0044` **entity_facts + episodes** bi-temporal SSOT schema (content-addressed natural key,
>   `valid_to_eff` INT64_MAX null-sink, `coverage_xid` xid8, merge_journal fact/episode-move cols). Idempotent 2×.
> - **F1b** `728efaf9` — `0045` **maintain_chain** the single `valid_to` writer (§12.3.3). Verified all 3 scenarios:
>   out-of-order backfill (A2), retract restitch (A3), oscillation (A4).
> - **F1c** `8a2b8e6d` — **fact core** Go (`facts.go`): appendFact (idempotent NK), retractFacts (restitch),
>   ingestEpisode, refreshEAVProjection (repair/cutover), per-(entity,attr) chain lock. `TestFactCore` PASSES (real DB).
> - **F1h** `8eb419f9` — `0046` **cold-start seed**: 22,056 facts seeded from live EAV; **projection==flat_eav 0 mismatches** (§12.5.4/D5).
> - **F2 schema** `fdf6c0d8` — `0047` **canonical versioned-cache** tables (canonical_snapshot + canonical_fold_state), §12.1.
>
> ⚠ Migrations **0044–0047 are applied to the running dev `loreweave_glossary`** (by F1c's `RunChain`); a fresh stack
> picks them up from the ledger on boot.
>
> **▶ PARALLEL track (background agent, worktree):** **F3 — KG ordinal valid-time unify** in `knowledge-service`
> (Python/Neo4j) — substrate-independent from glossary. Ordinal valid-time unified with `from_order`, ordinal-aware
> close (A2 on the KG side), extraction-driven invalidate/retract, quote-on-citation, per-entity ordinal snapshot.
> **Merge its worktree branch at the integration node before F4.**
>
> **▶ F3 — KG ordinal valid-time unify — MERGED `f2d5ca3e`** (was a parallel worktree agent); 24 F3 unit tests
> re-verified green post-merge. All under `services/knowledge-service/` (disjoint from glossary).
>
> **▶ F1f — fact-chain merge + split (DONE):** `ecc7e587` **merge** (§12.4.1, `mergeFactChains`/`revertFactChains`,
> journal `repointed_fact_ids`+`invalidated_fact_ids`, same-ordinal tiebreak, chain locks both sides) +
> `f52e50f7` **split** (§12.4.2, `splitFactsByEpisode` re-attribute-by-provenance, originals reason='split').
> `TestMergeFactChains`/`TestSplitFactsByEpisode` green; existing Merge/Revert/Dedup suites green (no regression).
>
> **▶ NEXT (remaining foundation, then fanout):**
> 1. **F4 — the KAL TypeScript service** (`services/knowledge-gateway`, NestJS like mcp-public-gateway) implementing
>    `kal.v1.yaml`: current-projection reads delegating to glossary + KG, write verbs delegating to the new fact core,
>    per-substrate `as_of` gating (KG `temporal_unsupported`→`ordinal_valid_time` now that F3 landed), bounded-complete
>    `roster`, `list_attr_values`; the **2 INV-KAL lints**; flip `language-rule.yaml` `missing`→`typescript`. Needs an
>    npm install/build/test cycle — a focused effort.
> 2. **F2 app** — the fold handler: lazy rebuild-on-read + ordinal-bucketed re-ground (B1) + compare-and-clear + backoff
>    (needs a provider-registry LLM call). Enhances `get_canonical` behind the frozen contract.
> 3. **F1g** — bi-temporal name/aliases (§12.4.3) + as-of-name. **Value partly gated on F1d** (deferred writeback wiring);
>    reconciles `D-TK-F1G-NAME-RECONCILE`.
> 4. **CHECKPOINT** → then parallel **fanout** X1–X7 (consumer migrations onto the KAL, FE temporal surfaces).
>
> **▶ Deferred Items (temporal-knowledge):**
> - **`D-TK-WRITEBACK-ORDINAL` (F1d)** — gate #1/#2 (cross-service contract): wire additive Path-A fact emission into the
>   glossary writeback. Needs the extraction caller (translation-service) to pass `chapter_ordinal` in the bulk-extract
>   request (currently absent — only chapter_id+content_hash). Glossary side accepts it optionally; caller update is a fanout item. Target: F1d.
> - **`D-KAL-HTTP-SURFACE-LINT` (D6)** — gate #2: the HTTP-surface INV-KAL lint (no consumer client hits owning-svc
>   `/internal/*` knowledge endpoints). Table-read grep ships in F4; HTTP-surface tracked-for-migration. Target: X7.
> - **`D-KG-INSTORY-EVENTDATE`** — gate #2: detected in-story time (`event_date_iso`) as a valid-time source (spec §9 dec-3). Target: post-foundation.
> - **`D-TK-F1G-NAME-RECONCILE`** (from /review-impl LOW-1) — gate #3 (naturally-next-phase): the cold-start seeds `name`/`aliases` as single-valued `attribute` facts (D5 projection depends on it). When **F1g** lands name/aliases as `fact_kind IN ('name','alias')` multi-valued bi-temporal facts (§12.4.3), it MUST supersede those cold-start attribute-facts so an entity carries one representation. No interim corruption (maintain_chain matches fact_kind). Target: F1g.
>
> **▶ /review-impl (2026-06-30) — 7 findings, ALL FIXED (no HIGH):** MED-1 same-ordinal single-valued conflict → last-write-wins supersede + deterministic projection tiebreak (`TestFactSameOrdinalConflict`); MED-2 unenforced chain-lock → strengthened contract doc + `TestFactChainLockSerializes` (same-chain blocks, disjoint free); LOW-2 cold-start ordinal `0→-1` (chapter_index is 0-based); LOW-5 targeted `ON CONFLICT` on the natural-key expression index; LOW-3 `refreshEAVProjection` attr_def_id-coupling doc; LOW-4 `reconcileEpisode` F1d-obligation doc + now exercised; LOW-1 → `D-TK-F1G-NAME-RECONCILE` above. All 3 facts tests green on real DB; cold-start re-verified `projection==flat_eav` 0 mismatches with the `-1` sentinel.

---

# ▶▶ (prior) **Motif book-collaboration tier (model B) + shared-graph links + MCP edit SHIPPED** · branch `feat/narrative-pattern-library` · HEAD `8c4c45c2`+ · 2026-06-29

> **▶ MERGE 2026-06-29:** `origin/main` merged into this branch (179 commits — the **public-MCP gateway + lazy tool-loading** track, critical-UX fixes, glossary/knowledge/campaign work). Conflicts resolved (composition `actions.py` confirm = JWT-identity ∪ public-MCP spend-attribution; engine `plan.py`/`stitch.py` signatures = both; studio panels = `canonview` ∪ `motifs`/`conformance`; gateway test `mcpPublicGatewayUrl`). The motif MCP tools are exposed to the public-MCP gateway: `find_tools` (lazy discovery) picks them up dynamically from the federation catalog, and they are classified in the edge `TOOL_POLICY` allowlist (commit `2aa65765`). Below is this branch's motif work; the merged-in main tracks + all prior history are archived (see the pointer at the bottom).

> **▶ Follow-up this session (2nd commit) — both model-B deferrals CLOSED:** `D-MOTIF-LINK-SHARED-TIER` (shared-graph link editing — guard rewrite + repo/MCP book_id paths) and `D-MOTIF-MCP-PATCH-SHARED` (the `composition_motif_patch` MCP edit tool). Details in the "Deferred … BOTH NOW CLEARED" block below. 150 motif unit tests + 38 motif DB integration tests green; migration re-smoked idempotent on real `loreweave_composition`; provider-gate clean.

> **▶ Shipped this session — the two NEW future-feature rows (now CLOSED):**
> - **`D-MOTIF-ADOPT-BOOK-COLLAB-TIER` (model B) — a THIRD tenancy tier (the book SHARED library).** Spec: [docs/specs/2026-06-29-motif-book-collab-tier.md](../specs/2026-06-29-motif-book-collab-tier.md). A `motif.book_shared=true` row is owned by its creator (attribution) but VISIBLE to the book's VIEW-grantees and WRITABLE by its EDIT-grantees — access is the **book grant resolved at the caller**, never row ownership. User decisions (this session): **context-scoped reads** (per-book gate, no global "all my books"), **any-EDIT-grantee writes** (edit + archive), **adopt + create + mine** all produce shared rows. The base read predicate is **UNCHANGED** (a foreign shared row is fail-closed invisible to get_visible/list_for_caller/catalog/get_by_codes); shared rows surface ONLY through the gated book-context methods. Touch-points: schema (`book_shared` col + `motif_book_shared_shape` CHECK [shared ⇒ book+owner+private, the public-catalog-orthogonality guard] + per-book `uq_motif_book_shared` + re-narrowed `uq_motif_user_book WHERE …AND NOT book_shared`); repo (`clone/adopt/create/_clone_with_code` thread book_shared; new `list_in_book/get_in_book/patch_shared/archive_shared`; adopt locks per-BOOK + dedups per-(book,code) for the shared tier); MCP (`adopt target=book_shared`, `create target=book_shared`, `mine promote_target=book_shared`, `archive book_id=`, new `composition_motif_book_list`); confirm dispatch (`book_shared` rides the payload, re-gated EDIT); FE (3rd adopt target "Share with collaborators" + `Shared` badge).
> - **`D-MOTIF-HTTP-ADOPT-BOOK` — HTTP parity.** `POST /motifs/{id}/adopt` now takes `target=user|book|book_shared`+`book_id`, **EDIT-gated before the clone** (no softer than MCP); `GET /motifs/book/{id}` (VIEW-gated list); `PATCH`/`DELETE …?book_id=` (EDIT-gated shared edit/archive, visibility-flip refused 400). A book-shared pattern root does NOT auto-adopt its members (the half-shared-pattern guard).
>
> **VERIFY:** 90 motif unit tests + new repo/mcp/router cases green; **integration (real PG)**: new `test_motif_book_shared_db.py` (shape CHECK, per-book dedup, list/get scoping, any-grantee patch/archive) + 32 existing motif DB tests pass on a throwaway DB; **migration live-smoked idempotent on the REAL existing model-A `loreweave_composition`** (added book_shared col + CHECK + uq_motif_book_shared + re-narrowed uq_motif_user_book; two runs, no error). FE 152 motif tests + tsc + provider-gate clean. **`/review-impl` adversarial tenancy review: 0 HIGH / 0 MED** — all 9 read/write/leak/confirm/dedup checks PASS with file:line evidence; 3 LOW/COSMETIC notes (deferred below).
>
> **▶ Deferred (from the model-B review — BOTH NOW CLEARED 2026-06-29):**
> - ✅ **`D-MOTIF-LINK-SHARED-TIER`** — **CLEARED:** the `motif_link_guard` was rewritten (NULL-safe) to a precise 3-arm same-tier rule — both SYSTEM, or both the SAME book's SHARED tier (owners may differ — the point of a collaborator graph), or both the SAME user's PRIVATE tier. A shared↔private/system/cross-book link is rejected at the DB. Repo `list_links/create_link/delete_link` gained a `book_id` path (anchor via get_in_book; both endpoints must be `book_shared AND book_id`); MCP link tools take `book_id` (VIEW for list, EDIT for create/delete). Live-PG tested (same-book allowed, 3 cross-tier rejections, 3rd-grantee list/delete) + migration re-smoked idempotent on real `loreweave_composition`. **Caught+fixed a SQL three-valued-logic bug**: `owner = owner` with a NULL operand yields NULL so `IF NOT NULL` wouldn't fire (a user→system link would have slipped) — every arm is now NULL-guarded.
> - ✅ **`D-MOTIF-MCP-PATCH-SHARED`** — **CLEARED:** new `composition_motif_patch` MCP tool (Tier-A) — owner-keyed by default, or a SHARED-tier edit with `book_id` (EDIT-gated → patch_shared). Optimistic-lock `expected_version` (stale → applied_conflict), visibility/publish deliberately NOT editable (separate flow), honest undo that patches changed fields back to prior values. Owner path denies a foreign row before any write; shared path confirms the row is shared-in-this-book.
>
> ---
>
> # ▶▶ (prior) **Motif library COMPLETE — audit 7/7 closed (WI-1…WI-6)** · HEAD `04bab448`+ · 2026-06-29

> **What this branch is:** the narrative-pattern (motif/arc) library — Tier-W cost-gated MCP flows for mining, conformance, adopt, and 3-way publish-sync, fronted by the FE→MCP-tool bridge. The feature body landed across prior sessions; this session closed the **completeness-audit tail** AND shipped **WI-5 per-book adopt**.
>
> **▶ Shipped this session (all green — 1083+ backend unit + 151 FE motif tests, tsc + provider-gate clean):**
> - **Audit tail (committed `f1157b25`…`b8f0ddb3`):** BYOK model_ref threading through `motif_mine`/`arc_import`; the **tag-beats LLM extractor** (knowledge `POST /internal/extraction/tag-beats` → composition mine pre-pass; cross-tenant injection neutralized); **WI-3 arc semantic retrieve** (`composition_arc_suggest`); **WI-1/WI-2/WI-4 FE** (mine panel, full editor, publish-sync); `/review-impl` fixes (arc back-fill scoped to own/system; editor edit-loss). Completeness audit: [`docs/reports/2026-06-29-motif-completeness-audit.md`](../reports/2026-06-29-motif-completeness-audit.md).
> - **WI-5 per-book adopt (`D-MOTIF-ADOPT-PER-BOOK`) — model A "book-scoped filter" (user-chosen, NOT the tier-reversal):** `motif.book_id` is a per-book LABEL on a clone the adopter still owns. The read predicate + 2-tier tenancy are **UNCHANGED** (book_id only narrows the owner's view, never widens visibility). Design: [`docs/plans/2026-06-29-motif-adopt-per-book.md`](../plans/2026-06-29-motif-adopt-per-book.md). Touch-points: schema (`book_id` col + `uq_motif_user` scoped to `book_id IS NULL` + new `uq_motif_user_book` partial + `idx_motif_book`); `MotifRepo.clone/adopt/_clone_with_code/list_for_caller`; `_MotifAdoptArgs.target=Literal['user','book']`+`book_id` (EDIT-gated at propose **and** confirm); FE adopt-to-book toggle (api/hook/AdoptTargetModal/MotifLibraryView). **Live-smoked** on real `loreweave_composition`: migration idempotent; global+per-book coexist; same-book dup blocked by `uq_motif_user_book`; 0 leaked rows.
> - **WI-6 motif_link edge-walk (`D-MOTIF-LINK-EDGEWALK`) — the FINAL §5 gap, closing the audit 7/7:** 3 MCP tools — `composition_motif_link_list` (R, traverse out/in/both with neighbor code+name), `composition_motif_link_create` + `_delete` (A). User-scoped; WRITE requires **BOTH endpoints owned by the caller** (the system↔system hole the DB `motif_link_guard` same-tier check misses — a user may never reshape the shared graph). `MotifRepo.list_links/create_link/delete_link`. **Live-smoked**: own→own create/list/delete OK; own→system rejected by the guard; 0 leaked rows. The completeness audit is now **7/7 closed, nothing deferred**.
>
> **⚠ Two already-built misfires earlier this session** (memory [[verify-built-before-building]]): `D-W8-MOTIF-BEAT-EXTRACTOR` and `D-MOTIF-SYNC-3WAY-BASE` backend were **already shipped** — I rebuilt a duplicate sync router and reverted it (`a24d99ea`). **Before building ANY "missing"/deferred motif item: `git grep` the route/module/test first.**
>
> **▶ NEXT:** **PR `feat/narrative-pattern-library` → main** — the feature body + audit tail + WI-5 are complete, green, and live-smoked. (Note: the WI-5 migration was applied to the *running* dev `loreweave_composition` by the live-smoke; a fresh stack picks it up from `migrate.py` on boot.)
>
> **▶ Deferred (motif — the §5 audit tail is 7/7 CLOSED; these were NEW future-feature rows):**
> - ✅ **`D-MOTIF-ADOPT-BOOK-COLLAB-TIER`** — **CLEARED (2026-06-29):** model B shipped (see the top block). The shared book tier landed with a 0-HIGH/0-MED adversarial tenancy review.
> - ✅ **`D-MOTIF-HTTP-ADOPT-BOOK`** — **CLEARED (2026-06-29):** the HTTP adopt route exposes `target`+`book_id`, EDIT-gated (see the top block).

---

> **▶ Archived 2026-06-30** — older / other-track handoffs moved to [`SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md) to keep this file to the **active branch** only. The 2026-06-29 merge pulled in main's `Critical UX` + `Public MCP` tracks and all prior session history (glossary / composition / roleplay / extraction / KG / campaign / Sessions 66–71); all of it (incl. each track's open-defer register) lives in the archive and on its own branch + `main`. Search `SESSION_ARCHIVE.md` for a `D-…` id if you need a prior-track defer.
