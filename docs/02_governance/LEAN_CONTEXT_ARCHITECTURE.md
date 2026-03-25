# Lean Context Architecture — Token-Efficient Documentation Strategy

> Status: Proposal | Applies to: Phase 1 onward | Author: Context Engineer (Assistant) | DA Review Required

---

## 1. Problem Statement

Current documentation generates **11–12 documents per module**, each with:
- Full metadata headers + change history tables (repeated in every file)
- Prose explanations of patterns already established in governance docs
- Content that is semantically redundant across files (e.g., scope described in execution pack, API contract, acceptance test plan, and readiness gate)

**Root cause**: Enterprise-grade doc templates applied to a 2-person solo model (1 DA + 1 AI). The structure was designed for team coordination overhead that doesn't exist here.

**Measured impact estimate**: A typical module session loads 4–6 files × 800–1,500 lines = 6,000–9,000 lines of context before any implementation prompt. With Claude's token cost, this is 15,000–25,000 tokens of governance overhead per session.

---

## 2. Design Principles for Lean Docs

| Principle | Meaning |
|---|---|
| **Single source of truth** | A fact lives in one place only. Other docs reference it, not copy it. |
| **Load by tier** | Load only what the current task needs. Session scope determines doc scope. |
| **Machine-scannable first** | Structured data (YAML, tables, checklists) over prose. AI extracts faster. |
| **Delta over replacement** | Update diffs, not full regeneration. Status changes = one-line edit. |
| **Human readable = navigable** | Humans need to find things quickly, not read everything. Use anchors and short summaries. |

---

## 3. Tiered Context Model

```
┌─────────────────────────────────────────────────────────┐
│  TIER 0 — Project Invariants (load once per project)    │
│  Scope dictionary · Mission · Out-of-scope · DA rule    │
│  Size target: < 150 lines                               │
├─────────────────────────────────────────────────────────┤
│  TIER 1 — Phase Context (load once per phase)           │
│  Active modules · Risk register · Decision log          │
│  Size target: < 200 lines                               │
├─────────────────────────────────────────────────────────┤
│  TIER 2 — Module Brief (load per module)                │
│  Replaces 11 docs with 1 structured file                │
│  Size target: < 400 lines                               │
├─────────────────────────────────────────────────────────┤
│  TIER 3 — Session Patch (load per task/conversation)    │
│  Current sub-phase · Open blockers · Last decision      │
│  Size target: < 80 lines                                │
└─────────────────────────────────────────────────────────┘
```

**Total context per typical session: ~830 lines vs current ~6,000+ lines**
**Estimated token reduction: 80–85%**

---

## 4. Document Format Changes

### 4.1 Replace metadata blocks with compact frontmatter

**Current pattern (every file, ~15 lines):**
```markdown
## Document Metadata
- Document ID: LW-XX
- Version: X.Y.Z
- Status: Draft
- Owner: SA
- Last Updated: 2026-03-21
- Approved By: DA
- Summary: ...

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | ... | Initial | ... |
```

**New pattern (every file, 3 lines):**
```yaml
---
id: LW-M05-BRIEF  status: active  owner: EA  approved: 2026-03-25
---
```

Change history is replaced by `git log` — the repo IS the change history.

---

### 4.2 Module Brief — Single Consolidated File

Replace 11 module documents with **1 Module Brief** structured in sections:

```markdown
# Module Brief: M05 — Glossary & Lore Management
---
id: LW-M05  status: in-progress  phase: 3  sp-active: SP-5
---

## Outcome
Creators can manage glossary entries, lore entities, and chapter links with
multilingual translations and RAG export for downstream AI grounding.

## Scope
IN: kinds(glossary|character|place|event|item), CRUD, chapter-links,
    attribute-values, translations, evidence-links, RAG export
OUT: public search, reader-facing wiki, AI-generated entries

## Acceptance (condensed)
- [ ] AT-M05-01: Create/read/update/delete entity by kind
- [ ] AT-M05-02: Chapter link attach/detach with position
- [ ] AT-M05-03: Translation CRUD per locale
- [ ] AT-M05-04: RAG export returns grounded chunks with evidence

## API Surface (refs contract file)
→ contracts/lore-svc/openapi.yaml

## Sub-phases
| SP | Scope | Status |
|---|---|---|
| SP-1 | Service skeleton + kind enum | done |
| SP-2 | Entity CRUD + filters | done |
| SP-3 | Chapter links | done |
| SP-4 | Attribute values + translations | done |
| SP-5 | Evidences + RAG export + smoke | in-progress |

## Risks (open only)
- R-M05-01: RAG chunk format not yet validated with downstream consumers [medium]

## Decisions
- DEC-M05-01: Evidence links stored as soft references (no FK cascade) [2026-03-20]
```

**Human readable**: Section headers make it scannable in 30 seconds.
**AI efficient**: Structured, no prose repetition, references instead of copies.

---

### 4.3 Compact RACI Notation

Replace `06_OPERATING_RACI.md` table format with inline notation in context where needed:

```
roadmap-priority:    A=DA  R=EA
module-slicing:      A=DA  R=EA  C=EA(arch)
api-contracts:       A=DA  R=EA
fe-be-readiness:     A=DA  R=EA
release-go-nogo:     A=DA  R=EA
```

In a solo 2-person model, all R are EA and all A are DA. The full RACI file is only needed at phase boundaries for explicit confirmation.

---

