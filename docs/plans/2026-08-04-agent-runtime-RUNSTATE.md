# RUN-STATE — Agent Runtime (framework + runtime, rebuilt on a membrane)

Spec: [`docs/specs/2026-08-03-agent-runtime-unification/`](../specs/2026-08-03-agent-runtime-unification/) —
`ARCHITECTURE.md` is the design, `DESIGN-HYPOTHESIS.md` §4 the red-team verdict, `BUILD-VS-BUY.md` the
external comparison, `SPEC.md` §10.1–10.2 the cleared questions.

---

## The commitment

> **Build a new runtime that starts empty, admit declarations one at a time, and prove each one against
> a frozen baseline of the old runtime.**
> Nothing is deleted. The old runtime stays live **as the control group** — because the claim to be
> proven is *"the new performs better than the old"*, and a clean floor destroys the only thing that
> sentence can be measured against.

**The failure this run exists to avoid is not "the build is late". It is "a new version ships, never
runs in anger, and repeats the old one's fate."** Every checkpoint below therefore requires a **live
run**, and every live run requires its **instrument** to be verified independently.

---

## ▶ THE ACTIVE GOAL (set 2026-08-04) — re-read after every compaction

**The claim, stated so an independent party can falsify it.** On the same task family, the new runtime
must beat the frozen old-runtime baseline on all four measured classes:

| class | old-runtime baseline (frozen at CP-0) | claim |
|---|---|---|
| **carry-forward** — a failure on a declaration that already succeeded this session | **61.8%** of failures (2,477/4,010) | strictly lower |
| **identifier resolution** — of real (non-breaker) errors | **≈57%** | strictly lower |
| **our own prose counted as tool error** | **65.7%** of failures | strictly lower |
| **turns ending `interrupted`** | to be frozen at CP-0 | strictly lower, and **`interrupted` is a defect, not an outcome** (§0.5) |

**Two rules that make the claim honest:**

1. **`3/3` is never evidence.** It bounds a failure rate only at **≤63.2%** against a **54.2%**
   baseline. A stated bound must be one the run can support (`ARCHITECTURE.md` §6.2).
2. **A test may reject; it may never admit** (§0.12). Test evidence gates the *contract*; the
   *behavioural* bound comes from production traffic on the new runtime and is **published, not
   required**.

### ▶ THE PER-CHECKPOINT PROTOCOL — repeated here because a pointer is forgettable

**Before opening any checkpoint, re-read: this file's checkpoint section + `ARCHITECTURE.md` for the
clauses that checkpoint implements.** A goal that only *links* the spec loses it at the first
compaction. Each checkpoint runs the same five steps:

| step | |
|---|---|
| 1 | **write the verifier prompts first**, commit them with the checkpoint opening — a prompt authored after the code is a prompt written to pass |
| 2 | build the items |
| 3 | **deploy the verifier agents** — α:1 (V-CODE) · β:2 (+V-LIVE) · γ:3 (+V-METRIC), in one message, fresh, no builder reasoning in the prompt |
| 4 | verdicts to `verification/CP-<n>-<role>.md`, linked from the board. `PASS` with no falsifier = `CANNOT DETERMINE`, which does **not** close |
| 5 | record the bound the evidence supports — never a bound it does not |

**The items most easily lost, restated so forgetting requires ignoring rather than not knowing:**

- **CP-0.7 `runtime_variant`** — without it **no comparison is computable at all**, whatever data
  accumulates. The comparison unit is the **declaration**, not the runtime.
- **`advertised_tools` is `jsonb`, an array per pass** — a `text[]` records only the last pass and
  **loses the mid-turn deletion the field exists to catch**.
- **The guardrail shadow arm is v1** — evaluate, record, do **not** act. Un-retrofittable.
- **C-13 `re_runnable` ships before any automatic re-run.** `binding-invalid` re-running a producer
  that is not idempotent is a duplicate-data generator; `kg_project_create` was measured **×57 in one
  turn**.
- **`done_when` that cannot be evaluated yields `unknown`, never `satisfied`** — it currently falls
  back to the call log, which is `ok=true`, which C-5 exists because it can be a lie.
