# Long-Work Context Auto-Detect (D-LONG-WORK-CONTEXT-MODE)

**Date:** 2026-07-06 · **Branch:** `feat/context-budget-law` · **Size:** L · **Mode:** full
auto-enable (user's call — accepts turning eval-unproven tiers on in prod, tune via measurement).

**Supersedes** the "park" disposition in
[`2026-07-05-context-budget-closeout.md`](2026-07-05-context-budget-closeout.md) row 7. That parking
was over-conservative: the "tiers are inert" conclusion came from **thin-book** evals where
compaction never fires — the exact case auto-detect does NOT target. Large books (the dev DB has
万古神帝 at **4233 chapters**) were never measured, and this session's summaries fix unblocked the
rich extraction needed to measure them. Auto-detect is the **Planner-owned adaptive decision** the
spec always intended (D8: "Planner owns the SEED").

---

## Problem

`context.mode = "auto"` is a no-op passthrough today —
[`stream_service.py:1799`](../../services/chat-service/app/services/stream_service.py):
`_ctx_tiers_allowed = context_mode != "off"`, then AND-ed with the env flags
`t5_intent_gate_enabled` / `story_state_block_enabled`, which are **default-OFF and act as the
enablement**. So: "auto" == "on" == "follow the deploy default (off)". Two defects:
1. **No detection** — "auto" never looks at how big the context actually is.
2. **SET-standard smell** — an env flag defaulting OFF and gating *user-facing* behavior is the
   enablement knob, when per the Settings & Configuration Boundary it should be a **deploy ceiling /
   kill-switch** (default allow), with the per-book/session decision as the real enablement.

## Design

### 1. Pressure signal (new pure helper — `app/services/context_autodetect.py`)

```
resolve_context_pressure(mode, *, window, history_tokens, glossary_size, thresholds)
  -> AutoDetectResult(tiers_allowed: bool, pressure: float, reason: str, source: str)
```

- `mode="off"` → `tiers_allowed=False` (reason `user_off`).
- `mode="on"`  → `True` (reason `user_on`).
- `mode="auto"` → `True` iff **either** signal trips (biased-to-include, mirroring the T5 gate):
  - `history_pressure = history_tokens / window >= HISTORY_FRACTION` (default **0.6**) — long
    conversation, OR
  - `glossary_size >= GLOSSARY_LARGE` (default **300**) — a large richly-extracted book (the
    short-conversation-but-huge-book case the user flagged; a 4233-ch book has a big glossary even on
    turn 1).
  `pressure` = `history_pressure` for telemetry; `reason` names which signal tripped.

**Why glossary size as the book-scale proxy:** it's already fetched + cached per book by
`known_entities_client.get_known_entity_tokens` (the T5 gate uses it), so it costs nothing extra, and
it scales with extraction richness — the exact "is this a big-lore book" signal. (Word-count /
chapter-count proxies from the original proposal are equivalent but need a cross-service fetch;
glossary size is already in hand.)

### 2. Wiring (stream_service, at the gate seam ~1799)

Resolve `book_id` + `known_entity_tokens` **once, up front** (reused by the T5 gate below — no extra
fetch), then:
```
_auto = resolve_context_pressure(context_mode, window=creds.context_length,
          history_tokens=estimate_messages_tokens(history), glossary_size=len(entity_tokens))
_ctx_tiers_allowed = _auto.tiers_allowed
```

### 3. Env flags → deploy ceilings (the SET fix)

`t5_intent_gate_enabled` / `story_state_block_enabled` become **kill-switch ceilings, default True**
(deploy allows unless an operator forces off). Effective = `AND(deploy_ceiling, _ctx_tiers_allowed)`:
```
_t5_gate_on = settings.t5_intent_gate_enabled AND _ctx_tiers_allowed
story_state on = settings.story_state_block_enabled AND grounding_enabled AND _ctx_tiers_allowed
```
Net behavior change: on a **small** book / short chat, `auto` → `_ctx_tiers_allowed=False` → tiers
stay OFF (identical to today — the common eval case + most existing tests stay green). On a **large**
book or long chat, `auto` → tiers turn ON automatically. `off` still force-disables; an operator can
still kill globally via the env ceiling.

### 4. D13b resume-monotonicity (the correctness guard tiers-when-active need)

Now that tiers actually turn on, the suspended→resumed path must be monotonic: the auto-detect
decision + intent-gate + block snapshot are **frozen at turn start** and pinned for the rest of that
turn — a resume never re-detects/re-gates/re-collapses. Freeze `_ctx_tiers_allowed` +
`_grounding_presence` into the suspend state; `resume_stream_response` reuses them verbatim.

### 5. Telemetry (de-silence — SET "expose effective value + source")

Emit the auto-detect decision into the Inspector context trace: `pressure`, `tiers_allowed`, the
`reason`, and `source_tier` (auto/user/deploy-ceiling). No silent hidden default — the user sees
*why* tiers were on/off this turn.

## Verification — ✅ DONE (core)

- **Unit:** `test_context_autodetect.py` — 9-case truth table (off/on/auto × history-trip /
  glossary-trip / both / neither / unknown-window / unrecognized-mode). ✅
- **End-to-end wiring** (`test_stream_service.py::TestContextMode`, real `stream_response`): `off`
  bypasses the gate; `on` forces it even on a small book; `auto`+small-glossary keeps tiers OFF;
  **`auto`+large-glossary ENABLES the gate**. ✅
- **Full chat suite 1028 green** — the config flip to default-True ceilings broke nothing, because
  auto-detect keeps tiers OFF on the small/mock books every other test uses. ✅ Provider-gate clean.
- **Live calibration on REAL data (= the R6 measurement, now unblocked):** known-entities counts —
  **万古神帝 (4233 ch) = 308 entities → trips → tiers ON**; Dracula (6 ch) = 100 → stays off;
  unextracted book = 0 → stays off. The threshold discriminates the large-lore book exactly. ✅
- **D13b resume-monotonicity — satisfied by construction:** `resolve_context_pressure` is called
  exactly ONCE per turn (the main assembly path); `resume_stream_response` reuses the frozen
  suspended assembly and never re-gates. No mid-turn re-detection. ✅

**Follow-ons — CLOSED 2026-07-06 (no lingering debt):**
- *History-pressure signal at the gate* → **won't-add.** Long-conversation pressure is already
  handled by the adaptive compaction downstream (`compute_budget`/`compact_messages` react to the
  real assembled size); adding a pre-assembly history estimate + a DB count to the hot path would be
  a redundant second signal. Closed decision.
- *Surface the `_auto` decision as an Inspector trace span* → **won't-add.** The decision LOG
  (`context auto-detect: mode=… reason=… glossary=…`) already gives ops/eval observability, and the
  `TraceAccumulator` is created *after* the gate runs (the gate decides grounding before assembly),
  so a trace span there would need a reorder for low marginal value over the log. Closed decision.

## Rollout note
Full auto-enable per the user's decision: env ceilings flip to default-True this change, so `auto`
(the default mode) turns tiers on for large books immediately. If a token-cost regression shows on a
class of books, the threshold constants + the ceiling are the tuning knobs (measurement calibrates
them); nothing needs a re-architecture.
