# Session Handoff — Session 34 (Final)

> **Purpose:** Give the next agent complete context to continue.
> **Date:** 2026-04-13 (session 34)
> **Last commit:** `0f1fcc3` — knowledge-service two-layer glossary anchoring pattern
> **Total commits this session:** 22
> **Previous handoff:** SESSION_HANDOFF_V5.md (session 33 — Voice Pipeline V2 complete)

---

## 1. What Was Done This Session

### Part A — Chat page re-architecture (MVC discipline)
Session 33 left a chat page review document identifying 5 structural problems. This session implemented the fix:

- **Context split by update frequency** — `ChatSessionContext` (stable: session, CRUD, models) + `ChatStreamContext` (volatile: streaming text, updates every SSE chunk). Prevents consumers from re-rendering on every chunk.
- **Never-unmount rule** — `ChatView` replaces `ChatWindow` and stays mounted at all times. Loading uses CSS `hidden`, not conditional render. Fixes the voice overlay unmount bug from session 33.
- **Hooks as controllers** — `useChatSession`, `useChatStream`, `useVoiceAssistMic` each own state/effects/cleanup. ChatPage shrunk from 315 lines to 81 lines (layout shell only).
- **Voice assist unified** — `useVoiceAssistMic` now uses the same `VadController` + backend STT pipeline as Voice Mode. Input bar mic and voice overlay share code. Fixes "browser Web Speech API vs backend STT" divergence.
- **Voice Assist TTS now backend-driven** — new endpoint `POST /voice/generate-tts` in chat-service; audio stored in S3, `/voice/audio-segments` replay endpoint used for playback. Follows cloud-deployment principle: everything in BE, FE just renders.
- **422 fixes** — STT and TTS requests now include `model` field (required by OpenAI-compatible provider proxy). Voice prefs save `provider_model_name` when user selects STT/TTS model in settings.

**CLAUDE.md updated** with Frontend Architecture Rules (React MVC):
- Separation of concerns (components render, hooks own logic, context shares state)
- Never conditionally unmount stateful components
- No useEffect for event handling
- Split context by update frequency
- No prop-drilling middlemen
- Max ~100 lines per component, ~200 per hook

### Part B — Knowledge Service design (end-to-end, no code yet)

Starting from the question "is our 50-message replay actually memory?" this session designed a complete knowledge service:

**Architecture document** — `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md` (~5500 lines):
- Inspired by MemPalace (acknowledged) but built from scratch for our scale
- L0/L1/L2/L3 memory stack (global → project → facts → semantic)
- Three memory modes: no_project / static (glossary fallback) / full (extraction enabled)
- Opt-in extraction per project (BYOK cost control)
- Per-project embedding model choice from curated list (5 models, dimension-indexed Neo4j indexes 384/1024/1536/3072)
- Pattern-based Pass 1 (quarantined) + LLM-based Pass 2 (validates) extraction
- Prompt injection defense (`<untrusted>` wrapper, neutralization patterns)
- Honest "trust me" privacy model (hobby scope)
- XML memory block format with temporal grouping, negative facts, CoT instructions
- Cross-user isolation (mandatory `user_id` filter, CI lint, integration tests)
- 5 review rounds applied: data engineer (10 issues), context engineer (10 issues + 5 recs), solution architect (cost + privacy + scale), 6-perspective review (29 issues), research validation

**Three PM-grade implementation checklists** (written specifically to preserve knowledge across sessions):
- `KNOWLEDGE_SERVICE_TRACK1_IMPLEMENTATION.md` — K0-K9, 64 tasks, 5 gates (Static Memory: no extraction, no Neo4j, no AI cost)
- `KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md` — K10-K18, 81+ tasks, 8+ gates (Extraction Infrastructure: opt-in, requires D2/D3)
- `KNOWLEDGE_SERVICE_TRACK3_IMPLEMENTATION.md` — K19-K22, 69 tasks, 9 gates (Advanced Features)

Each task includes: file paths, description, acceptance criteria, tests, dependencies, estimate, notes.

