# Plan — Wiki LLM-Generation, Phase-1 MVP (detailed, contract-first)

- **Date:** 2026-06-08 · **Branch:** `wiki/llm-gen` (off `main` @ `2ace6272`)
- **Spec:** [`2026-06-08-wiki-llm-building.md`](../specs/2026-06-08-wiki-llm-building.md) v3 · **Size:** XL (sliced)
- **Purpose:** front-load the **cross-milestone contracts** (IR, Markdown protocol, writeback payload,
  schema, fingerprint) so interface mismatches surface on paper, not in code. Per-milestone build steps
  stay just-in-time (each M = its own `/loom`). §I = contracts · §II = milestones · §III = **risks surfaced** · §IV = roadmap.

---

## I. Cross-milestone CONTRACTS (decide these once, here)

### C1 — Wiki Article IR (the canonical model; M0 defines, M3/M4/M5 depend)
Python, render-target-agnostic. A flat ordered block list + a sources table we own.
```
WikiArticleIR = {
  schema_version: int,
  entity_id, display_name, kind, language,        # language from BookProfile
  blocks:  [ Block ],                              # ordered
  sources: [ Source ],                             # the cite-label table (WE give these labels to the LLM)
}
Block  = { type: 'lead'|'heading'|'paragraph'|'list'|'quote'|'enriched',
           level?: int,            # heading
           ordered?: bool,         # list
           items?: [ [Span] ],     # list → array of lines, each a Span[]
           spans?: [ Span ],       # text blocks
           source_chapter_max: int|null }          # spoiler horizon per block (§5.1)
Span   = { text: str, cites: [str], source_type: 'glossary'|'enriched'|null, grounded: bool }
Source = { cite_id: str,           # 'P1'.. (we assign), echoed by the LLM
           kind: 'passage'|'glossary'|'kg',
           chapter_id?, block_index?, score?,       # passage → jump-to-source anchor
           snippet?: str }                          # ~160 chars → self-contained citation hover-preview (C3)
```
- **grounded=false spans are dropped/flagged at parse** (structural cite-enforcement, §4.3). Zero grounded → skip entity.
- `source_chapter_max` per block = max(cited passages' chapter sort_order) → enables section-level spoiler later; whole-article horizon = max over blocks.

### C2 — Markdown LLM-output contract + cite-label protocol (M3)
The LLM is the ONLY thing that emits free text; it emits **constrained Markdown**, never JSON/TipTap.
- We pass retrieved passages **pre-labelled** `[P1]..[Pk]` (+ a few glossary/KG facts as `[G1]`, `[K1]`).
- LLM rules (prompt): `## Section` headings · prose paragraphs · `- ` bullets · `> ` blockquote ONLY for
  enriched/dị-bản material · place `[Pn]` **inline right after the clause it supports** · every non-trivial
  claim carries ≥1 `[Pn]` · **synthesize in your own words, do not copy source phrasing** (copyright, §4.3).
- **Parser `markdown→IR` (deterministic, M0):** markdown AST → blocks; within text, lift `[Pn]` tokens into
  `Span.cites` (validate each ∈ sources → else drop the token + flag); `>` block → `type:'enriched'`. One
  reparse retry on malformed; then deterministic-floor fallback.
- **Cite labels are OURS** → the LLM only echoes a label we provided; it cannot hallucinate a source id.

### C3 — IR → TipTap mapper + Citation mark (M0 + M7; **first-class anti-hallucination feature**)
Reader (`ContentRenderer`) supports `paragraph, heading, bulletList, orderedList, blockquote, callout,
codeBlock, horizontalRule` + inline marks (StarterKit + `Link, Underline, Highlight, Sub/Superscript`).
**No citation mark exists → we BUILD one (FE + BE).** The citation is the **verifiable grounding link** that
makes every claim auditable against its source — the **core anti-hallucination mechanism**, not a rendering
nicety. Reusing a generic superscript+link would throw away the structured provenance the feature depends on,
so it is rejected.

- **Block map:** lead/paragraph→`paragraph`, heading→`heading{level}`, list→`bulletList`/`orderedList`,
  enriched→`callout` (`attrs.source_type='enriched'` — the H0 distinct section).
- **NEW `citation` mark** — an inline TipTap mark, attrs `{ cite_id, source_type, chapter_id, block_index,
  score, snippet }`:
  - **Editor** — `CitationMark` extension (sibling of `GlossaryExtension`): renders `[n]` as a superscript
    chip; **survives human edits**; serializes into `body_json` (an edited article keeps its citations).
  - **Reader** — `ContentRenderer` gains a citation-mark renderer: `[n]` → **hover/click popover** showing the
    cited `snippet` + a **"jump to source"** link (`/books/{book}/chapters/{ch}/read?block=N`, raw-search
    precise-scroll). The reader **verifies each claim against its source** = the anti-hallucination UX.
  - `snippet` (~160 chars of the cited passage, captured at generation) → self-contained hover-preview (no
    live fetch); jump-to-source gives full context.
  - **Public reader (`publicGetWikiArticle`) must render it too** — provenance survives sharing (R-10).
- A **"References" section** (heading + list) lists every source with relevance — at-a-glance grounding.
- **Uncited prose is the hallucination surface** → the rule-gate (C2/M3) drops/flags any non-trivial span with
  no `citation`; a body with zero grounded claims is skipped. The mark makes "is this claim grounded?" visible
  AND queryable (Phase-2 eval reads it).
- Mapper also emits `IR→markdown` (feedback-gold diffs §4.11) + `IR→plaintext` (search) — free.
- **Storage = TipTap `body_json`** (the citation marks live in it); IR is a generation-stage only (human edits
  TipTap directly, no TipTap→IR round-trip). The `cite_id↔source` table also persists in
  `generation_provenance.citations` (audit + Phase-2 eval).

### C4 — Generation pipeline data-flow (types at each boundary; M2-M6)
```
entity → CONTEXT(attrs, kg_neighbors, passages[]) → SANITIZE(all untrusted text)
       → PROMPT(brief, sources[P1..]) → LLM(submit_and_wait → markdown str)
       → PARSE(markdown → IR) → RULE-GATE(IR: cites resolve? grounded? sections?)
       → VERIFY(CanonVerifier(IR-as-facts) → flags, publish_blocked) → REVISE(if HIGH, 1×, keep-if-improved)
       → CITE(compose_cites → provenance.citations) → MAP(IR → TipTap body_json)
       → WRITEBACK(knowledge → glossary internal HTTP)
```

### C5 — Writeback contract (knowledge → glossary; M5)
`POST /internal/books/{book_id}/wiki/articles` (X-Internal-Token), body:
```
{ entity_id, body_json (TipTap), author_type:'ai',
  generation_provenance: { build_inputs, citations:[{cite_id,chapter_id,block_index,score}],
                           verify_flags, publish_blocked, grounding:{mode,k,rerank}, model_ref, step_models },
  source_usage: [{source_type:'entity'|'kg'|'block', source_id, source_version}],   # §5.1 reverse index
  spoiler_horizon: int }
```
Glossary side (Go): upsert-by-entity + **clobber-guard** (§4.6: AI overwrites only untouched `author_type='ai'`
draft; else → `wiki_suggestion`); writes `wiki_article_source_usage` rows; flips `generation_status`.

### C6 — Schema additions (M5)
- glossary `wiki_articles` +: `generation_status`, `generated_by`, `generation_provenance JSONB`,
  `generated_at`, `spoiler_horizon`, `is_knowledge_stale` (used Phase-2). `wiki_revisions.author_type` allow `'ai'`.
  **Migrate deterministic-stub revisions `author_type 'owner'→'system'`** (detect via `summary='Auto-generated
  from KG'`) so the clobber-guard tells AI/stub from human. NEW `wiki_article_source_usage(article_id,
  source_type, source_id, source_version, PK(article_id,source_type,source_id))`.
- knowledge `wiki_gen_jobs` (mirror `extraction_jobs` shape; reuse `state_machine.py`; states incl. `paused`).

### C7 — build_inputs fingerprint (M5; the §5.1 capture — Phase-2 reads it)
`generation_provenance.build_inputs = { schema_version, entity_id, entity_revision_num, entity_content_hash,
attr_set_hash, kg_neighborhood_hash, cited_blocks:[{chapter_id,block_index,content_hash}], retrieval_params_hash,
model_ref, prompt_version, pipeline_version }`. Hash via ported learning `_stable_hash`. **Computed in Python
only** (no Go recompute) — fine for now.

### C8 — BookProfile read contract (M1; option A)
NEW `GET /internal/lore-enrichment/books/{book_id}/profile` (X-Internal-Token, reuses `get_book_profile`,
neutral default if unset) — additive to LE's existing profile API. knowledge `BookProfileClient` reads it
**once per book per job** (cache; not per entity). Fields used: `worldview, voice, era_policy, language,
anachronism_markers`.

### C9 — Job/trigger flow (M6)
FE → glossary `POST /v1/glossary/books/{id}/wiki/generate` (auth, entity-select) → if `model_ref`: glossary
fires knowledge `POST /internal/knowledge/books/{id}/wiki/generate` (202 + job_id) → knowledge inserts
`wiki_gen_jobs` + **XADD `loreweave:events:wiki-gen`** → flag-gated consumer (clone LE `resume_consumer.py`)
drains, per-entity skip-done. FE polls the **job row** (truth), not glossary `generation_status` (mirror).

### C10 — Cross-cutting integration points
- **LLM** = provider-registry async-job `submit_and_wait(operation='chat', model_source, model_ref)` (clone
  knowledge `llm_client.py`; retry+meter free). Per-step `step_models` (prose/verify) nullable→model_ref.
- **Cost-cap** = knowledge `jobs/budget.py` (`can_start_job` preflight + `record_spending`/`charge_or_pause`
  per entity → `paused` on breach). NOT in `submit_and_wait`.
- **Grounding-SDK** = `loreweave_grounding` (in main): `compose_cites` (first live consumer) + `CanonVerifier`
  (port `make_glossary_canon_lookup` + `decide_auto_reject` from LE `wiring.py`; `FENGSHEN_ANACHRONISM_MARKERS`).
- **Sanitize** = LE `clients/sanitize.py:neutralize_injection` on ALL passages/attrs/KG **before** the prompt.
- **Retriever** = refactor `search_book` → `run_hybrid_search(user_id, book_id, ...)` callable in-process
  (no HTTP/JWT/not_indexed); params mode=hybrid, granularity=chapter, rerank=true, gate on `relevance`.

---

## II. Milestone breakdown (each = one `/loom`)

| M | Deliverable | Depends | De-risks |
|---|---|---|---|
| **M0** | IR (C1) + `markdown→IR` parser (C2) + `IR→{TipTap,markdown,plaintext}` mappers — **TipTap mapper emits `citation` marks** (C3) | — | the whole data model + grounding-link contract; testable with NO LLM/DB/services |
| **M1** | BookProfile internal endpoint (C8) + knowledge `BookProfileClient` | — | option (A); enables prompt-shaping |
| **M2** | `run_hybrid_search` in-process refactor + `context.py` (attrs+KG+passages) + sanitize | M1 | retrieval contract; passage→cite-label assignment |
| **M3** | `prompt.py` (Markdown contract, BookProfile, cite-labels) + `generate.py` (LLM→IR) + `rulegate.py` | M0,M1,M2 | **single-pass generation end-to-end** (the core proof) |
| **M4** | `verify.py` (CanonVerifier + decide_auto_reject) + `cite.py` (compose_cites) + `revise.py` (1× bounded) | M3 | grounding-SDK live integration |
| **M5** | glossary writeback endpoint (Go) + clobber-guard + schema (C6) + §5.1 capture (C7) | M3 | the write path + capture (can't retrofit) |
| **M6** | **fresh wiki orchestrator** (reuse generic job infra, §III-12) + cost-cap + `wiki_gen_jobs` + **per-book lock** (§III-13) + stream consumer + glossary delegate branch (C9) | M4,M5 | batch orchestration + resume + trigger durability |
| **M7a** | FE **`CitationMark` extension** — editor mark + reader hover-preview popover (snippet) + jump-to-source, in BOTH the authed and public reader (C3) | M0,M5 | the anti-hallucination verification UX (its own slice — it's the trust layer, not a side-feature) |
| **M7b** | FE rest — model picker, job-row progress, AI-unverified badge + verify flags, regenerate | M6,M7a | user-facing generation surface |
| **M8** | feedback-emit (`wiki.corrected`/`suggestion_reviewed` via glossary outbox) + thin eval harness | M5,M7 | flywheel capture + quality measure |

**Critical path:** M0 → M2 → M3 → M4 → M5 → M6 → M7b. M1 + M7a (needs only M0+M5) are parallel-able; M8 last.
**First shippable proof:** after M3 (a grounded article generates, even if not yet persisted via the full job).

---

## III. RISKS / problems surfaced by this plan (the payoff)

1. **Citation mark is a NEW build (FE+BE), not a reuse** (C3) — it IS the anti-hallucination/verification
   feature, so we build a structured `citation` mark. Risks to watch: (a) the mark must **serialize + survive
   human edits** in `body_json` (round-trip test in M7a); (b) `snippet` captured at gen time can go **stale** if
   the chapter is later edited — acceptable (jump-to-source is the live truth; refresh on Phase-2 regen);
   (c) must render in the **public** reader, not just authed.
2. **Markdown cite-label round-trip fragility** — LLM may omit/garble `[Pn]`. Mitigated: labels are ours +
   parser validates each token ∈ sources + drops unknown + rule-gate drops uncited claims + 1 reparse retry +
   deterministic-floor fallback. **Design the parser defensively from M0.**
3. **LE runner is clone-vs-adapt, not copy** — LE `runner.py`/`assembly.py` are coupled to enrichment's
   proposal-store + gap model. M3/M6 must EXTRACT the generic orchestration (estimate→generate→verify→persist,
   cost-cap, resume) and re-wire to the wiki IR/writeback — budget adaptation effort, not verbatim clone.
4. **Two generation paths writing `wiki_articles`** — the deterministic Go `renderWikiBody` (stub) + the new
   Python LLM path. M5 must migrate stub revisions `owner→'system'` so the clobber-guard distinguishes
   stub/AI/human; define precedence (LLM regen over a deterministic stub = allowed overwrite).
5. **`compose_cites` first live consumer** — unit-tested only; M4 needs a real-passage smoke (cross-service).
6. **submit_and_wait output = raw text** — truncation on long articles → invalid/partial markdown. Mitigated by
   markdown's graceful degradation (partial still parses) + output-token budget + the retry; flag for M3.
7. **Cost estimate needs provider pricing** — the FE "~$0.18" (M7) needs a token-estimate fn + provider-registry
   price lookup (may not be exposed). Verify the pricing seam at M7; fall back to token-count display if absent.
8. **BookProfile per-job cache** — read once per book per job (C8), not per entity, or N entities = N HTTP calls.
9. **not_indexed degradation** — books without knowledge passages → semantic leg empty → grounding = lexical+KG+
   attrs only. M2/M3 must handle (degrade + a "index for better results" hint), not error.
10. **Enriched/quarantine in the public reader** — confirm `callout` (C3) renders in the PUBLIC wiki reader
    path (`publicGetWikiArticle`), not just the authenticated one, so the H0 distinction survives sharing.
11. **CanonVerifier ↔ free-prose (M4)** — the SDK was built for enrichment's *dimension-keyed* facts; wiki is
    free prose. 3/4 checks (injection · anachronism · regurgitation) run on raw text directly — fine. Only
    **contradiction** needs a fact-granularity decision (per-section vs per-sentence "facts") + a `canon_lookup`
    that ignores dimension (returns the entity's authored canon). Not a blocker; M4 design point. *Lean:
    section-level facts.*
12. ✅ **LE runner = BUILD FRESH, don't clone `run_job` (VERIFIED).** `JobRunner` is a clean seam-injected
    orchestrator BUT coupled to enrichment's domain: it iterates **Gaps** (missing dimensions), persists
    **Proposals** via `ProposalStore`, and routes through `GateAwareStrategyFactory`/technique/fabrication —
    none of which wiki has (wiki iterates ENTITIES, persists ARTICLES via glossary HTTP, ONE technique).
    **Reuse the GENERIC building blocks:** `JobStateMachine`/`JobRecord` · `cost.py` `JobCostBudget`/
    `CostCapExceeded` · `JobEventEmitter` · `UsageMeter` · `make_complete_fn` (LLM seam) · `decide_auto_reject`
    · `make_glossary_canon_lookup` · the embed/retrieval-seam pattern. **Write a fresh ~150-line wiki
    orchestrator** (entity-loop → context→generate→cite→verify→writeback + cost-cap + skip-done) — LOWER-risk
    than untangling the gap/proposal/strategy coupling. → M6 = build-fresh reusing generic infra, NOT clone.
13. **Per-book generate dedup/lock (M6, add to C9)** — only ONE active wiki-gen job per book; a 2nd request
    409s or joins. Prevents double-spend + racing writebacks. Not yet in C9.
14. **Infobox vs LLM-body duplication (M3 prompt, add to C2)** — the infobox is read-time-derived (Go, from
    glossary attrs); the prompt MUST tell the LLM to write prose, NOT restate the infobox attributes verbatim
    (else the article duplicates the infobox).
15. **Minor, resolve at milestone:** Python markdown-AST lib choice (M0 new dep — markdown-it-py / mistune) ·
    existing Go `generateWikiStubs` gains the `model_ref`→delegate branch (M6 touches shipped code) ·
    entity-selection + `force` regenerate semantics (M6) · eval golden corpus build ~15 Fengshen entities (M8) ·
    provider-registry pricing seam for the cost estimate (verify M7b, fall back to token-count display).

---

## IV. Phase-2 + follow-up roadmap (lighter; just-in-time detail at each `/loom`)

**Phase-2 (change-control reaction — designed §5.2-5.4; starts after M5 lands `build_inputs`):**
- **P2-M1** `wiki_staleness` ledger + fingerprint sweep (recompute build_inputs vs current knowledge → ledger
  rows + flip `is_knowledge_stale`). Sweep-only.
- **P2-M2** "Knowledge updates" change-feed surface (mockup screen ⑤) — list ledger + cost-estimate + batched
  user-gated regen (cost-capped).
- **P2-M3** entity-lifecycle body-regen (§5.4) — merge/rename → mark-stale→ledger (integrity already landed in
  the bug-fix commit `775e6414`; this wires the deferred body regeneration).
- *P2-M4 (conditional)* live staleness consumer — only if the sweep proves too slow.

**Follow-ups (§11):** F1 consume feedback gold → few-shot in `prompt.py` · F2 judge-based eval + discrimination
probe · F3 section-level spoiler horizon + reader-gate (when public/share prioritized) · F4 precise KG-edge
events (`knowledge.kg_synced`) if sweep too coarse · F5 multi-pass refine >1 round if eval demands.

---

## V. Open decisions for PO (before M0)
1. ✅ **Citation rendering — RESOLVED (PO): build a custom `citation` mark (FE + BE).** Citations are the
   anti-hallucination/verification layer → the structured provenance (cite_id↔source + snippet + hover-preview)
   IS the feature; superscript+link rejected. Adds slice **M7a** + the mapper work in M0.
2. **Enriched block node** — `callout` (visually distinct, exists) vs `blockquote`. *Lean: callout (matches the
   deterministic renderer's distinct-section intent).*
3. **IR location** — `app/wiki/ir.py` in knowledge-service (with the rest of the module). Confirm not a shared SDK
   yet (only one consumer). *Lean: local to knowledge-service; promote to SDK only if a 2nd consumer appears.*
