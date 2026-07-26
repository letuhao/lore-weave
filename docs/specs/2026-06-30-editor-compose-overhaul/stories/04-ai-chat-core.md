# Story 04 — AI chat as the CORE ("Claude Code in VS Code")

> **Status:** ✅ shipped (story 04 BUILD + review remediation 2026-07-01) · **Epic:** C (C6) · **Touches backend:** YES ·
> **Evidence:** `enabled_tools`/`enabled_skills`/`activated_tools` on sessions; `agentSurface` SSE; rack + inspector on `/chat`; E2E `agent-context-rack.spec.ts`.

## PO intent
The AI chat should be the **core** of the writing assistant — like Claude Code in VS Code. Users mostly
use the chat panel. The agentic infra (MCP tool-calls + lazy-load) is already built; **missing = the
control surface**: manually load/select MCP tools, pick **skills** for the agent, and advanced
**LLM/model settings**.

## Investigation (canonical — don't re-explore)

### Chat architecture (FE)
- `features/chat/Chat.tsx` — root wrapper (props `bookId`, `editorContext`, `composeMode`, ...).
- `providers/ChatStreamContext.tsx` — stream orchestration (`useChatMessages` + `usePendingFacts`).
- `hooks/useChatMessages.ts` — message list + send; `streamPost` POSTs `/v1/chat/sessions/{id}/messages`.
- `hooks/runChatStream.ts` — pure SSE core; `buildRequest` (~98) builds body; parses AG-UI events
  (TEXT/REASONING/TOOL_CALL_START/RESULT, CUSTOM memory-mode/composing/activity).
- `components/ChatView.tsx` — main render; `AssistantMessage.tsx` — turns + tool-call chips.
- `components/NewChatDialog.tsx` — create: model pick + system-prompt preset (generationParams slot
  passed `undefined`, ~105 — **unused at create**).
- `components/SessionSettingsPanel.tsx` — per-session: model, **composer model**, **planner model**,
  project (memory), system prompt (+ presets), temperature, top_p, max_tokens, reasoning_effort.
- `api.ts` — `createSession` / `patchSession` (PATCH `/v1/chat/sessions/{id}`). **No tool selection.**

### Model / LLM settings
- Persisted per-session in `chat_sessions` (`chat-service models.py`): `GenerationParams`
  (`max_tokens`, `temperature`, `top_p`, `thinking`, `reasoning_effort`), `model_source/ref`,
  `system_prompt`, `composer_model_*`, `planner_model_*`, `project_id`.
- BE forwards temperature/max_tokens/top_p/reasoning to the SDK (`stream_service.py` `_stream_via_gateway` / `_stream_with_tools`).
- Advanced gen-params exist in `SessionSettingsPanel` (edit) but **NOT exposed at create**
  (`NewChatDialog` passes `undefined`).

### MCP tool-calling (the core) + lazy-load
- FE sends `disable_tools: bool` + `editor_context`/`book_context` (signal which frontend tools to
  advertise) — NOT a tool list (`runChatStream.ts:106-114`).
- BE assembles tools (`stream_service.py`): `catalog = knowledge_client.get_tool_definitions()` (~1226,
  the ai-gateway federated `/mcp` list, ~200 tools). Discovery mode advertises: always-on core
  (`find_tools` meta-tool + `ui_*` + `propose_record_edit` + `confirm_action`) + conditional frontend
  tools + a hot-domain seed; the agent calls **`find_tools`** to discover the rest, whose schemas are
  advertised on the next pass (`_advertise_discovery_tools` ~385, `tool_discovery.py`). **This is the
  "lazy load."** Admin mode uses `get_admin_tool_definitions`.
- Tools carry **tiers R/A/W/S**; Tier-W writes are confirm-token gated (= a built-in permission model).
- **Per-chat tool enable/disable today: NONE.** Only per-turn binary `disable_tools` (prose-only) +
  per-surface context. No persisted "selected tools".

### Skills
- **No first-class / user-selectable skills.** Skills exist ONLY as system prompts auto-injected by
  surface: `inject_glossary_skill` / `inject_universal_skill` / `inject_knowledge_skill`
  (`stream_service.py:1022/1050/1076`), conditional on surface/tools, never user-chosen. No skills
  table, no per-chat skill field, no UI.

### composeMode (Agent↔Compose)
- `if (args.composeMode) body.disable_tools = true` (`runChatStream.ts:114`) → BE skips tool
  fetch/advertisement (`stream_service.py:1202`) → model drafts prose, no tool calls. Orthogonal axis
  (model behavior), NOT a workmode.

### Where config would attach
- Per-session = `chat_sessions` (natural home for `enabled_tools` / `selected_skills`).
- Per-turn = `SendMessageRequest` (ephemeral override). Per-user prefs = possible default layer.

