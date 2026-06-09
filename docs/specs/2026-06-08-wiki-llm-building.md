# Wiki LLM-Building Upgrade — Design Spec (v3, + change-control layer)

- **Date:** 2026-06-08
- **Branch:** `wiki/llm-building` (cut from `main` @ `09fca211`)
- **Phase:** DESIGN v3 — v2 (4-pipeline sibling-review hardening) + a **Change-Control layer** from a
  knowledge-change architecture evaluation (3-pipeline mining: event bus, staleness precedents, entity
  lifecycle). Awaiting PO sign-off.
- **Task size:** **XL** — services: knowledge, glossary, book, provider-registry, learning; schema; new
  worker; new contracts; FE. `/loom` or `/amaw` BUILD recommended. Ships in **phases** (see §8).
- **Status legend:** 🔒 LOCKED · 🟡 PROPOSED · ✅ RESOLVED-by-review · 🟥 P0 · 🟧 P1 · 🟩 P2 · 🟦 phase-2

> **v1 → v2:** single-shot was under-designed. Sibling pipelines proved a grounded generator **cannot
> police its own grounding** (translation-v3), raw novel text is the **highest-risk injection vector**
> (lore-enrichment), and `wiki_articles.entity_id UNIQUE` makes naive writeback **clobber human edits**.
> → bounded multi-pass + 2 P0 safety fixes + feedback/eval flywheel.
>
> **v2 → v3:** wiki is not N one-shot articles — it is a **materialized view over a versioned, multi-service
> knowledge base that changes continuously** (chapters translated, attrs edited, entities merged, enrichments
> promoted, KG edges added). The hard problem is **controlling that change**. PO policy locked: **(1) NOT
> realtime CDC — capture change, defer the work in a DB ledger; (2) regeneration costs tokens → the user
> decides what/when to regenerate.** v3 adds a Change-Control layer (§5) split into *capture* (cheap, auto,
> **MVP**) vs *defer + decide* (**phase-2**, user-gated), plus entity-lifecycle propagation and 2 pre-existing
> data-loss bug fixes.

---

## 1. Problem

The wiki feature (in **glossary-service**, Go) is "mostly CRUD". Its generator —
`POST /v1/glossary/books/{book_id}/wiki/generate` → `generateWikiStubs` → `renderWikiBody` — is a
**deterministic Go template renderer with NO LLM**: it concatenates glossary attrs + 1-hop KG relations +
promoted enrichments into fixed Chinese TipTap sections. Articles read as attribute dumps, not prose.

Worse, even a great generator is not enough: a wiki is a **large, evolving derived corpus**. An article
generated today is built from knowledge-state-at-T; as the book evolves to T+1 the article silently goes
**stale**. The design must therefore treat the wiki as an **incrementally-(re)materialized view** whose change
is *captured, deferred, and reconciled under user control* — not a batch of fire-and-forget generations.

**Goals:** (a) grounded, cited, readable LLM articles from the source text; (b) **control knowledge change** —
generate / resume / merge / **update** a huge corpus without losing human work or silently serving stale
prose; keep the deterministic renderer as a degradation floor and glossary as the authored SSOT.

### Non-goals
- Not replacing wiki CRUD / revisions / suggestions (stays in glossary).
- Not writing Neo4j canonical content (Q2 LOCKED — read-only KG).
- Not auto-publishing AI output (lands `draft`, human promotes — H0 quarantine ethos).
- **Not realtime regeneration.** Change is captured and deferred; regeneration is always user-initiated.

---

## 2. Architecture (🔒 LOCKED)

The LLM wiki-generation flow lives in **knowledge-service** (Python) as a module + **durable-stream-driven
worker** — NOT glossary (Go; LLM SDKs are Python-only; language rule + provider-gateway invariant). It owns
the raw-search retriever (call **in-process**), the KG, and installs the grounding SDK. glossary stays the
SSOT + front door. Code template = **lore-enrichment** `runner→generate→verify→writeback`.

Two cooperating planes:
- **Generation plane** (§3–4): produce one grounded article on demand.
- **Change-control plane** (§5): track what each article was built from, *capture* knowledge change into a
  *deferred ledger* (no work), and let the user *decide* what to regenerate (cost-gated).

### 2.1 End-to-end flow (generation)

