# Intent-collection FSM — M1 (the machine)

**Size:** L · **Spec:** [`docs/specs/2026-07-28-intent-collection-fsm.md`](../specs/2026-07-28-intent-collection-fsm.md)
**Precondition:** SHIPPED — merge-on-re-plan (`dccf2393d`). The FSM may now write to `outline_node`
without the next re-plan deleting it.

M1 is the **machine + the instrument**. The gemma POC (metric A/B, the two arms) is M2 and consumes
what M1 records. Deliberately no conversational surface — spec §9.

---

## 1 · The three invariants this build must not break

These are the ones a passing unit test would not catch.

**I-1 · The FSM's slot list must be a SUBSET of what the re-plan merge carries.**
`OutlineRepo.INTENT_SLOTS` is the set `_lift_settled_intent` protects. If the FSM settles a slot
outside it — `pov_entity_id`, say — the next re-plan silently deletes it, which is exactly the bug
the precondition existed to prevent, re-introduced one layer up. **Asserted in code at import time
and tested.** This is why M1 does NOT ask the three entity slots even though spec §5 mentions POV:
the merge does not carry them yet, so asking would be a data-loss bug.

**I-2 · A slot name is never string-interpolated into SQL from anything but the frozen tuple.**
The apply step writes one column chosen at runtime. Membership-check against `INTENT_SLOTS` first,
then interpolate — never the reverse, never a value from the request.

**I-3 · `proposal_failed` is never silently dropped.** It is a recorded outcome with its own row in
the instrument. A run that omits its failures reports an acceptance rate it did not earn (spec §8,
the `empty`-counted-as-degrade shape).

---

## 2 · States (spec §4, made concrete)

```
opened ──propose──▶ proposing ──▶ awaiting_author ──answer──▶ applying ──▶ advanced ──propose──▶ …
                        │               │                                      │
                        ▼               └── decline ⇒ applies "absent" ────────┤
                  proposal_failed ──skip──────────────────────────────────────▶┘
                                                                          (no slots left) ⇒ done
```

`advanced` is a REAL state, not a transient: it is the resting point between two slots where no LLM
call is in flight and no author is blocked. Making it real is what keeps **every LLM call on exactly
one route** (`propose`), so cost is visible per call instead of hidden inside `answer`.

`answer` takes a closed-set `action`: `accept · revise · decline`. All three WRITE — decline writes
the `absent` marker, which is an authored statement (spec §6), not a no-op.

## 3 · Build order

| # | slice | why this order |
|---|---|---|
| 1 | DDL: `intent_run` + `intent_slot_record` | everything else needs the tables |
| 2 | `slots.py` — the slot registry (constraint class, type, writer cast) | the FSM and the prompt both read it; I-1 asserted here |
| 3 | `repo.py` — optimistic `transition` + record insert | copied shape from `glossary_build/service.py` |
| 4 | `engine.py` — ONE call, ONE retry, N candidates | copied bound from `glossary_build/engine.py` |
| 5 | `service.py` — the FSM | the whole point |
| 6 | router + deps | the surface |
| 7 | tests: unit (FSM transitions, I-1, I-2) + DB-gated (apply lands on the node) | the EFFECT gate |

## 4 · What the instrument records (spec §8)

One `intent_slot_record` row per slot VISITED — including failed and declined ones:
`slot · position · constraint_class · arm · candidates · verdict · author_value · applied_value ·
outcome · llm_calls · retried`.

`applied_value` is read back from the node AFTER the write, not echoed from the request — metric B
(`exact`/`drifted`/`dropped`) is only meaningful if the "applied" side is what the DB actually holds.

## 5 · Out of M1

- The conversational surface (spec §9)
- Scene runs (Q2 arm) — the machine is node-generic, so a scene run is a parameter, not new code
- Re-opening a settled slot (Q3) — not answerable until prose exists