**UI mockup** — `design-drafts/screen-knowledge-service.html` (1767 lines, 14 sections):
- Projects tab with 4 state cards (disabled/building/complete/paused-budget)
- **3-step build wizard** with target cards (timeline/entities/relationships/lore/summaries), chapter range, **dual-list glossary picker** (filter/sort/pagination, auto-pin suggestions for sparse-but-long-reaching entries — the "god in ch1/ch5000" case), budget & models with live cost estimate
- Extraction Jobs tab (running/paused/complete) + cost widget
- Global bio (L0) editor with version history
- **Entities tab as semantic layer** with ⭐ canonical / 💭 discovered / 📦 archived badges, anchor_score pills, Promote button
- Timeline view, Evidence browser
- **Pending Proposals** tab — unified inbox for KS-submitted glossary drafts + wiki stubs with deep links to review in their respective UIs
- **Glossary Gap Report** — summary cards + bulk-promote table + conflict detection + research citations explaining the feedback loop
- Chat header indicator (3 memory modes) + popover
- Memory block XML preview (Mode 2 + Mode 3, syntax-colored)
- Privacy page with "Trust Me" model
- Mobile phone frames, full state legend (13 states)

### Part C — Two-layer anchoring pattern (the critical design decision)

After the UI was drafted, the user raised a concern: does the knowledge service duplicate glossary and wiki? This triggered a deep investigation:

- **Glossary service source code reviewed** — found it already has `glossary_entities` with `status` (draft/active/archived), `confidence` on translations, `chapter_entity_links`, `attribute_definitions` EAV, `extraction_audit_log`, tiered chapter-contextual ranking, and **wiki tables inside it** (`wiki_articles`, `wiki_revisions`, `wiki_suggestions`). There is no separate wiki service.
- **First proposal** — drop KS entities tab entirely, write everything to glossary. User pushed back: entities are an **extension** of glossary — more general, semantic search, partial substring, allows minor mentions that don't deserve curation.
- **Research round** — delegated to research agent, found the pattern is validated:
  - **MemGPT/Letta** — "core memory" (authored) + "archival memory" (extracted), clearest match
  - **Microsoft GraphRAG** — `seed_graph` config pre-populates entities, ~34% duplicate reduction on LOTR fiction (arXiv:2404.16130)
  - **HippoRAG** — named anchor nodes give 18-25% improvement on multi-hop QA (arXiv:2405.14831)
  - **Lettria Qdrant case study** — 20% KG-QA gain pre-loading Postgres canonicals into Neo4j
  - Systems NOT doing this: LightRAG (different "dual-level"), Mem0 (flat), NotebookLM (flat)
- **Final design** (committed as `0f1fcc3`):
  - Glossary remains authored SSOT (small, precise, reader-visible, human-edited)
  - KS adds a fuzzy/semantic entity layer in Neo4j (large, every surface form, embeddings)
  - Linkage via nullable `glossary_entity_id` FK on `:Entity`
  - `anchor_score` float: 1.0 if linked to glossary, else `mention_count / max_mention_count`
  - RAG retrieval ranks by `similarity × anchor_score` → canonical entries float above fuzzy matches in single query path
  - Sync is one-way authoritative: glossary → entity (authoritative refresh), entity → glossary (proposal only)
  - Pre-loading: Pass 0 of every extraction job loads glossary as anchor nodes first, biasing the resolver toward known canonicals
  - Archive cascade: when glossary entry is deleted, KS entity is **soft-archived** (`archived_at` set, `anchor_score = 0`), NOT cascade-deleted, because graph edges + timeline events have independent value. Hidden from default RAG queries via `WHERE archived_at IS NULL`.
  - Cross-service sync contract documented in KSA §6.0 with Python skeleton for anchor pre-loader

**Architecture doc updates:**
- §3.4.B: added `glossary_entity_id`, `anchor_score`, `archived_at` to `:Entity`
- §3.4.D: L2 query filters `WHERE archived_at IS NULL`
- §3.4.E (new): Two-Layer Anchoring — comparison table, linkage model, sync direction, anchor pre-loading rationale with research citations
- §3.4.F (new): Archive Cascade
- §6.0 (new): Cross-Service Sync Contract — full HTTP contract, event handlers, anchor pre-loader Python skeleton, failure modes table

**Track 2 updates:**
- K11.5 extended with anchor/archive methods (`upsert_glossary_anchor`, `link_to_glossary`, `unlink_from_glossary`, `archive_entity`, `restore_entity`, `recompute_anchor_score`, `find_gap_candidates`)
- K11.10 (new): glossary service client (HTTP + event subscriber) + `create_evidence` method for automatic quote capture
- K13.0 (new): Pass 0 anchor pre-loader with ≥20% dedup smoke test target
- K13.1 (new): anchor score nightly refresh
- Gate 7 extended with 3 new acceptance criteria

**HTML updates:**
- Entities tab reframed as semantic layer with canonical/discovered/archived filter
- New Pending Proposals section
- New Glossary Gap Report section with research citation callout
- Build wizard target cards now show "→ glossary" / "→ wiki stubs" routing badges