```
FE → api-gateway-bff
  → glossary POST /v1/glossary/books/{book_id}/wiki/generate   (Go — auth, entity selection, SSOT front door)
       body: { kind_codes?, limit?, model_ref?, model_source?, step_models?, force? }
       ├─ model_ref ABSENT → deterministic renderWikiBody (synchronous, unchanged) ............. FALLBACK FLOOR
       └─ model_ref PRESENT → POST knowledge /internal/knowledge/books/{id}/wiki/generate
            knowledge: cost preflight (budget.can_start_job) → INSERT wiki_gen_jobs row
                       → XADD loreweave:events:wiki-gen {job_id,user_id,book_id} → return 202 {job_id}
  ── knowledge-service wiki-gen CONSUMER (flag-gated, clones resume_consumer.py) ──
     for each entity (skip if already generated this job — skip-done-before-spend):
       budget.charge_or_pause → on breach: job 'paused', stop (resumable)
       0. CONTEXT  attrs + KG neighborhood + raw passages (in-process run_hybrid_search, rerank=true)
       0b. SANITIZE every untrusted string BEFORE prompting (neutralize_injection)                🟥 P0
       1. WRITE (prose model) → grounded TipTap body; claims tagged grounded + cite-id; BookProfile-shaped
       2. RULE-GATE (free) → every [n] resolves to a passage? sections present? drop un-cited claims        🟧
       3. VERIFY (verify model) → CanonVerifier + decide_auto_reject                                         🟧
       4. REVISE (prose model) → only if HIGH flags, max 1 round; keep-if-improved deterministic
       5. CITE compose_cites → weave [n];  capture build_inputs fingerprint + source usage (§5.1)            🟥
       6. reconcile cost; advance_cursor
       7. WRITEBACK POST glossary /internal/books/{id}/wiki/articles { body, provenance(+build_inputs),
                    source_usage[], publish_blocked, verify_flags } (retried; idempotent; clobber-guarded)   🟥
  ── glossary (Go) ──
       upsert-by-entity (entity_id UNIQUE): AI overwrites ONLY untouched author_type='ai' draft;
       else → wiki_suggestion; tx INSERT wiki_articles + wiki_revisions(author_type='ai')
       + wiki_article_source_usage rows (§5.1) + flip generation_status; emit feedback events (§4.11)
```

Zero-regression: no `model_ref` ⇒ today's behaviour.

---

## 3. Generation: bounded multi-pass (🟥 P0)

**Why not single-shot:** translation-v3 proves the generator is blind to its own grounding violations; a
verifier that can only *quarantine* is half a system. Wiki's contract is *harder* (synthesize vs preserve).

| Pass | Model tier | What |
|---|---|---|
| 1. WRITE | prose (strong) | plan sections → grounded TipTap body; mark each claim `grounded` + cite-id |
| Gate A. RULE-CHECK | none (free) | every `[n]` resolves to a real supplied passage; required sections present; drop/flag un-cited claims — the wiki analogue of v3 `verifier.py:62`; this is what *guarantees* grounding |
| 2. VERIFY | verify (cheap) | `CanonVerifier` (injection/anachronism/regurgitation/contradiction) + `decide_auto_reject` |
| 3. REVISE | prose (strong) | **only if** HIGH flags, **max 1 round**; re-write flagged sections only |

Calibration copied from translation-v3 (`orchestrator.py:230,:300`): **LLM-flag demotion** (LLM-only flag never
triggers a destructive rewrite) + **deterministic keep-if-improved** (accept revise only if the rule-count
drops). Hard ceiling 1 round for MVP. NOT a multi-round loop.

---

## 4. Detailed design (generation)

### 4.1 Retriever — in-process refactor 🟡
Extract `search_book` body into `async def run_hybrid_search(...) -> RawSearchResponse`; public route becomes a
wrapper. Wiki worker calls it directly — no HTTP/JWT/`not_indexed`. Params: `mode=hybrid`,
`granularity=chapter`, `limit≈8–15`, **`rerank=true`** (cosine band [0.68,0.82] non-separable), gate on
`relevance`, carry `location.blockIndex`.

