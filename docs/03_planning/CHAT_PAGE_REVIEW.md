# Chat Page Architecture Review

> **Status:** Review — identified structural problems, refactoring recommended
> **Session:** 33 (2026-04-12)
> **Files:** `pages/ChatPage.tsx` (315 lines), `features/chat/components/ChatWindow.tsx` (194 lines)

---

## 1. Current Problems

### 1.1 Conditional rendering unmounts child components

```tsx
// ChatPage.tsx line 258
{activeSession && chat.isLoading && chat.messages.length === 0 ? (
  <LoadingSpinner />
) : activeSession ? (
  <ChatWindow />    // ← UNMOUNTS when condition changes
) : (
  <EmptyState />
)}
```

When `chat.refresh()` sets `isLoading=true` and `messages` is temporarily empty, ChatWindow unmounts. All child hook state resets: `useVoiceChat.isActive = false`, `useAutoTTS` stops, `AudioContext` destroyed. This caused the voice mode overlay closing unexpectedly.

**Rule violated:** Never conditionally render components that own stateful hooks. Show/hide with CSS, don't mount/unmount.

### 1.2 ChatPage owns too many concerns

ChatPage currently manages:
- Session list (useSessions)
- Active session selection (useState + URL routing)
- Model name resolution (useEffect + providerApi)
- Message streaming (useChatMessages)
- Context attachment (3 handlers + state)
- Send with context resolution (async handler with book/chapter/glossary API calls)
- Keyboard shortcuts (useEffect)
- Cross-editor events (onSendToChat listener)
- Session CRUD handlers (5 functions)
- Mobile sidebar state
- Session list refresh after streaming (useEffect)
- New chat dialog state

That's 12+ concerns in one component. Changes to any concern risk breaking others.

### 1.3 ChatWindow is a prop-drilling middleman

ChatWindow receives 11 props from ChatPage and passes most through to children:
- `session` → ChatHeader, SessionSettingsPanel, ChatInputBar
- `chat` → MessageList, ChatInputBar (via callbacks)
- `modelNameMap` → ChatHeader
- `contextItems` + 3 handlers → ChatInputBar
- `onSendWithContext` → ChatInputBar
- `onOpenSidebar` → ChatHeader
- `onRename`, `onSessionUpdate` → ChatHeader, SessionSettingsPanel

ChatWindow adds its own state: voice mode, auto-TTS, settings panels. It's both a pass-through and an owner — unclear responsibility.

### 1.4 Voice mode state split across 3 layers

| State | Where | Problem |
|-------|-------|---------|
| `isActive` (overlay visible) | `useVoiceChat` useState | React state — can lag |
| Pipeline phase | `VoicePipelineState` class | Class instance — immediate |
| `activeRef.current` | `useVoiceChat` useRef | Ref — not reactive |

Three different mechanisms track "is voice active." They can diverge. The `isActive` useState was added to fix the pipeline-phase-closing-overlay bug, but it's a patch on a patch.

### 1.5 useEffect chains cause cascading re-renders

```
User speaks → voice turn completes
→ onTurnComplete() calls chat.refresh()
→ chat.refresh() sets isLoading=true → re-render
→ chat.refresh() completes, sets messages → re-render
→ useAutoTTS sees new message → may trigger TTS
→ ChatPage useEffect sees isStreaming change → refreshSessions()
→ refreshSessions() updates sessions → re-render
→ URL effect may fire → re-render
```

One user action triggers 4-6 re-renders through cascading effects. Each effect can trigger side effects that trigger more effects. This is the React "effect waterfall" anti-pattern.

---

## 2. Bugs This Architecture Caused

| Bug | Root cause | Fix applied |
|-----|-----------|-------------|
| Voice overlay closes after audio plays | Conditional rendering unmounts ChatWindow → useVoiceChat resets | Changed loading condition to `messages.length === 0` |
| AI chatting with itself | useAutoTTS fires during voice mode, VAD captures speaker output | Added `voiceModeActive` param to skip auto-TTS |
| Chat freezes on second voice turn | TTSPlaybackQueue `allPlayedFired` not reset between turns | Reset on new `enqueue()` after `close()` |
| Messages disappear on reload | `activeSession` useState resets to null | Added URL-based routing |
| Session title stays "New Chat" | Session list not refreshed after auto-title | Added useEffect to refresh on streaming end |
| Double TTS playback | Voice pipeline TTS + useAutoTTS both play for same message | Guard auto-TTS during voice mode |

All six bugs stem from state being split across too many places with no single source of truth.

---

## 3. Recommended Refactoring

### 3.1 Never conditionally unmount stateful components

```tsx
// WRONG
{condition ? <ComponentA /> : <ComponentB />}

// RIGHT — both always mounted, visibility controlled by CSS
<div className={condition ? '' : 'hidden'}><ComponentA /></div>
<div className={condition ? 'hidden' : ''}><ComponentB /></div>
```

Or use a stable key:
```tsx
<ChatWindow key={session.session_id} />  // Only remounts on session change, not loading
```

### 3.2 Split ChatPage into focused components

```
ChatPage (layout only — sidebar + content area)
├── SessionSidebar (owns session list)
├── ChatView (owns message display + input — never unmounts)
│   ├── ChatHeader
│   ├── MessageList
│   ├── ChatInputBar
│   └── Panels (settings, voice settings)
├── VoiceMode (owns all voice state — independent from chat view)
│   ├── VoicePipelineState (class — source of truth)
│   ├── VoiceChatOverlay
│   └── PipelineIndicator
└── NewChatDialog
```

Key change: **VoiceMode is a sibling of ChatView, not a child.** It doesn't unmount when chat refreshes.

### 3.3 Replace useEffect chains with explicit event flow

```
Current: useEffect watches state changes → triggers side effects → more state changes

Better: explicit event dispatch
  voiceTurnComplete → dispatch('VOICE_TURN_COMPLETE')
    → chatMessages.refresh() (handler, not effect)
    → sessionList.refresh() (handler, not effect)
  
  No cascading re-renders — each handler runs independently.
```

### 3.4 Context provider for shared state

Instead of prop-drilling 11 props through ChatWindow:

```tsx
<ChatSessionProvider session={activeSession} chat={chat} modelNameMap={modelNameMap}>
  <ChatHeader />      {/* reads from context */}
  <MessageList />     {/* reads from context */}
  <ChatInputBar />    {/* reads from context */}
</ChatSessionProvider>
```

This eliminates the prop-drilling middleman pattern.

---

## 4. Priority

| Priority | Change | Risk | Effort |
|----------|--------|------|--------|
| **P0** | Stop unmounting ChatWindow on refresh | Low | Small — done |
| **P1** | Move VoiceMode to sibling of ChatView | Medium | Medium |
| **P2** | ChatSessionContext provider | Low | Medium |
| **P3** | Replace useEffect chains with events | Medium | Large |
| **P4** | Split ChatPage into focused components | Medium | Large |

P0 is already fixed. P1-P4 are future refactoring tasks — each reduces the chance of state-related bugs.

---

*Created: 2026-04-12 — LoreWeave session 33*
