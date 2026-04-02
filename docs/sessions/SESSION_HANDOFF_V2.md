# Session Handoff — Session 16

> **Purpose:** Give the next agent complete context to continue.
> **Date:** 2026-04-03 (session 16 end)
> **Last commit:** `bec9eef` — MIG-02 Chat page migrated
> **Previous focus:** Phase 3.5 media blocks + design draft gap fixes + V1→V2 migration
> **Current focus:** V1→V2 migration in progress (2 of 10 done). Next: MIG-03..MIG-10.

---

## 1. What Happened This Session (session 16)

### Phase 3.5 Media Blocks — E4 + E5 COMPLETE (12 tasks)
| Task | What |
|------|------|
| E4-01 | Image block (resize, caption, alt text, selection ring) |
| E4-02 | Image upload (drag-drop, paste, MinIO, progress bar) |
| E4-03 | AI prompt field (reusable MediaPrompt component) |
| E4-04 | Classic mode guards (keyboard protection, placeholders) |
| E4-05 | Video block (player, upload, caption, AI prompt) |
| E4-06 | Code block (lowlight syntax highlighting — native Tiptap, no custom NodeView) |
| E4-07 | Slash menu + toolbar integration (media insert) |
| E4-08 | Source view (Block JSON viewer) |
| E5-01 | Media version tracking backend (block_media_versions table, CRUD) |
| E5-02 | Version history UI (timeline, comparison, prompt diff) |
| E5-03 | AI image generation (provider-registry → AI provider → MinIO) |
| E5-04 | Re-generate from prompt |

### Video Generation Service — Skeleton
- `video-gen-service`: Python/FastAPI, returns `status: "not_implemented"`
- Gateway proxy `/v1/video-gen` wired
- FE Generate button calls API, shows skeleton message

### Design Draft Gap Fixes (M1-M6)
| Fix | What |
|-----|------|
| M1 | Version history button in Classic mode placeholders |
| M2 | Guard toast notification on blocked keypress |
| M3 | Paste protection in Classic mode |
| M4 | Drag handles (tiptap-extension-global-drag-handle) |
| M5 | Copy filename button on Classic placeholders |
| M6 | Unsaved-changes dialog on AI→Classic mode switch |

### V1→V2 Migration (2 of 10 done)
| Task | What | Lines |
|------|------|-------|
| MIG-01 ✅ | Trash page (`/trash`) — 4 tabs, TrashCard, FloatingTrashBar, restore/purge | 683 |
| MIG-02 ✅ | Chat page (`/chat`) — session sidebar, SSE streaming, context integration | 2388 |

### Bug Fixes
- Code block: 5 iterations to fix focus/whitespace (final: no custom NodeView, native Tiptap)
- Image upload: `setImageUploadContext` not wired → wired in ChapterEditorPage
- MinIO URL: `minio:9000` (Docker internal) → `localhost:9123` (MINIO_EXTERNAL_URL)
- Mode switch: didn't update NodeViews → `_mode` transient attr forces re-render
- Image hover overlay: Replace + Delete buttons
- Dockerfile: Go 1.22 → 1.25 for minio-go v7.0.100
- Removed localStorage query cache persistence (caused stale data everywhere)
- Chapter cache invalidation after create/restore

### Planning Docs Added
- VG-01..VG-10: Video generation provider integration (10 tasks)
- MV-01..MV-07: Media version retention policy (7 tasks)
- VH-01..VH-12: Version history panel enhancements (12 tasks)
- MIG-01..MIG-10: V1→V2 migration plan (10 tasks, 2 done)

---

## 2. Key Architecture Changes

### Media Blocks (new in session 16)
```
components/editor/
  ImageBlockNode.tsx    — ReactNodeViewRenderer, resize, upload, alt, prompt, history
  VideoBlockNode.tsx    — Same pattern as image, HTML5 video player
  CodeBlockNode.tsx     — NO custom NodeView (native Tiptap CodeBlockLowlight)
  CodeBlockToolbar.tsx  — Floating toolbar on code block focus
  MediaPrompt.tsx       — Reusable AI prompt field (image + video)
  MediaGuardExtension.ts — Keyboard guards + toast + paste protection
  useResize.ts          — Shared resize hook
  VersionHistoryPanel.tsx — Split-panel version comparison
  VersionTimeline.tsx   — Dot timeline with tags
  PromptDiff.tsx        — LCS-based line diff
  SourceView.tsx        — Read-only Block JSON viewer
```

### Backend Changes
- `book-service`: MinIO upload endpoint, media version tracking, AI generation
- `video-gen-service`: New Python/FastAPI skeleton (port 8088/8213)
- Gateway: `/v1/video-gen` proxy added

### Cache Change
- **Removed** `PersistQueryClientProvider` (localStorage persistence)
- Now: plain `QueryClientProvider`, staleTime: 30s, refetchOnWindowFocus: true

---

## 3. What's Next

### Immediate — V1→V2 Migration (7 remaining, all S-size)

| Task | Route | Source Lines |
|------|-------|-------------|
| MIG-03 | `/usage` | 81 |
| MIG-04 | `/usage/:logId` | 59 |
| MIG-05 | `/settings/:tab` | 54+ |
| MIG-06 | `/browse` | 45 |
| MIG-07 | `/browse/:bookId` | 81 |
| MIG-08 | `/s/:accessToken` | 68 |
| MIG-09 | Chapter translations | 245 |
| **MIG-10** | **Delete old `frontend/`** | — |

After MIG-10, the old `frontend/` directory is deleted entirely.

### Then
- P3-08a/b: Genre Groups (BE+FE)
- Translation Workbench
- Phase 4: Settings, Usage, Browse polish
- Phase 4.5: Audio/TTS

---

## 4. Key Files for Next Agent

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project rules, 9-phase workflow |
| `docs/sessions/SESSION_PATCH.md` | Current status |
| `docs/03_planning/99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | Full task list (152 tasks) |
| `frontend-v2/src/components/editor/` | All editor components (media blocks, code, guards) |
| `frontend-v2/src/features/chat/` | Chat page (23 files, migrated from v1) |
| `frontend-v2/src/features/trash/` | Trash page (5 files, migrated from v1) |
| `services/video-gen-service/` | Video generation skeleton |
| `services/book-service/internal/api/media.go` | Media upload + version tracking + AI generation |

---

## 5. Important Decisions Made This Session

| Decision | Reasoning |
|----------|-----------|
| Code block: no custom NodeView | 5 iterations of ReactNodeViewRenderer all broke focus/whitespace. Native Tiptap rendering works perfectly. Header bar via floating CodeBlockToolbar instead. |
| Removed localStorage cache persistence | PersistQueryClientProvider caused stale data on every mutation (create, restore, trash). In-memory cache with 30s staleTime is simpler and correct. |
| Default editor mode → AI | Design spec says "Default: AI Assistant for new users". Classic mode is opt-in. |
| video-gen-service as skeleton | Interface stable now, FE wired. Real provider integration later (VG-01..VG-10). |
| MinIO external URL | Browser can't resolve Docker-internal `minio:9000`. Added `MINIO_EXTERNAL_URL=http://localhost:9123`. |
| `_mode` transient attr for mode switch | React NodeViews don't re-render on storage change. Touching `_mode` attr forces React re-render. Stripped from saved JSON. |
| Backspace protection in AI mode too | Atom blocks (image, video) protected in both modes. Code blocks only in Classic. |