- **Every withholding registers.** An exclusion with no `{tool, stage, reason}` is a defect, not a
  policy.

---

## ▶ THE VERIFICATION AXIS — independent, three roles, never the builder

**The goal cannot self-verify. Measured, this session: four of my own measurements were wrong, every
one from reading a proxy instead of the artifact the consumer receives** — and the repo's standing
"211/224 tools pass" gate certifies a tool that scores **0/101** in real use. Self-verification here is
not a theoretical bias; it is a reproduced defect.

**Mechanical independence — not a promise:**

- a verifier is a **separate agent invocation with no shared context** with the builder;
- it receives **the claim and the artifact**, never the builder's reasoning;
- **a PASS is invalid unless it states what would have made it FAIL.** *"Looks correct"* is not a
  verdict;
- **the builder may not answer a verifier's finding by explaining intent** — only by changing the
  artifact or withdrawing the claim.

### The three roles

| role | reads | must answer | may NOT |
|---|---|---|---|
| **V-CODE** | source | does the code do what the document claims? where can it be **bypassed**? is any gate **vacuous** (NV-1..6)? | run the system, or accept a docstring as behaviour |
| **V-LIVE** | the running system | does it work **in anger**, on real content, through the real front end? what breaks that the tests do not see? | read the builder's notes before running |
| **V-METRIC** | the instrument | **is the measurement sound** — denominator, sample, contamination, statistical power? *would this number look good even if the thing were broken?* | evaluate whether the feature is good |

### ▶ DEPLOYMENT PROTOCOL — explicit, mandatory, mechanical

**A checkpoint closes only when its required verifier agents have been DEPLOYED and have returned a
verdict. This is a required action, not a disposition.**

| scale | agents to deploy | how many |
|---|---|---|
| **α** one mechanism | `V-CODE` | 1 |
| **β** one layer coherent | `V-CODE` · `V-LIVE` | 2 |
| **γ** an architecture claim | `V-CODE` · `V-LIVE` · `V-METRIC` | **3** |

**How each is deployed — every clause here exists to remove a way the check could be faked:**

1. **A fresh `Agent` invocation per role.** Never a continuation of the builder's agent, never a
   second question to a verifier that already passed something in this checkpoint. Deploy the roles
   **in one message so they run concurrently and cannot influence one another.**
2. **The prompt carries the CLAIM and the ARTIFACT PATHS. It must not carry the builder's reasoning,
   its commit messages, or its self-assessment.** A verifier told *why* a thing was built will grade
   the justification instead of the artifact.
3. **The verifier prompt is written BEFORE the build starts**, and committed with the checkpoint's
   opening. A verifier prompt authored after the code is a prompt written to pass — the same defect as
   acceptance criteria written after the result.
4. **Each returns a structured verdict: `PASS` / `FAIL` / `CANNOT DETERMINE`, plus the falsifier.**
   A `PASS` with no stated falsifier is recorded as `CANNOT DETERMINE`. **`CANNOT DETERMINE` does not
   close a checkpoint** — it is a finding about observability, which is itself the subject of CP-0.
5. **Verdicts are written to `verification/CP-<n>-<role>.md`** and the checkpoint row in this file
   links them. An unlinked checkpoint is open, regardless of what was built.
6. **The builder may not respond to a finding by explaining intent** — only by changing the artifact or
   withdrawing the claim. If the builder believes the verifier is wrong, **a second independent
   verifier is deployed on that single question**; the builder does not adjudicate its own work.
7. **A disagreement between roles is not resolved by majority.** V-METRIC saying *the number is
   unsound* voids a V-LIVE `PASS` built on that number, because a result measured wrongly is not a
   result.

**One prohibition, and it is the one this session earned:** the builder may not run the verification
queries itself and present the output as verification. **Four of this session's own measurements were
wrong, every one from reading a proxy instead of the artifact the consumer receives.** Running the SQL
is evidence-gathering; it is not a verdict.

**V-METRIC is the role this session proved necessary and it is the one usually skipped.** Its subject
is the instrument, never the result. Its standing questions:

