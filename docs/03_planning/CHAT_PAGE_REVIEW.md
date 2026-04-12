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

## 3. Revised Architecture Plan (session 34)

### Design Principle: Impose MVC on React

React merges logic and view in one file. We impose separation ourselves:

```
hooks/          ← "controllers" — own logic + state
  useSessionManager.ts    (session CRUD, URL sync, navigation)
  useChatMessages.ts      (already exists — message streaming)
  useContextAttachment.ts (attach/detach/clear/resolve)
  useKeyboardShortcuts.ts (Ctrl+N, Escape)

context/        ← "services" — shared state across components
  ChatSessionContext.tsx   (stable: session, models, session CRUD)
  ChatStreamContext.tsx    (volatile: messages, streaming state)

components/     ← "views" — render only, no business logic
  ChatPage.tsx            (layout shell — <50 lines)
  ChatView.tsx            (message list + input + voice — never unmounts)
  ChatHeader.tsx          (reads from context)
  MessageList.tsx         (reads from context)
  ChatInputBar.tsx        (reads from context)
  VoiceChatOverlay.tsx    (inside ChatView — voice IS chat)
```

Components receive data from context, call handlers, render. No useEffect for data
fetching inside view components. No API calls inline.

### 3.1 ChatSessionContext + ChatStreamContext (P1)

Split into two contexts to avoid unnecessary re-renders during streaming:

**ChatSessionContext (stable — changes on session switch):**
- `activeSession`, `setActiveSession`
- `modelNameMap`
- Session CRUD handlers (create, rename, archive, delete, togglePin)
- Context attachment state + handlers
- `refreshSessions()`

**ChatStreamContext (volatile — changes every SSE chunk):**
- `chat` (the `useChatMessages` return value: messages, streamingText, isStreaming, send, stop, etc.)

```tsx
// ChatPage.tsx — layout shell only
<ChatSessionProvider>
  <ChatStreamProvider>
    <div className="flex h-full">
      <SessionSidebar />
      <ChatView />      {/* always mounted */}
    </div>
    <NewChatDialog />
  </ChatStreamProvider>
</ChatSessionProvider>
```

Children call `useChatSession()` for stable data, `useChatStream()` for volatile data.
ChatHeader only needs session → doesn't re-render on every streamed token.

### 3.2 Never unmount ChatView (P2)

Voice mode is NOT a separate feature — it's an alternative input method for the same
chat conversation. It shares the session, sends messages to the same stream, triggers
the same `chat.refresh()`. Making it a sibling was **wrong**.

**Correct structure:**
```
ChatView (always mounted when session exists — hidden via CSS otherwise)
├── ChatHeader (text + voice toggle)
├── MessageList
├── ChatInputBar (text input)
├── VoiceChatOverlay (voice input — same conversation)
├── VoiceConsentDialog
└── Panels (settings, voice settings)
```

**Fix:** Don't ternary-render ChatView. Render it always, show loading/empty states
with CSS `hidden` or internal branching within the component.

```tsx
// BEFORE — unmounts ChatView
{activeSession && loading ? <Spinner /> : activeSession ? <ChatView /> : <EmptyState />}

// AFTER — ChatView always mounted
<EmptyState className={activeSession ? 'hidden' : ''} />
<ChatView className={!activeSession ? 'hidden' : ''} />
{/* Loading state handled INSIDE ChatView */}
```

### 3.3 Split ChatPage + extract hooks (P3)

Extract ChatPage's 12 concerns into focused hooks:

| Hook | Extracted from | Concern |
|------|---------------|---------|
| `useSessionManager` | ChatPage lines 23-58, 186-237 | Session CRUD, URL routing, navigation |
| `useContextAttachment` | ChatPage lines 88-148 | Context items, resolve + build context block |
| `useKeyboardShortcuts` | ChatPage lines 152-166 | Ctrl+N, Escape |
| `useModelNames` | ChatPage lines 61-73 | Model UUID → display name resolution |

ChatPage becomes a ~40-line layout shell that composes providers and renders sidebar + chat view.

### 3.4 Replace useEffect chains with explicit handlers (P4)

```
Current (effects):
  voiceTurnComplete → chat.refresh() → isLoading → re-render
                    → messages change → re-render → autoTTS
                    → isStreaming change → re-render → refreshSessions via useEffect

Better (explicit handlers):
  voiceTurnComplete:
    handler1: chat.refresh()
    handler2: refreshSessions()    ← called directly, not via effect

  streamingEnd:
    handler1: refreshSessions()    ← called from useChatMessages callback, not effect
```

Replace `useEffect(() => { if (prev && !current) ... }, [current])` pattern with
explicit `onStreamingEnd` / `onTurnComplete` callbacks passed into hooks.

---

## 4. Revised Priority + Execution Order

| Step | Priority | Change | Risk | Effort |
|------|----------|--------|------|--------|
| done | **P0** | Stop unmounting ChatWindow on refresh | Low | Small — **done** |
| 1 | **P1** | ChatSessionContext + ChatStreamContext | Low | Medium |
| 2 | **P2** | Never unmount ChatView (CSS show/hide) | Low | Small |
| 3 | **P3** | Extract hooks + split ChatPage into shell | Medium | Medium |
| 4 | **P4** | Replace useEffect chains with callbacks | Medium | Large |

**Why this order:**
- P1 first: context providers are the foundation — enables everything else
- P2 second: trivial once context exists (no more prop drilling to worry about)
- P3 third: extract hooks makes ChatPage a clean shell
- P4 last: hardest, least urgent — P0 fix already prevents the worst bugs

**Dropped:** Original P1 "Move VoiceMode to sibling of ChatView" — wrong design.
Voice mode is part of chat, not independent. It stays inside ChatView.

---

*Created: 2026-04-12 (session 33) — Revised: 2026-04-12 (session 34)*
