# Story 03 — Compose / AI-Assistant re-frame (Epic C)

> **Status:** 🟡 discussing · **Epic:** C (huge — decomposed into C0–C5) ·
> **Evidence:** [`../00_INVESTIGATION.md` §3,§4,§7,§8](../00_INVESTIGATION.md) + media-gen findings below.

## PO intent
Original "AI assistant" design was simple — **use AI to: suggest story, make TTS, make video, make
image.** Then the **composition** feature was built and "changed the game": "suggest story" exploded
into a full authoring system (24 panels). The original assistant is now only a small slice. **The AI
assistant must be re-framed correctly** around the composition reality.

## Current AI surfaces (6, overlapping)
1. **AI Chat** tab (right panel) — `<Chat>` + Agent/Compose toggle, `propose_edit`.
2. **CoWriterChat** (compose `cowriter` panel) — discuss → insert / use-as-guide.
3. **BookAssistantDock** — floating "Ask AI" on glossary/reader; dead-ends for compose.
4. **Composition Studio** — the 24 authoring panels.
5. **Enrichment Compose** — glossary entity enrichment (separate Book-Detail tab).
6. **Media gen** — image (`ImageBlockNode` → `booksApi.generateImage`, WIRED), video
   (`features/video-gen` `videoGenApi.generate` `/v1/video-gen/generate`, WIRED), TTS
   (`useAutoTTS`, reader/chat). Scattered + gated behind the `ai` editor mode.

Surfaces 1+2+3 are **the same idea** ("talk to AI about my book") built three times.

## Proposed re-frame — 3 roles, one Compose workspace
- **💬 TALK** — converse with AI (brainstorm, discuss prologue, suggestions). The **front door** +
  the original "suggest story". Discussions spill into actions (create scene, draft, illustrate).
  → unify surfaces 1+2+3 into ONE assistant.
- **🛠 BUILD** — the manuscript tools (draft, outline/beats/planner, scenes, story bible, critic) =
  the 24 panels grouped into 5 sections. The "changed the game" depth.
- **🎬 PRODUCE** — generate assets bound to prose (image / TTS / video) = the original media jobs,
  re-framed as one coherent "produce media for this scene/chapter" capability.

> Positioning: **Talk + Produce were the whole original idea; Build is what composition added.**

## Decomposition of Epic C
- **C0** — adopt the Talk/Build/Produce frame. _(discussing)_
- **C1** — Compose command-center surfacing the 3 roles. _(⬜)_
- **C2** — group the 24 Build panels into 5 sections (= M2). _(⬜)_
- **C3** — discuss→content (Talk spills into Build). _(⬜)_
- **C4** — unify the 3 chat surfaces into one Assistant; disambiguate "Compose" vs glossary
  "Enrichment". _(⬜)_
- **C5** *(new)* — unify media gen (image/video/TTS) as the **Produce** role, surfaced per
  scene/chapter. _(⬜)_
- **C6 (AI CHAT as CORE)** — see [`04-ai-chat-core.md`](04-ai-chat-core.md). The PO's primary ask:
  make the AI chat the central surface ("Claude Code in VS Code"). _(🟡 investigating)_

## Open framing decisions (PO)
- [ ] **C0-D1** — adopt Talk / Build / Produce as the mental model? (or adjust the roles)
- [ ] **C0-D2** — unify the 3 chat surfaces (AI Chat / CoWriter / BookAssistantDock) into ONE assistant?
- [ ] **C0-D3** — treat media gen (image/video/TTS) as a first-class **Produce** role (C5)?

## Decisions locked
_(none yet — C6 "AI chat as core" is being discussed first, see story 04.)_
