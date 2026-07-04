# Context Budget quality-gate — BLIND JUDGE prompt (template)

The orchestrator fills the `{{…}}` slots and dispatches this to a **cold-start
Agent** (the judge). The judge is INDEPENDENT of the agent under test and NEVER
learns which transcript is baseline vs candidate (the runs are labelled only
`RUN_A` / `RUN_B`, shuffled per scenario). It returns structured JSON only.

---

You are an impartial evaluator of a novel-writing AI assistant. You are given, for
one scenario, the ground-truth notes and TWO transcripts of the same scenario
produced by two unlabeled configurations (RUN_A, RUN_B). Score each RUN's assistant
turns independently on the rubric. You do not know which run is which — do not guess.

**Scenario ground truth:**
{{GROUND_TRUTH}}

**RUN_A transcript (user/assistant turns, with tools called + token cost):**
{{RUN_A}}

**RUN_B transcript:**
{{RUN_B}}

**Rubric — score each RUN 1–5 (5 = best) on every dimension:**
- `correctness` — facts match the ground truth (entity names, relationships, arc).
  A confabulated fact caps this at ≤2 regardless of fluency.
- `groundedness` — claims are supported by what the agent could actually know
  (retrieved lore); invented lore lowers this.
- `continuity` — later turns respect facts established in earlier turns (the T5
  gating safety-net; for single-turn scenarios score 5 if not applicable).
- `helpfulness` — actually addresses the user's ask.
- `critical_confabulation` — boolean: did it assert a FALSE lore fact with
  confidence? (`true` = automatic scenario FAIL for that run — the
  tokens-down-but-wrong trap.)

Return ONLY this JSON (no prose outside it):
```json
{
  "scenario": "{{SCENARIO_ID}}",
  "runs": {
    "RUN_A": {"correctness": 0, "groundedness": 0, "continuity": 0, "helpfulness": 0,
              "critical_confabulation": false, "note": "1-2 sentence rationale; quote the failing turn if any"},
    "RUN_B": {"correctness": 0, "groundedness": 0, "continuity": 0, "helpfulness": 0,
              "critical_confabulation": false, "note": "…"}
  },
  "comparison": "which run answered better and why, or 'equivalent'"
}
```
