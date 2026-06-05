# PLAN — Compose Slice 1 (spine + mode D) · 2026-06-04

> Spec: [`docs/specs/2026-06-03-enrichment-compose.md`](../specs/2026-06-03-enrichment-compose.md) §2.3/§2.5/§2.7/§5 (slice 1 row).
> Branch `lore-enrichment/foundation`. Type **L** (FS). Slice 0 (de-bias) DONE.
> **Split (mirrors C3 0d/0e):** **1-BE** (spine + DraftExpand + compose API) → its own VERIFY+POST-REVIEW+COMMIT, then **1-FE** (composer shell + draft form) → its own VERIFY+POST-REVIEW+COMMIT.

## Acceptance (slice 1, from spec §5)
draft → 202 → worker → **quarantined** proposal for an **existing AND a new** entity (location + generic); promoting the new one **mints the glossary anchor** (reject leaves glossary untouched); **both expand_modes** (add_only/rewrite); **book-aware** voice; FE `compose()` wired.

## Load-bearing findings (from code read, 2026-06-04)
1. **DB CHECK blocks `compose_draft`** — `enrichment_job.technique` ([migrate.py:219-220]) AND `enrichment_proposal.technique` ([migrate.py:313-314]) both `CHECK (technique IN ('template','retrieval','fabrication','recook'))`. The runner persists `technique=pipeline.technique_value()` → **a migration is required** (spec §2.8 "no migration" was wrong for the technique value). Idempotent `DO $$` named-constraint blocks (precedent: `source_corpus_license_vocab`).
2. **③ regurgitation IS wired live** (`verify_and_annotate`→`CanonVerifier.verify`→`_check_regurgitation`, HIGH auto-rejects) but compares output vs `proposal.grounding`; mode-D proposal has **empty grounding** → ③ mechanically N/A (F8). Pin with a test.
3. **New-entity-at-promote H0** — `write_entity_through_glossary` POSTs glossary `/extract-entities` (resolve-or-create) keyed on `_anchor_name()` (prefers `canonical_name`). No compose-time glossary write needed; verify in BUILD.
4. **Synthetic source_ref** — `SourceRef` has no `kind` field; mint `corpus_id="author_draft"`, `chunk_id=sha256(draft)[:16]`, `chunk_index=0`, `score=0.0`. Non-UUID `corpus_id` naturally trips the recook `UUID(corpus_id)` forward-guard (§2.5). No H0-model change.

## 1-BE tasks (TDD)
- **T1 migrate** `app/db/migrate.py`: add `compose_draft` to both technique CHECKs — update inline + idempotent `DO $$` drop-old-`_check`/add-`_technique_vocab` blocks (guard `NOT EXISTS(vocab)`). Test: round-trip up; insert job+proposal with technique='compose_draft' succeeds.
- **T2 enum+ctx** `app/strategies/base.py`: `Technique.COMPOSE_DRAFT="compose_draft"` + `_TECHNIQUE_TIER[...]=Tier.P1`; `StrategyContext.seed_text: str|None=None`, `expand_mode: str|None=None` (frozen, additive). Test: tier==P1; ctx carries seed_text/expand_mode; other strategies ignore them.
- **T3 strategy** `app/strategies/draft_expand.py` (new): `DraftExpandStrategy(technique=COMPOSE_DRAFT)`; `build_draft_prompt(proposal, profile, seed_text, expand_mode)` book-aware (zh/non-zh, add_only KEEP-verbatim vs rewrite voice-sync); own `complete` call (no retrieval/grounding); `repair_generation`; mint facts via `make_enriched_fact` with synthetic `author_draft` SourceRef + `extra_provenance={"seed":"author_draft","expand_mode":...}`; `verify_and_annotate`; `estimate_cost` (P1 token pre-charge, no embed). Refuses empty `seed_text` (ValueError). Tests: empty-corpus draft mints a fact (no raise); add_only prompt keeps draft; rewrite prompt; both languages; no-grounding → ③ flag absent.
- **T4 pipeline** `app/jobs/stages.py`: `DraftExpandPipeline(strategy)` → `run_gap` returns `StageResult` (proposal w/ empty grounding, facts, verify, source_refs from author_draft ref); `technique_value()=="compose_draft"`. Test: run_gap returns compose_draft StageResult; verify ran.
- **T5 assembly** `app/jobs/assembly.py`: construct `DraftExpandStrategy(complete, verifier)`, add to factory `strategies=[...]`; **explicit** `elif selected.technique is Technique.COMPOSE_DRAFT: pipeline=DraftExpandPipeline(...)` BEFORE `else→GapPipeline`; `cost_strategy=selected`, `runner_meter=meter`. Test: build_live_runner(technique='compose_draft') selects DraftExpandPipeline (P1 ungated, no gate raise).
- **T6 compose API** `app/api/compose.py` (new): `POST /v1/lore-enrichment/projects/{project_id}/compose`, owner-auth; body discriminated by `input_source`; **slice 1 = `gap`|`draft`**; target existing|new (kind any+generic); draft → create_job(technique=compose_draft, entity_kind=target.kind) + save_job_request{input_source, seed_text, expand_mode, targets:[target], book_id, model_refs, …} + enqueue → 202+job_id; gap → reuse targets path (technique from body). `context`/`files`/`intent` → 400 "not available in slice 1". Register router. Tests: draft → 202 + request persists seed_text/expand_mode + technique=compose_draft; new-target body (target_ref None); 401 no-auth; unsupported source → 400.
- **T7 worker** `app/worker/resume_consumer.py`: thread `seed_text=request.get("seed_text")`, `expand_mode=request.get("expand_mode")` into `StrategyContext`; entity_kind from request. Test: redrive builds ctx with seed_text/expand_mode.
- **T8 contract** `contracts/api/lore-enrichment/v1/openapi.yaml`: add `/projects/{project_id}/compose` (request/response). (resolve-intent/uploads deferred to slices 2-4.)

**1-BE VERIFY:** pytest (full suite green, new tests pass) + cross-service **live-smoke**: draft compose → 202 → worker re-drive → quarantined `compose_draft` proposal for an existing (location) AND a new (generic) entity; promote the new → glossary anchor minted; reject leaves glossary untouched. POST-REVIEW (offer /review-impl). COMMIT (BE).

## 1-FE tasks (TDD, after 1-BE)
- `EnrichmentView.tsx` + `EnrichmentContext.tsx`: add `'compose'` panel (lead strip, no-unmount).
- `components/compose/`: `ComposePanel` (shell), `ModeSelector` (D active; A reuse; B/C/F disabled "coming soon"), `ComposeDraftForm` (draft_text + expand_mode radio), `ComposeTarget` (existing | +new: name + kind dropdown), `ComposeConfig` (model pickers via `providerApi.listUserModels` + cost-cap + top_k + ①②③④ strip + H0 chip).
- `hooks/useCompose.ts` (`compose()` 202 + invalidate jobs/proposals + toast).
- `api.ts`/`types.ts`: `compose`, `ComposeBody`, `ComposeTargetInput`.
- i18n `compose` namespace en/vi/ja/zh-TW (parity green).
- vitest: ComposeDraftForm, ComposeTarget, ComposeConfig, ComposePanel (mode switch + run body), useCompose.

**1-FE VERIFY:** vitest + tsc + i18n:check; optional browser e2e (extend `enrichment-profile.spec.ts`). POST-REVIEW. COMMIT (FE).

## Out of scope (later slices)
C paste-context (2), F files+OCR (3), B intent + resolve-intent (4). `/uploads`, `app/files/extract.py`, `app/compose/intent.py` — NOT in slice 1.