### Part D — Evidence storage investigation

User asked: current glossary FE shows "X evidence" count — what's actually in the DB? Investigation found:

- **Full evidence list exists** in `glossary.evidences` table tied to attribute values (not entities directly). Columns: `evidence_id`, `attr_value_id`, `chapter_id`, `chapter_title`, `block_or_line`, `evidence_type` (quote/summary/reference), `original_language`, `original_text`, `note`, `created_at`. Also `evidence_translations` sub-table with verification status.
- **API already returns nested structure** — `GET /v1/glossary/books/{book_id}/entities/{entity_id}` returns `attribute_values[].evidences[].translations[]`. The FE currently only renders `evidences.length`.
- **Creation is manual only** today (no automatic extraction writes to `evidences`).
- **KS extension** — when KS extraction proposes an attribute value, it can also `POST /entities/.../evidences` with the chapter quote that supports it. The glossary reviewer sees the supporting text inline during draft review.

Two follow-up tasks created:
- **G-EV-1** (glossary FE, ~2-3 days): build evidence browser modal — filter by type/chapter/language, sort by created_at/chapter, pagination. FE-only task, API already returns everything needed.
- **KS-EV-1**: extended K11.10 in Track 2 to include `create_evidence(...)` method and acceptance criteria. Dependency added: K11.10 depends on G-EV-1 so reviewers can see KS-created quotes.

---

## 2. Known Issues / Open Items

### From Session 33 (carried forward)
- TTS quality still suboptimal with local TTS service (need OpenAI/ElevenLabs test for comparison)
- GDPR delete button not in Settings UI (endpoint exists)
- Voice Assist "always-on VAD" not implemented (prefs exist, UI toggle missing)

### New from Session 34
- **Knowledge service has 0 lines of code written** — design is complete but implementation has not started
- **CLAUDE.md still references knowledge-service as "planned"** — no scaffolding yet
- **Chat session memory is still 50-message replay** — the "real memory" work is the knowledge service, which is not yet built

---

## 3. What to Do Next Session

### Priority 1 — G-EV-1: Glossary FE evidence browser (pre-requisite for KS)

**Why first:** Knowledge-service task K11.10 (Track 2) now has a dependency on G-EV-1 because KS-EV-1 will create evidence rows automatically — those rows must be visible in the glossary UI for reviewers to actually use them during draft approval. Building KS first would create data that has no UI.

**Scope (FE-only, no backend changes needed):**
1. Find where the current evidence count is displayed in `frontend/src/features/glossary/` and locate the entity detail component
2. Build an evidence browser modal or side panel that iterates the already-nested `attribute_values[].evidences[]` array from the entity detail API response
3. Render cards per evidence: `chapter_title`, `block_or_line`, `evidence_type` badge, `original_text` (expandable), `translations[]` with confidence badges, `created_at`
4. Add filters: `evidence_type` (quote/summary/reference), `chapter_title` (dropdown from unique values), `original_language`
5. Add sort: `created_at`, `chapter_title`, `block_or_line`
6. Add client-side pagination (evidence arrays typically <100 per attr — fallback to server-side only if any exceeds 500)
7. Wire the "X evidence" count chip in the entity editor to open the browser
8. Smoke test with real data using the test account

**Files to expect:**
- `frontend/src/features/glossary/components/EvidenceBrowser.tsx` (NEW)
- `frontend/src/features/glossary/components/EntityEditor.tsx` (MODIFIED — wire the chip)
- Possibly `frontend/src/features/glossary/hooks/useEvidenceFilter.ts` (NEW — filter/sort logic if complex)

**Estimate:** 2-3 days following the 9-phase task workflow.

### Priority 2 — Begin Knowledge Service implementation (Track 1 K0)

After G-EV-1 ships, start Track 1 from the beginning. Track 1 (K0-K9) builds "Static Memory" — plain-text L0 + L1 bios, no extraction, no Neo4j, zero AI cost. This gets the service scaffolding in place without any of the extraction complexity.

Read in order:
1. `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md` §1-4 (problem, scope, schemas, memory stack)
2. `docs/03_planning/KNOWLEDGE_SERVICE_TRACK1_IMPLEMENTATION.md` — execute tasks K0 through K9 in order
3. Reference `docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md` for foundation schemas if needed

Track 1 completion gives you: `knowledge-service` Python/FastAPI scaffolding, Postgres migrations for `knowledge_projects` / `knowledge_summaries` / `extraction_pending` / `extraction_jobs`, `/internal/context/build` endpoint returning L0+L1 plain text, chat-service integration via `useKnowledgeContext`. No AI cost, no Neo4j, no embedding model — that's Track 2.

