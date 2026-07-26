# Context Budget — Optimization Evaluation Methodology

**Status:** methodology locked (self-proposed 2026-07-04), pre-measurement. Execute from this
doc; record results in `docs/eval/context-budget/OPTIMIZATION-RESULTS-<date>.md`.
**Purpose:** choose the Context Budget `Planner` / `CompactionStrategy` policy that keeps chat
users **comfortable** (quality + consistency + smooth UX) **without burning their money**
(session token/$ cost) — a MULTI-OBJECTIVE decision, not a token-savings race. Grounded in
current multi-turn-agent eval practice (task completion · output quality · latency · cost ·
knowledge retention · conversational coherence). The kernel's swappable seams
(`loreweave_context.Planner`, `CompactionStrategy`) make each hypothesis a one-function swap.

---

## 1. Core principle — CAPABILITY-first (maximize usefulness under cost/latency ceilings)

**The product only exists if the agent is smart enough that a human WANTS to work with it.** A
cheap, fast, *dumb* writing assistant has zero users — so **capability is the OBJECTIVE we
maximize; cost and latency are ceilings we stay under, not targets we minimize at intelligence's
expense** (user directive, 2026-07-04). Cost is a *constraint* (don't bankrupt the user), not
the goal.

The rule (revised — this INVERTS the earlier floor-then-minimize):

1. **Disqualify** any config that breaches the **hard safety floor** (`critical_confabulation`)
   or blows a **cost/latency CEILING** (unbearably slow, or burns the user's money).
2. Among survivors, **MAXIMIZE capability** — how genuinely useful/smart the agent is for real
   writing work (craft quality · collaborative competence · depth/nuance · consistency · recall).
3. Break ties toward **lower cost/latency** (cheaper is good *only when capability is equal*).

Token savings alone is still a trap axis — but now for TWO reasons: (a) it hid a session-cost
regression (per-turn savings buried under summarizer overhead, see RESULTS), and (b) **cutting
context to save tokens can make the agent DUMBER** (shallower, loses the nuance it needs to help)
— which is the *worst* outcome, however cheap. "Comfortable AND affordable" = *stay smart first;
keep cost under a ceiling second.*

---

## 2. Metric families & exact definitions

Each metric is tagged **[FLOOR]** (eligibility gate — a breach disqualifies) or **[SCORE]**
(ranks eligible configs) or **[DIAG]** (diagnostic, explains *why*).

### 2.1 Cost — the bill (session-level, incl. hidden spend)
- **`session_total_tokens`** [SCORE, primary objective] — Σ over the whole session of **input +
  output** tokens across **every** LLM call: the main turns **plus** hidden spend (compaction
  **summarizer** calls, tool-loop extra passes, **subagent** spawns). Source: provider-registry
  `usage_logs` filtered by session (ground truth), cross-checked against the per-turn
  `contextBudget.used_tokens` estimate.
- **`session_cost_usd`** [DIAG] — the same, weighted by provider input/output pricing. On the
  local gemma sweep this is **$0**, so **tokens are the cost proxy** (they map to $ on a paid
  deployment). Reported for completeness.
- **`overhead_ratio`** [DIAG] — (summarizer + tool-loop + subagent tokens) / session_total. How
  much the user pays for machinery vs answers.
- **`compaction_events`, `summarizer_calls`** [DIAG] — the hidden cost + latency driver that
  task-elastic compaction introduces (fires earlier ⇒ more summarizer calls).

### 2.2 Quality / accuracy
- **`critical_confabulation`** [FLOOR — zero tolerance] — the agent asserted a FALSE lore fact
  with confidence in ANY run. A confident-wrong answer is worse than any token cost →
  **any occurrence disqualifies the config.** Source: blind judge boolean + programmatic
  cross-check against ground truth.
- **`correctness`** [FLOOR + SCORE] — facts match ground truth (blind judge 1–5, **and**
  programmatic fact-token recall %). Floor: **mean ≥ 4.0/5 AND no single run < 3/5.**
- **`helpfulness` / `completeness`** [SCORE] — fully addresses the ask (judge 1–5).

### 2.2b Capability — the PRIMARY objective (is it a smart, useful writing collaborator?)
Recall alone measures "doesn't forget facts", not "is worth working with". These are the
top-weighted scores. Judged by a **capable cold-start Agent** (Claude-class via the Agent tool —
reliable even though the agent-under-test is gemma), on the actual writing outputs:
- **`craft_quality`** [SCORE, primary] — is the produced writing/edit/plan actually GOOD and
  useful (prose quality, editorial judgment, specificity) vs generic filler? (1–5)
- **`collaborative_competence`** [SCORE, primary] — does it understand intent, build on prior
  turns, and use the established world/context so the human does NOT have to re-explain? (1–5)
- **`depth_nuance`** [SCORE] — does it draw richly on available context (references established
  lore, prior decisions) vs shallow/context-blind answers? A config that compresses context away
  scores LOW here even if recall is fine — the tell that "cheaper" made it "dumber". (1–5)

### 2.3 Consistency — the multi-turn failure modes
- **`knowledge_retention`** [FLOOR + SCORE] — % of facts established early that are still
  correctly recalled after compaction (plant→recall, programmatic, markdown-normalized). Floor:
  **mean ≥ 90% AND worst run ≥ 80%** (no run collapses).
- **`cross_turn_coherence`** [SCORE] — later turns respect earlier-established facts/decisions
  (judge 1–5; the "make it darker, keep the character" test).
- **`run_to_run_variance`** [FLOOR + SCORE] — spread of correctness/retention over N repeats.
  A flaky chat reads as broken even at good *average* quality (we measured 1/9→9/9 pre-breadcrumb).
  Floor: **correctness range across runs ≤ 1.5 points.** Score: lower spread wins ties.

### 2.4 UX / convenience — user comfort
- **`recovery_friction` / re-ask rate** [FLOOR + SCORE] — count of turns where the agent asked
  the user to **re-supply** a fact it should have had ("I don't have that, please provide…",
  "could you remind me…") — the **false-economy detector** (leanness that pushes work back onto
  the user). Detected from reply text (pattern + judge). Floor: **no *silent* fact loss that
  becomes a confident wrong answer** (that's the confab floor); friction re-asks are SCORED
  (fewer = better), not floored, because an honest re-ask ≫ a confabulation.
- **`latency_first_token` / `latency_turn`** [SCORE] — perceived responsiveness + total turn
  time. Compaction adds summarizer latency; a laggy chat erodes trust. Source: driver timing.
- **`turns_to_resolution`** [DIAG in scripted mode] — fewer = cheaper *and* comfier. Scripts are
  fixed-length, so in this harness it is **approximated by `recovery_friction`** (each re-ask =
  a would-be extra turn in real use). Noted as a limitation (§8).

---

## 3. Decision rule (concrete)

A config is **ELIGIBLE** iff, across all scenarios × all N runs:
- `critical_confabulation` == 0 (hard safety floor), **and**
- `correctness` mean ≥ 4.0/5 and no run < 3/5, **and**
- `knowledge_retention` mean ≥ 90% and worst run ≥ 80%, **and**
- `run_to_run` correctness range ≤ 1.5, **and**
- **cost/latency CEILINGS not blown** — `session_total_est` ≤ the affordability ceiling and
  `latency_turn_avg` ≤ the responsiveness ceiling (ceilings set after the C1 baseline calibrates
  "normal"; a config that's smart but bankrupting or unbearably slow is out).

Among **eligible** configs → **WINNER = MAX capability** (a weighted blend, capability-first:
`craft_quality` + `collaborative_competence` + `depth_nuance`, then `helpfulness`, `correctness`,
`consistency`). **Cost/latency are tie-breakers ONLY when capability is statistically equal** —
we do NOT trade intelligence for a cheaper bill. Report the capability–cost Pareto so a genuinely
smarter config that costs more (but under the ceiling) is chosen over a cheaper, dumber one.

If capability is **equal** across configs (e.g. C0≈C1 on recall) → then and only then does cost
decide (→ the cheaper config; this is why C1 beat C0 in the baseline). If a cheap config is
**measurably dumber** (lower craft/depth) → it LOSES even if it passes the recall floor. If **no**
config clears the safety floor → report it, ship nothing. Thresholds/ceilings are **tunable** —
calibrated with the user after the C1 baseline.

---

## 4. Scenario set

Run **N = 4** per (scenario × config) to capture variance. **Fresh session per run**; delete
`qg-*` sessions after (shared-DB hygiene). Hybrid realism:

| ID | Shape | Bind | Stresses | Notes |
|---|---|---|---|---|
| **S1** | Long working session (~20 turns: plant lore, then write/edit/status/recall interleaved) | **lore (Dracula KG)** | session cost · compaction cadence · retention · coherence | the realistic "author works an hour" case — the primary cost signal |
| **S2** | Multi-fact plant→pad→recall (4 fact types) | synthetic | correctness · retention · recovery | clean ground truth (have it) |
| **S3** | Continuity chain ("darker, keep the character" ×N) | lore | cross_turn_coherence | |
| **S4** | Mixed lore + status/smalltalk turns | lore | cost efficiency w/o quality loss (task_weight path) | needs T5 gate ON to exercise light target |
| **S5** | Re-ask trap (a turn whose answer needs a compacted-away detail) | synthetic | recovery_friction · confab-vs-honest | the false-economy + safety probe |

Synthetic (S2/S5) = controlled, reproducible recall ground-truth. Lore-bound (S1/S3/S4) =
realistic grounding/retrieval cost. Ground-truth notes per scenario feed the blind judge.

---

## 5. Data collection

**Per turn** (extend `scripts/eval/run_quality_gate.py`): user text · assistant text ·
`contextBudget` frame (used/target/breakdown) · **provider input+output tokens** (from the SSE
`usage` event / persisted message, not just the estimate) · **compaction event** (fired? tokens
before→after? summarizer invoked?) · **tool calls** (names + count — `conversation_search`,
`run_subagent`, …) · `latency_first_token` · `latency_turn`.

**Per session** (aggregation pass): the AGENT cost is **provider TRUTH** — the driver queries
`chat_messages.input_tokens`/`output_tokens` (the real LM Studio usage chat-service persists per
turn) after the run. The **summarizer** is the ONE estimate (BYOK-local summarizer calls are NOT
metered — `usage_outbox` only tracks platform/extraction ops): estimated from the ephemeral
compaction events (tokens_before) AND the C_persist input-drops (a persist is a summarizer call
that is not a stream event — detected as a turn whose input drops sharply below the prior turn).
`session_total` = real agent + estimated summarizer. (Cross-checked: the driver's per-turn
`contextBudget.used_tokens` estimate == the real `chat_messages.input_tokens`, e.g. t4=5,347 in
both — so the estimator was already provider-accurate on the input side; the upgrade removes the
output + summarizer guesses.)

**Two scorers:**
- **Programmatic** — cost, latency, `knowledge_retention` (fact-token match, markdown-normalized),
  `recovery_friction` (re-ask pattern), variance.
- **Blind judge** (cold-start Agent, `scripts/eval/judge_prompt.md`, RUN_A/RUN_B shuffled) —
  correctness, coherence, helpfulness, `critical_confabulation`.

---

## 6. Candidate configs (the hypotheses — each a kernel swap)

| ID | Config | Swap point |
|---|---|---|
| **C0** | Incumbent: task-elastic ON (14K/32K target) + breadcrumb ON | current default |
| **C1** | Flat trigger (task-elastic OFF) — pre-T2 reference | `COMPACT_TASK_ELASTIC_ENABLED=false` |
| **C2** | More aggressive target (lower `_TARGET_MAX_FRAC`/cap) | `Planner` / `budget` variant |
| **C3** | Graded task_weight by intent (smalltalk<status<lore, not binary) | `Planner` subclass |
| **C4** *(opt)* | breadcrumb OFF (ablation — proves the breadcrumb's value under this rubric) | `COMPACT_BREADCRUMB_ENABLED=false` |

C1 = the max-quality/max-cost anchor; C2 = the max-savings probe (does it survive the floors?);
C3 = the "smarter policy" bet; C4 = an ablation that quantifies the breadcrumb.

---

## 7. Analysis & output

Per config, a **scorecard row** across all four families (means + worst-run + variance). Then:
- A **Pareto plot**: `session_total_tokens` (x) vs `correctness`/`retention` (y) — see the
  cost/quality frontier at a glance.
- Apply §3's rule → the winner (or "none eligible / incumbent holds").
- **Ship the winner by flipping config with evidence** (the way T2 + the breadcrumb shipped) —
  never on a token number alone.
Results + the decision recorded in `OPTIMIZATION-RESULTS-<date>.md`.

---

## 8. Limitations & threats to validity (state them, don't hide them)

- **Single weak model (gemma-4-26b).** Local-only per the $0 rule (no paid gpt-4o). gemma's
  **weak tool-use** means it ignores `conversation_search`, so the recovery-net UX metrics
  **understate** a stronger tool-following model. The chosen policy is therefore
  **gemma-specific**; generalizing to Claude/GPT-class needs a re-run (out of scope now). Flag
  any winner as "validated on gemma-26b" and revisit if a stronger model becomes the default.
- **Judge reliability** — LLM-as-judge is itself gemma-class here (or a separate cold-start
  agent). Cross-check every judge score against the **programmatic** ground-truth; on
  disagreement, programmatic wins for factual metrics.
- **Synthetic vs real** — synthetic plants over-index on named-entity recall; the lore-bound
  scenarios (S1/S3/S4) counterbalance with realistic retrieval cost.
- **Variance / N=4** — small; report the spread, don't over-read a single lucky run. Raise N if
  a config sits on a floor boundary.
- **Scripted turns** — `turns_to_resolution` can't be measured directly (fixed length); we proxy
  it via `recovery_friction`. A future adaptive/interactive harness would measure it properly.
- **Shared dev DB** — runs hit the shared Postgres; serialize, clean `qg-*` sessions, and don't
  interleave with a live browser smoke (KG integration tests TRUNCATE tables).
- **Summarizer-call attribution** — session cost is only ground-truth if the summarizer/subagent
  LLM calls carry the session id into `usage_logs`; verify during harness build, else fall back
  to the per-turn budget deltas + an explicit summarizer-call counter.

---

## 9. Execution plan

1. **Extend the harness** — per-turn provider token split + compaction/summarizer event capture +
   the session aggregation pass (+ verify `usage_logs` session attribution).
2. **Author S1, S3, S4, S5** (S2 exists) with ground-truth notes.
3. **Run C0 (baseline)** over all scenarios × N=4 → calibrate the §3 thresholds with the user.
4. **Run C1–C4** same matrix.
5. **Score** (programmatic + blind judge) → the scorecard + Pareto plot.
6. **Decide** per §3 → ship the winner by config flip, or report "incumbent holds / none eligible".
7. Record in `OPTIMIZATION-RESULTS-<date>.md`.
