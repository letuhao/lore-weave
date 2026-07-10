# Deterministic capability sweep — 116 tools, no LLM, no spend

**Date:** 2026-07-10 · **Track D · WS-D3 / ND3** · `scripts/eval/tool_liveness/sweep.py`

## The idea

The CD4 ship gate blocks on **`executes`** — *"does this tool work when called correctly?"*
That question **does not need a model.** Only `proven` (G1–G4 under a real LLM) does.

    NL probes  → `proven`   expensive · one model turn each · yields the F5 selection signal
    THIS sweep → `executes` cheap · MCP-direct · finds BROKEN tools

So the gate's blocking predicate can be populated over the whole catalog for free. The
manifest went from **10 tools → 119**.

## Safety — why calling ~116 real tools is allowed

| tier | n | swept? | why |
|---|---|---|---|
| **R** | 70 | ✅ | reads |
| **W** | 48 | ✅ | mints a `confirm_token` and writes **nothing** at call time; never redeemed |
| **A** | 83 | ❌ | auto-commits. `settings_update_profile` would mutate the real account; `memory_forget` would delete rows. Needs authored, fixture-scoped args. |
| paid | 5 | ❌ | a capability probe must never spend the user's money |

Everything ran against a throwaway fixture, torn down after. No probe addressed an id it
did not create.

## Result

    executes=true   57      proven to work when called correctly
    executes=false   0      (after the fix below)
    executes=null   62      inconclusive — never blocks

## The bug it found: `settings_get_profile` had **never worked**

```
validating tool output: validating root: validating /properties/profile:
type: map[...] has type "object", want one of "null, array"
```

Reproduced directly against provider-registry — no gateway, no LLM, **empty arguments**.

**Root cause.** `getProfileOut.Profile` was `json.RawMessage`. That type is `[]byte`, so the
Go MCP SDK infers its output schema as `["null","array"]` — while `encoding/json` marshals
it as the raw JSON it *holds*, an **object**. The SDK validates the tool's own output
against its own declared schema and rejects it. **100 % of calls, for every user, since the
tool was written.**

Its twin **`settings_update_profile`** is broken identically. The sweep could not call it —
it is Tier A — but the declared schema proves it: `profile.type = ["null","array"]`. Found
by reasoning from the root cause, not by probing.

**Why nothing caught it.** Every wire gate in this repo asserts over `tools/list`
**metadata**. Not one issues a `tools/call`. And no NL probe covered the settings domain.
A tool can be fully tiered, correctly scoped, schema-mirrored, drift-locked — and still
fail every single call.

**Fix + gate.** Both fields become `map[string]any`.
`TestSettingsMCP_NoOutStructUsesRawMessage` walks the package AST and fails on any
`*Out` struct with a `json.RawMessage` field. It asserts on the **Go type**, not the
schema: a genuine slice (`[]webSearchSource`) *also* declares `["null","array"]` and
correctly marshals as an array — the schema shape cannot tell them apart, the type can.
(My first attempt got this wrong and flagged four healthy tools. Negative-controlled: a
temp `Out` struct with a `RawMessage` field reds it; removing it greens.)

## The mistake I nearly shipped

The **first** sweep reported **11 broken tools**. Ten were my own bad arguments:

```
badly formed hexadecimal UUID string     ← I passed "tle-sweep" where a UUID was wanted
unknown kind: tle-sweep                  ← I passed a placeholder kind-code
no live genre with that code in this book
world_id is not a valid id: 'tle-sweep'
```

Had I fed that to the manifest, the CD4 gate would have **blocked ten healthy tools** from
every workflow and hidden them from `tool_list` — the exact false-block the three-valued
`executes` exists to prevent, defeated by a sloppy classifier.

Two fixes, and the second matters more than the first:

1. **Refuse to call what you cannot supply.** `fill_args` returns `None` for an id/uuid/
   reference-code with no fixture value. Not calling is the safe move: a placeholder id
   produces a lookup failure that says nothing about the tool.
2. **A widened caller-fault regex must not swallow the real bug.**
   `test_sweep_classifier_still_catches_the_real_bug_it_was_built_to_find` pins the exact
   `settings_get_profile` output-validation message as `executes: false`, alongside eight
   observed caller-fault messages pinned as `null`. Widen the regex all you like — that
   test says whether you widened it too far.

## Also found: 3 untiered tools on the federated wire

`tool_list`, `tool_load`, `find_tools` carried **no `_meta` at all**, so `tool_tier()`
silently defaulted them to `R`. Correct by luck — they are pure disclosure — but it is the
exact silent-default hole the per-service wire gates exist to close. They are
**consumer-local**, so no domain service's gate ever covered them. Now declared
`tier: R, scope: none` in lockstep (ai-gateway `find-tools.ts` + chat-service
`tool_discovery.py`). The federated catalog is now **100 % tiered**.

## What `executes: null` means here

62 tools are inconclusive, mostly because a required arg is an id or a reference-code the
fixture cannot supply (`motif_id`, `world_id`, `run_id`, `kind`, `slug`). They are **not**
blocked and **not** hidden. Closing them is the P1 grind: authored args per tool, which is
also what unlocks Tier-A capability probing.

## Reproduce

```bash
python -m scripts.eval.tool_liveness.sweep                  # dry run: the plan + safety split
python -m scripts.eval.tool_liveness.sweep --execute --date <date>
python -m scripts.eval.tool_liveness.manifest \
    docs/eval/tool-liveness/<date>/matrix.json \
    docs/eval/tool-liveness/<date>-sweep/sweep.json
```

The manifest writes `contracts/tool-liveness.json` plus the two service copies; a drift
lock in each service reds if they diverge.