### Priority 3 — Then Track 2 K10 onward

Only after Track 1 works end-to-end. Track 2 requires D2/D3 from the data re-engineering plan (Neo4j setup + event pipeline). Check `docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md` for prerequisites before starting K10.

---

## 4. Key Files Modified This Session

### Backend (chat-service)
- `app/services/voice_stream_service.py` — added `generate_tts_for_message` function for backend TTS with S3 storage
- `app/routers/voice.py` — new `/generate-tts` endpoint

### Frontend (chat page refactor)
- `pages/ChatPage.tsx` — reduced from 315 → 81 lines (layout shell)
- `features/chat/providers/ChatSessionContext.tsx` — NEW (stable context: session, CRUD, models)
- `features/chat/providers/ChatStreamContext.tsx` — NEW (volatile context: streaming messages)
- `features/chat/components/ChatView.tsx` — NEW (replaces ChatWindow, never unmounts)
- `features/chat/hooks/useVoiceAssistMic.ts` — NEW (unified STT via VadController + backend STT)
- `features/chat/hooks/useAutoTTS.ts` — modified to use backend TTS + model field
- `lib/audioUtils.ts` — shared `float32ToWavBlob` + `transcribeAudio` with model field
- `features/chat/components/VoiceSettingsPanel.tsx` — STT/TTS model saves `provider_model_name`
- `features/chat/voicePrefs.ts` — added `sttModelName`, `ttsModelName`

### Planning / Design (knowledge service)
- `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md` — ~5500 lines (NEW)
- `docs/03_planning/KNOWLEDGE_SERVICE_TRACK1_IMPLEMENTATION.md` — 2006 lines (NEW)
- `docs/03_planning/KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md` — 2380+ lines (NEW, extended with anchor pattern + K11.10 + K13.0/K13.1)
- `docs/03_planning/KNOWLEDGE_SERVICE_TRACK3_IMPLEMENTATION.md` — 1968 lines (NEW)
- `design-drafts/screen-knowledge-service.html` — 1767+ lines (NEW)

### Project-level
- `CLAUDE.md` — Frontend Architecture Rules section added; knowledge-service row annotated with two-layer pattern; note that wiki lives inside glossary-service

---

## 5. Important Decisions & Rationale (for future reference)

### Why build knowledge-service from scratch instead of forking MemPalace
- MemPalace uses SQLite; LoreWeave is Postgres+Neo4j polyglot at 5000-chapter scale
- We need multi-user, per-project scoping, BYOK cost control, opt-in extraction — all absent in MemPalace
- Fork would cost more than rewriting the ideas in our architecture

### Why reject Mem0 as an alternative
- Single flat fact store; no knowledge graph support
- Cannot scale to 5000-chapter novels where relationship graphs are essential
- User explicit call: "Mem0 cannot scale up our work"

### Why opt-in extraction per project (not automatic)
- User has BYOK credits; automatic extraction on every chapter burns money unpredictably
- User explicit call: "we already a SSOT as postgresql, we don't need build knowledge graph automatic but allow user build that they want"

### Why curated embedding model list (5 models) not arbitrary
- Dimension-indexed vector columns in Neo4j require known dimensions
- Supports: bge-m3 (1024, free, default), OpenAI small/large (1536/3072), voyage-3 (1024), cohere (1024)
- Extensible later

### Why two-layer pattern (glossary + entity) not merge
- User explicit call: entities are **extension** of glossary — more general, support semantic search, partial substring, allow minor mentions that don't deserve curation
- Research validated: GraphRAG, HippoRAG, Lettria all show the pattern works and improves quality

### Why soft-archive (not cascade-delete) when glossary entry is deleted
- User explicit call: "suggest mark it archived to avoid RAG query it, can reduce RAG quality if we don't archived"
- Preserves graph edges, timeline events, embeddings that have independent value
- Hidden from default RAG via `WHERE archived_at IS NULL`, user can restore

### Why honest "trust me" privacy model
- User explicit call: hobby project, no money for audits, no BAA needed
- If sharing enterprise later, revisit then

---

## 6. Test Account

```
email:    claude-test@loreweave.dev
password: Claude@Test2026
name:     Claude Test
```

---

*Session 34: 22 commits. Chat page MVC refactor + knowledge service design end-to-end (architecture + 3 Track plans + UI mockup + two-layer anchoring pattern validated by research). Implementation starts next session with G-EV-1, then Track 1 K0.*
