# Translation Pipeline V3 — Multi-Agent QA Design

> **Status:** Design proposal (DESIGN phase) · awaiting human REVIEW
> **Branch:** `feat/translation-pipeline-v3`
> **Author:** Session 2026-06-06
> **Prior-art research:** [market & prior-art note](./2026-06-06-translation-llm-market-research.md) (validates the multi-agent direction; sharpens §10)
> **Architecture review:** [arch review & benchmark plan](./2026-06-06-translation-v3-architecture-review-benchmark.md) (current-pipeline limits + the pre-benchmark readiness gate)
> **Size:** XL (10+ files, additive schema, ≥2 services) — `/amaw` recommended for schema + multi-service milestones
> **Supersedes nothing** — runs PARALLEL to V2 behind a feature flag (`pipeline_version`).

---

## 0. Problem & Goals

V2 (the current block pipeline, see [TRANSLATION_PIPELINE_V2.md](../03_planning/data_pipelines/TRANSLATION_PIPELINE_V2.md)) already does CJK-aware tokens, glossary injection, structural validation, retry, and auto-correct. But it cannot detect **semantic** failure:

- A paragraph of 10 sentences translated as 7 (dropped content) passes V2 — block count is right, length ratio is within 0.3×–4×.
- A glossary name rendered with the **wrong** target spelling (`Tirana` vs `Tirami`) passes V2 — `auto_correct_glossary` only replaces **untranslated source** terms, not wrong target ones.
- Cross-chapter context is dead code (loaded, never threaded — see §1.3).

**Goals (confirmed with PO 2026-06-06):**

| # | Goal | V3 mechanism |
|---|------|--------------|
| G1 | Smarter multi-agent organization | Translator → Verifier → Corrector loop, model-per-role |
| G2 | Detect dropped/missed content | Verifier: sentence-alignment + number/entity preservation + LLM semantic check |
| G3 | Detect & fix wrong names | Verifier: glossary target-name presence + name-drift check → targeted re-translate |
| G4 | Context-aware translation | Wire cross-chapter memo (fix dead code) + semantic rolling summary |
| G5 | Smarter chunk splitting | Semantic-aware batching (keep dialogue/scene together) |
| TD | Clear tech debt first | Fix memo wiring, converge sync/worker paths, quality persistence |

**Architecture decision (PO):** parallel **V3** pipeline behind a feature flag, A/B against V2, safe rollback. **QA depth:** full multi-agent loop (translate → verify → correct, iterate to a quality threshold, model-per-role).

---

## 1. Current state recap (what V3 builds on / fixes)