- where does the denominator come from — **the SSOT, or from what we built?**
- is the sample contaminated? *(the corpus contains a 37-session harness run with 580 blank-args calls;
  duplicate-book counts are dominated by test fixtures)*
- what bound does N actually support?
- **is the guard red-able, and red-able over the right subject?** *(a guard proven red over the wrong
  field is the audit's own NV-1 instance)*
- does any number here rely on `ok=true`, which C-5 exists because it can be a lie?

---

## Invariants that must hold at every checkpoint

1. **Nothing is deleted.** The old runtime, the public edge (170 policy entries, third-party keys) and
   the FE bridge (8 tools) keep serving.
2. **The membrane is construction, not filtering.** No code path from the old catalog to the new
   surface — enforced by an import-graph gate (M2), not by a lint.
3. **Every withholding registers.** An exclusion with no `{tool, stage, reason}` row is a defect.
4. **No plan terminates except by `done_when` or by reaching a human.**
5. **Every constraint is visible to the model and appealable by it**, except P6 (§0.3).
6. **No checkpoint closes on self-verification.**

---

## ▶ CHECKPOINTS — by layer, then by scale

Scale ladder, and it sets which verifiers must sign:

| scale | closes when | V-CODE | V-LIVE | V-METRIC |
|---|---|---|---|---|
| **α** one mechanism | the code does what it says | ✅ | — | — |
| **β** one layer coherent | it works end-to-end, live | ✅ | ✅ | — |
| **γ** an architecture claim is testable | the number is trustworthy | ✅ | ✅ | ✅ |

### L0 · INSTRUMENT — `CP-0` **(γ) · BLOCKS EVERYTHING** · 🟡 **OPEN 2026-08-04**

Nothing below is observable without it. **A brick laid before its instrument is a brick nobody can see
fall.**

**Verifier prompts, committed at opening — before any CP-0 code existed** (protocol clause 3; the
commit precedes the build commits in `git log`, which is the check):
[`V-CODE`](../specs/2026-08-03-agent-runtime-unification/verification/CP-0-V-CODE-PROMPT.md) ·
[`V-LIVE`](../specs/2026-08-03-agent-runtime-unification/verification/CP-0-V-LIVE-PROMPT.md) ·
[`V-METRIC`](../specs/2026-08-03-agent-runtime-unification/verification/CP-0-V-METRIC-PROMPT.md) ·
[the rules they run under](../specs/2026-08-03-agent-runtime-unification/verification/README.md)

| # | item | state |
|---|---|---|
| 0.1 | `chat_messages.advertised_tools` — **`jsonb`, array per pass** (a scalar loses the mid-turn deletion the field exists to catch) | ⬜ |
| 0.2 | `chat_messages.withheld_tools` — `{tool, stage, reason}`; `budget_names_by_tokens` returns `(kept, dropped)` **as its sibling 20 lines below already does** | ⬜ |
| 0.3 | `tool_calls[].source ∈ {tool, breaker, meta}` + `latency_ms` — no migration needed (jsonb) | ⬜ |
| 0.4 | mandatory outcome on **every** terminal path, incl. cancel and crash (`finish_reason` covers **9.4%** today) | ⬜ |
| 0.5 | **freeze the baseline** — snapshot `tools/list` into `contracts/`, script arms A–E. They were built from a live catalog and **are not reproducible today** | ⬜ |
| 0.6 | measure the **binding format** on our own model (§0.11 — do not import the YAML benchmark) | ⬜ |
| 0.7 | **`runtime_variant` + the declaration identity on every recorded call** — without these the comparison in §"the measurement unit" **cannot be computed at all**, however much data accumulates | ⬜ |

### The measurement unit is the DECLARATION, not the runtime

**You cannot A/B a runtime holding one declaration against one holding 315.** Session-level assignment
is therefore either impossible (the new runtime can do nothing) or **biased** (route the easy work to
the new one) — and a biased assignment invalidates the control group, which V-METRIC would reject at
CP-0.

| from | compare | valid because |
|---|---|---|
| **brick 2 onward** | calls to declaration **D on the new runtime** against **D (or its predecessor) in the frozen baseline** | **matched pairs on the same capability** |
| **CP-4** | one real task **both runtimes can complete**, with randomised session assignment | only here does a fair whole-runtime contrast exist |

Recording `runtime_variant` is what makes the first row computable; without it the run produces data
that cannot answer its own question.

**V-METRIC signs CP-0 or the run does not start.** Its specific job: prove each field answers a
question that has no answer today, and prove the baseline is reproducible **from the snapshot alone**.

### L1 · FRAMEWORK — `CP-1` (β) · the membrane, empty

**Where it lives — decided 2026-08-04:** a **package inside chat-service, `app/agentruntime/`**, not a
new service (SPEC §6) and not a shared SDK (two of the three assemblers are TypeScript, so a Python
primitive would cover one of three — `SPEC.md` §10.1 Q2). The import-boundary gate has a working
precedent in this repo: **`scripts/lint-no-direct-llm-imports.sh`**. Extractable later if a second host
needs it; the package boundary is what makes M2 mechanical today.

| # | item | state |
|---|---|---|
| 1.1 | `contracts/agent-runtime-manifest.json`, generated, **starts empty** (M1) | ⬜ |
| 1.2 | **import-graph gate** — the new assembler cannot reach any legacy catalog module (M2) | ⬜ |
| 1.3 | discovery reads M1 only; a legacy-only declaration of **each of the three kinds** returns zero rows (M3) | ⬜ |
| 1.4 | **construction *is* validation** — `Admitted[D]` with a private field, so a bypass is a compile error. **Verified missing today:** Go's `NewToolMeta` validates nothing; 14 validator call sites against 58 uses in glossary alone (M4) | ⬜ |
| 1.5 | a reference to a non-admitted declaration is **unresolvable** (M5) — today 12 rails point at 30 dead tools behind a gate that **fails open** | ⬜ |
| 1.6 | **C-0 identity** — id · owning service (derived) · lifecycle state · contract version | ⬜ |

**V-CODE's mandate here is bypass-hunting**, and it has a named precedent: `require_meta`'s docstring
ships its own exemption. **V-LIVE proves the empty surface is honest** — the agent must *say* it has no
declarations, not silently emit a tool-free pass.

### L2 · RUNTIME — `CP-2` (β)

| # | item | state |
|---|---|---|
| 2.1 | P4 assembly on the bought toolset — **and it must be the deferring API, not the filtering one.** Both exist one method apart; one is a ceiling and one is an enabler | ⬜ |
| 2.2 | **the widening rule** (§4.3) — a plan step's declaration must be advertised while that step is current. **Deletes three heuristics**: the rail next-step exemption, the backtick prose scraper, `load_skill`'s un-advertised names | ⬜ |
| 2.3 | deterministic tool ordering — `active_tool_names` is a `set[str]` iterated unsorted, so **the order changes on every restart** and `tools` is the first cache block | ⬜ |
| 2.4 | withheld things stay **reachable on request**; the model can tell *withheld* from *never existed* | ⬜ |
| 2.5 | P5 fields written on every path; **guardrail shadow arm — evaluate, record, do not act.** v1 only; un-retrofittable | ⬜ |

### L3 · PLAN — `CP-3` (γ) · **the architecture's central claim**

| # | item | state |
|---|---|---|
| 3.1 | `plans` table — **SPEC versioned + hashed, STATE event-sourced**, one live plan per session, template identity **by value** (two databases, so there is no FK to have) | ⬜ |
| 3.2 | markdown authoring surface → parsed to structured SPEC; **a parse failure is a rejection with locus (C-12)** | ⬜ |
| 3.3 | the projection — **generated with a gate**, declares its own lossiness, **stable between plan events**, and **never compresses an identifier** | ⬜ |
| 3.4 | executor binds `emits` → `accepts` **directly**, instead of asking the model to retype a UUID it has already seen | ⬜ |
| 3.5 | recovery: five scopes incl. `abandoned-by-user`; **C-13 `re_runnable` before any auto re-run**; completed-effects ledger as replan input | ⬜ |
| 3.6 | the four silent exits close as **one** mechanism — *a plan that ends anywhere but `done_when` names what is live and hands it to a human*. **`sweep_expired_runs` has zero callers; no `'streaming'` row is ever read back** | ⬜ |
| 3.7 | approval binds to the **SPEC hash over gated steps**; a permission **pre-flight** at plan time (every input is static) | ⬜ |

**CP-3 is where the 61.8% is tested, and it is the checkpoint most likely to fail.** V-METRIC's
question here is the sharp one: **is the reduction real, or did we convert loud failures into quiet
ones?** Both this design and every rival do that, and this repo counts only loud ones.

### L4 · DECLARATIONS — `CP-4` (γ) · one at a time

Bricks 2→5: a near-zero-argument read · a read taking a **name** not an id (C-4) · **a two-step pair
whose step 2 consumes step 1's `emits`** (C-6) · a write with a confirm token approved **as a plan**.

**Brick 2 is `book_list` — chosen, not convenient.** It already satisfies several clauses the contract
will demand, which makes it a test of the *membrane* rather than of the declaration:

- `kind` **defaults to `books`**, so the default call is argument-free;
- *"List REFERENCES only — never bodies"* — **it is already the `ResourceLink` shape**;
- paged, with `page.is_complete` and a `guidance` line **telling the caller when to stop** — C-3 and a
  self-terminating result contract, already shipped;
- it **supersedes three legacy tools**, so it exercises consolidation, our primary migration operation;
- **and it is the declaration `budget_names_by_tokens` silently deleted in arm E.**

> Admitting `book_list` first closes the exact defect that founded this work.

Throughput is a first-class metric here: **≈13 admissions/week** keeps pace with the model cadence.
Report it per checkpoint. *(The first draft's metric — "admits fewer than it retires" — cannot fire,
because nothing is retired.)*

---

## ▶ WHERE THE RUN STANDS

**Design: closed.** Red team (7 agents) and module interrogation (8 agents) complete; nine of twelve
original assumptions dead and the design rebuilt on what survived. All 18 spec questions plus N1–N3
cleared. Seven defects in the design itself were found and fixed **before any code was written** —
including one (`binding-invalid` re-running a non-idempotent producer) that was a recipe for duplicate
data.

**Build: `CP-0` opened 2026-08-04.** Its three verifier prompts are committed and nothing else is —
the build starts from a position where the checks that can fail it already exist and cannot be
retrofitted to whatever gets built.

| checkpoint | scale | state |
|---|---|---|
| **CP-0** instrument + frozen baseline | γ | 🟡 **OPEN** — [prompts committed](../specs/2026-08-03-agent-runtime-unification/verification/), items 0.1–0.7 building |
| CP-1 membrane, empty | β | ⬜ |
| CP-2 runtime | β | ⬜ |
| CP-3 plan | γ | ⬜ |
| CP-4 declarations | γ | ⬜ |

---

## Open, and each is honestly one of three kinds

| | kind | blocks? |
|---|---|---|
| is a plan also a **user-facing document** in the product sense? | product decision | no |
| binding format on our own model | **an unrun measurement** — belongs to CP-0 | CP-3 |
| `ARCHITECTURE.md` §0.2 sits after §0.12 | reading order, one pass | no |
| third-party sunset window | blocked on prerequisites: no `Sunset` header, unversioned `/mcp`, **114 tools with no `deprecated_at`** | CP-4 |

**Closed 2026-08-04, and one of them changed the measurement axis:**

| | resolution |
|---|---|
| where the new runtime physically lives | `app/agentruntime/` inside chat-service, with an import-boundary gate modelled on `scripts/lint-no-direct-llm-imports.sh` (CP-1) |
| **what routes a turn to old vs new** | **it does not — the comparison unit is the declaration, not the runtime.** Session-level assignment is impossible or biased; matched per-declaration pairs against the frozen baseline are neither. **This added CP-0.7** — without `runtime_variant` recorded, the comparison cannot be computed at all |
| the first declaration | `book_list` — already references-only, self-terminating, a consolidation of three, **and arm E's silent-deletion victim** |
