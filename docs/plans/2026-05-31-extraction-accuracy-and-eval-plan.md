# Plan — Extraction accuracy via user-correction loop + eval hygiene (cycle 74e)

**Date:** 2026-05-31 · **Status:** PLAN (no code yet) · **Author:** session 74 ·
**Supersedes the "grow an unbiased gold set" direction** with a correction-loop-centric one,
per PO reframe: *genre/dynamic-taxonomy bias is a FEATURE, not a defect.*

## 0 · Decision: production-readiness

The original gate ("production-good → STOP; low quality / high cost → PLAN") resolves to
**ship-ready, with a forward-looking improvement plan** — NOT a blocker:

- Extraction **output is genuinely good** (near-top-tier local models; strong-model review corroborates). Model quality is not the limiter.
- **Genre bias is intended.** The product targets literary works with a *dynamic* taxonomy (kinds/glossary/attributes user-driven from day one). Measuring against our own product policy is legitimate; external academic benchmarks (CoNLL/DocRED/LitBank) score us low only because they test a *different task with a fixed taxonomy* — that penalty is the benchmark's, not ours.
- The one real RAG correctness bug (**2-hop L2 retrieval**) is **fixed** (commit `bca5819a`, cycle 74d).
- The only genuine *measurement* artifact left is the **self-reinforcement WIRING** (a model grading its own output instance) — narrow, cheap to fix, and distinct from genre bias.

So: **ship the pipeline.** This plan is how accuracy keeps improving *after* ship, and how the eval stays trustworthy as a relative signal in the meantime.

## 1 · Eval philosophy (corrected)

| Principle | Consequence |
|---|---|
| Genre + dynamic-taxonomy bias is a **feature** | Do NOT chase a "neutral" gold set or make external benchmarks a gate. |
| Taxonomy is **dynamic** (EAV kinds/attributes, per-project) | A fixed N-type benchmark (LitBank's 6 ACE types) is structurally the wrong shape — our concept/artifact extractions are *richer*, not wrong. |
| Ground truth lives in **the user's evolving corpus** | The real metric-of-record should converge to **user-correction-derived gold**, which is unbiased *by construction* (it IS the user's truth). |
| External benchmarks = **sanity-floor only** | CoNLL/DocRED/LitBank stay informational ("did we regress to empty?"), never quality gates. |
| Self-judging is a **wiring** artifact, not genre bias | Worth a cheap fix (judge ≠ extractor/filter) because it distorts A/B deltas — the thing we actually use eval for. |

**Empirical backing (this session):** clean re-judge (judges disjoint from extractor+filter) = **0.869** vs locked **0.913** (extractor self-grades **0.972**) → ~4–5pp self-reinforcement on the *relative* signal. LitBank independent-anchor alignment = name-level P 0.59 / R 0.48 raw, but **~0.80 precision on shared kinds** once LitBank's missing concept/artifact taxonomy is excluded (23/36 "FPs" were dynamic-taxonomy entities LitBank cannot represent), and recall is low largely **by design** (scene-relevance omission). Both confirm: external numbers are deflated by *definition*, not model error.

## 2 · CENTERPIECE — learning-from-users loop (two input axes)

The accuracy engine for a dynamic-taxonomy, fully-customizable product is **operational user signal**, not offline annotation. It has **two input axes feeding one engine**:

- **Axis 1 — corrections:** the user overrides extraction *output* (rename/re-kind/merge entity, fix a relation, etc.).
- **Axis 2 — adjustments:** the user overrides the *configuration* that produced it (model choice, prompt edits, parameters). The product exposes full RAG customization to normal + power users; LoreWeave ships only a *default* setting and every user tunes per-novel. Logging these adjustments over time turns the defaults from a guess into the population's **outcome-weighted revealed preference**, and makes per-genre presets a *mined* feature.

Both axes are **largely an extension of existing infrastructure**, not greenfield:

### 2.0 · Existing foundation (verified in code)

- **Dynamic taxonomy:** glossary `glossary_entities` + EAV (`attribute_definitions` w/ `is_system`, `entity_attribute_values`); `cached_name`/`cached_aliases` denormalised from EAV. Kinds + attributes are already user-extensible per book/project.
- **Change stream:** glossary **transactional outbox** (`outbox_events`: aggregate_type/aggregate_id/event_type/payload) already emits `glossary.entity_updated` on every canonical write (atomic single-create path), relayed by worker-infra's outbox-relay.
- **Approval workflow precedent:** `wiki_suggestions` (status pending → accepted) already models human-reviewed suggestions.
- **Two-layer anchor:** knowledge-service already anchors its fuzzy/semantic entities to glossary via `glossary_entity_id` FK and consumes glossary state.
- **Graph edit primitives:** knowledge-service `merge_entity` / `invalidate_relation` / `archive_entity` exist (relation/event edits today are NOT on the outbox — gap, see 2.1).

