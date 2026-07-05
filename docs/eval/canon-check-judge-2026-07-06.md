# D-KG-EXTRACTION-CANON-GATE — judge accuracy eval (2026-07-06)

**Question answered:** the POC (2026-07-05, see `docs/sessions/SESSION_HANDOFF.md`) proved the
symbolic-prefilter + LLM-judge mechanism in
`services/knowledge-service/app/extraction/canon_check.py` works end-to-end, but left judge
*accuracy* on hard cases as an open, anecdotal question. This eval scores it with a fixed,
scored fixture set instead of more spot-checks.

**Harness:** `services/knowledge-service/eval/run_canon_check_eval.py` +
`eval/canon_check_fixtures.py` (16 fixtures, unit-tested scoring logic in
`tests/unit/test_canon_check_eval_metrics.py`, 11 tests green).

**Fixture design:** all 16 fixtures use a fixed snapshot (`Alice`, `status=gone`,
`from_order=3_000_000`) and all contain the literal name "Alice" so the symbolic pre-filter
always flags a candidate — the judge, not the filter, is what's being scored. 10 fixtures are
expected `False` (should NOT flag — flashback, dream, metaphor, counterfactual, quoted document,
reported memory, **narrated/explained revival**, name-collision with a different person, twin
sibling, sarcasm) and 6 are expected `True` (should flag — plain present-tense action/dialogue/
conflict with no explanation, across easy and hard phrasings). `False` outnumbers `True`
deliberately: for a hard-block gate, a false positive (blocking legitimate writing) is the
costlier failure mode than a false negative, so the fixture set stresses precision more than
recall.

## Results

| Model | Accuracy | Precision | Recall | Inconclusive | Confusion (tp/fp/tn/fn) |
|---|---|---|---|---|---|
| **Gemma-4 26B QAT** (`019ebb72-27a2-72f3-a42d-d2d0e0ded179`) | **93.75%** (15/16) | 0.857 | 1.0 | 0 | 6/1/9/0 |
| **Qwen3 35B** (`019dc738-a6b7-7bff-b953-b47868ae7db0`) | 87.5% (14/16) | 0.75 | 1.0 | 0 | 6/2/8/0 |

Both runs used composition's proven degrade-safe defaults (`reasoning_effort: none`, thinking
disabled, `max_tokens: 1024`, `temperature: 0.0`), $0 local models via LM Studio through
provider-registry (BYOK), real Neo4j-shaped snapshot (in-memory, no DB write needed since
`check_extraction_canon` takes a snapshot dict directly).

**Both models have PERFECT recall (6/6)** — neither ever misses a real continuity error across
the 6 positive fixtures, including the two "hard" unexplained-revival phrasings that were
inconsistent in the original POC's ad-hoc testing. This is the safer failure mode for a
hard-block gate.

**The "stronger" model (Qwen3 35B, larger parameter count) performed WORSE than the smaller
baseline (Gemma-4 26B QAT) — a genuinely counter-intuitive result, not a rerun-noise artifact**
(both fixture sets and configs were identical; verified by re-reading each model's `why` field).
Both models miss `name_collision_new_person` (flagging "Alice Chen" — a different, surnamed
person — as a contradiction); Qwen3 35B additionally misses `explained_revival` (flagging a
narrated necromancer resurrection as a contradiction, when it is legitimate new canon per the
precedent already documented in `entity_status.py`'s "gone→active is advisory, never a
standalone hard gate" note). Reading both `why` fields: both models reason correctly about
*physical presence* ("she is acting, therefore alive") but neither reliably reasons about
*identity distinctness* (name-plus-surname ≠ same entity) or *narrative framing* (a revival
narrated in the text is new information, not an extraction error) — this looks like a
class-of-failure specific to smaller/quantized local models' handling of pragmatic inference,
not a capacity difference between these two specific checkpoints.

## Conclusion

**Recommendation: wire `check_extraction_canon` using Gemma-4 26B QAT, as a quarantine/review
gate (not a hard block), not Qwen3 35B.** Rationale:
- Perfect recall on both models means the gate will never silently let a real continuity error
  through — the core value proposition of moving Knowledge extraction off `none`-strictness holds.
- Gemma-4 26B QAT's 1-in-16 false-positive rate is a defensible cost for a **quarantine+review**
  strictness tier (per the Narrative Forge Universal Gate Taxonomy) — an author/reviewer sees one
  extra false alarm per ~16 gone-entity mentions, not a silent corruption. It should NOT be wired
  as a **hard-block** without a human-review step, given precision is 85.7%, not ~100%.
  Recommended taxonomy tier: `quarantine+promote` (same tier as Enrichment's H0 invariant), not
  `hard-block`.
  - Qwen3 35B is both slower (35B vs 26B-effective-4B-active MoE) and less accurate here — no
    reason to prefer it for this task.
- Not tested: gpt-4o (`019eadbe-8027-77f2-af80-35e71c71cba5`, real per-token cost) as a ceiling
  comparison. Deferred — the local model already clears "good enough for quarantine, not hard
  block," so spending real money to find a possibly-marginal ceiling improvement wasn't judged
  worth it without an explicit ask. If wiring later reveals the 1-in-16 FP rate is too disruptive
  in practice, this is the next lever to pull.

## Follow-ups (tracked, not started this session)

- **D-KG-EXTRACTION-CANON-WIRE** — wire `check_extraction_canon` into `pass2_orchestrator.py`
  before `write_pass2_extraction` (Step 5), as `quarantine+promote` (flagged extraction is written
  but marked for review), not a hard block. Needs its own PLAN (touches the extraction write path).
- **D-CANON-CHECK-SDK-UNIFY** (carried over from the POC) — `canon_check.py` is still a deliberate
  near-duplicate of composition-service's file; unification into `sdks/python/` is appropriate once
  wiring lands, not before.
- The `name_collision_new_person` false positive (both models) suggests the symbolic pre-filter
  itself could be tightened later (e.g. don't flag when the matched span is immediately followed
  by a distinguishing surname/qualifier not in the entity's known aliases) — noted as a possible
  precision improvement independent of judge model choice, not pursued here since scope was
  judge-accuracy measurement, not filter refinement.