### 4.4 Phase Context File (replaces execution pack)

```markdown
# Phase 1 Context
---
status: in-progress  modules: M01(done) M02(done) M03(done)
---

## Active Constraints
- FE + BE must develop in parallel per module
- No module closure without smoke test passing
- DA approval required for scope change

## Open Decisions
- (none)

## Risk Register (open items)
- R-01: Scope drift [medium/high] · mitigation: weekly review gate
- R-03: Governance cadence degradation [medium/high] · mitigation: checklist in session patch

## Recent Decisions (last 5)
- DEC-003: Roadmap style → phase-based [2026-03-21]
- DEC-M05-01: Evidence links as soft refs [2026-03-20]
```

---

## 5. Session Patch Pattern

At the start of each work session, load a 1-file **session patch** that gives AI exactly what changed since last time:

```markdown
# Session Patch — 2026-03-25

## Where we are
Module: M05-SP-5
Last completed: evidence link POST endpoint + unit tests
Next: RAG export endpoint + smoke test

## Open blockers
- None

## Context to load
- Tier 0: docs/02_governance/PROJECT_INVARIANTS.md
- Tier 1: docs/02_governance/PHASE3_CONTEXT.md
- Tier 2: docs/03_planning/MODULE05_BRIEF.md
- Contracts: contracts/lore-svc/openapi.yaml (sections: /entities, /export)
```

This replaces the need to re-explain project context at each session start.

---

## 6. Local Model for Context Management (Recommendation)

### 6.1 The Problem It Solves

Even with lean docs, context can grow as modules accumulate. A local model can act as a **context router** — extracting only the relevant sections from docs before sending to Claude, further reducing token usage.

### 6.2 Recommended Setup

**Tool: [Ollama](https://ollama.com)** — free, runs locally, no API cost.

**Recommended models** (choose by hardware):
| Model | RAM Required | Best For |
|---|---|---|
| `qwen2.5:3b` | 4 GB | Fast summarization, structured extraction |
| `phi-3.5-mini` | 4 GB | Instruction following, doc filtering |
| `llama3.2:3b` | 4 GB | General purpose context compression |
| `qwen2.5:7b` | 8 GB | Higher quality, slower |

### 6.3 Use Cases

**Use Case A — Section Extraction**
> "From this 400-line Module Brief, extract only the API surface and acceptance criteria for SP-5"

The local model returns a 30-line extract. You send the extract to Claude, not the full file.

**Use Case B — Session Patch Generation**
> "Given the current git diff and the module brief, generate today's session patch"

Local model reads the diff + brief and writes the session patch automatically. Zero manual effort.

**Use Case C — Doc Compression Before Load**
> "Summarize this risk register to only open items with severity ≥ medium"

Useful for phase context files that accumulate over time.

**Use Case D — Consistency Check**
> "Does this implementation diff match the acceptance criteria in the module brief?"

Local model does a pre-check before you even open a Claude session. Catch misalignments early.

### 6.4 Basic Workflow

```
[Project Docs]
      │
      ▼
[Ollama: qwen2.5:3b]  ← "extract relevant sections for task X"
      │
      ▼
[Compressed Context: ~500 tokens]
      │
      ▼
[Claude: focused implementation/review task]
```

### 6.5 Getting Started (Minimal Setup)

1. Install Ollama: `winget install Ollama.Ollama`
2. Pull a model: `ollama pull qwen2.5:3b`
3. Use via CLI: `ollama run qwen2.5:3b "From this doc: [paste doc] — extract only: [specific need]"`

No code required to start. Can evolve into a script or Claude hook later.

---

## 7. Migration Plan

### What NOT to change (backward compatibility)
- `docs/02_governance/05_WORKING_MODEL_SCRUMBAN.md` — keep as reference
- `docs/02_governance/06_OPERATING_RACI.md` — keep as reference
- All Phase 0 / Phase 1 / M01-M05 existing docs — do not rewrite, leave as-is

### New artifacts to create (Phase 1 onward means M06+)

| File | Replaces | Size |
|---|---|---|
| `docs/02_governance/PROJECT_INVARIANTS.md` | Charter + scope dict excerpts | < 150 lines |
| `docs/02_governance/PHASEN_CONTEXT.md` (per phase) | Execution pack | < 200 lines |
| `docs/03_planning/MODULE_NN_BRIEF.md` (per module) | 11 module docs | < 400 lines |
| `docs/sessions/SESSION_PATCH.md` (per session, overwritten) | Re-explaining context | < 80 lines |

### Transition trigger
Apply new format starting from **next new module** (M06 or first module in next phase). No backfill needed.

---

## 8. Expected Outcomes

| Metric | Current | Lean Target |
|---|---|---|
| Docs per module | 11–12 files | 1 file (Module Brief) |
| Lines loaded per session | ~6,000 | ~830 |
| Token overhead per session (est.) | 18,000–25,000 | 2,500–4,000 |
| Time to onboard session | manual re-context | load session patch (auto) |
| Human navigability | requires reading multiple files | single file, scannable in 30s |

---

## 9. DA Decision Required

- [ ] Approve new Module Brief format for M06+
- [ ] Approve session patch pattern
- [ ] Decision on local model adoption (optional — start simple, no code required)
- [ ] Approve PROJECT_INVARIANTS.md creation as Tier 0 baseline

---

*This document itself follows the lean format: no change history table, no redundant metadata, no prose repetition. It is its own proof of concept.*
