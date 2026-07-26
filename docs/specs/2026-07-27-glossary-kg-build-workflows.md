# Glossary-Build + KG-Build deterministic workflows — spec

**Date:** 2026-07-27 · **Status:** CLARIFY/POC · **Origin:** Mị Đế author-dogfood pivot
(PO decision — see `docs/sessions/2026-07-26-mide-author-dogfood.md`, findings 1–23).

## Why (the proven failure)

A weak local model (gemma-4-26b) in the conversational agent **cannot reliably CHOOSE tools**,
even after 10 platform fixes made the surface correct (breaker coverage, budget exemptions,
schema projection, repeat steps…). A fresh session still picked `glossary_propose_entity_edit`
to CREATE a character. Tool-choice is the unfixable link; content generation is not — the same
model produced a 7-attribute rich character when the call happened.

**Therefore: move the state machine OUT of the agent** (the PlanForge pattern — compile → passes
→ Pass Rail checkpoints). The LLM only fills content inside a step; the platform makes every
tool call deterministically; the human approves at checkpoints.

## The two dimensions (PO requirement)

| Dimension | What | Failure it prevents |
|---|---|---|
| **Vertical (depth)** | The model reasons IN FOCUS on ONE entity per call — one character, one event, one faction — producing rich, detailed attributes. | Asking for depth across many entities at once ⇒ shallow, no-detail output. |
| **Horizontal (breadth)** | Many glossary entries built across a scene/story — coverage of everything the text establishes. | Asking one call to enumerate AND detail ⇒ truncation, loops, missed entities. |

**Hard rule (PO): a single LLM call NEVER both reasons deeply and fans out.** Reasoning steps
and action steps are separate calls; breadth is a LIST decision, depth is a PER-ITEM build.

## Planner / Executor split (PO requirement — "steering control is the hard part")

```
                    ┌─ PLANNER (breadth) ──────────────────────────────┐
 story text ──────▶ │ 1 LLM call: enumerate WHAT to build              │
 existing glossary  │ out: worklist [{name, kind, priority, why}]      │
                    └──────────────┬───────────────────────────────────┘
                                   │ platform validates (kinds exist, dedup vs glossary)
                                   ▼  human checkpoint #1: approve/trim the worklist
                    ┌─ EXECUTOR (depth), per worklist item ────────────┐
                    │ 1 LLM call per entity: build THIS one richly     │
                    │ out: {name, kind, attributes{…}, relations[…]}   │
                    └──────────────┬───────────────────────────────────┘
                                   │ platform: glossary_propose_entities (1 item/call, draft)
                                   ▼  human checkpoint #2: review inbox (existing panel)
                    ┌─ KG PHASE (deterministic + 1 LLM relation step) ─┐
                    │ ensure-project → entities-to-nodes →             │
                    │ relations from executor output → propose edges   │
                    └──────────────┬───────────────────────────────────┘
                                   ▼  human checkpoint #3: approve edges
```

- The **executor emits relations as NAMES** (source=self, target=name, type from a closed set);
  the platform resolves names→entity ids AFTER all entities exist (kills the
  "Lâm gia is not a node" / name-instead-of-UUID class permanently — the model never sees ids).
- Steps are resumable rows (an FSM table, like authoring-runs): `planned → approved →
  building(i/N) → proposed → reviewed → kg_projected → edges_proposed → done`. Every LLM call
  is bounded (1 entity), retried once on invalid JSON, then skipped-with-record (no loops possible).

## POC BEFORE BUILD (PO requirement)

Call gemma **directly through LM Studio** (localhost:1234, $0, `_NO_THINK`) to validate the
decomposition before any service code:

| Exp | Shape | Question |
|---|---|---|
| **E1 vertical** | 1 call: build Tô Thanh Dao alone, full attribute JSON | Is a focused call rich + valid? |
| **E2 horizontal-naive** (predicted failure) | 1 call: build ALL Mị Đế entities with full detail | Does depth collapse / output truncate? |
| **E3 planner→executor** | 1 planner call (worklist only) + 1 executor call per item | Same coverage as E2, depth of E1? |

**Success criteria:** E3 ≥ E1 depth per entity (attribute count + chars/attribute), E3 coverage ≥
E2 coverage, all E3 outputs parse as valid JSON, zero refusal/loop. E2 is expected to lose on
depth — that measured gap IS the justification for per-item execution.