### 2.1 · Capture (tier 0)

**Axis 1 — corrections (output overrides):**
- **Correction = any user edit that overrides an extraction:** rename/re-kind/merge/split/delete an entity; fix a relation's predicate/endpoints/polarity/modality; fix/add/remove an event; edit an attribute or alias; accept/reject a wiki suggestion.
- **Persist a `corrections` log** with provenance: `(tenant, project, target_type, target_id, op, before, after, source_extraction_run_id?, source_chapter?, source_span?, actor, ts)`. The `before→after` diff + the link back to the originating run is what makes it training/eval-grade.
- **Reuse the outbox:** enrich `glossary.entity_updated` to carry before→after + provenance; **extend the same transactional-outbox pattern to knowledge-service relation/event edits** (current gap — `invalidate_relation`/`merge_entity` should emit `knowledge.relation_corrected` / `knowledge.entity_corrected`).
- **Diff classification:** tag each correction (kind-change / boundary / spurious-drop / missing-add / predicate-fix / merge) so downstream tiers can weight them.

**Axis 2 — config adjustments (the telemetry goldmine).** Snapshot-vs-diff is a false dichotomy; use a **3-part, content-addressed (git-like) schema** so the data is both complete and minable:

1. **`config_registry(config_hash PK, resolved_config JSONB, base_default_version)`** — each *effective* config (resolved model + prompt + params after merging default + overrides) hashed and stored **once**. N runs on the same config → 1 row + N references. Content-addressing = full reconstructability with **no bloat** (this is why "full snapshot every run" only fails when stored *duplicated*).
2. **`config_adjustment_events(tenant, project, actor, ts, base_default_version, target, op, before, after, reason?)`** — the **behavioral diff stream** ("what users change, vs which default version"). Append-only, **async / lossy-OK** (Redis-Streams or fire-and-forget — NOT the transactional outbox; this is analytics, not truth). JSONB payloads so the param space can grow without schema migration.
3. **`extraction_runs(run_id, tenant, project, chapter, config_hash → registry, model_ref, metrics, outcome, ts)`** — each run references its `config_hash` and carries the **outcome label** that makes config data valuable (see §2.4). Outcome supports **both implicit** (did the user then *correct* the output / re-run / discard) **and optional explicit** (thumbs up/down) — designed to accept either, neither required at cold-start.

**Versioning is load-bearing:** every adjustment event records the `base_default_version` it diffed *from* (defaults are themselves content-addressed templates + a semver label), so a diff is never "changed from what?". Shipping a new default → existing user customizations are 3-way-rebased against it.

**Privacy split (mandatory):** log the **structural** diff freely (which param/prompt-template-id changed, prompt *hash*); treat **content** (novel text embedded in a prompt — copyrighted + possible PII) under redact/hash + retention policy + strict per-tenant isolation. See §5.

### 2.2 · Use — four tiers

1. **Dynamic anchor update (immediate; foundation exists).** Corrections flow (outbox → knowledge-service consumer) into the per-project glossary/anchor index so the *next* extraction reuses corrected canonical names/kinds/aliases. A new user-added kind or re-categorisation updates the project taxonomy. *This is the existing two-layer pattern; we extend it to consume correction events, not just entity-created.*
2. **Few-shot injection (near-term).** Aggregate high-frequency, high-confidence corrections into **per-project / per-genre few-shot exemplars** injected into the extraction prompts (entity/relation). Guardrails from prior lessons: example text must NOT overlap eval fixtures; symmetric multilingual phrasing to avoid English-token gravity on CJK.
3. **Organic eval gold (the bias answer).** Corrections ARE ground truth for that corpus → accumulate into a **growing, per-domain gold set** that is unbiased by construction. The **metric-of-record migrates** static-fixtures → blended → correction-derived as volume grows. This retires the "self-built gold is biased" worry without academic benchmarks.
4. **Domain fine-tune (later).** When a tenant accumulates enough corrections, fine-tune the local extractor (or a per-tenant LoRA) on their domain. Gated on volume + cost; LM-Studio-target per the local-first principle.

### 2.3 · Metric-of-record migration

```
now            : static fixtures (9) — relative signal only, genre-policy-matched
+ correction log: blend(static, correction-gold) weighted by correction volume/confidence
mature         : correction-derived per-domain gold = primary; static = regression-lock; external = sanity-floor
```

### 2.4 · Config data-mining tier (axis 2 → product feedback)

Once `config_registry × adjustment_events × extraction_runs.outcome` accrues, mine it to feed the product back:

