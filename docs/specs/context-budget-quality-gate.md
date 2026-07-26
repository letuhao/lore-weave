# Context Budget — LLM Quality Gate (judge-driven, non-strict)

**Status:** METHODOLOGY (build-first, per user 2026-07-04) · **Model under test:** local
`google/gemma-4-26b-a4b-qat` (LM Studio) — never the paid gpt-4o.
**Related:** [[prefer-e2e-and-evaluation-over-live-smoke-poc]], spec §9 (answer-correctness gold set, sealed #7).

## Why this exists

The Context Budget effort changes **what context the chat agent sees** (wire trimming,
reference-first tools, grounding gating, compaction). A unit test can prove tokens dropped;
it CANNOT prove the agent still *answers well* on less context. That is an **LLM-quality**
question → it needs a **non-strict, judge-driven** gate, not a boolean assertion. Tokens-down
with a fluent confabulation must score as a FAIL, not a pass.

## The gate, in one loop

```
 baseline (pre-change)  ┐
                        ├─▶ judge subagent CHATS with the live lore-weave agent on scenarios
 candidate (post-change)┘        │  (real endpoint, test acct, gemma-4-26b, full stack)
                                 ▼
                    scores each turn on the rubric → writes a REPORT.md
                                 ▼
        the orchestrator (me) READS the report → decide:  PASS ▸ continue
                                                          REGRESS ▸ fix + re-run
                                                          UNSURE/needs-human ▸ DEFER + continue
```

Non-strict = the judge emits a **graded 1–5 score + prose rationale per dimension**, and the
PASS criterion is **"no regression beyond a threshold vs the baseline AND no critical
confabulation"** — a distribution comparison, not an exact match.

## Components

### 1. Scenario set (`scripts/eval/context_budget_scenarios.json` — committed)
Each scenario = a short multi-turn conversation plan over the **12-ch POC book**, tagged by
what the tier stresses. Ground truth is drawn from the book's glossary/outline (deterministic
where possible).

| Tag | Probes | Example |
|---|---|---|
| `lore_recall` | agent knows a book entity's facts | "Who is Lâm Uyển and what is her arc?" |
| `continuity` | a follow-up keeps lore after a gated turn (T5) | "…now make that scene darker" |
| `status_op` | a no-lore op does NOT over-fetch (T1/T5) | "set chapter 3 to drafting" |
| `cross_chapter` | recall spanning chapters (T4/T6) | "how did X change from ch1 to ch8?" |
| `no_lore_smalltalk` | a lore-free turn stays cheap + correct | "what can you help me with?" |

### 2. Driver (`scripts/eval/run_quality_gate.py`)
Runs INSIDE/against the live stack. For each scenario it POSTs the turns to the real chat
endpoint (SSE), collects the agent's replies + the persisted `contextBudget` frame (tokens),
and records the transcript + token cost per turn. Prefers a **local** model ($0). Emits a raw
`transcript.jsonl` per run (baseline and candidate).

### 3. Judge subagent (LLM-as-judge)
A **separate cold-start agent** reads a scenario's transcript + the ground-truth notes and
scores each agent turn on the rubric below. It NEVER sees which run is baseline vs candidate
(blind A/B) to avoid bias. It writes structured JSON + prose. Runs via the Agent tool (or a
local judge model); the judge is INDEPENDENT of the agent under test.

**Rubric (1–5 each; 5 = best):**
- **correctness** — facts match the book ground truth (entity names, relationships, arc). A
  confabulated fact caps this at ≤2 regardless of fluency.
- **groundedness** — claims are supported by what the agent could know (no invented lore).
- **continuity** — the reply respects prior turns' established facts (the gating safety-net test).
- **helpfulness** — actually addresses the user's ask.
- **critical_confabulation** — boolean: did it assert a *false* lore fact with confidence? (any
  `true` is an automatic scenario FAIL — this is the token-down-but-wrong trap).

### 4. Report (`docs/eval/context-budget/<tier>-<run-id>.md` — written each run)
Per-scenario table (dimension scores + verdict + the specific failing turn quoted), a
baseline-vs-candidate delta table, aggregate means, the token savings, and a top-line verdict:
**PASS / REGRESS / NEEDS-HUMAN**. This md is what the orchestrator reads to decide.

### 5. Decision policy (orchestrator = me)
- **PASS** ⟺ candidate mean(correctness, groundedness, continuity) ≥ baseline − 0.3 (tolerance
  for judge noise) **AND** zero new `critical_confabulation=true` scenarios **AND** tokens ↓.
- **REGRESS** ⟺ a dimension dropped > 0.3 or a new critical confabulation → **fix the tier, re-run**.
- **NEEDS-HUMAN** ⟺ the judge flags ambiguity the ground truth can't settle (a subjective
  quality call) → **DEFER row in SESSION_HANDOFF, continue other work** (per the defer-don't-block
  rule). Never hard-block the run.

## Gold-set autonomy (sealed #7 says the user validates)
The user is away, so: the agent drafts ~12 lore-needing Q&A from the POC book's glossary/outline
and **self-validates** the deterministic ones (answers checkable against the DB). Any Q&A whose
"correct answer" is a judgment call is **flagged in the report for human review**, NOT used as a
hard gate — it becomes a NEEDS-HUMAN defer, not a blocker.

## When each tier runs the gate
- **T5** (grounding gate) — the first real quality risk: prove a gated no-lore turn is cheaper
  AND a lore/continuity turn is unharmed. Baseline = pre-T5; candidate = post-T5.
- **T6** (compaction) — prove a 40-turn conversation keeps load-bearing facts.
- **FINAL** — the whole system on all scenarios; the standing acceptance gate.
- Earlier tiers (T0–T4) are byte/behavior-preserving → unit + live-e2e suffice, no judge needed.

## Reuse
Mirrors the existing eval scripts (`scripts/enrichment_eval.py`, `run_rawsearch_eval.py`,
`tests/e2e/test_compose_quality_e2e.py`) — same "drive live + score + report" shape; this adds
the blind A/B + the LLM-judge rubric + the md-report decision loop.
