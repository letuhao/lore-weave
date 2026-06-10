# FD-1 / narrative_thread S2 — the OPEN-detection producer

> **Roadmap:** [feature-debt](2026-06-09-feature-debt-roadmap.md) FD-1 → reshaped (PO 2026-06-09) to **build the full narrative_thread feature (070), sliced**. **This cycle = S2 (producer) only.** S3 (re-injection) + S4 (debt-check + eval) are follow-on cycles (XL-checkpoint pattern). **Size:** L. Composition-only.
> **Spec:** reasoning-engine §4d/§5.2/§6 (promise ledger; CFPG `(Foreshadow,Trigger,Payoff)`; `commit → update state (close promises)`).

## Why (the honest reframe)
The cy14 ledger is INERT (zero callers). The PO has repeatedly chosen to build it; "production-ready, no silent seams" says don't ship it half-built. So we build it properly, sliced. **S2 gives the ledger a real WRITER** tied to generation: a scene's commit opens new promises and pays existing ones. (S3 makes generation READ them; S4 checks unpaid debt + evals.)

## S2 scope — producer only
On the **auto-generate commit** (scene + chapter paths), after `run_canon_reflect`, run a **best-effort, config-gated** detection pass:
1. Fetch the project's current `list_open` threads.
2. One LLM pass over the just-generated prose + the open-thread list → structured `{opened:[{kind,summary,trigger}], paid:[thread_id]}`.
3. `open_thread(...)` each new promise (deduped); `update_status(id,"paid",payoff_node=node)` each paid.
4. Never fail generation (degrade-safe like canon-reflect F1).

### Design
- **New `app/engine/narrative_thread.py`** — `detect_and_update_threads(*, llm, repo, user_id, project_id, scene_text, opened_at_node, open_threads, drafter_source, drafter_ref, reasoning_effort) -> ThreadUpdateResult`. Mirrors `canon_reflect` LLM-call shape (SDK submit_and_wait, tolerant JSON parse per `feedback_llm_schema_tolerate_filter`).
- **New prompt** `narrative_thread_detect_system.md` — extract NEW opened promises/foreshadows/MICE-opens (Chekhov's gun planted) + which of the GIVEN open threads are now paid/progressed. Coarse V1 (`kind` ∈ promise/foreshadow/question/mice_thread). Anti-think prefix; local-LLM-first (gemma baseline).
- **Dedup:** the LLM is given the open list (avoid re-opening) AND a code-side fold (`_excerpt_key(summary)` vs existing open) so a re-gen doesn't duplicate. Bound new opens per scene (`narrative_thread_max_open_per_scene`, default 5).
- **Gate:** per-project `work.settings["narrative_thread_enabled"]` (default **false** — opt-in, cost control; an extra LLM call/scene). Disabled → no-op, zero cost.
- **Deps:** add `get_narrative_thread_repo` to `deps.py`; wire into the auto scene path + chapter path commit.
- **Pay match:** the LLM returns `paid` thread_ids drawn from the provided open list (ids are passed in); code validates each id is in the open set before `update_status`.

### Test plan
- detector unit (fake LLM): opens N threads with right kind/summary; pays a given open id; dedups a same-fold re-open; bounds at max_open; degrades to no-op on LLM error/malformed JSON (best-effort, never raises).
- wiring: gated off → detector NOT called (no cost); gated on → called once after canon-reflect; an exception in the detector does NOT fail the generate (best-effort).
- Single-service (composition); no live-smoke token needed. Optional: a real local-LLM detect smoke.

## Out of scope (follow-on cycles)
- **S3** — re-inject `list_open` into the pack (F2) so generation honors open promises; `compress`.
- **S4** — arc-end unpaid-promise debt check (§7) + an eval arm (dropped-promise-rate).
- Trigger-firing eligibility (CFPG executable predicates), MICE-LIFO enforcement, per-character belief state — deeper §5/§7, later.