### 4.2 wiki-gen module (NEW `app/wiki/`) 🟡
`context.py` (clone enrichment `assembly.py`) · `sanitize.py` (LE `clients/sanitize.py:56`) 🟥 ·
`prompt.py` (BookProfile-shaped; LE `generate.py:114-187`) · `generate.py` (LE `complete.py` + grounded-flag
`generate.py:190-230`) · `rulegate.py` (v3 `verifier.py:62`) 🟧 · `revise.py` (v3 `corrector.py:44`) ·
`cite.py` (SDK `cites.py:92`) · `verify.py` (LE `wiring.py:92-139`) · `fingerprint.py` (build_inputs hash, §5.1) 🟥 ·
`runner.py` (LE `runner.py:149` + skip-done `:200-205`) · `cost.py` (knowledge `jobs/budget.py:48`) ·
`consumer.py` (LE `resume_consumer.py:138-193`) 🟧 · `eval/` (knowledge `app/benchmark/metrics.py`) 🟩.
**Transport = async-job** (`submit_and_wait` — retry yes, cost-cap is the job layer not the SDK).
**Trigger = direct internal HTTP** (mirror `fetchWikiNeighborhood`).

### 4.3 Prompt + output contract 🟡 (✅ closes language open-Q)
- **BookProfile-shaped** 🟧: interpolate `worldview / voice / era_policy / language` into the prompt;
  `profile.language` decides generation language (Chinese-only renderer was the de-bias bug). Unset →
  `NEUTRAL_PROFILE`. **BookProfile stays in lore-enrichment (AI-domain — the correct boundary: it
  carries LLM-detected de-bias config + anachronism markers + dimension overrides, NOT book core
  identity).** knowledge-service reads it via a new internal-token `GET /internal/lore-enrichment/
  books/{id}/profile` (additive to LE's existing profile API). NOT moved to book-service — that is
  Go/CRUD and cannot host the LLM detection (`profile_suggest.py`); pushing AI-config there is the
  wrong boundary (decided after scoping — see §9).
- **Copyright guard at gen time** 🟧: "**synthesize in your own words; do not copy source phrasing**" — note it
  fights the cite-everything instruction (raises regurgitation LCS); auto-reject wholesale copy only.
- **Structural cite-enforcement** 🟧: grounded-flag protocol — un-cited claims dropped at parse; zero grounded →
  skip entity (actionable reason, no hollow stub). Mirror `provenance.py:268-319`.
- **Output:** TipTap `doc` (FE renderer unchanged) + references list + inline `[n]` anchored to `blockIndex`
  (reuses raw-search `?block=N`). Enriched/KG facts keep H0 `source_type` marker.

### 4.4 Security: injection sanitize 🟥 P0
Raw passages → prompt is the **highest-risk injection surface**. Sanitize passages + attrs + KG **before**
prompting (`neutralize_injection`, LE `sanitize.py:56`); `_safe()`-wrap writeback fields (LE `writeback.py:84`).

### 4.5 Verification gate 🔒
`CanonVerifier(canon_lookup, anachronism_markers=book_profile.anachronism_markers)`. Port `decide_auto_reject`
(`wiring.py:92-139`): injection / HIGH-contradiction / ≥2 anachronism / HIGH-regurgitation → persist but
`publish_blocked=true` + flags. `verify_degraded` ⇒ `passed=False`. Publish-block **server-enforced**.

### 4.6 Writeback endpoint + clobber guard (NEW, Go) 🟥 P0
`POST /internal/books/{book_id}/wiki/articles`. **`entity_id` is UNIQUE** (`migrate.go:562`) → blind insert
throws on re-run; blind `ON CONFLICT … UPDATE` clobbers human edits. Rules: (1) upsert-by-entity with
`SELECT … FOR UPDATE` (`wiki_handler.go:490`); (2) **human-edit guard** — AI overwrites ONLY untouched
`author_type='ai'` `draft`; if `published` or any owner/human revision → land as **`wiki_suggestion`**
(`migrate.go:599`); (3) retry-idempotent (no-op if `body_json` unchanged, `wiki_handler.go:458`); (4) stamp
`author_type='ai'` + provenance; (5) transactional per article + write `wiki_article_source_usage` rows (§5.1).

### 4.7 Trigger · job-state · resume 🟧 P1
202 handshake + **durable Redis-stream** trigger (clone `resume_consumer.py`, NOT `asyncio.create_task`).
Job SSOT = new `wiki_gen_jobs` table in knowledge-service (mirror `extraction_jobs`; reuse `state_machine.py`;
states incl. `paused`). **FE polls the job row** as truth; glossary `generation_status` is an advisory mirror
(fixes the failure-mirror: worker failure → job row carries it, glossary not stuck `pending`). **Skip-done
before spend** (`runner.py:200-205`); **Regenerate = `force=true`** bypasses skip-done, routes through §4.6
guard. Per-entity writeback retried; one bad entity ≠ abort batch.

### 4.8 Cost-cap pause/resume 🟥 P0
Knowledge `jobs/budget.py` (`can_start_job` preflight + `try_spend` + `record_spending`) + LE charge-before /
reconcile-after (`cost.py:75-132` + `runner.py:419-432`). Breach → `paused` (work preserved), resumable.

### 4.9 Model routing 🟧 P1 (✅ answers cost open-Q)
Optional `step_models = { prose_model_ref?, verify_model_ref? }`, nullable fall-through to `model_ref`
(`orchestrator.py:209`). Cheap verify / strong prose. Tiered routing = the cost lever. Reasoning =
`reasoning_effort` **pass-through** only; no wiki reasoning classifier for MVP.

### 4.10 Schema changes 🟡
**`wiki_articles`** add: `generation_status TEXT DEFAULT 'none'` (`none|pending|generated|failed`),
`generated_by TEXT`, `generation_provenance JSONB` (incl. **`build_inputs`** fingerprint, §5.1, +
`citations`, `verify_flags`, `publish_blocked`, `grounding`, `step_models`), `generated_at TIMESTAMPTZ`,
**`is_knowledge_stale BOOLEAN DEFAULT false`** (denormalized flag, §5.2).
**`wiki_revisions.author_type`** — allow `'ai'`; migrate deterministic-stub author `'owner'`→`'system'` so
"human-touched" is detectable.
**NEW `wiki_article_source_usage(article_id, source_type, source_id, source_version, PRIMARY KEY(article_id,
source_type,source_id))`** — reverse dependency index (§5.1), the `chapter_translation_glossary_usage` analogue.
**NEW `wiki_staleness(staleness_id, article_id, reason_code, source_ref JSONB, severity, detected_at,
status DEFAULT 'pending')`** — the deferred change ledger (§5.2).
**NEW `wiki_gen_jobs`** (knowledge-service) — job SSOT incl. `paused`.
Change FK `wiki_articles.entity_id` **`ON DELETE CASCADE` → `ON DELETE RESTRICT`** (§5.5).

### 4.11 Feedback learning loop 🟩 (MVP = emit)
Wiki already stores the gold translation had to build — `wiki_revisions` (AI-draft→human-edit pairs) +
accept/reject `wiki_suggestions`. Emit `wiki.corrected` (from `patchWikiArticle` when prior revision was
`author_type='ai'` + owner edits) + `wiki.suggestion_reviewed` via glossary's outbox → learning-service
`corrections` + `quality_scores` (`target_kind='wiki_article'`). **Follow-up:** consume gold as few-shot in
`prompt.py`.

### 4.12 Quality eval harness 🟩 (MVP = thin advisory)
`app/benchmark/wiki/` over a ~15-entity Fengshen golden: **citation-resolvability** + **verify-flag-rate**
(GROUP BY over `generation_provenance` — zero new code) deterministic → advisory CI band; **coverage**
(`recall_at_k`); **groundedness** (LLM-judge + discrimination probe) = follow-up.

### 4.13 Frontend (`features/wiki`) 🟡
Model picker (+ optional per-step) + deterministic/LLM toggle. Poll **job row** for batch progress.
Article view: citations + "jump to source", **"AI-generated · unverified"** badge + verify flags,
**Regenerate** (`force=true`). **NEW (phase-2): "outdated vs current knowledge" badge** (driven by
`is_knowledge_stale`) + a **"Knowledge updates" change-feed** (§5.3) — stale articles grouped by the knowledge
change that caused them (chapter re-publish / attr edit / merge / broken citation / recipe upgrade), each with
what-changed + severity (🔴 hard-broken-citation / 🟡 structural / 🔵 content), **batch-select → cost-estimate →
cost-capped regenerate**; human-edited articles route to suggestion not overwrite; the deferred banner makes
clear nothing regenerates until the user acts. AI-as-suggestion shows when the clobber-guard routes a regen to
review.

**Mockup:** all FE states (reader · generate dialog · job progress · suggestions · **change-feed**) are
prototyped in `docs/specs/2026-06-08-wiki-llm-building-mockup.html` (5 switchable screens, theme-faithful).

---

## 5. Change-Control: wiki as a deferred-sync materialized view 🟦

PO policy: **(1) not realtime CDC — capture, defer the work in a DB ledger; (2) regeneration costs tokens → the
user decides.** Three stages — *capture* (cheap, auto, **MVP**) → *defer* (ledger, no work, phase-2) → *decide*
(user-gated, phase-2) — plus entity-lifecycle propagation. Every staleness precedent in the repo
(`translation`, `stale-image-guard`, `enrichment`) independently lands on **flag-don't-auto-rebuild**.

### 5.1 CAPTURE — dependency fingerprint + reverse usage-index (🟥 MVP, mandatory)
**Why MVP even though reaction is phase-2:** you cannot reconstruct "what knowledge an article was built from"
after the fact — same logic as emitting feedback events in MVP. The generation worker, at writeback, records:

- **`wiki_article_source_usage`** rows — every input the article actually consumed: each `entity_id` (self +
  KG neighbors used), each cited `(chapter_id, block_index)`. The `chapter_translation_glossary_usage` analogue
  (`translation/app/migrate.py:299`).
- **`generation_provenance.build_inputs`** fingerprint (hash with ported learning `_stable_hash`):
  `{ schema_version, entity_id, entity_revision_num, entity_content_hash, attr_set_hash, kg_neighborhood_hash,
  cited_blocks:[{chapter_id, block_index, content_hash}], retrieval_params_hash, model_ref, prompt_version,
  pipeline_version }`. Sources of each token already exist: `entity_revisions.revision_num` (monotonic, clock-
  skew-immune), `chapter_blocks.content_hash` (book-service), the glossary `entity_snapshot`.

This is the *only* change-control work in MVP — it is data capture, no reaction logic. Cheap, additive.

### 5.2 DEFER — staleness ledger, NOT realtime CDC (🟦 phase-2)
Capture change into the **`wiki_staleness` ledger**; do **zero** LLM work. Two feeds, both lightweight:

- **Push — a lightweight `wiki-staleness` consumer group** on `loreweave:events:{glossary,chapter}` (clone
  `translation/app/events/glossary_consumer.py`: forward-only `id="$"` so first deploy doesn't replay ~200k
  events; idempotent; bounded-retry-ack; **no-false-negative fallback** — an article with no usage rows gets a
  coarse book-level flag). On an event it **joins `wiki_article_source_usage`** and, for each affected article,
  upserts a `wiki_staleness` row (`reason_code`, `source_ref`, `severity`) + flips `is_knowledge_stale=true`.
  **It never regenerates.** Signals subscribed:
  - `glossary.entity_updated` (covers attr/name/short_description **and** enrichment promote/retract) → article
    of that entity stale (reason `entity_attr_changed` / `name_changed` / `enrichment_changed`).
  - `glossary.entity_merged` → loser article → `merged` (redirect, §5.4); winner article stale.
  - `chapter.published/unpublished/deleted` → join cited `chapter_id` → `chapter_regrounded` (drifted) or
    `citation_broken` (hard — block no longer canon).
- **Pull — a periodic fingerprint sweep** (nightly / on-demand) recomputes `build_inputs` vs current knowledge
  for a slice and writes ledger rows for drift the events can't cover: pipeline-driven **KG changes emit nothing**
  (the catalog's GAP A — neighbor re-extraction); and **`prompt_version`/`pipeline_version` bumps** = same-input
  recipe drift (the stale-image-guard §6b lesson — version-hash can't catch behavioral drift, so make it an
  explicit token). The sweep is the authoritative tier-2; events are the responsive tier-1.

> Because it is **not realtime**, the live consumer is itself optional for a first cut — a pure periodic sweep is
> a valid simpler start; the consumer is the latency upgrade. Either way the ledger is the single deferred queue.

**Severity (from learning `split_snapshot`):** `kind` change = **structural** (frame wrong → strongly suggest
regen); `short_description`/attr tweak = **content** (soft, advisory); broken citation = **hard** (cite points
at non-canon). Severity drives how loudly the UI nudges, never auto-action.

### 5.3 DECIDE — user-gated update (🟦 phase-2; token cost is the reason)
Regeneration is **never automatic**. A **"Knowledge updates" surface** drains the ledger:
- Lists stale articles grouped by reason ("3 bài outdated — 妲己: chương 23 tái-publish · 姜子牙: sửa attr · …"),
  each with a "what changed" diff and the staleness severity.
- User **selects / batches** → **cost estimate** (N × ~tokens) → confirm → enqueues a regenerate job (the §4.7
  pipeline, `force=true`) → **cost-capped + pause/resume + skip-done** (§4.8/4.7). On completion the ledger rows
  resolve (`status='regenerated'`) and `is_knowledge_stale` clears.
- **Clobber-guard respected:** a stale article that is human-edited → regen lands as a **suggestion** diff, never
  an overwrite (§4.6).
- **Free floor may auto-refresh:** the deterministic `renderWikiBody` is free + deterministic, so cheap changes
  (e.g. rename) MAY re-render it synchronously; only **LLM** regeneration is user-gated. User can also "dismiss"
  a staleness row (accept-as-is) — it resolves without spend.

### 5.4 Entity-lifecycle propagation 🟦
Split: **structural integrity = immediate** in the write tx (free/cheap; about not losing data); **expensive
body regen = deferred** to the ledger (user-gated). Copy the proven enrichment pattern (repoint + union +
journal, in the same `mergeOne` tx).

- **MERGE** — *immediately*: union loser's `wiki_revisions` onto winner (re-number versions), journal the moved
  PKs + a snapshot of the deleted loser article (for un-merge), leave a **redirect** (read-path resolves a
  merged loser's article → winner, using `merged_into_entity_id`). *Deferred*: mark winner `is_knowledge_stale`
  (reason `merged`) → ledger; body regenerates from the merged context when the user decides. **Fixes the
  silent-abandon data-loss bug (§5.5).**
- **RENAME** — title/infobox auto-follow (read-time derivation, already correct — do **not** add a title
  column). Deterministic body re-renders free; LLM body → ledger row (`name_changed`).
- **DELETE (soft)** — article hibernates with its entity (already reversible). Fix the detail-serves-soft-deleted
  inconsistency (`loadWikiArticleDetail` lacks the `deleted_at` filter, `wiki_handler.go:1114`).
- **UN-MERGE** — journal-restore the loser's human revisions; mark **both** articles stale → bodies regenerate
  (deferred) the way the KG reconverges (it no-ops un-merge and re-derives). Human revisions are journal-restored
  (not derivable); the body is regenerated (derivable).

### 5.5 Two pre-existing data-loss bugs (🟥 fix before/with MVP — the body is now the product)
1. **Merge abandons the loser's article** (`merge_handler.go:305`: repoints only if winner has none; else the
   loser's article + revisions are silently orphaned on a soft-deleted row). Contradicts the merge spec's own
   AC4. Under the LLM design the body is the product (no Neo4j copy to re-derive) → this is real data loss.
   **Fix:** revision-union + redirect (§5.4).
2. **`ON DELETE CASCADE` on a product table** (`migrate.go:562`): deleting a *kind* (`kinds_crud.go:225`)
   hard-deletes its entities and **silently destroys** their `wiki_articles` + revisions + suggestions, no
   count, no warning. **Fix:** FK → `ON DELETE RESTRICT`; purge / kind-delete must explicitly archive + emit
   `wiki.deleted` (so the feedback loop captures the gold first) before deleting.

---

## 6. Failure modes

| Condition | Behaviour |
|---|---|
| `model_ref` absent | Deterministic `renderWikiBody` (floor). |
| Provider/LLM down | Job `failed` (job row); FE offers deterministic fallback. |
| Cost cap breached 🟥 | Job `paused`, work preserved; resumes skip-done. |
| Book not indexed | Semantic leg empty → grounding degrades to lexical+KG+attrs; hint. |
| Zero grounded claims 🟧 | **Skip** entity with actionable reason (no hollow article). |
| Verify auto-reject | Persist `draft` + `publish_blocked` (server-enforced) + flags; human review. |
| Re-run / regenerate 🟥 | Upsert-by-entity; clobber-guard → refresh untouched ai-draft, else `wiki_suggestion`. |
| Worker crash mid-batch 🟧 | Stream redelivery → resume from skip-done cursor. |
| **Knowledge changed** 🟦 | Captured to `wiki_staleness` ledger + `is_knowledge_stale` flag. **No regeneration** until the user decides. |
| **Staleness consumer down** 🟦 | Periodic fingerprint sweep backstops it; ledger is eventually-consistent, not realtime (by design). |
| **Entity merged/renamed/deleted** 🟦 | Structural integrity immediate (revision-union/redirect/restrict); body regen deferred to ledger. |

---

## 7. Testing

- **Unit:** prompt builder (BookProfile), TipTap parser, rule-gate, revise keep-if-improved, sanitize,
  clobber-guard branches, cost charge/reconcile, skip-done, **build_inputs fingerprint determinism**, **staleness
  join (event → affected articles)**, **merge revision-union + redirect**.
- **Cross-service live-smoke (REQUIRED — ≥4 services):** real generation on Fengshen through
  glossary→knowledge→provider-registry→book-service; assert grounded body + citations→real block_index + draft
  writeback + **re-run routes to suggestion not clobber** + **source_usage rows written**. First live
  `compose_cites` consumer → real-passage smoke. **Phase-2:** edit an attr → assert the article's ledger row
  appears + flag flips + **no LLM call fired** (deferral proven); merge two entities → assert loser revisions
  preserved on winner + redirect resolves.
- **Eval harness** (§4.12) advisory band.

---

## 8. Rollout & phasing

Opt-in by `model_ref` ⇒ zero regression. Ships in phases:

- **Phase 1 (MVP) — generation + capture.** Bounded multi-pass + all P0/P1 hardening + feedback-emit + thin
  eval + **§5.1 dependency capture (mandatory — cannot retrofit)** + **§5.5 bug fixes** (data-loss, do early).
  Output: the wiki can generate grounded articles and *records what each was built from*. No staleness reaction
  yet — but the data to react is being captured from day 1.
- **Phase 2 — change-control reaction.** §5.2 ledger + (sweep and/or consumer) · §5.3 user-gated "Knowledge
  updates" surface · §5.4 entity-lifecycle body-regen · §4.13 stale badge. All user-gated, cost-capped.
- **Follow-up.** Consume feedback gold as few-shot · judge-based eval · §5.2 precise KG-edge events (net-new
  `knowledge.kg_synced` emit) if the sweep proves too coarse.

---

## 9. Resolved-by-review
1. ✅ **Generation language** → `BookProfile.language`. 2. ✅ **Multi-pass vs single** → multi-pass IS MVP.
3. ✅ **Cost/batch** → `budget.py` cap + pause/resume + tiered routing; **regeneration user-gated (§5.3).**
4. ✅ **Index prerequisite** → degrade + hint. 5. ✅ **Model selection** → picker + per-step override.
6. ✅ **Realtime vs deferred staleness** → **deferred ledger, not CDC** (PO). 7. ✅ **Auto vs manual update** →
**user-decides, token-cost-gated** (PO).

## 10. Explicitly NOT copied (avoid over-engineering)
TransAgents many-role company (3 passes ceiling) · multi-round loop / self-consistency (1 revise) · rolling-
summary stitch · sub-article checkpoints · auto-reasoning classifier (pass-through only) · enrichment eval-gate
/strategy-factory · KG-write half of enrichment writeback (wiki read-only KG) · redundant ownership re-check ·
**realtime CDC / auto-regeneration** (deferred + user-gated by design). Wiki correctly differs: SDK
`GroundingCite` (clean first consumer, advances D-063) · own TipTap output contract · title read-time-derived
(no title column).

## 11. Deferred / watch
- `compose_cites` first live use → real-passage smoke (VERIFY gate).
- ✅ **BookProfile access RESOLVED (option A, post-scoping)** — knowledge reads it via a LE
  internal HTTP endpoint; NOT moved to book-service (B would push LLM-config + LLM detection into a
  Go/CRUD service = wrong boundary; profile is AI-domain config, not book identity). Owner-vs-a-more-
  neutral-AI-home is a separate, non-urgent refactor — the API read keeps wiki decoupled from it.
- `D-GROUNDING-COMPOSE-MIGRATE` (063): wiki adopting `GroundingCite` informs the enrichment migration.
- Precise KG-edge invalidation: only if the §5.2 chapter-proxy sweep proves too coarse → add
  `knowledge.kg_synced` emit (net-new plumbing, follow-up).
- Recycle-bin GC (does not exist yet): when built, must NOT rely on CASCADE — explicit archive + `wiki.deleted`.