*(A POC script under `eval/` calling LM Studio directly is test tooling — the production pipeline
resolves the model via provider-registry like every other pipeline; no invariant exception.)*

## Ownership & surfaces (design sketch — firmed at DESIGN after POC)

- `glossary-service`: owns the glossary-build FSM + planner/executor prompts (Python? **No — glossary-service is Go.**
  The LLM steps live in an AI service; the FSM's natural home is **composition-service** (Python, owns
  authoring-run FSM + seams) calling glossary/knowledge via internal APIs — OR knowledge-service.
  **DESIGN DECISION after POC**, guided by the language rule (Python = AI/LLM) + provider-registry invariant.)
- FE: a **World Setup wizard panel** (Pass Rail UX): paste text → see worklist → approve → watch
  per-entity build progress → review inbox → edges review. Existing AI-suggestions panel upgraded
  to show full proposed attributes (dogfood finding #17).
- Chat: unchanged (supporter for atomic edits). The rail can later delegate to this pipeline.

## Out of scope (this cycle)

- Wiki/enrichment integration, translation of built entities, multi-book batch runs.
- Replacing the chat rail (it stays for strong models).

## POC results (2026-07-27, gemma-4-26b-a4b-qat via LM Studio, `eval/glossary_build_poc.py`)

| | Coverage | Avg attrs/entity | Avg chars/attr | Valid JSON | Loops |
|---|---|---|---|---|---|
| **E1 vertical** (1 entity, focused) | 1 | **8** | 74 | ✅ | 0 |
| **E2 horizontal-naive** (all-in-one) | 9 | **3.2** (first=7 → last=1, monotonic collapse) | 76 | ✅ | 0 |
| **E3 planner→executor** | **13** (planner) · 6/6 built | **5.7** (characters 8) | **116** | ✅ 6/6 | 0 |

**Verdict — the PO's decomposition is validated on BOTH axes:**
- **Depth**: E2's per-entity detail collapses monotonically (later entities get 1-2 thin
  attributes); E3 matches/exceeds the E1 focus baseline (characters hit 8 attrs, 84-90 chars/attr).
- **Breadth**: the planner found **13** entities vs E2's 9 — it caught Chân Linh, Tô gia and the
  relationship entities E2 skipped, because enumerate-only is a cheap focused task too.
- Relations come back as **names** (e.g. Tô Thanh Dao → 3 relations) — the name-resolve-later
  design works with zero id exposure.
- Cost: ~5s/entity local; a 13-item build ≈ 70s of LLM time, fully parallelizable later.

**⇒ Proceed to DESIGN with this exact two-phase shape; E2-style single-call breadth is dead.**

### E4 — steered deep-build (PO experiment: plan → steer per section, one conversation)

1 plan call (outline the profile as 6-8 sections with focus questions) + 1 steered call per
section in the SAME conversation, profile-so-far in context (Tô Thanh Dao, same entity as E1):

| | E1 single-shot | **E4 steered loop** |
|---|---|---|
| Output | 8 attrs × 74 chars ≈ **590 chars** | 6 sections × 1,148 chars = **6,887 chars (≈10×)** |
| Structure | flat attribute values | Diện mạo · Năng lực/tu luyện · Tâm lý/hệ giá trị · Quan hệ/động lực · Biến cố · Mặt tối/điểm yếu |
| Quality | correct but thin | **invents consistent canon-fitting specifics** ("Trận pháp Ứng dụng Hệ thống", "Chủ nghĩa Thực dụng Cực đoan", "Thiên Linh Động", "Điểm mù của sự kiểm soát") — cross-section consistent (accumulated context works) |
| Cost / risk | 4.2s | 33s total (plan 4.7s + 6×~5s), **all finish=stop, zero loops** |

**Design consequence — the executor gets a DEPTH DIAL, assigned by the planner per item:**
- `depth: "standard"` — single-shot (E1/E3 shape, ~5s) for minor entities (a terminology, a prop).
- `depth: "deep"` — plan+steer loop (E4 shape, ~35s) for major entities (protagonists, factions,
  the power system). The steering loop is bounded by its OWN plan (6-8 sections, one call each,
  one retry per section) — same no-loop guarantee, just more steps.
The planner's worklist item shape gains `depth` (closed set: standard|deep) + `priority`.
