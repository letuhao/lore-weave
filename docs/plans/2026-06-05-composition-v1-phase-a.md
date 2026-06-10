# Composition V1 — Phase A PLAN (evidence-backed core, validate-first)

> **From** [`2026-06-05-composition-v1-reasoning-engine.md`](../specs/2026-06-05-composition-v1-reasoning-engine.md) §8 Phase A + §9 D1–D6 (locked).
> **Goal:** build ONLY the evidence-backed core, **eval-gated at each slice** — prove it beats the V0 `Retrieve→Draft→Critique` loop on **our local models** before any Phase-B recipe library / ledger. If a slice doesn't beat V0, stop and rethink.
> **Boundary:** composition-service (engine) + knowledge-service (KG reads, A2 only) + the eval harness. lore-enrichment NEVER. Additive.

## Slices (each = its own VERIFY + eval-gate + COMMIT)

### A1 — `diverge → converge` (internal selection) — THE highest-yield (F3)
The single most evidence-backed addition (Re3 rerank: +14% coherence). Generalize the §8.2 "takes" into an **internal, auto-scored** selection.

**Build (composition-service):**
- `engine/select.py` (new):
  - `async diverge(packed, profile, operation, k, drafter) -> list[Candidate]` — **K parallel non-stream completion jobs** via the loreweave_llm SDK (reuse `cowrite.build_messages`; completion not stream — we don't show tokens, we pick). Each `Candidate = {text, metering}`. Fan-out with `asyncio.gather`, per-job timeout + graceful degrade (≥1 candidate or error).
  - `async score(candidates, rubric, judge) -> Ranked` — a **rerank LLM call** (judge ranks K candidates for `coherence + premise/canon relevance`, the Re3 rubric; reuse the `eval_client`/`judge_prose` infra + the `messages[0].content` extractor lesson). Returns ranked + the winner. Tolerant parse (fence-strip + filter, like the critic).
- `engine.py`: a new **auto draft path** — `POST /generate` gains `mode: 'cowrite'|'auto'` (Literal, 422-pre-stream per the M6 enum lesson). `auto` = pack → `diverge(k)` → `score` → return the winner as a `generation_job` result (NOT an SSE stream — a job with the winner text + the K candidates retained for transparency). Co-write path unchanged.
- **Adaptive K (D3):** A1 ships **fixed K** (config `compose_diverge_k`, default 3) + a `# TODO(A3): derive K from beat structural weight + tension`. Adaptive needs A3's decompose output → deferred to A3, noted now so the interface (`k` param) is already in place.
- **Cost guard (D1/H2):** `score`/canon-check run on the **winner only**; `diverge` is the only K-multiplied call. Budget pre-check (§5) covers K candidates up front.

**Eval-gate A1:** harness compares `auto K=3 + rerank` vs `cowrite K=1` (V0) on a fixed scene set → judge `coherence` (disjoint-judge median, the KS lesson). **Ship A1 only if K=3 ≥ K=1.** Reuse `loreweave_eval` + the host-orchestrated re-judge pattern (avoid container OOM).

**Files:** `engine/select.py` (new) · `routers/engine.py` (mode enum + auto branch) · `clients/eval_client.py` (rerank prompt) · `config.py` (`compose_diverge_k`) · tests + 1 eval script. **No schema.** No knowledge-service touch.

### A2 — `check → revise vs KG` (the canon differentiator, F4)
**Build:**
- `engine/canon_check.py` — (1) **SCORE-style symbolic guard** (D2 primary): pull the winner's entities → query knowledge-service for status/timeline → pure-code contradiction flags (item `active` after `lost`; event before its predecessor). (2) **LLM-judge canon-check** on the winner only (ConStory taxonomy rubric) for the semantic residue. Emit `violations[{span, type, evidence}]`.
- knowledge-service: a thin **fact-for-check** read (entities + status + timeline for a set of entity ids, project-scoped) — extend the existing internal context API, not a new service.
- `engine.py` auto path: `diverge→converge→ check → reflect(revise ≤N)`; **HARD gate** (D4) = canon-fact contradiction + spoiler-leak only → revise; still failing → flag.

**Eval-gate A2:** canon-consistency dimension lift vs A1 (no-check). Ship if it raises canon-consistency without tanking coherence.

### A3 — detailed `decompose` (F5) + adaptive K
**Build:** a planner (`engine/plan.py`) producing beats with `intent + tension + present_entities` (structured output, reuse extraction pattern) → richer `outline_node`. Wire **adaptive K** = f(beat function, tension) from A1's `k` hook. Eval-gate: coherence lift from tighter upstream constraints (the DOC result).

## Sequencing + checkpoints
A1 → eval-gate → COMMIT → A2 → eval-gate → COMMIT → A3 → eval-gate → COMMIT. **Human checkpoint after A1's eval** (does the core thesis hold on our models?) before A2/A3. Each slice is M–L, cross-service only at A2.

## Open / risks
- **Local-LLM cost:** K parallel completions on LM Studio — measure A1 wall-clock; if K=3 is too slow, the eval still tells us if it's worth it (quality vs time).
- **rerank reliability:** a weak local judge may rerank poorly → A1 eval also validates the *judge*, not just diverge. If rerank ≈ random, F3's benefit won't show → that's a real finding, not a bug to hide.
- **A1 has no schema + no knowledge-service touch** → lowest-risk first build, fastest to the first eval-gate (the validate-first payoff).
