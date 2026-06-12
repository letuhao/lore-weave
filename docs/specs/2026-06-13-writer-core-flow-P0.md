# Core writer flow (write-from-scratch / continue-writing) — what's missing · HIGH PRIORITY

**Date:** 2026-06-13
**Scope:** ONLY the writer's core loop — open a book, write prose, and use AI to *continue writing* / draft a
scene. Deliberately excludes worldbuilding, knowledge-graph, translation, dị bản.
**Status:** P0 triage. Re-prioritizes the writer branch ahead of the rerank/knowledge work.

---

## 0. Headline finding (the reframe that changes your priorities)

> **The core writer flow is NOT blocked by the reranker or the knowledge graph.** You believed you had to
> register a reranker and build a knowledge graph before you could write — **you don't.** Those gate
> *worldbuilding/grounding richness*, not writing. For write-from-scratch and continue-writing, the co-writer
> needs **exactly one thing: a chat (LLM) model.** Embedding, rerank, extraction, and the knowledge graph are
> all **optional and degrade gracefully.**

This is verified in code, not assumed:

- **Generation degrades gracefully with no knowledge.** The packer gathers context from 8 lenses; the
  knowledge ones return empty (not error) when there's no graph, and the packer only adds an advisory warning
  and continues. `services/composition-service/app/packer/pack.py:253-254`
  (`if not bundle.knowledge_seen: warnings.append("grounding_unavailable …")`),
  `app/packer/lenses.py:268` (`if not query.strip(): return [], False`).
- **Present-entity lookup falls back to glossary FTS** when there are no embeddings — no embedding model
  required. `lenses.py:129-131`.
- **Rerank is optional** — ≤1 candidate or any failure → pick candidate[0], never raises.
  `app/engine/select.py:145-169` (`return 0, "rerank_unavailable", False`). Cowrite mode doesn't rerank at all.
- **The co-writer Work creates a *bare, empty* knowledge project** with no embedding/rerank — the call sends
  only `{name, project_type:"book", book_id}`. `app/clients/knowledge_client.py:100`. Knowledge
  `ProjectCreate` defaults `extraction_enabled=false`, `embedding_model=null`. So it needs **no** rerank/embed setup.
- **The FE generate request carries no knowledge/embedding/rerank fields** — just scene + model + guide +
  reasoning. `frontend/src/features/composition/hooks/useCompositionStream.ts:70-93`.

### Minimum viable setup to write + AI-continue (this works today)
| Need | Required? | If absent |
|------|:--------:|-----------|
| Chat (LLM) model | ✅ **the only hard need** | model picker empty → Generate disabled |
| Co-writer Work | ✅ (one click "Set up co-writer") | empty-state button creates it |
| A scene | ✅ (inline "+ Scene") | "Pick a scene" hint; create inline |
| Embedding model | ❌ | grounding uses glossary FTS / degrades |
| Rerank model | ❌ | auto-mode picks candidate[0] |
| Knowledge graph / extraction | ❌ | grounding empty (advisory amber), generation proceeds |

**So the real writer blocker was never rerank.** It's that the platform never *tells* you writing is ready,
and the one genuine prerequisite (a chat model) has no in-flow setup path. Those are the P0s below.

---

## 1. What already works (don't rebuild)
- **Plain writing is fully independent of composition.** The Tiptap editor renders unconditionally; a writer
  can open a fresh chapter and type with zero AI/model/knowledge setup. `pages/ChapterEditorPage.tsx:878-908`.
- **Co-writer setup is one click.** Empty state → "Set up co-writer" → `POST /work`.
  `features/composition/components/CompositionPanel.tsx:79-97`.
- **Generate gating is honest and minimal** — needs a scene + a model, shows clear amber hints for each.
  `features/composition/components/ComposeView.tsx:48-54,156-163`.
