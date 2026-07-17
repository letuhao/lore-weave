# PlanForge — deterministic protagonist/cast injection (A1)

> **Status:** build-ready spec (design). Part of the PlanForge-v2 Proposer-Grounding track
> (`docs/plans/2026-07-17-planforge-v2-grounding-track.md`). **Highest-value item** — the reliable way
> to make grounding actually improve cast continuity, since the A/B eval proved prompt-grounding alone
> does not (`docs/reports/2026-07-17-propose-blind-ab-eval.md`).

## 1 · The problem (measured)
A grounded LLM propose does NOT reference the book's existing cast: with a character-less braindump the
model emits no characters, and `normalize` pads a single `Nữ chính` placeholder (`propose_llm.py:53-59`
`_pad_traits_from_analyze`; `normalize.py:39,45`). Prompt-grounding (the EXISTING STATE block +
CONTINUITY rule) *references* entities the model already writes about, but does not make it *invent* a
cast from the existing names. Result: cast continuity 0/3, grounded == blind.

The rules path already solved the analogous problem deterministically: `merge_existing_into_spec`
(`existing_state.py`) carries an existing character's `glossary_entity_id` onto a NAME-matched proposed
character. But it only fires when the model ALREADY produced the matching name — which it doesn't.

## 2 · The fix — inject, don't just annotate
When grounding is effective AND the book has an existing protagonist/cast, **seed the existing
protagonist directly into `layers.characters`** (name + `glossary_entity_id`), deterministically, so
continuity does not depend on model compliance. This is the same philosophy as the rules-path merge,
extended from *annotate-if-present* to *inject-if-absent*.

### 2.1 Where — a new step in the existing merge
Extend `merge_existing_into_spec(spec, existing)` (`existing_state.py`) with an INJECTION pass, run
AFTER the current annotate pass:
- Let `proposed = spec["layers"]["characters"]`.
- Let `existing_names = {c.name.casefold() for c in existing.cast}`.
- **Protagonist anchor:** find the proposed protagonist (role=="protagonist", else `characters[0]`).
  - If its name is a PLACEHOLDER (`Nữ chính`, `[TBD]`, `char_main`, empty) AND `existing.cast` is
    non-empty → **replace its name with the existing protagonist's name + set `glossary_entity_id`**.
    The existing protagonist = `existing.cast[0]` (the roster's drain order; A3 later makes this
    mention-ranked — until then, first is a reasonable default, and the injection is capped to 1).
  - If its name already matches an existing cast name → the annotate pass already carried the id (no-op
    here).
- **Do NOT flood the roster:** inject only the single protagonist anchor by default (config
  `PLANFORGE_INJECT_CAST_MAX`, default 1). Injecting N existing side-characters risks contradicting the
  braindump's own new cast; the protagonist is the highest-value, lowest-risk anchor. A later iteration
  (gated on measurement) can raise the cap.
- **Cold-start / no existing cast → no-op** (scenario-1 stays byte-identical).

### 2.2 Interaction with normalize's `Nữ chính` padding
`_pad_traits_from_analyze` pads `{name: "Nữ chính"}` when the model emitted zero characters. The
injection runs on the spec AFTER `normalize_spec` (same point the current merge runs — `propose_llm.py`
`materialize_from_analyze` calls `merge_existing_into_spec(spec, existing)` last), so it sees the padded
placeholder and REPLACES it. Order is load-bearing: inject after pad, never before.

### 2.3 Trait handling
Keep the injected protagonist's `traits` from whatever the model produced (or empty) — do NOT fabricate
traits from the glossary (the KAL roster has none; A3 may add them). The NAME + entity_id is the
continuity signal; traits are the model's to write. This respects "absent ≠ invented".

## 3 · Config (SET boundary)
- `PLANFORGE_INJECT_CAST_MAX: int = 1` — deploy-tunable ceiling on how many existing cast to inject.
  Rides the existing `ground_on_existing` effective-AND (no injection when grounding is off). Not a
  per-user knob — it is a platform tuning constant for the rollout.

## 4 · Acceptance criteria
1. A grounded propose on a book with an existing protagonist yields
   `layers.characters[0].name == <existing protagonist name>` and `glossary_entity_id` set — even when
   the model emitted only the `Nữ chính` placeholder. (Unit test over `merge_existing_into_spec` with a
   placeholder-only spec + a non-empty `existing.cast`.)
2. A grounded propose where the model ALREADY named an existing character keeps it + carries the id
   (the current annotate behaviour — no double-injection, no duplication).
3. Cold-start (empty `existing.cast`) → byte-identical to today (no injection).
4. `PLANFORGE_INJECT_CAST_MAX=0` disables injection (escape hatch), annotate still runs.
5. **Live smoke:** a grounded LLM propose on book 019f6555 now contains "Diệp Vấn Vũ" (or Elara/Void) in
   `layers.characters` where blind contains only `Nữ chính`.
6. **The A/B re-eval (B1) shows grounded cast continuity > blind** — the whole point.

## 5 · Test + rollout
- Unit: `merge_existing_into_spec` injection (placeholder→existing, already-named→annotate-only,
  cold-start no-op, cap=0 disables, cap=1 injects one).
- Live smoke on the running stack (ceiling ON) — grounded vs blind character list.
- Then run B1 (char-rich braindump A/B). If grounded beats blind → flip the ceiling.

## 6 · Risk / size
M–L. Contained to `existing_state.merge_existing_into_spec` + a config constant + tests. No schema, no
new service, no provider call. Risk: over-injecting could fight the braindump's own cast — mitigated by
the default cap of 1 (protagonist only) + the measurement gate before raising it.
