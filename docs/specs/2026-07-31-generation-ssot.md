# Generation SSOT — one spine for PLAN and PROSE

**Date:** 2026-07-31 · **Status:** SPEC v2 (post-red-team) · **Size:** multi-milestone program
**Trigger:** a dogfood defect that no test, no judge, and no gate could see.
**Companion audit:** `d:\Works\source\inkos\INKOS-ANALYSIS-FOR-LOREWEAVE.md` (F1, F4, F5 are the
same disease seen from three other services).

> **v1 → v2.** v1 was written from composition-service and generalised to the repo. A four-lane
> cold-start red team falsified it: the scope was **4 services**, the truth is **13 services + 6
> shared SDKs + Go + Rust**; the counts were low by ~3×; two of four stated root causes were wrong;
> and the "checked and clean" section — written expressly to be falsifiable — was falsified on both
> of its claims. **The corrections are kept in-line rather than deleted**, because the failure mode
> (count inside the file you just read, then state it for the repo) is the same one this spec
> exists to fix.

---

## 0 · The one-sentence thesis

> **Deciding what the story says and writing what the story says are the same problem, and this
> repo solves them with disjoint toolchains that share nothing but a provider client.**

And a corollary the red team forced into the open:

> **A guard that cannot fail is worse than no guard, because it is load-bearing in a document.**

---

## 1 · Evidence

### 1.1 Two halves, in composition-service

| | **PROSE half** | **PLAN half** |
|---|---|---|
| context assembly | `packer/` — lenses → `Segment` → priority ladder → budget trim → 2-axis spoiler → sanitize → `<block>` | **f-strings** |
| input budget | `packer/budget.py`, protected tiers | none |
| spoiler guard | `packer/spoiler.py`, fail-closed | none |
| injection guard | ⚠️ **sanitized in the pack, then re-appended RAW by the wrapper** — see B2 | none |
| craft directives | `cowrite.build_messages` | none |
| LLM judges | select · canon_reflect · motif_conformance | plan_heal · promise_audit |
| deterministic measures (**not** judges) | — | arc_conformance · tension_conformance |
| verdict type | `CanonViolation` · `MergedFinding` · `_Repetition/_OverResolveFinding` | `PlanFinding` · `Finding` |

### 1.2 Counted — v1 numbers struck, v2 numbers verified

| measure | v1 claimed | **verified** |
|---|---|---|
| services with LLM generate/grade paths | 4 | **13** (+ 6 shared SDKs, + a dead Rust crate) |
| languages involved | Python | **Python · Go · Rust** |
| `build_*_messages` in composition | ~30 | **23–25**; widening to `*_prompt` builders → **~41** (`plan_forge/prompts.py` and `glossary_build/prompts.py` hold 6 each — the *newest* plan paths, invisible to the pattern v1 counted by) |
| LLM callers bypassing the packer | 24, "all planning passes" | **18, and ≥10 are prose-side or neither** — the "two halves" framing hid the majority of the fragmentation |
| flat `max_tokens` in composition | ~21 | **~40 across 19 distinct values**, and **~31 are default parameter values**, not call-site literals |
| self-grading call sites | 5 / 2 services | **17+ / 8 services** |
| finding/verdict types | 6, "no shared base" | **≥9**, and `CanonViolation` already extends `loreweave_canon_check.CanonCandidateBase` |
| `llm_verifier` silent `[]` paths | 5 | **7** |
| learning-service online LLM judges | 4 | **3** (`online_eval.py` is deterministic) |
| context/token estimators | 2 | **4** counting conventions (+2 more that must stay separate: the **billing** convention, deliberately over-estimating, one of them Go) |
| self-heal implementations | 2 | **3** — `error_block_heal.py` is the one that already got reuse right |

### 1.3 The dogfood defect — corrected diagnosis

Chapter 1 of Mị Đế. Scene 1's prose kills **Tô Thanh Dao**, whom the plan has alive and present in
scene 2. Canon reported `{"status":"checked","resolved":true,"violations":[]}`.

