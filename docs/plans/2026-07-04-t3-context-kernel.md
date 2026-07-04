# T3 — Planner/Compiler Context Kernel (`sdks/python/loreweave_context`)

> **STATUS (2026-07-04):** T3.1 ✅ committed `6ac653ec4` (kernel + `build_system_message`
> renderer, unifies the two A1 ladders; 7 golden + 926 chat green + live-smoked). T3.2 ✅
> DONE + tested (13 kernel + 927 chat green + live-smoked) — the code landed **inside**
> `53adb22ee` (a concurrent agent's `git add -A` on this shared branch swept my staged T3.2
> files into its "notifyevent" commit; content verified intact). T3.2 = kernel `budget.py`
> (`compute_target` moved out of chat's `token_budget`, re-exported) + `plan.py`
> (`CompilePlan` + `Planner.plan()`, the swappable policy seam) + `_emit_chat_turn` wired to
> `_PLANNER.plan()`. **T3.3a ✅ DONE (see COMMIT):** the script-aware token estimator
> (`estimate_tokens`/`estimate_messages_tokens`) moved into the kernel (`loreweave_context.tokens`;
> chat's `token_budget` re-exports it) — the foundational budget primitive compaction needs.
> 16 kernel tests + 926 chat green (byte-identical) + live packaging check. **T3.3b ✅ DONE
> (see COMMIT):** `compaction.py` (tiered clear→summarize→truncate + T6/D6 breadcrumb/
> recovery-hint) moved to `loreweave_context.compaction`; chat's module is now a re-export
> shim (stream_service, sessions router, compact_service, tests unchanged); added a
> `CompactionStrategy` swappable class (the compaction analogue of the Planner seam). The
> summarizer stays INJECTED so no chat dep leaks into the kernel — provider-gate clean. 45
> chat compaction + 926 full green (byte-identical). **NEXT: T3.4** (package + voice/roleplay
> consumer + retire the byte-copy coupling), then the optimization-hypothesis A/B sweep.

**Spec:** `docs/specs/2026-07-03-context-budget-law.md` §5 (Planner/Compiler), §12 (kernel),
A1 (assembly surface), row T3. **Goal:** extract the scattered prompt-assembly + planning
logic out of `chat-service/stream_service.py` into a shared, **behavior-preserving**
(byte-identical) kernel — so (a) the twice-built system prompt (A1 footgun) has ONE source of
truth, (b) roleplay/composition can reuse it, and (c) — the payoff the user asked for — the
**Planner policy becomes a swappable seam we can A/B different optimization hypotheses against**
via the quality-gate harness, then choose the winners.

## Design (from §5 + §12)

- **`Planner.plan(state, intent, budget) → CompilePlan`** — POLICY. Which blocks, grounding
  yes/no (T5), retrieval mode (D1), task_weight (D3/T2), tool seed (D8). This is the knob-turning
  surface. *The optimization testbed.*
- **`Compiler.compile(plan, state) → CompiledContext`** — MECHANISM. Render the ordered block
  list (two ways: Anthropic cache-dict vs plain-string), run compaction. Deterministic.
- **`CompactionStrategy`** — the tiered clear→summarize→truncate (already in
  `compaction.py`; move under the kernel).
- Kernel imports **no provider SDK** (provider-gate clean); LLM/embeddings are injected ports.

## Slices (incremental, each byte-identical + suite-green)

- **T3.1 — Unify the system-message ladders (THIS slice).** New `loreweave_context.build_system_message`
  reproduces BOTH inline ladders (`stream_service.py` cache path ~2088–2129 + plain path
  ~2131–2161) from one ordered `tail_blocks` list. Golden test pins byte-identical output across a
  present/absent × cache/plain matrix. Kills the A1 "add a block in two places" footgun. Establishes
  the kernel package. *Lowest risk, clearest win, no policy change.*
- **T3.2 — CompilePlan + Planner.** Lift the inline decisions (T5 grounding gate, task_weight,
  block-inclusion flags, tool seed D8) into a `CompilePlan` dataclass + a `Planner.plan()` pure
  function. chat computes `state`, calls the planner, consumes the plan. Byte-identical (same
  decisions, relocated). **This is the seam the optimization A/B plugs into.**
- **T3.3 — Compiler.compile + CompactionStrategy.** Move `compact_messages`/breadcrumb under the
  kernel; `Compiler.compile` orchestrates render + compaction. chat wires the ports.
- **T3.4 — Package + second consumer.** `pyproject` include; wire the voice path (A1 note 2) and
  confirm roleplay/composition can consume. Retire the byte-copy coupling.

## After T3 — the optimization testbed (the user's "build+test all hypotheses, choose optimize")

With `Planner.plan()` isolated, A/B candidate policies through the quality-gate harness
(`scripts/eval/run_quality_gate.py`) + blind judge, each a swap of the plan function:
- task_weight computation (binary grounding flag → richer signal; per-intent bands).
- grounding threshold / retrieval-mode-by-tier (D1 pull mode for strong models).
- block-inclusion under budget pressure (drop low-value skills first).
- compaction aggressiveness (target caps per model window).
Keep the winners (flip defaults with evidence, as T2 did); discard the rest. The kernel makes
each hypothesis a one-function change with a measured verdict, not a stream_service surgery.

## Safety

Golden test FIRST each slice (capture current output → refactor → assert identical). The
existing chat suite exercises assembly end-to-end; byte-identical ⇒ green. Provider-gate must
stay clean on the kernel. No behavior/quality change lands under T3 — optimization is a
SEPARATE, measured step on top.
