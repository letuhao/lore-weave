# Composer Feature Inventory (Writing Studio Chat GUI)

> Purpose: a flat, numbered, countable checklist of every discrete user-facing feature in the Writing Studio Composer (`ComposePanel.tsx` → `Chat.tsx` → everything it mounts), mirroring [`2026-07-06-editor-feature-inventory.md`](2026-07-06-editor-feature-inventory.md)'s format. Source-of-truth for scoping Composer's guided tours.
>
> **~94 discrete items across 20 groups.** Each entry: name — one-line description — `file:line` — `data-testid` (or **NO TESTID**) — control shape.

---

## A. ComposePanel shell / chrome — 4 items

1. **Compose panel root** — dock panel container. `ComposePanel.tsx:81` · `studio-compose-panel`
2. **Pop-out button (⤢)** — opens Compose in a separate OS window; disabled until a chapter is open or already popped out. `ComposePanel.tsx:83-92` · `studio-compose-popout`
3. **Self-titling dock tab** — `ComposePanel.tsx:67-69` · NO TESTID
4. **Command-palette/agent-rack registration** — advertises `composition_` tool prefix + `universal` skill. `ComposePanel.tsx:54-63` · NO TESTID · cross-panel seam

## B. Session management — 10 items

5. **Session switcher** (header dropdown) — `SessionSwitcher.tsx:85-100,102-170` · `session-switcher-trigger`
6. **Per-row Archive** — `SessionSwitcher.tsx:142-155` · NO TESTID
7. **"New chat" row** — `SessionSwitcher.tsx:159-168` · NO TESTID
8. **New Chat dialog** — `NewChatDialog.tsx:101-201` · NO TESTID
   8a. model picker `:118-125` · 8b. capability badges `:128-145` · 8c. persona presets (Novel/Translator/Worldbuilder/Editor) `:149-168` · 8d. system-prompt textarea `:171-187` · 8e. Start-chat `:189-196`
