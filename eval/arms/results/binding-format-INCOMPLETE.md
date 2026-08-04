# CP-0.6 — binding-format measurement: **INCOMPLETE**, and committed as such

**Status: 2 of 5 arms ran. This is not a result, and no design decision may cite it.**

Committed because "the measurement did not complete" is itself an output, and an empty directory
records nothing. An absent file reads as *"not attempted"*; this reads as *"attempted, and here is
exactly how far it got and why it stopped"*.

## What ran

| arm | exact | n | note |
|---|---|---|---|
| `prose` — the value buried in conversational narration (how it reaches the model today) | 3/3 | 3 | |
| `labelled` — `chapter_id: <uuid>` under a PLAN STATE heading | 3/3 | 3 | |
| `binding` — named as a binding, with its producer | — | — | **not run** |
| `json` — structured plan with `emits`/`accepts` | — | — | **not run** |
| `decoy_control` — two ids present, the WRONG one mentioned more recently | — | — | **not run** |

## Why it stopped

`gemma-4-26b-a4b-it-uncensored-apex-quality` (LM Studio, the local target model) unloaded mid-sweep:
`{"error":"terminated"}`, after an earlier `llama-server did not become healthy: 503` on first load.
Two load attempts; the second succeeded and the model was evicted again during arm 3.

## Why 3/3 and 3/3 settle nothing

1. **The control never ran.** `decoy_control` is the only arm that separates *"the model read the
   binding"* from *"the model copied the one UUID in sight"*. Without it, both perfect arms are
   consistent with a model that ignores the plan entirely and copies the nearest identifier — which
   is exactly the behaviour the CP-3 projection has to rule out.
2. **`3/3` bounds a failure rate only at ≤63.2%.** Two arms at 3/3 do not distinguish formats; they
   fail to distinguish them, which is a different statement.
3. **It ran on ONE model.** The finding is about our target model, not about binding formats.

## What must happen before CP-3 uses this

Run all five arms including the control, at n ≥ 5, with the model pinned loaded for the duration
(`ARMS_TIMEOUT_S` is already generous; the constraint is LM Studio eviction, not the client).

    python eval/arms/binding_format.py --trials 5

Harness: `eval/arms/binding_format.py`. Grading is in code, on the argument actually sent — never on
prose, and never by asking a model whether the answer looks right.
