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

## Addendum (2026-07-06, same day) — a parsing bug found + fixed, and a sobering
## re-measurement of judge reliability

While wiring the gate into `pass2_orchestrator.py` and unifying both services' canon-check
modules into `sdks/python/loreweave_canon_check` (see `docs/plans/2026-07-06-canon-check-
wire-and-unify.md`), re-running this eval against the refactored (behaviorally-identical, per
16/16 + 19/19 passing unit tests on both services) code surfaced two real findings:

**1. A genuine, pre-existing parsing bug, found and fixed (affects BOTH services' original
implementations identically — not introduced by the refactor).** The verdict parser used a
naive `text.find("{") .. text.rfind("}")` span to extract the judge's JSON. Captured live: this
$0 local model sometimes "thinks out loud" and emits a first (wrong) JSON verdict, followed by
prose like `*(Self-correction: re-evaluating...)*`, followed by a corrected second JSON block.
The naive span swallowed the prose between the two blocks, produced unparseable text, and
silently discarded the model's own self-corrected (usually right) answer as a parse failure —
counted as `inconclusive`, not `wrong`, so it never surfaced as a scoring anomaly until traced
directly. Fixed in `loreweave_canon_check.base.parse_judge_verdicts` via a string-aware
brace-balanced scanner (`_balanced_json_objects`) that isolates each top-level JSON object and
takes the LAST one that parses as `{"verdicts": [...]}`, honoring a model's self-correction as
its final answer. 4 new regression tests (double-JSON-block, brace-in-quoted-string,
unterminated-JSON, prose-only) in `sdks/python/tests/test_canon_check.py`. This fix reduced
`inconclusive` from up to 9/16 (when the bug was triggered) to a clean 0/16.

**2. Even with the parser fixed, re-running the SAME 16-fixture eval against Gemma-4 26B QAT
three times in this later session gave a STABLE but LOWER score than the original single run:
68.75% accuracy / 33% recall / 66.7% precision (confusion 2/1/9/4)** — a clear regression from
the original 93.75%/100%/85.7% reading earlier the same day. Root-caused this is NOT a code
regression (verified via `debug_eval_repro.py`/`debug_eval_repro2.py`: the exact request dict
sent to the model is unchanged, confirmed identical field-for-field; the mocked-LLM unit tests
pass identically before and after the refactor). Reading the `why` text on the newly-wrong
verdicts is revealing: the model's own REASONING correctly identifies the contradiction
("Alice is portrayed as an active presence... contradicting her status as gone") but the
`violated` BOOLEAN it emits is `false` anyway — a genuine reasoning/output inconsistency in the
model itself, not a parsing or wiring defect. **Conclusion: this $0 quantized local model's
judge reliability is noisier session-to-session than a single eval run can show** — the
original 93.75% was a real but optimistic draw from a distribution that can score as low as
~69% (and recall as low as 33%) at other times, even at `temperature=0.0`. This reinforces
rather than undercuts the existing decision: wiring landed as `quarantine` (log-and-flag via
`job_logs`, never a hard block, see `D-KG-EXTRACTION-CANON-WIRE` below) specifically because
precision/recall could not be trusted at ~100%. Live-smoke through the REAL pipeline (not just
this eval harness) also observed the SAME single-fixture flip (`confirmed=False` then `=True`
across consecutive full-pipeline runs) — corroborating the eval, not an eval-harness artifact.
**Not pursued further this session** (diminishing returns per the POC's own established
discipline about not over-tuning hyperparameters) — flagged as a real open question for
whoever next revisits judge-model choice: a single eval run is not sufficient evidence of this
model's true reliability; report a RANGE from repeated runs, not a point estimate.

## Follow-ups

- **`D-KG-EXTRACTION-CANON-WIRE` — DONE (2026-07-06, see `docs/plans/2026-07-06-canon-check-
  wire-and-unify.md`).** `check_extraction_canon` is wired into `pass2_orchestrator.py` via
  `_maybe_run_canon_check_gate`, called right before `write_pass2_extraction`. Quarantine, not
  hard-block: a confirmed candidate is logged to `job_logs` (`event: pass2_canon_flag`, already
  wired to the Studio's JobLogsPanel); the write proceeds unconditionally regardless. Live-smoked
  end-to-end through the REAL pipeline (real Neo4j, real LLM, real `extract_pass2_chapter` call) —
  confirmed the log fires correctly on `confirmed=True`. New `list_gone_entities()` in
  `entity_status.py` builds the snapshot (no pre-existing "all gone entities" query existed).
- **`D-CANON-CHECK-SDK-UNIFY` — DONE (2026-07-06).** Hoisted the mechanical pieces (span-matching,
  verdict parsing, judge request shape, verdict application, base candidate fields) into
  `sdks/python/loreweave_canon_check`; both composition's and knowledge's `canon_check.py` are now
  thin per-service wrappers (prompt wording + candidate subclass + orchestration stay local). Also
  fixed knowledge's error-handling gap (adopted composition's `LLMError` + precise content
  extraction over the old bare-`except Exception` + manual indexing) and the double-JSON parsing
  bug described in the addendum above.
- The `name_collision_new_person` false positive (both models) suggests the symbolic pre-filter
  itself could be tightened later (e.g. don't flag when the matched span is immediately followed
  by a distinguishing surname/qualifier not in the entity's known aliases) — noted as a possible
  precision improvement independent of judge model choice, not pursued here since scope was
  judge-accuracy measurement, not filter refinement.