9. **Auto-create book-scoped session** — `Chat.tsx:92-135` · NO TESTID · behavior
10. **Chat empty state** — `ChatEmptyState.tsx:9-39` · NO TESTID
11. **Rename session** (pencil) — `ChatHeader.tsx:144-153` · NO TESTID
12. **Archived badge** — disables edit/regenerate/delete/send. `ChatHeader.tsx:86-90` · NO TESTID
13. **Export conversation** (Markdown only — see Gap #94) — `ChatHeader.tsx:61-64,136-143` · NO TESTID
14. **Mobile "open conversations" hamburger** — ⚠️ **Gap #90**, dead-ends. `ChatHeader.tsx:69-77` · NO TESTID

## C. Header chips — 2 items

15. **Memory/grounding indicator** (chip+popover) — `MemoryIndicator.tsx:37-167` · NO TESTID
16. **Context budget meter** ("% used" chip) — `ContextMeter.tsx:52-140` · `context-meter`

## D. Composer / input bar — 13 items

17. **Response-format pills** (Auto/Concise/Detailed/Bullets/Table) — `ChatInputBar.tsx:207-223` · NO TESTID
18. **Slash "/" template & command picker** — user's registry commands + 9 built-ins. `:129-153,226-233` + `PromptTemplates.tsx:37-141` · `slash-picker`/`slash-command-item`
19. **"@" mention popover** (inline context attach) — `:236-242` + `MentionPopover.tsx:20-66` · `chat-mention-listbox`
20. **Context bar** (attached pills, remove/clear-all) — `:245-252` + `ContextBar.tsx:30-118` · NO TESTID
21. **Message textarea** (Enter/Shift+Enter/Ctrl+Enter=Fast/Ctrl+Shift+Enter=Think) — `:255-283` · NO TESTID
22. **Attach-context button** (paperclip → Context Picker modal) — `:289-296` + `ContextPicker.tsx` · NO TESTID
23. **Voice-Assist ON/OFF toggle** — `:301-318` · NO TESTID
24. **Push-to-talk mic button** — `:319-349` · NO TESTID
25. **Stop-TTS button** — `:352-361` · NO TESTID
26. **Permission-mode dropdown** (Ask/Plan/Write, Ctrl+.) — `:365-421` · `permission-mode-toggle`/`permission-mode-menu`/`mode-opt-{ask|plan|write}`
27. **Reasoning-effort dropdown** (shared `EffortSelect`) — `:426-431` + `EffortSelect.tsx:27-97` · `effort-select`/`effort-select-menu`/`effort-select-opt-{level}`
28. **Send / Stop button** — `:436-455` · NO TESTID
29. **Composer hint footer** — `:458-462` · NO TESTID

## E. Context Picker modal — 1 item

30. **Context Picker** (Book/Chapter/Glossary tabs, search, filters, attach/detach) — `ContextPicker.tsx:18-279` · NO TESTID

## F. Voice (overlay + settings) — 9 items

31. **Voice Mode toggle** (mic, header) — `ChatHeader.tsx:97-113` · NO TESTID
32. **Voice Mode overlay** — `VoiceChatOverlay.tsx:34-187` · NO TESTID
33. **Mic-consent dialog** — `ChatView.tsx:292-315` · NO TESTID
34. **Pipeline debug indicator** — `PipelineIndicator.tsx:34-101` · NO TESTID
35. **Waveform visualizer** — `WaveformVisualizer.tsx:10-28` · NO TESTID
36. **Voice Settings button** (sliders, header) — `ChatHeader.tsx:114-123` · NO TESTID
37. **Voice Settings drawer** — `VoiceSettingsPanel.tsx:42-514` · NO TESTID, with 18 sub-controls (STT source/model/language, silence threshold, auto-send, show-interim, TTS source/model/voice+preview/browser-voice/speed, auto-play, pause-mic-during-TTS, VAD recommendation/presets/manual sliders, voice-assist toggles, show-metrics, reset)
38. **Audio replay player** (per TTS'd message) — `AssistantMessage.tsx:350-353` + `AudioReplayPlayer.tsx:24-187` · NO TESTID
39. **Voice metrics footer** — `MessageBubble.tsx:175-205` · NO TESTID

## G. Session settings panel — 1 item, 11 sub-controls

40. **Session Settings** (gear, header) → drawer — `ChatHeader.tsx:154-164` · `chat-session-settings-button` + `SessionSettingsPanel.tsx:27-521`:
    40a. model picker · 40b. composer model (A2A) · 40c. planner model · 40d. multi-KG picker · 40e. system-prompt + 6 presets · 40f. max-tokens slider+∞ · 40g. temperature · 40h. top-P · 40i. reasoning-effort · 40j. session-info grid · 40k. reset-to-defaults

## H. Agent context rack (tool/skill management) — 3 items

41. **Agent Context Rack bar** — `AgentContextRack.tsx:60-193` · `agent-context-rack`
    41a. summary chip `agent-rack-summary` · 41b. per-server tool chips `agent-rack-server-{key}`/`agent-rack-server-dot-{key}`/`agent-rack-chip-tool-{name}` · 41c. enabled-skill chips · 41d. "+ Add" `agent-rack-add` · 41e. discovered count · 41f. "Clear discovered" `agent-rack-clear-discovered`
42. **Tool/Skill Add modal** — `ToolSkillAddModal.tsx:22-282` · `tool-skill-modal`, `tool-skill-tab-{tools|skills}`, `tool-skill-search`, `tool-skill-category-chip-*`, `tool-skill-item-{name}`
43. **Agent Runtime Inspector strip** (phase indicator, expand for detail) — `AgentRuntimeInspector.tsx:23-109` · `agent-runtime-inspector`, `agent-inspector-phase`, `agent-inspector-advertised`, `agent-inspector-trail`

## I. Context budget meter & breakdown — 3 items

44. Context Meter chip — see item 16.
45. **Context Breakdown panel** (Now/History tabs) — `ContextBreakdownPanel.tsx:175-392` · `context-breakdown-panel`, `context-panel-tabs`, `context-tab-now`, `context-tab-history`
    45a. stacked bar+compact marker `context-breakdown-bar`/`context-compact-marker` · 45b. category rows+manage `context-manage-{category}` · 45c. memory drill-down `context-row-memory-toggle`/`context-memory-sections` · 45d. zero-categories line `context-zero-line` · 45e. baseline/free/until-compact footer · 45f. Compact-now section `context-compact-instructions`/`context-compact-now`/`context-compacted-through`/`context-compact-clear`
46. **Context History tab** (per-turn token-usage chart) — `ContextHistoryTab.tsx` + `ContextHistoryChart.tsx` · NO TESTID

## J. Message list & per-message actions — 13 items

47. Message list/auto-scroll — `MessageList.tsx:28-159` · NO TESTID
48. "✍️ Drafting…" indicator — `:133-142` · NO TESTID
49. Typing indicator — `:144-153` · NO TESTID
50. User message edit (branch) — `UserMessage.tsx:46-89` · NO TESTID
51. User message delete — `UserMessage.tsx:106-115` · NO TESTID
52. Branch navigator (◀ N/M ▶) — `BranchNavigator.tsx:17-87` · NO TESTID
53. Context-attachment pills (sent message) — `MessageBubble.tsx:94-116` · NO TESTID
54. Assistant markdown render + streaming cursor — `AssistantMessage.tsx:182-188` · NO TESTID
55. Copy message — `:421-428` · NO TESTID
56. Regenerate (+ implicit 👎) — `:429-438` · NO TESTID
57. Thumbs up/down — `:389-419` · NO TESTID
58. "More actions" → Copy as Markdown / Send to Editor (⚠️ Gap #91) — `:440-469` · NO TESTID
59. Token/timing footer (Fast⚡/Think🧠, ↑in/↓out, time, TTFT) — `:359-384` · `message-token-footer`

## K. Thinking / reasoning — 2 items

60. Live thinking block (elapsed timer, long-thinking warning) — `ThinkingBlock.tsx:13-134` · NO TESTID
61. Completed thinking block ("Thought for Xs") — `ThinkingBlock.tsx:93-134` · NO TESTID

## L. Tool-calling / agent-mode indicators — 2 items

62. Tool-call indicator chips (expand→detail) — `ToolCallIndicator.tsx:30-90` · `tool-call-indicator`, `tool-call-chip`, `tool-call-detail`
63. **Tool Approval card** (Tier-A undoable write, Approve once/Always/Deny) — `ToolApprovalCard.tsx:40-138` · `tool-approval-card`, `tool-approval-tier`

## M. Propose-edit review (writes into the Editor panel) — 1 item, 5 sub-controls

64. **Propose-Edit card** ("suggested rewrite/insertion" + Apply/Dismiss) — `ProposeEditCard.tsx:217-323` · `propose-edit-card`
    64a. per-hunk accept/reject `propose-hunks`/`propose-hunk-{id}` · 64b. Apply/Apply-N/Keep-original · 64c. Dismiss · 64d. cross-chapter guard · 64e. popout-relay Apply (BroadcastChannel to opener's editor)

## N. Confirm / high-impact action-gate cards — 6 items

65. Glossary Diff card — `GlossaryDiffCard.tsx:118-171` · `glossary-diff-card`
66. Record Diff card (generic `propose_record_edit`) — `RecordDiffCard.tsx:95-149` · `record-diff-card`
67. Confirm card (legacy glossary) — `ConfirmCard.tsx:128-186` · `confirm-card`
68. **Confirm Action card** (batch rows, execute_plan→Planner view, per-op destructive opt-in, re-price on drift) — `ConfirmActionCard.tsx:92-399` · `confirm-action-card`, `confirm-batch-rows`, `enable-op`, `confirm-reprice`, `pending-destructive` (embeds `PlannerPlanView.tsx:34-120`)
69. Batch Confirm card (coalesces N proposals) — `BatchConfirmCard.tsx:43-197` · `batch-confirm-card`, `batch-confirm-rows`, `batch-confirm-result`
70. Skill Proposal card — `SkillProposalCard.tsx:42-105` · `skill-proposal-card`, `skill-proposal-approve`, `skill-proposal-reject`
71. Translation Review card (read-only) — `TranslationReviewCard.tsx:76-132` · `translation-review-card`

## O. Memory & pending facts — 1 item

72. **Pending Facts card** (`memory_remember` queue, Confirm/Reject per row) — `PendingFactsCard.tsx:29-124` · `pending-facts-card`, `pending-fact-row`, `pending-fact-confirm`, `pending-fact-reject`

## P. Output cards — 1 item

73. **Output card** (extracted code/text, Copy/Send-to-Editor/Download) — `OutputCard.tsx:19-95` · NO TESTID

## Q. Activity strip — 1 item

74. **Activity Strip** (Tier-A auto-applied ops, per-row Undo) — `ActivityStrip.tsx:24-80` · `activity-strip`, `activity-row`, `activity-undo`

## R. Popout window — 4 items

75. Pop-out button — see item 2.
76. **Studio Popout Host page** (`/studio/popout`) — `StudioPopoutHost.tsx:24-103` · `studio-popout-dock-back`
77. Popout lifecycle bridge (open/poll/close, dock-back handshake) — `PopoutBridge.tsx:21-81` · NO TESTID
78. Cross-window Apply relay (see 64e) — `popoutRelayContext.ts:16-27` · NO TESTID

## S. Cross-panel seams (not directly clickable) — 7 items

79. Studio bus context feed (book/project/chapter → agent tool menu) — `ComposePanel.tsx:34-49` · NO TESTID
80. Editor write-back gate (`editorContext`, enables item 64) — `ComposePanel.tsx:40-49` · NO TESTID
81. Nav-tool interception (same-book, avoids unmounting Compose) — `studioUiNav.ts:53-83` · NO TESTID
82. Studio `ui_*` tool resolution (no human gate) — `studioUiNav.ts:11-45`, `StudioAgentBridge.tsx` · NO TESTID
83. Generic `ui_*` nav executor (all chat surfaces) — `useUiToolExecutor.ts:34-71` · NO TESTID
84. Agent-write → GUI reconciler (Lane B: book/glossary/kg/translation panels refresh) — `useStudioEffectReconciler.ts:23-67` + `handlers/*.ts` · NO TESTID
85. "Send to Editor" event bus (⚠️ Gap #91, no listener) — `pasteToEditor.ts:1-27` · NO TESTID

---

## Gaps found while enumerating

- **#90 — Mobile hamburger dead-ends.** `ChatHeader`'s "open conversations" button calls `setMobileSidebarOpen(true)`, but nothing in Compose's tree renders `SessionSidebar` (only `ChatPage.tsx` does). Clicking it in Studio does nothing visible.
- **#91 — "Send to Editor" has no listener.** `onPasteToEditor` (the receiving half of `pasteToEditor.ts`) has zero call sites anywhere. Both "Send to Editor" affordances (item 58, item 73) dispatch a DOM event nothing subscribes to — a real capability gap, not just a testid gap.
- **#92 — Context-inspector button is suppressed on Compose.** `ChatView` passes `onOpenInspector={!embedded ? … : undefined}`; Compose always sets `embedded=true`, so it can never open the standalone `/context-inspector` page — only the in-panel Agent Runtime Inspector (43) and Context Breakdown panel (45) are available. (Likely intentional, not necessarily a bug — flagging for awareness.)
- **#93 — `chat-ai-settings` cascade is NOT part of Compose.** Its only consumers are `SettingsPage.tsx` and the legacy Composition workspace. Compose's real per-session settings surface is `SessionSettingsPanel` (item 40) — simpler, no cascade-resolution UI. A tour must not assume the cascade lives in Compose.
- **#94 — JSON export has no UI.** `chatApi.exportUrl` supports `'json'`, but the export button (item 13) is hardwired to `'markdown'`.
- **#95 — Global chat keyboard shortcuts don't reach Compose.** `ChatKeyboardShortcuts` (Ctrl+N, Esc-to-stop) mounts only on the standalone `ChatPage`, never on Compose.

## Tour-readiness summary

| Group | Items | Testid coverage | Notes |
|---|---|---|---|
| A — Panel chrome | 4 | partial | good first-step material |
| B — Session mgmt | 10 | partial | switcher + new-chat dialog tour-worthy |
| C — Header chips | 2 | partial | |
| D — Composer bar | 13 | good (mode/effort) | prime tour targets |
| E — Context picker | 1 | none | |
| F — Voice | 9 | none | large surface, 1-2 steps max |
| G — Session settings | 1+11 | button only | single "open settings" step suffices |
| H — Agent rack | 3 | excellent | strong tour material already |
| I — Context budget | 3 | excellent | strong tour material already |
| J — Message actions | 13 | minimal | hover-revealed, self-explanatory |
| K — Thinking | 2 | none | |
| L — Tool-calling UI | 2 | good | |
| M — Propose-edit | 1+5 | good | core differentiator — high value |
| N — Confirm cards | 6 | good | safety-net story — high value |
| O — Pending facts | 1 | good | |
| P — Output cards | 1 | none | |
| Q — Activity strip | 1 | good | |
| R — Popout | 4 | partial | multi-monitor power feature, 1 step |
| S — Cross-panel seams | 7 | none (not clickable) | narrate, don't spotlight |

**Recommendation:** Groups H (agent rack), I (context budget), M (propose-edit), N (confirm cards) are Compose's real differentiators vs. a generic chat box and are already well testid'd — anchor tours here. Group D's permission-mode/effort dropdowns are the other must-show controls. Voice (F) and Output/Media (P) are real but large — 1 combined step each. Group S can't be spotlighted (no DOM anchor) — worth one narrated step at most. **Fix Gap #91 before advertising "Send to Editor" in a tour** — it's currently a dead button.