### 1.1 Reusable, keep as-is
- `chunk_splitter.estimate_tokens` — CJK-aware token math ([chunk_splitter.py:53](../../services/translation-service/app/workers/chunk_splitter.py#L53))
- `block_classifier` — Tiptap ↔ markdown round-trip ([block_classifier.py](../../services/translation-service/app/workers/block_classifier.py))
- `block_batcher.build_batch_plan` — token-budget batching, expansion ratios, 40-block cap (V3 extends this for semantics)
- `glossary_client` — fetch + scope + `correction_map` ([glossary_client.py](../../services/translation-service/app/workers/glossary_client.py))
- `worker.py` retry/DLQ + stale recovery; `chapter_worker` job-completion bookkeeping

### 1.2 Reused as the **rule layer** of the Verifier
- `validate_translation_output` (block count / missing / extra / length-ratio) → becomes Verifier rule-check tier 1 ([session_translator.py:722](../../services/translation-service/app/workers/session_translator.py#L722))
- `auto_correct_glossary` (source-term residue replace) → Corrector deterministic pre-pass

### 1.3 Bugs / debt V3 must fix
| ID | Issue | Location |
|----|-------|----------|
| TD1 | `prev_memo` loaded then discarded; `_save_chapter_memo` reads `translated_body_text` which is `None` for block pipeline → memo always empty | [chapter_worker.py:119](../../services/translation-service/app/workers/chapter_worker.py#L119), [:243](../../services/translation-service/app/workers/chapter_worker.py#L243) |
| TD2 | Sync `/translate-text` block mode is a stale fork: hardcoded 8192, no glossary/validation/retry/auto-correct | [translate.py:75](../../services/translation-service/app/routers/translate.py#L75) |
| TD3 | Block pipeline writes **no** `chapter_translation_chunks` rows → V6 quality columns unused on the main path | block path in [session_translator.py:804](../../services/translation-service/app/workers/session_translator.py#L804) |
| TD4 | Length-ratio (0.3×–4×) is the only "completeness" signal — too crude for G2 | [session_translator.py:754](../../services/translation-service/app/workers/session_translator.py#L754) |

---

## 2. V3 Architecture

### 2.1 Selection (feature flag)
- New column `pipeline_version TEXT DEFAULT 'v2'` on `user_translation_preferences`, `book_translation_settings`, **snapshotted** onto `translation_jobs` at job creation (same pattern as `model_ref`).
- `coordinator` copies `pipeline_version` into each chapter message; `chapter_worker._process_chapter` branches:
  - `'v2'` → existing `translate_chapter_blocks` / `translate_chapter` (unchanged)
  - `'v3'` → `v3.orchestrator.translate_chapter_v3(...)`
- Default `'v2'`. Opt-in per book (or per job via API). Rollback = flip the flag; no data migration.

### 2.2 Module layout (`services/translation-service/app/workers/v3/`)
```
v3/
  __init__.py
  orchestrator.py     # per-batch translate→verify→correct loop; assembles chapter; persistence
  translator.py       # Agent A — draft translation (translator model)
  verifier.py         # Agent B — rule tier + LLM tier → IssueReport (verifier model)
  corrector.py        # Agent C — targeted re-translation of flagged blocks (translator model)
  semantic_chunker.py # G5 — dialogue/scene-aware batch plan (wraps block_batcher)
  context.py          # G4 — cross-chapter memo build/load + within-chapter rolling summary
  quality.py          # IssueReport / BlockVerdict dataclasses, scoring, thresholds
  models.py           # shared dataclasses + config (rounds, threshold, model refs)
```
Reuses `glossary_client`, `block_classifier`, `block_batcher`, `chunk_splitter` directly — no fork.

### 2.3 The loop (per chapter)
```
ctx = context.load(book_id, chapter_index, target_lang)      # G4: prev memo + glossary
plan = semantic_chunker.plan(blocks, ctx)                     # G5
for batch in plan.batches:
    draft = translator.translate(batch, glossary, ctx.rolling)            # Agent A
    for round in range(max_qa_rounds):                                    # G1 full loop
        report = verifier.verify(batch.source, draft, glossary, ctx)      # Agent B (rule+LLM)
        if report.passes(threshold): break
        flagged = report.blocks_needing_fix()
        draft = corrector.correct(batch, draft, flagged, glossary, ctx)   # Agent C (targeted)
    persist(batch, draft, report)        # chapter_translation_chunks + translation_quality_issues
    ctx.rolling = context.update(ctx.rolling, draft)                      # G4 semantic summary
assemble Tiptap JSON → persist chapter_translations (+ quality rollup)
context.save_memo(book_id, chapter_index, target_lang, ctx)              # G4
```

### 2.4 Agent contracts

**Agent A — Translator** (`translator.py`)
- Model: job's translator `model_source/model_ref`.
- Input: batch `[BLOCK N]` source + scoped glossary + `ctx.rolling` (within-chapter) + `ctx.memo` (cross-chapter).
- Output: `[BLOCK N]` translated text. (Essentially today's batch translation, extracted + context-enriched.)

**Agent B — Verifier** (`verifier.py`) — the heart of G2+G3.
- **Tier 1 (rule, deterministic, free):**
  - *Wrong/missing name (G3):* for each glossary `correction_map` source term present in the source block, assert its target name appears in the draft. Absent → `wrong_name` (high).
  - *Source-script leak:* target language is non-CJK but draft contains CJK chars → `untranslated` (high). (MVTN's CJK-leak check, never ported.)
  - *Number preservation:* digit-run multiset of source vs draft; mismatch → `number_mismatch` (med).
  - *Sentence-count alignment (G2):* count sentence-enders (reuse `_SENTENCE_ENDS`); `target < 0.6 × source` → `omission` (med).
  - *Structural:* existing `validate_translation_output` (block count / length ratio).
- **Tier 2 (LLM, semantic):** verifier model receives source + draft + glossary, prompted adversarially ("list every omitted clause, mistranslated name, or invented sentence; default to reporting when unsure"), returns strict JSON `IssueReport`. Tier 2 runs only on blocks Tier 1 passed or flagged ambiguous (cost control), or always when `qa_depth=thorough`.
- Output: `IssueReport = [BlockVerdict{ block_index, issues[Issue], score }]`.
  `Issue = { type: omission|wrong_name|added|number_mismatch|format|untranslated, severity, detail, source_span?, expected? }`.

**Agent C — Corrector** (`corrector.py`)
- Model: translator model (quality-sensitive).
- Input: original source + current draft + the `Issue` list for **flagged blocks only** + glossary.
- Prompt: "Your previous translation of [BLOCK k] had these problems: …; produce a corrected translation of ONLY these blocks." → re-translate flagged blocks, splice back.
- Deterministic pre-pass: run `auto_correct_glossary` before invoking the model (cheap fixes first).

### 2.5 Loop termination & quality outcome
- `max_qa_rounds` default **2** (configurable per job). Stop early when no `high`-severity issues remain.
- After exhausting rounds with unresolved high issues: keep the **highest-scoring** draft, persist the residual issues, set block `quality='needs_review'`.
- Chapter status stays `completed` / `partial` / `failed` (no new enum values — avoids breaking the coverage matrix). A **separate** rollup (`unresolved_high_count`, `quality_score`) drives a future "needs review" UI badge.

---

## 3. Semantic chunking (G5)

Extend (not replace) `build_batch_plan` with a pre-pass in `semantic_chunker.py`:
1. Tag each translatable block with a **group id**:
   - *dialogue run* — consecutive blocks whose text contains dialogue markers (`「」` `『』` `“”` `"` leading em-dash);
   - *scene boundary* — `heading`, `horizontalRule`, or a blank/structural block starts a new group;
   - otherwise paragraph cluster.
2. Greedy-fill batches as today, but **prefer not to split a group** across a batch boundary unless the group alone exceeds the token budget.
3. Keep hard caps: token budget + `MAX_BLOCKS_PER_BATCH=40`.

Net effect: a dialogue exchange or a scene tends to land in one LLM call, so within-batch context stays coherent. Falls back to today's behavior when groups are large.

---

## 4. Context (G4)

`context.py`:
- **Load:** previous-chapter memo (`translation_chapter_memos`) → `ctx.memo` (terms_used, story_summary, style_notes), actually **passed into** Translator + Verifier + Corrector (fixes TD1).
- **Within-chapter rolling summary:** replace the naive "last 5 sentences" slice with compaction via the configured compact model when the running summary exceeds budget (reuse `_compact_history` machinery).
- **Save memo (works for block pipeline):**
  - `terms_used` = glossary terms actually applied/corrected this chapter (from Verifier/Corrector telemetry) — gives the next chapter a concrete name map.
  - `story_summary` = compact-model summary of the chapter's **translated block text** (joined), not the always-`None` `translated_body_text`.
  - `style_notes` = optional tone notes from the Verifier.

---

## 5. Schema changes (additive, idempotent — appended to `migrate.py` DDL)

```sql
-- V8: Pipeline V3 selection + per-role models + QA config
ALTER TABLE user_translation_preferences
  ADD COLUMN IF NOT EXISTS pipeline_version      TEXT NOT NULL DEFAULT 'v2',
  ADD COLUMN IF NOT EXISTS verifier_model_source TEXT,
  ADD COLUMN IF NOT EXISTS verifier_model_ref    UUID,
  ADD COLUMN IF NOT EXISTS max_qa_rounds         INT  NOT NULL DEFAULT 2,
  ADD COLUMN IF NOT EXISTS qa_depth              TEXT NOT NULL DEFAULT 'standard'; -- rule_only|standard|thorough
-- same three columns on book_translation_settings and translation_jobs (snapshot)

-- V8: per-block QA issues (drives re-translate + future "needs review" UI)
CREATE TABLE IF NOT EXISTS translation_quality_issues (
  id                     UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_translation_id UUID NOT NULL REFERENCES chapter_translations(id) ON DELETE CASCADE,
  block_index            INT  NOT NULL,
  round                  INT  NOT NULL DEFAULT 0,
  issue_type             TEXT NOT NULL,   -- omission|wrong_name|added|number_mismatch|format|untranslated
  severity               TEXT NOT NULL,   -- high|med|low
  detail                 TEXT,
  expected               TEXT,
  resolved               BOOLEAN NOT NULL DEFAULT false,
  detected_by            TEXT NOT NULL DEFAULT 'rule', -- rule|llm
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tqi_ct ON translation_quality_issues(chapter_translation_id);

-- V8: per-chapter quality rollup (cheap badge source; no status-enum churn)
ALTER TABLE chapter_translations
  ADD COLUMN IF NOT EXISTS quality_score        INT,
  ADD COLUMN IF NOT EXISTS unresolved_high_count INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS qa_rounds_used        INT NOT NULL DEFAULT 0;
```
Block pipeline (V2 + V3) should also start writing `chapter_translation_chunks` rows (TD3) so the existing V6 quality columns are populated.

**No-hardcoded-model rule:** verifier model resolved from registry/user config, never literal. Nullable verifier model ⇒ fall back to translator model.

---

## 6. Milestones (each = one reviewable, A/B-testable PR)

| M | Title | Deliverable | Services touched |
|---|-------|-------------|------------------|
| **M0** | Tech debt + scaffold + flag | Fix TD1 (memo wiring, both pipelines); add `pipeline_version` flag + V8 schema; V3 package skeleton that calls V2 logic (behavioral parity, flag off) | translation only |
| **M1** | Verifier rule-tier + persistence | Deterministic checks (name/number/sentence/leak) + `translation_quality_issues` + targeted re-translate on rule failures + chunk rows for block pipeline (TD3) | translation (+ glossary read) |
| **M2** | LLM Verifier + Corrector loop | Agent B Tier-2 + Agent C + full translate→verify→correct loop with rounds/threshold + per-role model config | translation, provider-registry |
| **M3** | Semantic chunker | Dialogue/scene-aware batching (G5) | translation |
| **M4** | Context done right | Cross-chapter memo populate/use + semantic rolling summary (G4) | translation |
| **M5** | Surfacing + convergence | "Needs review" badge in FE coverage/reader; converge sync `/translate-text` onto shared builder (TD2); A/B metrics; docs | translation, gateway, frontend |

M0–M1 alone deliver most of G2/G3 value (deterministic detection + re-translate) at ~1× cost. M2 adds the LLM loop.

---

## 7. Testing & verification

- **Unit:** Verifier rule tier is fully deterministic → golden table of known-bad drafts (dropped sentence, wrong name, CJK leak, number drift) asserting exact `Issue` output. Semantic chunker grouping tests. Context memo build/load.
- **Contract:** `IssueReport` JSON schema (LLM tier) validated; malformed LLM output degrades to rule-tier verdict (never crashes the chapter).
- **Live smoke (CLAUDE.md ≥2-service rule):** real zh→vi chapter through V3 on a stack-up; confirm verifier flags a seeded omission and the corrector fixes it. Evidence token `live smoke: <one-liner>` or explicit deferral.
- **A/B:** same chapter set through V2 vs V3; compare `unresolved_high_count`, glossary-correction count, token cost, wall-clock.

---

## 8. Risks & open decisions

| Risk | Mitigation |
|------|------------|
| Cost/latency blow-up from the loop | Tier-1 rules gate Tier-2 LLM; `max_qa_rounds=2`; verifier can be a cheaper model; flag-gated opt-in |
| Verifier hallucinates issues → needless re-translate churn | Adversarial-but-calibrated prompt; require `severity:high` to trigger a redo; cap rounds; A/B watch |
| LLM verifier JSON drift | Strict parse + fall back to rule-tier verdict; never fail the chapter on verifier parse error |
| Additive migration on shared DB | All `IF NOT EXISTS` / nullable; rollback = flip flag + stop writing; recommend `/amaw` for M0/M2 |

**Open decisions for PO (defaults proposed; confirm or adjust in REVIEW):**
1. **Verifier model** — (a) dedicated cheaper model (e.g. a small local) vs (b) reuse translator model. *Default: nullable config → reuse translator if unset.*
2. **`max_qa_rounds` default** — *proposed 2.*
3. **On unresolved-after-max-rounds** — keep best draft + `needs_review` badge (proposed) vs mark block failed. *Default: keep + badge.*
4. **Re-translate granularity** — per-block (proposed, cheaper/surgical) vs per-batch. *Default: per-block.*

---

## 9. Out of scope (this feature)
- Glossary **extraction** pipeline (separate concern — discovers new entities; see [GLOSSARY_EXTRACTION_PIPELINE.md](../03_planning/data_pipelines/GLOSSARY_EXTRACTION_PIPELINE.md)). V3 only *reads* glossary.
- Back-translation round-trip scoring (possible M2+ enhancement; not required).
- Media `alt`-text translation (V2 Bug 5 — track separately).

---

## 10. Research-driven refinements

Folded in from the [market & prior-art research](./2026-06-06-translation-llm-market-research.md). These sharpen the milestones above without changing their structure:

- **Verifier = MQM-style error detector**, not a metric gate (GEMBA-MQM; TransAgents' low-BLEU-but-preferred paradox). `Issue.type` aligns to MQM Accuracy (omission/addition/mistranslation/untranslated) + Terminology (wrong/inconsistent term) + Locale/format; `severity` major/minor → weighted score. **No BLEU/COMET gate.** → M1/M2
- **Adopt GalTransl's proven rule checks** into the Verifier rule-tier: residual source-script · punctuation/symbol count · **repetition > N (looping detector)** · length ratio · line/block count · **glossary-term-used compliance** · non-target-language chars. → M1
- **Fix glossary correction to word-boundary/conditional** (GalTransl conditional dict) — current `auto_correct_glossary` blind `str.replace` risks substring over-replacement. → M1
- **Cross-chapter memo = multi-level memory** (DelTA: Proper-Noun Records · Bilingual Summary · Long/Short-term) — our `terms_used`/`story_summary`/`style_notes` columns already match; populate + carry a running proper-noun record. → M4
- **Add a lightweight per-book "preparation" pass** (TransAgents) — derive style guidelines + plot-so-far, richer than a sentence slice. → M4
- **Block pipeline persists per-batch rows** to enable mid-chapter **resume** (GalTransl real-time cache) and populate the unused V6 quality columns. → M1 (with TD3)
- **Finer-grained redo on omission** — Corrector re-translates a flagged block at sentence granularity when omission persists (DelTA). → M2/M3
- **Model tiers** — cheap local 7B (Sakura-class) for bulk translate, stronger model for verify; per-role config already in §5. → M2

---

## 11. Exploiting glossary-service + knowledge-service (the original pipeline pre-dates both)

The V1/V2 pipeline pulls **one** glossary endpoint — `GET /internal/books/{book_id}/translation-glossary` → `[{zh:[…], vi:[…], kind}]`. That is a fraction of what the two-layer stack now offers. Reference integrations: **composition-service** (`app/packer/` lens model) and **lore-enrichment-service** (`app/clients/port.py` read-ports) — both proven consumers we copy patterns from.

### 11.1 What's available vs what we use today

**glossary-service** = authored SSOT (trust it). Real signals we currently ignore:

| Source (file) | Signal | Use in V3 | Goal |
|---|---|---|---|
| `attribute_translations.confidence` (`draft`\|`confirmed`\|`published`) + `translator`, `updated_at` | Per-name **trust level** | **Hard-lock** confirmed/published names in Verifier; draft = hint only | G3 |
| `entity_attribute_values` aliases + `glossary_entities` variants | All **variant source names** | Catch a name written differently than the primary | G3 |
| `chapter_entity_links.relevance` (`major`\|`appears`\|`mentioned`) | Authored **per-chapter priority** | Tier-1 scoping by relevance, not just raw occurrence×length | G4/G5 |
| `glossary_entities.is_pinned_for_context` | User "always include" | Tier-0 pinned | G4 |
| `short_description` + `kind` | **Character notes** (role/gender cues) | Pronoun/honorific guidance in prompt (the GalTransl GPT-dict lesson) | G3/G4 |
| `evidences.original_text` | Source **usage examples** | Few-shot for ambiguous terms | G2/G3 |
| `POST /internal/books/{book_id}/select-for-context` (tiered pinned→exact→FTS→recent) | Smarter **selection** than our raw scorer | Replace `build_glossary_context` scoring | G4 |

**knowledge-service** = derived semantic/graph layer, anchored to glossary via `glossary_entity_id` (trust-weight by confidence). This is **entirely unused** by translation today:

| Endpoint / MCP tool (file) | Returns | Use in V3 | Goal |
|---|---|---|---|
| `memory_recall_entity` (`mcp/server.py`) | entity + **1-hop relations** (parent_of, leader_of, married_to…) | **Pronoun/honorific disambiguation** — who outranks/relates to whom → 你/您, anh/em/ngài. The killer feature for context-correct names | **G4** |
| `memory_timeline` (`mcp/server.py`) | events up to a reading position (participants, dates) | Cross-chapter context richer than a 5-sentence slice; reading-position-aware memo | **G4** |
| `memory_search` / `GET /v1/knowledge/drawers/search` | semantic passage recall (chapter/chat/glossary) | How a term/scene was rendered before → Verifier consistency check; ambiguous-term lookup | G2/G3 |
| `POST /internal/knowledge/wiki-neighborhood` | 1-hop KG neighborhood for an entity | Entity context bundle for the Translator | G4 |
| `GET /v1/knowledge/entities/{id}` | entity detail + relations + `confidence`/`source_types` | Trust-weighted name authority | G3 |

> **Integration note — namespace bridge:** translation works in **`book_id`** space; knowledge is scoped by **`project_id`** + `X-User-ID`/`X-Project-ID`. Resolve via `GET /v1/knowledge/projects?book_id=…` (composition's `knowledge_client.py:63`) once per job. If a book has no knowledge project → treat as cold-start (§11.3.C).

### 11.2 Trust model (one ladder for both layers)

Build the name map + context from **highest-trust-first**, mirroring composition's tiered selector + `valid_until IS NULL` filter:

```
TRUST 1 (lock):   glossary confirmed/published translation  ·  knowledge confidence=1.0 / source_types∋'glossary'
TRUST 2 (use):    glossary draft translation                ·  knowledge confidence≥0.8, valid_until IS NULL, not pending_validation
TRUST 3 (hint):   knowledge pending_validation / confidence<0.8 / pattern-extracted   → inject as "candidate", never auto-correct against
EXCLUDE:          alive=false · deleted_at/archived_at set · valid_until set (superseded) · status≠active
```

The Verifier's glossary-compliance check (G3) fires only against **TRUST 1**; TRUST 2/3 inform the Translator but don't trigger forced re-translation.

### 11.3 The three data states

**A. Data EXISTS (mature book) — exploit fully.**
- Glossary context via `select-for-context` (tiered) → confirmed/published names locked.
- Per chapter, enrich with knowledge: `memory_recall_entity` for each linked entity (relations → pronoun/honorific), `memory_timeline` before this chapter (context), `memory_search` for prior renderings.
- Verifier wrong-name check is **authoritative** (TRUST 1 map). Cross-chapter memo (G4) = knowledge timeline + `terms_used`, not a sentence slice.

**B. Data OUTDATED / STALE — detect and degrade, don't trust blindly.** Staleness sources + handling:
| Stale signal | Detection | Action |
|---|---|---|
| Unreviewed names | `confidence='draft'` | Use as hint (TRUST 2), don't lock; surface for review |
| Lagging graph | `project.extraction_status≠'ready'` OR `last_extracted_at` < latest chapter | Degrade to **glossary-only** for recent chapters; don't trust relations/timeline there |
| Superseded facts | `valid_until IS NOT NULL` / `pending_validation` | Filter out (composition's rule) |
| Entity edited after translation | `entity.updated_at` > `translation.updated_at` | Treat target name as stale → Verifier flags; prefer newer authored decision |
| Retired entity | `alive=false` / `archived_at` / `deleted_at` | Exclude |
| Memo vs glossary conflict | running `terms_used` ≠ glossary confirmed | Glossary confirmed wins ties (newer `updated_at` breaks it); Verifier surfaces the inconsistency |
- **Never block on stale** — degrade quality, always produce output (composition F1 / enrichment Q6).
- **Self-healing:** when translation hits a name absent from glossary, or a glossary name lacking a target translation, **write it back** (draft) via `POST /internal/books/{book_id}/extract-entities` — idempotent, quarantined as draft, seeds the next chapter (enrichment write-back pattern, `writeback.py`).

**C. NO data (cold start / translate from scratch) — bootstrap as we go.**
- Glossary/knowledge return `[]` / `{found:false}` (no 404). Pipeline **must still translate** (unlike enrichment, which refuses without grounding).
- Maintain an **in-run proper-noun record** (DelTA-style) in the cross-chapter memo so the SAME run stays self-consistent even with zero glossary.
- At chapter end, **harvest chosen names** (source→target) → write back as draft glossary entities → chapter N+1 now has data.
- Offer two modes (PO choice): **single-pass** (translate + in-run memory, cheap) or **two-pass** (pass 1 translate+harvest → seed glossary → pass 2 re-translate with glossary, higher consistency — the V2 doc's "run extraction first, then re-translate" edge case made automatic).
- Verifier in cold-start: rule-tier still works (script-leak, numbers, repetition); glossary-compliance falls back to the in-run harvested map.

### 11.4 Patterns to reuse + new ports

- **`KnowledgeReadPort` / `GlossaryReadPort` (3 impls each)** like enrichment `port.py`: `Http` (degrade to typed empties), `Null` (feature-flag off / local dev), `Cached` (TTL per (book_id/project_id)). Fetch **once per chapter**, inject into every batch (V2's stability rule).
- **Lens-packer token budget with protected segments** (composition `budget.py`): glossary names + locked terms are *protected*; knowledge breadth (relations/passages) dropped first under budget. Never silent overflow — carry an `over_budget` flag.
- **Cache the glossary anchor id, not the knowledge id** (composition DI3) — rename-safe.
- **Injection-defense** on injected glossary/knowledge text before it enters the Translator/Verifier prompt (enrichment crosses this boundary; we must too).
- **Idempotent write-back** (deterministic ids) if translation seeds glossary.

**Net:** this folds into the milestones — M1 swaps the glossary scorer for `select-for-context` + the trust ladder + write-back of missing names; **M4 adds the knowledge layer** (relations for pronouns, timeline for memo) and the cold-start bootstrap modes. No change to the milestone count.

---

## 12. Plan-of-record (finalized 2026-06-06 — supersedes §6 milestone list)

After the architecture-validation review, the following decisions and scope are locked.

### 12.1 Resolved decision — parallel vs. sequential cross-chapter context
**Problem:** the coordinator fans out all chapters in parallel (competing-consumer workers), but the cross-chapter memo (§4) reads "chapter N-1's memo". On a fresh full-book job, chapter N-1 is usually not done yet → memo absent → G4 silently no-ops, and relying on it would force serialization.
**Decision (approved):**
- **Glossary + in-run `terms_used` are the parallel-safe consistency backbone.** Name/term consistency comes from the per-book glossary (stable, fetched once per chapter, identical across workers) + the harvested proper-noun record — NOT the sequential memo. Full parallelism preserved.
- **Cross-chapter memo is opportunistic enrichment** — used when N-1's memo already exists (re-translation, or naturally-ordered processing); skipped otherwise. Never a correctness dependency, never forces ordering.
- **Optional sequential "context-refinement" mode** (opt-in, max-quality / re-translation): process chapters in order so each gets the prior memo. Trades throughput for coherence. Default = parallel + glossary-backbone.
→ G4's *reliable* lever is glossary/knowledge ground-truth, not the memo. §4 is reframed accordingly.

### 12.2 Confirmed validation refinements
1. Quality **guarantees come from the rule-tier + ground-truth data**, not the LLM verifier (LLM judges are miscalibrated for literary text). LLM-verifier = enhancement, conservatively gated.
2. **LLM-only flags are low-severity (suggest)**; destructive re-translation requires deterministic corroboration (e.g., the sentence-count rule confirms an omission). Prevents regression.
3. **Chapter-level consistency pass** (deterministic): after all batches, assert each source name maps to exactly one target across the chapter. → M1.
4. **Feed knowledge relations to the Verifier too** (not just the Translator).
5. Defaults: **qa_depth = standard (1 verify pass)**, full loop opt-in; **verifier model defaults to a local/cheap tier** (Sakura-class) to keep the loop economical.

### 12.3 New scope folded in
| Item | Why (quality) | Where |
|---|---|---|
| **Romanization/transliteration policy** (zh→vi Sino-Vietnamese vs pinyin) | Consistent rendering of *un-glossaried* names — major zh→vi lever | **M1** |
| **Chapter-level consistency pass** | Cross-batch name drift = most visible error | **M1** |
| **Permanent regression gold-set** (seeded-error corpus) | CI gate vs quality regressions | **M1** |
| **Human-correction → glossary(confirm) → targeted re-translate + propagate** | Highest leverage: 1 fix → all occurrences | **M6 (new)** |
| **Translation staleness/invalidation** (glossary change ⇒ flag old translations stale) | Living-book correctness | **M5** |
| **Per-block provenance + publish quality-gate** (hold high-`unresolved_high` chapters) | Trust + safe publish | **M5** |
| User-authored **style guide** (formality/honorifics/name rules) | Preparation-stage quality (TransAgents) | Deferred — Track 2 |
| **Pause → edit glossary → resume** | Mid-job correction | Deferred (on M1 resume) |
| Streaming block delivery | UX, not quality | Deferred — Track 2 |

### 12.4 Milestone plan-of-record
| M | Title | Core |
|---|---|---|
| **M0** | Readiness gate + scaffold | instrumentation (metrics) · block chunk-rows + resume · memo-wiring fix (TD1) · `translation_quality_issues` + rollup schema · `pipeline_version` flag + V3 package parity · txn fix (W7) |
| **M1** | Deterministic quality + data upgrade | Verifier rule-tier (names/numbers/leak/repetition/sentence) · romanization policy · chapter consistency pass · glossary `select-for-context` + trust ladder + write-back missing names · gold-set |
| **M2** | LLM verify + corrector loop | Agent B Tier-2 + Agent C · full loop (rounds/threshold) · per-role models (local verifier default) · conservative gating |
| **M3** | Semantic chunker | dialogue/scene-aware batching |
| **M4** | Knowledge layer + context | relations→pronouns (Translator+Verifier) · timeline→memo · cold-start bootstrap (1-pass/2-pass) · parallel-safe glossary backbone (§12.1) |
| **M5** | Living-book + surfacing | staleness/invalidation · provenance + publish quality-gate · "needs review" UI · sync-path convergence (TD2) |
| **M6** | Human-in-the-loop flywheel | user correction → glossary confirm → targeted re-translate + propagate |

Deferred (Track 2): user style guide · pause/resume-with-edit · streaming delivery · media alt-text · back-translation scoring.
```