## Gap summary
- **FE missing:** MCP tool-selector/browser UI; advanced model settings at create; skills picker;
  per-chat tool filtering.
- **BE missing:** tool-selection persistence (`enabled_tools`) + a filter step in discovery assembly;
  skills store + per-chat selection; **fix `top_p` forwarding** (bug); (later) model↔tool compat.
- **Scope:** this is genuinely **new build** (tool-curation surface + skills system), the one place the
  overhaul leaves "re-arrange + wire."
- **Studio FE design (Writing Studio v2):** [`07_studio_agent_chat.md`](../../2026-07-01-writing-studio/07_studio_agent_chat.md) +
  [`07a`](../../2026-07-01-writing-studio/07a_agent_context_rack.md) (rack UI) +
  [`07b`](../../2026-07-01-writing-studio/07b_agent_runtime_inspector.md) (lazy-load inspector) +
  [`07c`](../../2026-07-01-writing-studio/07c_studio_tool_registry.md) (incremental registration).
  Mockup: [`screen-studio-agent-chat.html`](../../../design-drafts/screens/studio/screen-studio-agent-chat.html).
  `enabled_tools` / `enabled_skills` on `chat_sessions` are the persistence layer for #07a pins (D12).
  `agentSurface` CUSTOM SSE (proposed in 07) feeds #07b phase display.
- **Agent→GUI reconciliation (studio):** [`09_agent_gui_reconciliation.md`](../../2026-07-01-writing-studio/09_agent_gui_reconciliation.md) —
  three-lane model (ui intent / MCP reload / human-gate); `StudioEffectReconciler` + `consumer_capabilities`
  on send; mockup [`screen-studio-agent-gui-bridge.html`](../../../design-drafts/screens/studio/screen-studio-agent-gui-bridge.html).
- **Agent lifecycle hooks (studio):** [`10_agent_lifecycle_hooks.md`](../../2026-07-01-writing-studio/10_agent_lifecycle_hooks.md) —
  sandboxed `.loreweave/hooks.json` on server; `HookOrchestrator` in chat-service; reconciler runs
  **before** user `postToolUse`; SSE `hook_audit` / `hook_progress`; mockup
  [`screen-studio-agent-hooks.html`](../../../design-drafts/screens/studio/screen-studio-agent-hooks.html).

## Proposed shape
- **Tool curation** — per-chat tool picker (browse federated catalog by domain + tier, enable a
  subset). Persist `enabled_tools` on the session; empty ⇒ today's auto-discovery fallback. Reuse
  `find_tools`/catalog + tier metadata. **Studio UI:** [#07a Context Rack](../../2026-07-01-writing-studio/07a_agent_context_rack.md).
- **Skills** — a skill = playbook prompt + optional pinned tool set + optional model settings. Step 1:
  make the existing injected skills **selectable System skills** (read-only). Step 2 (later): per-user
  custom skills (tenancy: System read-only + per-user). **Studio UI:** same rack (skill chips).
- **Runtime visibility** — expose lazy-load phases + activated tool counts. **Studio UI:**
  [#07b Runtime Inspector](../../2026-07-01-writing-studio/07b_agent_runtime_inspector.md) +
  `agentSurface` SSE (see [07](../../2026-07-01-writing-studio/07_studio_agent_chat.md)).
- **Model settings** — fix `top_p` forward; expose advanced gen-params at create; keep
  `SessionSettingsPanel` as the advanced home.
- **GUI reconciliation** — `consumer_capabilities` on `SendMessageRequest`; FE
  `StudioEffectReconciler` reloads hoists after MCP writes (studio only v1). See
  [#09](../../2026-07-01-writing-studio/09_agent_gui_reconciliation.md).
- **Lifecycle hooks** — `HookOrchestrator` wraps tool loop; optional SSE `hook_audit` /
  `hook_progress` on stream. User hooks cannot weaken [mcp-fanout](../../2026-06-20-mcp-fanout-agent-universal-control.md)
  Tier-W/S gates. See [#10](../../2026-07-01-writing-studio/10_agent_lifecycle_hooks.md).

## Open decisions (PO)
_(C6-D1–D3 locked 2026-07-01 — see Decisions locked.)_

## Decisions locked
- **C6-D1 — Tool curation:** per-chat rack pin subset (`enabled_tools` whitelist-with-escape); empty = auto hot-set + `find_tools`. No `@tool` mentions v1.
- **C6-D2 — Skills:** System catalog selectable v1 (`enabled_skills`); no user-defined skills table yet.
- **C6-D3 — Priority:** global `/chat` rack + inspector shipped first; studio compose mount after #03.