- **Grounding-empty is already a graceful advisory**, with the right message ("No knowledge graph yet — run a
  knowledge extraction once … publishing chapters keeps canon up to date"). `GroundingPanel.tsx:38-47`.

---

## 2. The real gaps for the writer flow (HIGH PRIORITY)

Severity: **P0** = a greenfield writer hits a wall or wrongly believes they're blocked · **P1** = rough/unguided.

### P0

**WG-1 — Empty chat-model list dead-ends with no way out.**
If the user has no active chat model, the model picker is empty and Generate stays disabled with only a
"Pick a model" hint — **no link/affordance to register one.** This is the writer's *true* one prerequisite,
and the flow doesn't help them satisfy it. (Unlike rerank, chat models *can* be registered today — the path
just isn't surfaced from where the writer is.)
*Fix:* when the chat-model list is empty, replace the disabled picker with a "**Add a model to start writing →**"
CTA that deep-links to model registration and returns. One model, one click, back to drafting.
*Refs:* `CompositionPanel.tsx:171-182`, `ComposeView.tsx:156-163`.

**WG-2 — Knowledge/rerank *look* required; nothing says writing is ready.**
The user concluded they must build the knowledge graph before writing — a direct symptom of this gap. The
"you can write now, knowledge is optional/for-later" message exists only buried in the Grounding sub-tab.
*Fix:* surface a positive readiness cue in the Compose view ("**Ready to draft** — grounding gets richer after
you build a knowledge graph, but it's optional"). Never present embedding/rerank/extraction as a gate on the
writing path. This is mostly **copy + placement**, cheap and high-impact.
*Refs:* `GroundingPanel.tsx:38-47` (good message, wrong place).

### P1

**WG-3 — Work-setup is hard-coupled to knowledge-service health (502 risk).**
`POST /work` creates a bare knowledge project and **502s if that call returns None** (knowledge-service down/
unreachable) — which would block opening the co-writer entirely, *even though writing needs nothing from
knowledge*. `routers/works.py:139-160`, `knowledge_client.py:103-109` (returns None on any non-2xx/HTTP error).
*Fix:* make Work-setup resilient — create the Work with a null/lazy `project_id` and degrade grounding, rather
than failing the whole co-writer because an optional dependency is unavailable. **This fully decouples writing
from the knowledge-service the user is fighting.** (If the user's current "block" is actually a Work-setup
502, this — not rerank — is the culprit. Verify live.)

**WG-4 — No guided first-run after "Set up co-writer."**
Setup drops the writer into an empty Compose with three empty dropdowns and no next step.
*Fix:* auto-create a first scene, auto-select the only/registered model, and show a one-line "ready to draft"
cue — turn 3 empty selects into a primed Generate.

**WG-5 — "Continue writing" isn't a first-class verb.**
The flow is scene-centric ("pick a scene → Generate"). A writer continuing an existing chapter thinks
"continue from where my cursor is." Inline AI / selection tools partially cover this, but only once a Work
exists, and "continue from here" isn't an obvious primary action.
*Fix:* add a direct "**Continue from cursor**" affordance in the editor (uses recent-prose lens, no scene
pick needed) so continuing reads as continuing, not as scene management.
*Refs:* selection/inline layer gated on `composeProjectId` — `ChapterEditorPage.tsx:886-894`.

**WG-6 — Plain-write → AI handoff is discoverable only via the Co-write tab.**
Plain writing works with zero setup (good), but bridging into AI assist requires finding the Co-write tab and
running setup. Make the bridge a visible inline action from the editor.

---

## 3. Re-prioritization vs the blocker register

In `2026-06-13-writer-persona-use-cases-scenarios.md §5A`, **BL-1..BL-4 (rerank/knowledge QoL)** are hard
blocks for the **worldbuilder / grounding-richness** path — they are **NOT** blockers for the **core writer
flow**. For the writer branch, promote **WG-1 and WG-2 to the top**; they're smaller, cheaper, and unblock
writing *without* waiting on the rerank/knowledge fixes.

Sequence for the writer branch:
1. **WG-1 + WG-2** (model-empty CTA + "ready to write" messaging) — unblock + de-confuse. Small FE.
2. **WG-3** (Work-setup resilience) — removes the only hidden hard dependency on knowledge-service.
3. **WG-4 + WG-5 + WG-6** (guided first-run, continue-from-cursor, editor→AI bridge) — make it feel good.
4. *Then* return to BL-1..BL-4 for the worldbuilding/grounding-richness uplift.

---

## 4. Immediate next step — live-verify the write path

The code says a greenfield writer with one chat model can write + AI-continue today. Confirm it live on the
running stack with the test account:
1. New book + chapter → type prose (expect: works, no setup).
2. Co-write tab → "Set up co-writer" (expect: succeeds **iff** knowledge-service is up — if it 502s, that's
   **WG-3**, the real block, *not* rerank).
3. "+ Scene", pick the chat model → **Generate** (expect: prose streams back with empty grounding + advisory).
If any step fails, capture which one — it pinpoints WG-1 (no model), WG-3 (setup 502), or a deeper defect,
and tells us whether the writer is truly blocked or just under-guided.