| v1 cause | verdict |
|---|---|
| **#1** the check runs one direction only (`gone_written_present`; no `alive_written_dead`) | ✅ **correct** |
| **#2** "this book has no KG" | ❌ **wrong wording.** `degraded = snapshot is None`, and `fact_for_check` returns `None` only on transport failure. A 200 carrying `{"entities": []}` is truthy. A genuinely absent KG would have read `degraded` — so the project **exists and holds no status rows.** |
| **#3** a missing `NO_RULES` honesty state | ✅ **correct, and it is the proximate cause** |
| **#4** the judge was the drafter | ❌ **wrong path.** Canon is called `judge_source=critic_source` with **no** `or`-default (`operations.py:402`, `:516`); `canon_reflect.py:70` already computes `distinct` and passes `judge=None`. The two `or`-defaulted sites feed **rerank** and **motif-conformance**, neither of which produces `canon`. **S6 would not have caught this.** |
| **#5** *(found by red team)* the snapshot is **present-but-empty**, so any cascade keyed on *snapshot presence* resolves `source="kg"` and never falls through to the plan | ✅ **new — and it breaks v1's S2 design** |

**Consequence:** `NO_RULES` must be decided **per entity, per fact**, on the input corpus — never on
the matched subset, and never on snapshot presence.

### 1.4 "Checked and clean" — **falsified on both claims**

- ~~All 11 composition judges de-bias to `source_language`~~ → **false.** `plan_heal` *takes*
  `source_language` and never references it (a dead parameter); `motif_mine.build_judge_messages`
  has none; and `arc_conformance` / `tension_conformance` call no LLM at all — v1 miscategorised
  deterministic measures as judges.
- ~~The provider path is genuinely single~~ → **false.** `translation-service/poc_v2_real.py:208`
  and `poc_v2_glossary.py:130` call Ollama directly over `httpx` with a hardcoded `"gemma3:12b"`,
  **not allowlisted** in `scripts/ai-provider-gate.py`.

**Both were written in the section meant to be falsifiable, and both were falsified by reading one
directory wider.** That is the finding, not a footnote.

---

## 2 · Scope

**In.** composition-service · translation-service (**whole service**) · knowledge-service
(extraction + wiki + working_memory + jobs) · learning-service · chat-service · lore-enrichment-service ·
worker-ai · **glossary-service (Go)** · campaign-service · **tilemap-service (Rust)** · worker-infra ·
and the SDKs `loreweave_grounding` · `loreweave_extraction` · `loreweave_eval` · `loreweave_context` ·
`loreweave_llm` · `loreweave_canon_check`.

A per-service fix that leaves `loreweave_grounding/verify.py:352` and
`loreweave_extraction/pass2_filter.py:247` intact **relocates the disease rather than curing it** —
which is this spec's own argument against premature extraction.