- **Genre-specific golden prompts** — cluster configs by genre (Tiên hiệp / trinh thám / sci-fi …); surface prompt patterns that correlate with **good outcomes** (not just popularity). Offer as per-genre presets.
- **Model × task matrix** — which model the community trusts for which step (e.g. a heavy model for Extraction Pass 2, a fast small model for the Precision Filter), weighted by outcome.
- **Default-drift detection** — if a default param is changed by most users *and the changes converge*, update the shipped default. If changed a lot but **high-variance / non-convergent**, the signal is "this is per-novel" → ship a **per-genre preset**, NOT a new global default.

**Two guardrails baked in (else the mine produces noise):**
- **Popularity ≠ quality** — every recommendation/insight must join to the `outcome` label, never raw change-frequency. A confident-wrong default is *under*-changed and looks "good" without this join.
- **Explore vs exploit** — recommending "popular" prompts drives a monoculture that kills discovery (rich-get-richer). Surface alternatives sometimes; keep a fraction of exposure for exploration. And segment for **selection bias** (power users who customize heavily are not representative — weight, don't extrapolate).

## 3 · Cheap eval hygiene (secondary, near-term — small)

Independent of the loop; makes A/B trustworthy now. Pure code, no annotation:

1. **Disjoint-judge metric of record** — bake "judges must exclude the extractor (`019e6a20`) and filter (`019e5650`)" into the locked metric instead of running the exclude-subset ad-hoc. (gemma + ≥1 other non-pipeline model; pricing row needed per cycle-74e gotcha.)
2. **Bootstrap confidence intervals over chapters** — treat any cycle delta inside the CI as a tie; stop shipping on sub-noise ±0.1–0.3pp.
3. **Demote external anchors** (CoNLL/DocRED/LitBank) to an explicit **sanity-floor** ("not regressed to empty"), labelled non-gate.
4. **Rename** `claude-4.7-opus` → its real `qwen3.6-35b-…-abliterated` name everywhere (misleading provenance).

## 4 · Sequencing

| Phase | Work | Size | Depends on |
|---|---|---|---|
| **A (near-term)** | Cheap eval hygiene (§3.1–3.4) | M | none |
| **B (near-term)** | Axis-1 correction capture (§2.1): `corrections` log + extend outbox to knowledge-service relation/event edits + provenance link | L | outbox (exists) |
| **B2 (near-term)** | Axis-2 config telemetry (§2.1): `config_registry` (content-addressed) + `config_adjustment_events` (async) + `extraction_runs.outcome` + default versioning | L | run plumbing |
| **C** | Tier-1 dynamic anchor update from correction events (§2.2.1) | M | B |
| **D** | Tier-2 few-shot injection (§2.2.2) | M | B + volume |
| **E** | Tier-3 organic gold + metric migration (§2.3) | L | B + volume |
| **E2** | Config data-mining → defaults / per-genre presets / model×task (§2.4) | L | B2 + volume |
| **F (later)** | Tier-4 domain fine-tune (§2.2.4) | XL | E + volume |

Phases A + B + B2 are the immediate next steps; C–F/E2 unlock as correction/adjustment volume accrues post-ship.

## 5 · Deferred / open / risks

- **Relation/event edits not yet on outbox** — knowledge-service graph edits must adopt the transactional-outbox pattern for capture parity with glossary (Phase B core task).
- **Correction quality control** — users mis-correct too; tier-3 gold needs a confidence/agreement gate (wiki_suggestions approval precedent) before a correction becomes gold.
- **Privacy / content-vs-structural split** — adjustment logs and corrections may embed copyrighted novel text + PII. Log the *structural* layer (param/template-id/prompt-hash) freely; redact/hash + retention-policy + strict per-tenant isolation for *content*. Few-shot/fine-tune must NOT leak one tenant's corpus into another's prompts/weights.
- **Popularity ≠ quality** — any config-mining insight must join to the `outcome` label, never raw change-frequency (a confident-wrong default looks "good" by being under-changed).
- **Explore/exploit + selection bias** — auto-recommending popular configs drives a monoculture that kills discovery; keep an exploration fraction. Power users who customize heavily are unrepresentative — segment + weight, don't extrapolate. High-variance change signals → per-genre preset, not a new global default.
- **Cold-start** — before correction/adjustment volume exists, static fixtures + the cheap hygiene carry the eval; do NOT block ship on the loop. Outcome label is optional at cold-start.
- **L2 temporal bucketing** (audit MED) and **realized-vs-filter-output F1** remain separate tracked items, untouched here.

## 6 · What this plan explicitly does NOT do

- Does NOT grow a large hand-built "neutral" gold set (wrong target — genre bias is intended).
- Does NOT make LitBank/CoNLL/DocRED a quality gate (taxonomy-shape mismatch; sanity-floor only).
- Does NOT change the extractor's scene-relevance omission or 6-kind dynamic taxonomy (those are product policy).
