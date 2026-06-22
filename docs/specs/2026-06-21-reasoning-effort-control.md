# Reasoning / Effort Control — Design Spec

**Status:** DESIGN COMPLETE — open questions (§4) resolved in the
[detailed design](2026-06-21-extraction-pipeline-detailed-design.md) §1 (RE-1…RE-5); build via the
[parallel plan](../plans/2026-06-21-extraction-pipeline-plan.md) lane **RE**.
**Date:** 2026-06-21
**Branch:** `feat/extraction-knowledge-architecture`
**Goal:** let users select reasoning **effort** (graded, not just on/off) and toggle **thinking**
from BOTH the chat GUI and via MCP tools, plus an inline `/no_thinking`-style command — with
one canonical vocabulary, model-capability-aware, resolved by a clear precedence.

---

## 1. Current state (the floor works; everything above is binary or broken)

| Layer | State | Reference |
|---|---|---|
| **Provider floor** | ✅ Graded. `forwardOptionalChatFields` forwards `reasoning_effort` (`none/low/medium/high`) + `chat_template_kwargs {thinking, enable_thinking}` to OpenAI / LM Studio / Ollama; strips unsupported fields for non-reasoning OpenAI models; flags o1/o3/Opus as thinking-capable. | provider-registry `adapters.go` `forwardOptionalChatFields`, `openaiIsReasoningModel`, `stripDefaultOpenAIUnsupportedFields` |
| **Effort helper** | ⚠️ Binary only. `thinking_llm_fields(enabled)` maps on→`{effort:medium, thinking:true}`, off→`{effort:none, thinking:false}`. **No graded effort.** Not centralized — composition-service hardcodes the same dict inline in 4 modules. | translation-service `llm_thinking.py`; composition `canon_check.py`/`compress.py`/`critic.py`/`eval_judge.py` |
| **Chat path** | ❌ **BROKEN.** `SendMessageRequest.thinking: bool` + `ChatSession.generation_params.thinking` are accepted and stored, but `_stream_via_gateway` **never forwards `thinking` to the provider**. The Think/Fast toggle is a **no-op** today. | chat-service `models.py`, `stream_service.py` |
| **Model capability** | ⚠️ Discoverable, unused. `capability_flags.thinking` / `extended_thinking` set for o1/o3/Opus/Sonnet; FE type has `capability_flags` but no UI reads it. | provider-registry `adapters.go`; frontend `ai-models/api.ts` |
| **MCP** | ⚠️ Inconsistent. Only translation-service tools expose `thinking_enabled: bool`. Not on glossary / knowledge / others. No effort granularity. | translation-service `mcp/server.py` |
| **GUI** | ⚠️ Binary. Session + per-message **Think/Fast** toggle; `ThinkingBlock` renders reasoning. **No effort selector, no capability gating.** | frontend `SessionSettingsPanel.tsx`, `ChatInputBar.tsx`, `ThinkingBlock.tsx` |
| **Inline command** | ❌ None. `/` in the input opens a prompt-template picker; no server-side directive parsing of message text. | frontend `ChatInputBar.tsx`; chat-service `routers/messages.py` |
| **Reasoning output** | ✅ Streamed (`ReasoningEvent` → AG-UI `REASONING_MESSAGE_CONTENT`) + rendered; stored in `content_parts` JSONB but not replayed. | chat-service `stream_service.py`; frontend `useChatMessages.ts` |

**Summary:** the hard part (provider passthrough + reasoning rendering) is done. What's missing
is a **unified, graded, capability-aware control surface** — and a wiring fix so the existing
toggle actually does something.

---

## 2. Design

### 2.1 One canonical vocabulary

Define a single effort enum used at every layer (API, chat, MCP, SDK, UI):

```
ReasoningEffort = "none" | "low" | "medium" | "high"      # (+ "max"/"xhigh" later if a model exposes it)
```

- `none` ≡ thinking OFF. The legacy binary maps in: `thinking:false → none`, `thinking:true → medium`.
- This **subsumes** the on/off toggle — "thinking" becomes "effort ≥ low". One field, not two.
- Keep `thinking: bool` as a **backward-compat alias** at the API edge (deprecated), normalized to `reasoning_effort` immediately on ingest.

### 2.2 Centralized, capability-aware SDK helper (replaces the duplication)

One helper owns the effort→provider-fields mapping AND the capability clamp:

```
reasoning_fields(effort: ReasoningEffort, model_caps: ModelCaps) -> dict
  - if model not reasoning-capable     -> {} (no-op; never sends effort to a model that can't use it)
  - if effort not in model.valid_levels-> clamp to nearest supported, record the clamp
  - else -> {reasoning_effort, chat_template_kwargs:{thinking: effort!="none", enable_thinking: ...}}
```