**Out.** All transport/gateway services and the 16 ops services (verified zero LLM call sites) ·
embeddings/rerank (no instruction channel, no verdict) · image/TTS/STT · video-gen (typed errors, no
empty-success) · provider-registry internals (it *is* the gateway) · deterministic helpers ·
`chat-service/app/services/tool_plan.py` (**dead code — delete, don't migrate**) ·
retrieval quality (audit F2) · control-plane multilingual (audit F3).

---

## 3 · PHASE 0 — the live bugs. Fix · live-smoke · **seal**, before any refactor.

**Decided 2026-07-31: bugs first, verified live, sealed with a gate; then the SSOT work.** A
baseline measured on a packer that trims Vietnamese wrongly is not a baseline, and a refactor that
carries a security hole forward has laundered it.

**"Sealed" = the fix + a gate proven red-able by injecting the defect + a live run pasted into the
record.** Not one of the three alone.

| id | bug | outcome | correction to the original diagnosis |
|---|---|---|---|
| **B5** | `except DispatchError: owned = True` failed OPEN on an ownership check | **FIXED** — 503 `CAMPAIGN_OWNERSHIP_UNVERIFIABLE`; gate reds with `201 Created` on an unverified project | the fail-open was *justified in a comment* (`"the dispatch path re-verifies"`). `verify_project_owner` has ONE call site — the one making the claim. The bug was the fictional justification, not the degradation. |
| **B2** | `guide` sanitized into the pack, then re-appended RAW and LAST | **FIXED** — 2 bypass sites; gate reds on 3 payloads | — |
| **B1** | packer counted with `cl100k_base`, retired repo-wide 2026-07-07 | **FIXED** — `o200k_base` + the fallback chain composition lacked; VN 1.98 → 2.94 chars/budget-token | the "~56%" was measured against the *heuristic*. Against **o200k**: English 29,756 chars per 6000-token budget, Vietnamese **11,777 → 17,636** (40% → 59%). cl100k over-counts VN by **1.50×**. |
| **B6** | decoupled filter: unjudged⇒keep, coverage discarded, `filter_status` never written | **FIXED** — both now ride the result; **plus** a ZeroDivisionError found in `compute_filter_kept` | the extracted helper is documented "identical to `_filter_one_category`'s tail" — and the `n_input == 0` guard lives in the HEAD. A chapter with no events is ordinary input. |
| **B7** | direct Ollama + hardcoded model in two POC files | **FIXED, and far wider than stated** — POCs deleted; the *gate* was the real bug | the gate enforced **half** its own rule (SDK imports, not direct API calls) and `MODEL_NAME` **knew no local family** — no gemma, no qwen, no bge, i.e. none of the models actually served. And the superseding gate ran **only as a pre-commit hook**, so CI had only the narrow legacy lint. Both now in `foundation-ci`. |
| **B4** | judge model chosen by the caller, distinctness never recorded | **PARTIALLY FIXED** — `judge_distinct` tri-state on the wiki judge only | **severity walked back**: `/internal/learning/wiki/judge` is internal-token gated (401). NOT attacker-selectable from outside. The real defect is that a self-graded score persists indistinguishably from an independent one. |
| **B3** | `YamlGuardrail`: 0 call sites vs 2 documents claiming it gates every L3 write | **CORRECTED IN DOCS + gated by S12** | not a choice between two options: roleplay-service makes **no LLM calls at all**, so it cannot host a pre-prompt check, and the L3 write path does not exist. Correcting the claim was the only available move. |
| **B8** | tilemap fallback narration returned as `Ok` | **CLOSED — NOT A BUG** | "type-indistinguishable" is true and irrelevant: the harness runs only as a CLI that prints `"N narration(s), M attempt(s), K canonical-default fallback(s)"`. `src/http/` does not use it. No consumer can be misled. |

**Three red-team findings needed walking back after verification** (B4's severity, B5's framing, B8
entirely). Cold-start reviewers are excellent at finding the SHAPE of a defect and unreliable about
its REACHABILITY. Accepting them unverified would have produced two fixes for non-problems and
mis-ranked the queue.

**B1 carries a trap.** The estimator swap and the `pack_token_budget = 6000` / `prompt_ceiling`
(413 `PROMPT_TOO_LARGE`) re-calibration are **one semantic change** — the constant is denominated in
the old estimator's units. They land in one commit or the fix silently inflates every VN prompt
~1.8×. And every packer test injects a deterministic word counter, so **the suite cannot detect
this**: the missing gate is a **character-count** assertion on a real VN pack (characters are
estimator-invariant), plus calibration against the `input_tokens` composition already stores on every
completed job — a free, measured ground truth.

**B3 was decided** (see the table): the documents were corrected and §S12 built, because wiring was
not an available option.

### 3.1 · PHASE 0 RESIDUE — what the fixes surfaced and did NOT close

Written 2026-07-31 in response to *"check whether the un-cleared items got into the spec, or were
just forgotten."* They were being forgotten. Every row below is a real thing Phase 0 uncovered and
left standing; each names the later slice that owns it, so none of it depends on anyone remembering.

**🔴 ROT-1 — the skip audit stopped at the two variables it happened to be looking at.**
ROT-0 found 41 never-executed DB-gated tests and wired two CI jobs. Sweeping *every* `*_TEST_*`
DSN in Go tests against every workflow afterwards found **eight more variables that no workflow
sets**, covering **159 further test functions that have never run anywhere**:

| env var | test funcs | service |
|---|---:|---|
| `TEST_PROVIDER_REGISTRY_DB_URL` | 54 | provider-registry — BYOK credentials, model catalog, pricing |
| `USAGE_BILLING_TEST_DB_URL` | 37 | usage-billing |
| `AUTH_TEST_PG_URL` | 36 | auth-service |
| `INCIDENT_TEST_REDIS_URL` | 12 | incident-bot |
| `SCHEDULER_TEST_DB_URL` | 8 | scheduler-service |
| `ADMINCLI_TEST_PG_URL` | 6 | admin-cli |
| `METAPG_TEST_PG_URL` | 3 | meta pg |
| `PIIKMS_TEST_KMS_ENDPOINT` | 3 | piikms KMS |

**200 never-run tests total, and 41 was reported.** This is the same failure the red team caught in
§1.4 — count inside what you are looking at, then state it for the whole — committed again, one day
later, by the person who wrote that sentence. The fix shape is known and cheap (ROT-0 did it twice);
what was missing was the sweep. Owner: **ROT-1, before Phase 1.**

**Carry-forward by origin.** None of these are blockers; all are un-closed.

| from | left standing | owner |
|---|---|---|
| **B1** | composition now counts with `o200k`, the kernel still uses the script-class heuristic — **still two estimators**, just closer ones. And `cowrite._TOKENS_PER_WORD` now duplicates `loreweave_llm.budget.TOKENS_PER_WORD`: a *third* home for language-density constants. | **S11** |
| **B2** | the guide is still sent **twice** (protected `<guide>` segment + the wrapper's trailing line). Both sanitized now, so the hole is closed, but the model reads the same steer twice and pays for it twice. | **S4** |
| **B2** | `build_revise_messages` interpolates `draft` (model output) and violation spans lifted from it; `build_selection_messages` interpolates `selection` — none through `neutralize()`. The 2nd-order echo class the red team named. | **S4** |
| **B2** | `injection-coverage-lint.py`'s 15-row baseline still exempts **every** composition engine module. | **S4** |
| **B4** | only the **wiki** judge records distinctness. `events/handlers.py:735` (translation judge, model off the Redis payload), `online_judge.py` and `online_translation_judge.py` record nothing. | **S6** |
| **B4** | distinctness is **recorded, never enforced**, and no caller supplies `generator_model` — so every persisted value is `null` today. That is honest, and it is also the number S6 needs before a refusal can be switched on. | **S6** |
| **B6** | the upstream swallow (`except: local = {}`, "a bad batch degrades to all-unjudged") is still **silent at the swallow site**; only the aggregate coverage records it. | **S1** |
| **B6** | `partial_policy="keep"` stays the default — deliberate (dropping real candidates on an outage is worse), now recorded rather than assumed. | *decision, closed* |
| **B7** | `lint-no-direct-llm-imports.sh` is superseded but still runs in CI — two gates for one rule, and the weaker one has no expiry. | **S12** |
| **B7** | the new `/scripts/` exemption is broad: a *production* job living under a service's `scripts/` would be exempt from the model-name rule. | **S12** |
| **B7** | `MODEL_NAME` still omits served non-chat families (kokoro/TTS, whisper/STT). | **S7** |
| **B3** | the guardrail stays unwired until an L3-event write path exists; `contracts/.spectral.yaml` stays unwired per DEFERRED 078. Both now declared, not claimed. | *tracked* |
| **S12** | the gate checks **contract files only**. It does **not** cover the B5 class — a *comment* asserting a guarantee (`"the dispatch path re-verifies"`) — nor the `INV-*` code-invariant rows in the standards index. Those are the two shapes that produced two of this cycle's three worst findings. | **S12 (widen)** |

**A note on S12's own construction, because it is the lesson of the phase.** The gate went GREEN on
its own motivating example three times running, each time for the disease it exists to catch:
*"something reads it"* (the crate does — and nothing calls the crate); *"something references it"*
(a doc comment, and a workspace membership list, which is not linkage); and finally *"something
reads it"* again — **itself**, because its docstring names the contracts it discusses. It only ever
went red because the original fiction was re-injected and watched. **A gate that has never been seen
to fail is not a gate.**


---

## 4 · The SSOT slices — corrected

### S1 · `GuardReport` — one honest verdict shape

```python
class CheckStatus(StrEnum):
    CHECKED          = "checked"            # ran against a real, NON-EMPTY input corpus
    NO_RULES         = "no_rules"           # ran; the input corpus was empty        ← new
    NO_JUDGE         = "no_judge"           # no distinct judge available            ← new
    NOT_APPLICABLE   = "not_applicable"     # gated off / not sampled — renders as NOTHING ← new
    UNPARSEABLE      = "unparseable"        # the judge answered, unusably           ← new
    UNVERIFIED_INPUT = "unverified_input"   # the INPUTS degraded, not the guard      ← new
    TRUSTED_CALLER   = "trusted_caller"     # the verdict was self-reported upstream  ← new
    NO_SUBJECT / NO_POSITION / DEGRADED / FAILED
```

**Corrections the red team forced:**

- **`GuardStatus` cannot be a scalar.** Every real guard is a multi-check composite that degrades
  per check (wiki verify runs four; translation runs a deterministic rule tier **plus** an LLM tier).
  A single status makes every adopter lie. → `GuardReport.checks: dict[str, CheckStatus]` is the
  primitive; the report-level status is derived.
- **`verdict is None unless CHECKED` must apply to the VERDICT ONLY.** Findings are orthogonal: *a
  guard may return `verdict=None` with a non-empty `findings` list, and callers MUST act on findings
  regardless.* Otherwise the rule reads "unverified ⇒ discard the evidence" and breaks
  translation's corrector loop and two publish gates.
- **`NO_RULES` is computed on the INPUT CORPUS**, never the matched subset — else every book in
  which nobody has died renders permanent amber, training the author to ignore the banner. That is
  the failure S1 exists to prevent.
- `motif_conformance._EMPTY`, cited by v1 as the proven precedent, is a **per-dimension** tri-state.
  S1 as v1 wrote it would have **flattened** it. The precedent supports `checks{}`, not a scalar.
- **The gate must enumerate generation PATHS, not Python modules** — and must reach **Go and Rust**.
  The two worst false-greens found (`wiki_staleness.go:581`, `l4_retry.rs:234`) are unreachable by a
  Python-module enumeration. The SSE/stream paths carry **no `canon` key at all**, so a module-based
  gate greens on a path containing zero guard modules.

### S2 · One cast-liveness SSOT, both directions

Per-entity, per-fact resolution — `unknown` + `source="none"` when the snapshot carries no status row
for *that* entity. Cascade KG → plan → none. Gate fixture is a **non-empty snapshot with no status
row for the subject**, not an empty KG (v1's fixture would have passed while the bug survived).

### S6 · No model is silently its own judge

- **`purpose` discriminator is mandatory:** `resolve_judge(..., purpose: "grade"|"rank"|"confirm")`.
  `select.py`'s actor-as-judge is **correct by design** — best-of-N rerank (`usage_purpose:
  "prose_rerank"`), not grading. A blanket ban makes `score()` fall to `candidates[0]`, burning k×
  draft tokens to pick at random, on **every** auto-generate.
- **Enforce at write/dispatch time, not only at call time** — B4's judge arrives on an event payload.
- **Move enforcement to provider-registry**, where the role resolves. v1 cited it as precedent; the
  MUST-differ rule there is **a comment with no check**. The repo's only working refusal is
  `chat-service/app/routers/evaluate.py:174-182`.
- **Compare resolved provider models, not `model_ref`** — two `user_model` rows can point at one
  upstream model and pass any `!=`.
- **Blocked on a UI slice.** No surface sets a critic: `critic_model_ref` lives in `work.settings`
  JSONB and `CompositionSettingsView` contains no `critic` string. The self-graded fraction is not
  "measure later" — it is **100% minus hand-edited JSONB**. Ship the affordance in the same slice or
  the label is noise the author cannot clear.
- The static gate must be **"every grading call site resolves through `resolve_judge`"** (allowlist
  with recorded reasons), not pattern-matching `or` — which misses the ternary form and the whole
  class that has no critic parameter at all.

### S7 · One output budget

- The gate must red on an **int default in any signature that reaches an LLM call** (~31 of the ~40
  are defaults, not call-site literals) **and** on an **absent** `max_tokens` (`llm_verifier`,
  glossary's Go tools, tilemap pass none at all) **and** on a missing `finish_reason == "length"`
  check — glossary-service has **zero** `FinishReason` checks service-wide.
- `output_budget(...)` **must clamp against `context_length`**; two SDK sites clamp today and two do
  not, which is why worker-ai's distiller is unclamped while its extractor is not.
- **Split the slice:** `output_budget(prose)` is mechanical; the JSON kinds each need their own
  sizing model (`cast_plan`'s 4000 is *rows × per-row tokens*; `motif_conformance`'s 512 is *a
  20-word reason*). v1's "mechanical once the function exists" was wrong.

### S8 · The pack's diagnostics ride the job

**v1 inverted the semantics.** `over_budget=True` means protected segments were **kept** and the
budget was blown — nothing load-bearing was dropped. The genuinely silent signal is
**`dropped_count`** (lore/references/threads actually discarded) plus `l4_dropped_no_position`.
All of them + `warnings[]` ride the job result.

### S3 · One `Finding` — **moved after S11**

`locator` as `span | scene_index | node_id` cannot express *"which lens/segment produced this"* —
the thing the trace makes addressable and the thing "why is debugging expensive" actually needs.
Landing S3 first re-cuts every producer twice. `trace_span_id` is reserved in the union.

### S11 · One context compiler — **the crux is already answered**

v1 framed the estimator choice as an open measurement. **It was measured in this repo on 2026-07-07**
(`docs/eval/context-budget/M3-tokenlever-tuning-2026-07-07.md`): cl100k over-counts CJK ~40% against
what the platform actually serves, including gemma/qwen. The script-aware heuristic tracks o200k
within 3–6%; **cl100k is the outlier.** Two further constraints settle it: `split_to_token_budget`'s
no-character-dropped guarantee is **not implementable on a BPE tokenizer** (mid-token cuts decode to
U+FFFD — silent corruption in worker-ai's journals), and tiktoken as a kernel dependency violates the
kernel's stated stdlib purity and fetches its BPE file over HTTPS at first use.

**Other corrections:**
- `compute_target` and `enforce_budget` are **not complementary** — their denominators differ ~25×
  (whole context window vs the grounding block alone). The **allocation layer between them does not
  exist** and must be written. v1 asserted they compose.
- **Additive-then-switch is impossible through a shared symbol.** The SDK is not version-pinned;
  every service does `COPY sdks/python` + `pip install /sdk`, so changing `estimate_tokens` in place
  is adopted by chat/knowledge/worker-ai on their next unrelated rebuild. → **introduce a new name**,
  flip each consumer in its own commit.
- The frozen `contracts/context-trace.contract.json` `breakdown_categories` is a **closed chat
  vocabulary** asserted on **both** sides (BE snapshot + FE ⊆ BE **and** BE ⊆ FE). Extending it is a
  consumer-visible shape change → **namespace per surface** (`chat.*` / `composition.*`).
  `phase` is a closed TS union that is compile-time only → add `phases`/`tiers` to the contract JSON.
- The plan half already partly uses the packer (`plan_forge/existing_state.py` imports `Segment` +
  `enforce_budget`), and its budget is cl100k-calibrated too.

### S4 · The plan half onto the spine — **the gate already exists**

`scripts/injection-coverage-lint.py` is S4's gate. Work = **widen `SCAN_DIRS`** (currently 4
services) to translation, worker-ai, learning, glossary (Go), tilemap (Rust), and **put an expiry on
its 15-row permanent baseline** — which today exempts every composition engine module.

Two classes it structurally cannot see, to be added: **second-order echo** (tilemap replays raw model
output into the next turn; worker-ai re-prompts on prior LLM output) and **declared-but-unimplemented
fencing** (tilemap's prompts *promise* `<author_text>` tags its payload builders never emit — a
sanitizer that exists only as text the model is asked to trust).

The gate's property is **"every untrusted string reaching a message body passed through
`neutralize()`"** — an allowlist of sanitized sources. v1's "no string concatenation" is unshippable:
every prompt in the repo is a string built from data.

Spoiler filtering is **deliberately excluded** from the plan half — every `PASS_REGISTRY` pass
reasons over the whole book by construction, and the prose cutoff fails closed without a scene
position. Recorded, not silently skipped.

### S9 · The shared guard SDK — **inverted**

It would be the **fourth** guard SDK (`loreweave_grounding`, `loreweave_canon_check`,
`loreweave_eval` exist, with three unreconciled verdict shapes), and **three of the four adopters v1
named produce a float score, not a tri-state verdict.** There is also no version to pin.

→ Land `GuardReport` **inside composition**; implement the same contract **independently** in
translation and knowledge as part of their own slices; **then** extract what all three actually
agreed on. Entry criterion is mechanical: *three services carry a structurally identical
`GuardReport` with no service-specific fields, proven by a test that imports all three.* The
extraction folds in `loreweave_canon_check` and `loreweave_grounding`'s verdict types, or it ships a
repo with four.

### S5 · One heal loop — **three consumers, ten stages**

`error_block_heal` documents the real pipeline: *judge → locate → snap → vote → verify → rerank →
edit → merge → splice → re-judge*, and deliberately drops six with a stated reason each. `plan_heal`
implements four. → Extract the **stage protocol** (per-stage opt-out **with a recorded reason**),
and name `error_block_heal` as the third consumer — it is the one that already got reuse right.

### S10 · The instrument — **it does not exist yet**

There is no `composition-service/eval/`. S10 is a **build slice at least as large as S2**, not a
formality. And a baseline whose known-defect set is **one** cannot detect a *new* defect a later
slice introduces — which is exactly what §6's risk table asks of it. → Scope it as a build slice with
its own gate; define the baseline as a **scored set with ≥N seeded defects**, reusing the existing
`eval/*.toml` + LLM-judge methodology.

### S12 · *(new)* Every declared enforcement site must resolve to a real call site

B3's class, generalised: `docs/standards/README.md` names enforcement sites; a gate asserts each one
resolves. A standard whose enforcement is fiction is worse than an unwritten standard.

### S13 · *(new)* Cite the exemplars instead of re-deriving them

Already shipped, correct, and to be lifted rather than reinvented:
`lore-enrichment/app/eval/judge_usefulness.py` (judge-family diversity + Fleiss-κ floor +
`credit: None` + conservative tie-break) · `judge_binding.py:56-59` (*"never silently returns empty
(which would parse as an unjudged item)"*) · `knowledge/app/working_memory/executive.py:96` (already
returns the `CheckStatus` string set) · `translation/app/workers/extraction_worker.py:1149`
(`LLM_ERROR` as a first-class outcome) · `loreweave_eval.JudgePanel.excluded` (S6's exclusion set —
but fix `panel.py:25`'s hardcoded `DEFAULT_EXTRACTOR_REF` UUID, which silently fails to exclude a
deployment's real self-grader).

---

## 5 · Migration surface — this is not a refactor

A status/verdict shape change reaches: `chapter_translations.quality_score` +
`unresolved_high_count NOT NULL DEFAULT 0` (**the exact "unverified reads as clean" bug, already
documented biting in production**) → the auto-promote gate and the manual publish 409 → an MCP tool
payload → an FE badge → the outbox → `learning.quality_scores`; and `wiki_articles.generation_status`
(**Go-owned**) → a closed TS union with **no contract file and no drift test**.

Each surface needs its **null-semantics decision recorded**: does NULL fail open (publish unverified)
or closed (block every verifier-less translation, i.e. most of them)? Plus
`contracts/guard-status.contract.json` covering `CheckStatus` **and** `wiki.generation_status`, with
a parsing drift test across Python/Go/TS — the repo's own convention, and the only thing stopping
this from becoming a fourth un-synced enum.

---

## 6 · Order

```
PHASE 0   B5 · B2 · B1 · B6 · B7 · B4 · B3   ← DONE (B8 closed as not-a-bug)
ROT-1     the 159 never-run tests the ROT-0 sweep missed  ← before Phase 1
PHASE 1   S10 (build the instrument)  →  S1  →  S2  →  S8  →  S12
PHASE 2   S7  →  S6 (+ its UI slice)  →  S11  →  S3  →  S4
PHASE 3   [translation + knowledge adopt in place]  →  S9  →  S5
```

**ROT-1 comes before Phase 1** for the same reason S10 does: an instrument built on a repo whose
auth, billing and credential-store tests have never executed is measuring an unknown baseline. It is
also the cheapest item in the whole plan — the shape is already proven twice.

**Risk boundaries (checkpoint + commit):** each Phase-0 bug · S10 · S1 · S2 · S7 · S11 · S4 · S9 · S5.

---

## 7 · Definition of done

1. Every LLM-grading path — **Python, Go and Rust** — returns a `GuardReport`; **no path can report
   clean without having checked something.**
2. No model is silently its own judge, and **no judge is selectable by an untrusted caller**.
   Distinctness is decided on the **resolved provider model**.
3. No LLM call site has an integer `max_tokens` (literal **or** default), an **absent** cap, or a
   missing truncation check.
4. Every untrusted string reaching a message body passed through `neutralize()`, enforced by the
   **widened** `injection-coverage-lint` with an expiring baseline.
5. One **context-budget** estimator (the billing convention stays separate, with the reason
   recorded); one heal-stage protocol; one finding type; one pass registry.
6. Every enforcement site named in `docs/standards/README.md` resolves to a real call site.
7. **The Mị Đế chapter-1 defect is caught by a gate**, not by a human reading the prose.

Item 7 is the acceptance test. Everything else is how it gets there.

---

## 8 · Decision log

| date | decision | by |
|---|---|---|
| 2026-07-31 | Full scope, spec first, repo-wide | author |
| 2026-07-31 | Merge the two context-budget systems (S11) | author |
| 2026-07-31 | Red-team the spec before writing code — 4 cold-start lanes over disjoint corpora | author |
| 2026-07-31 | **Bugs first, run live, seal — then refactor.** *"This repo is rot and needs de-rot."* | author |
| 2026-07-31 | S6 ships label-then-tighten **with** its UI slice; a hard refusal on day one fails every default-configured job, and today no UI can clear the label | agent |
| 2026-07-31 | Spoiler filtering deliberately excluded from the plan half — reason recorded, not silently skipped | agent |
| 2026-07-31 | S9 inverted: converge in three services first, extract after — it would otherwise be the fourth unreconciled guard SDK | agent |
