# Story 05 — Compose panels as a toolbox (+ Media tool)

> **Status:** 🟡 discussing (3 decisions open) · **Epic:** C (C2 reshaped + C5 = Media) ·
> **Evidence:** [`../00_INVESTIGATION.md` §4](../00_INVESTIGATION.md) + findings below.

## PO frame
The compose panels "feel like a toolbox in Photoshop / After Effects" — **and they are.** The
**media generator + browser** (TTS / video / image) is a **new tool** in that toolbox — the original
plan that drifted (from April).

## Finding 1 — the Photoshop toolbox UX ALREADY EXISTS (flag-OFF)
`WorkspaceLayoutContext` already implements a full dockable-panel system, default **OFF** via the
per-device flag **`loom.workspace.enabled`** (`WorkspaceLayoutContext.tsx:16,80`). When ON:
- **dock** (rail) / **float** (`FloatingWindow.tsx` — draggable+resizable, portaled, viewport-fixed) /
  **pop-out** to a separate OS window (`PopoutBridge`/`PopoutHost`/`popoutChannel.ts`, BroadcastChannel).
- Arrangement **persists per-device (localStorage) + syncs across devices** (server prefs, WS-D).
- **Live SSE/generation state survives** dock↔float↔popout moves (streams hoisted above the layer).

⇒ The toolbox feel is mostly **flip the flag default ON + polish + apply the 5-section grouping** as
the panel menu. The flat `TabScrollStrip` is only the fallback.

## Finding 2 — no Media panel exists (genuinely new)
No media/asset generator+browser panel exists (only `MotifLibraryView` + `ArcTemplateLibraryView`
libraries). Generation backends exist + are wired in scattered spots: image (`booksApi.generateImage`),
video (`videoGenApi.generate` `/v1/video-gen/generate`), TTS (`useAutoTTS`). **No panel that
generates + browses media assets.** ⇒ "Media" is a new tool in the box.

## Reframe (supersedes the 3-role split in [03](03-compose-reframe.md))
"Produce" is **not a separate role** — it's a **tool in the Build toolbox**:
- **Talk** = the AI chat (core tool — [`04-ai-chat-core.md`](04-ai-chat-core.md)).
- **Build** = the toolbox of dockable panels; **Media (generate + browse)** is a new panel alongside
  Draft / Structure / Story Bible / Quality.

## Proposed approach
- **Reshape M2:** instead of "group a flat strip," make the **existing windowing the default Compose
  experience** (flip `loom.workspace.enabled` default ON + polish), with panels organized by the
  5-section grouping (`workspace/groups.ts`) as the toolbox's panel menu.
- **Media tool (was C5):** new **Media panel** = generator (reuse `booksApi.generateImage` /
  `videoGenApi` / TTS) + **asset browser**. New build; the browser likely needs a small
  **media-asset listing** (mini-investigation when scoped: does a generated-asset registry exist, or
  is it new?).

## Decisions

- **C5 (Media tool) — DEFERRED** _(PO, 2026-06-30)_. Defer reason: **out of scope for the core
  writing experience** — classic books have no media, so Media must not gate the journey. Revisit
  after the core compose journey (story 06) ships. C5-D1/C5-D2 (scope, asset binding) parked.
- **C2-D1 — Embrace the toolbox:** ⬜ still open (deferred behind the workflow/journey question in
  [`06-compose-journey.md`](06-compose-journey.md) — grouping a toolbox only matters once the tools
  have an order). _(rec: yes — already built.)_

## Open decisions
- [ ] C2-D1 — embrace the dock/float/pop-out toolbox as default Compose? _(after journey is settled.)_
- [x] C5 (Media) → **deferred.**