- Lives in a shared SDK (`sdks/python/loreweave_llm` reasoning module) so chat / translation /
  composition / knowledge all import ONE implementation. Deletes `thinking_llm_fields` + the
  composition inline copies.
- `ModelCaps` (reasoning-capable? valid effort levels?) is resolved from the **model registry**
  (`capability_flags`), not guessed per service.

### 2.3 Resolution precedence (per turn)

```
inline command (/no_think, /effort=high)        # highest — explicit per-message
  > per-message UI selector
  > session default (generation_params.reasoning_effort)
  > model default (capability_flags.default_effort, if any)
  > platform default (e.g. "none" for cost, or "low")
  ──────── then CLAMP to model capability ────────
```

One resolver function returns the effective `ReasoningEffort` for the turn; everything else feeds it.

### 2.4 GUI — graded selector, capability-gated

- Replace the binary **Think/Fast** with an **effort selector** (None / Low / Medium / High) —
  per-message override in `ChatInputBar`, default in `SessionSettingsPanel`.
- **Capability gating:** read the selected model's `capability_flags`; show the selector only when
  the model is reasoning-capable, and only the levels it supports. For non-capable models, hide it
  (or show disabled with a tooltip) — no more silent no-op.
- `ThinkingBlock` already renders the reasoning stream; unchanged.

### 2.5 MCP — standardize the param across tools

- Adopt `reasoning_effort: ReasoningEffort = "none"` as the **standard** agentic/pipeline-tool
  param, superseding `thinking_enabled: bool`. Keep `thinking_enabled` as a deprecated alias
  (`true→medium`) for one cycle.
- Apply consistently to the tools where effort matters (extraction, translation, deep-research,
  any future agentic tool) via the shared kit, so the name/shape is identical everywhere.

### 2.6 Inline `/no_thinking` command (new capability)

No inline directive parsing exists today, so this is net-new. **Parse server-side** in chat-service
(works regardless of client), at the *start* of the message only, then **strip it before the model
sees it**:

```
/no_think  | /nothink | /no_thinking        -> effort = none   (this turn)
/think                                       -> effort = medium (this turn)
/effort=high | /effort high                  -> effort = high   (this turn)
```

- A tiny directive grammar (leading token, case-insensitive). Unknown `/x` is left untouched (so the
  FE template picker keeps working — those are different: template names vs reserved effort verbs).
- The parsed directive becomes the **highest-precedence** per-turn override (§2.3) and the directive
  text is removed from the content persisted + sent. Optionally echo a tiny chip ("thinking off for
  this turn") in the UI.
- Rationale: it's the fastest "shut up and answer" lever for cheap/quick turns, and it works from any
  surface (mobile, API) without UI.

### 2.7 The wiring fix (prerequisite, not optional)

`_stream_via_gateway` must read the resolved `reasoning_effort` and put `reasoning_fields(...)` into
the provider `StreamRequest` input. **Without this, none of the above takes effect** — and it also
fixes the currently-dead Think/Fast toggle. This is the foundational item.

---

## 3. What this buys

- **One mental model** end-to-end: a single graded `reasoning_effort` from GUI, MCP, inline command,
  or session default, capability-clamped, with one resolver and one SDK helper.
- **Cost control made explicit:** `none` is the cheap/fast default; users opt into spend per-turn.
- **Fixes a live no-op** (the chat thinking toggle does nothing today).
- **Kills duplication** (composition's inline copies, the binary-only helper, the ad-hoc MCP param).

---

## 4. Open questions (for whenever this moves past design)

1. **Platform default effort** — `none` (cheapest, opt-in thinking) or `low` (a little reasoning by
   default)? Affects cost on every turn.
2. **Effort vocabulary** — stick to `none/low/medium/high`, or include `max`/`xhigh` now for models
   that expose more (OpenAI o-series, Claude extended thinking budgets)?
3. **Inline command surface** — chat-only, or also a generic directive other agentic surfaces honor?
4. **`thinking: bool` deprecation** — keep the alias indefinitely, or hard-cut to `reasoning_effort`
   after one cycle?
5. **Per-tool MCP exposure** — every agentic tool, or only the expensive ones (extraction,
   deep-research, translation)?

---

## 5. Notes

- Provider floor + reasoning rendering already exist → the bulk of this is **composition + wiring +
  a UI control + a small parser**, not new infrastructure.
- The currently-dead chat toggle (§2.7) is a real defect surfaced by this mapping; it should be fixed
  even if the rest stays in design.
