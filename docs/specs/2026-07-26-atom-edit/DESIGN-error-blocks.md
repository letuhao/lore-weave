# DESIGN — Error Blocks (Phase D)

**Status:** DESIGN (phase 2 of 12) · **Track:** atom-edit · **Board:** [`CHECKLIST.md`](./CHECKLIST.md)
**Sealed input (Q3, CLARIFY 2026-07-26):** *both* surfaces — Draft Review (pre-accept) **and** the
chapter editor (persisted prose) — **sharing one block-marking primitive.**

> **The author marks a span of wrong prose and says what's wrong with it. The co-writer proposes a
> fix grounded in that instruction plus the book's canon/KG/glossary. The author accepts or rejects.**

---

## 1 · The reframe — this is not a new feature

`engine/self_heal.py` already runs exactly this pipeline, with an LLM in the author's chair:

```
  JUDGE (LLM) ──▶ Finding{type, span, issue, fix} ──▶ locate ──▶ satellite edit ──▶ splice ──▶ re-judge
  ^^^^^^^^^^^                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  replace with the HUMAN                             already built · shipped · tested
```

**An error block is a human-authored `Finding`.** The author supplies what the judge would have
produced — and supplies it *better*: the span is verbatim by construction (they selected it), and
the `issue` is real intent rather than an inference.

So Phase D is **~70% wiring**. The design below reuses the located→edit→splice→review machinery
verbatim and adds only: one table, one engine seam, one MCP tool, two marking affordances.

## 2 · What already exists (verified, with evidence)

| Capability | Where | Reusable as-is? |
|---|---|---|
| Span proposal shape `{id,type,tier,start,end,before,after,issue,fix,recommended}` | `EditProposal` — `engine/self_heal.py:68` · `SelfHealProposal` — `frontend/…/composition/api.ts:780` | ✅ **verbatim** |
| Drift-guarded splice (skip when `slice(start,end) !== before`) | `applySelfHealEdits` — `api.ts:872`; Python twin `apply_self_heal_edits` | ✅ **verbatim** |
| Fuzzy span→offset re-anchoring | `locate_span` — `self_heal.py:169` (exact → ws-flexible → ellipsis → 5-word shingle) | ✅ pure fn |
| Satellite editor taking **author instruction + grounding** | `build_selection_messages(selection, profile, op, guide=, grounding=)` — `engine/cowrite.py:169` | ✅ `guide` **is** the note slot |
| Satellite edit *is* grounded today | `self_heal.py:485` → `grounding=canon` | ✅ |
| Multi-proposal accept/reject review gate | `QualityHealPanel` (`quality-heal`, catalog:373) + `usePolishProposals` | ✅ pattern |
| Co-writer → editor write-back, human-gated | `propose_edit` (ai-gateway `propose-edit-tool.ts`; def `frontend_tools.py:80`) → ProposeEditCard → `applyProposedEdit` | ✅ **the apply path is done** |
| chat ↔ editor seam | `features/chat/context/editorBridge.ts` | ⚠️ **write-only** — see gap 2 |
| TipTap editor + selection affordance + decoration layers | `EditorPanel.tsx` (catalog:173) · `SelectionToolbar` · `useMentionHeatmap`/`useProvenance` | ✅ pattern |
| KG + glossary + canon + motif + reference grounding | `packer/pack.py:198` — grant-aware, project-scoped, budget-bounded | ✅ see §7 |

## 3 · What is actually missing — four gaps

1. **No persisted human finding.** Nothing stores "this span is wrong, here's why."
   `GenerationCorrection` (`db/models.py:409`) is the near-miss: it has `guidance`, but it is
   **job-scoped with no span**, and its `kind` enum (`edit|pick_different|regenerate|reject`) is an
   eval-gate metric with a deliberate H2 self-reinforcement guard. Wrong grain — **do not overload it.**
2. **The co-writer cannot read the author's marks.** `editorBridge` exposes write only
   (`insert_at_cursor` / `replace_selection`). There is no "what did the author flag?" read.
3. **No MCP tool for prose self-heal at all.** `proposeSelfHeal` is REST-only (`api.ts:654`); the
   only `self_heal` string in `mcp/server.py:5126` is the *PlanForge pass name*, unrelated. Per the
   MCP-first invariant the co-writer cannot reach prose healing today — **a fresh instance of this
   track's recurring "built, never wired for the agent" class.**
4. **No marking affordance** on either surface.

## 4 · Data model

New table `chapter_error_block` (composition-service). **Tenancy tier: Per-book/per-resource** —
owner + E0 grantees; every query filters by the scope key; no System-tier row exists.

**Column shape verified against the house pattern** (`canon_rule` migrate.py:265,
`narrative_thread` :334, `generation_correction` :384 — all three agree):

```sql
CREATE TABLE IF NOT EXISTS chapter_error_block (
  id             UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by     UUID NOT NULL,     -- actor stamp (25 M3) — stored, NEVER filtered on (PM-5)
  project_id     UUID NOT NULL,     -- the Work / partition
  book_id        UUID NOT NULL,     -- tenancy scope key (25 M1/M2) — the E0 gate
  -- target (discriminated union) --
  target_kind    TEXT NOT NULL CHECK (target_kind IN ('chapter_draft','draft_job')),
  chapter_id     UUID,              -- chapter_draft arm
  draft_version  INT,               -- the OI-2 OCC token the offsets were computed against
  job_id         UUID REFERENCES generation_job(id) ON DELETE CASCADE,  -- draft_job arm
  -- span anchor (§5) --
  start_offset   INT  NOT NULL,     -- Unicode CODE POINTS over tiptap_doc_to_text(), see R5
  end_offset     INT  NOT NULL,
  quote          TEXT NOT NULL,     -- verbatim marked text: drift guard + re-locate key
  -- the finding --
  source         TEXT NOT NULL DEFAULT 'human'
                 CHECK (source IN ('human','judge','critic','canon')),      -- §11c
  kind           TEXT NOT NULL
                 CHECK (kind IN ('continuity','voice','pacing','fact','logic','style','other')),
  note           TEXT NOT NULL,     -- the author's instruction ("she died in ch3")
  desired        TEXT,              -- optional: what they want instead
  -- lifecycle --
  status         TEXT NOT NULL DEFAULT 'open'
                 CHECK (status IN ('open','proposed','resolved','dismissed','orphaned')),
  proposal_id    TEXT,              -- the EditProposal that resolved it
  resolution     TEXT,
  version        INT NOT NULL DEFAULT 1,          -- OCC, If-Match (canon_rule precedent)
  is_archived    BOOLEAN NOT NULL DEFAULT false,  -- soft delete + restore, house convention
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at    TIMESTAMPTZ,
  CONSTRAINT chapter_error_block_target CHECK (
       (target_kind = 'chapter_draft' AND chapter_id IS NOT NULL)
    OR (target_kind = 'draft_job'     AND job_id     IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_ceb_chapter ON chapter_error_block(project_id, chapter_id, status)
  WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_ceb_book ON chapter_error_block(book_id);
```

⚠️ `book_id` is the scope key — **not** `owner_user_id`, which an earlier draft of this design
wrongly specified. `created_by` records *who* marked it and is never a filter.

**Closed sets** (enum-validated on write, per the Frontend-Tool-Contract discipline — a free string
here is the `panel_id` silent-no-op bug all over again):

- `kind`: `continuity · voice · pacing · fact · logic · style · other`
- `status`: `open · proposed · resolved · dismissed · orphaned`

`other` exists deliberately — a closed set the author can't fit their problem into would push them
to abandon the mark. `note` carries the nuance.

### Feeding the eval gate

On resolve, **also** write a `GenerationCorrection{kind='edit', guidance=note}` when the block
targets a generation job. Reuse, not a parallel track: the correction-rate dashboard
(`getCorrectionStats`) then counts author-marked defects as what they are.

## 5 · Span anchoring and drift — the hard part

Offsets die the instant anyone edits the prose. The rule is inherited, not invented:

1. **On every read**, validate `text[start:end] == quote`.
2. **Mismatch → re-anchor** via `locate_span(quote, text)`; persist the new offsets.
3. **Won't locate → `status='orphaned'`, and SHOW IT.** Never silently drop an author's mark —
   a dropped mark is indistinguishable from a fixed one. (Degrade-safe guards must surface
   "unverified".)

**Human-marked spans locate far better than judge spans.** The POC measured only 3/7 judge spans
matching exactly (the judge abbreviates and re-spaces); an author's selection is verbatim, so the
exact-match branch normally hits on the first try.

⚠️ **Known limitation — CJK.** `locate_span`'s fallbacks tokenize on whitespace
(`_ws_regex`, `self_heal.py:163`). For a CJK span `split()` yields one token, so the ws-flexible
and 5-word-shingle branches collapse into exact match. Human-verbatim quotes make this mostly
academic, but a CJK block whose surrounding prose was edited will orphan rather than re-anchor.
Record as a limitation; do **not** silently ship it as if solved.

⚠️ **Offset unit mismatch is pre-existing and load-bearing.** Offsets are Python code points,
spliced in JS UTF-16 code units — an astral char before an edit shifts it. `applySelfHealEdits`
already documents this and fails safe on the `before` check. Error blocks inherit both the bug and
the guard. Do not "fix" it in this track without re-testing self-heal.

## 6 · Two surfaces, one primitive

| | **Draft Review** (pre-accept) | **Chapter editor** (persisted) |
|---|---|---|
| host | `scene-compose` (catalog:355) · `chapter-assemble` | `EditorPanel` (catalog:173) |
| prose lives in | panel React state + generation job result | chapter draft, versioned |
| anchor | `job_id` + span | `chapter_id` + `draft_version` + span |
| mark UI | select in preview → **Mark problem** | `SelectionToolbar` → **Mark problem** |
| render | inline highlight | ProseMirror **node `Decoration`** — *not* `classList` |

**The Draft Review constraint that shapes the design:** the compose/assemble views clear their
draft *unconditionally* right after `onAccept` returns (`useAcceptIntoEditor.ts` header) — the
preview prose is ephemeral and has no chapter identity yet. Hence the `job_id` target arm.

**Accept migration — what makes "one primitive" true.** When a draft carrying blocks is accepted
into the editor, each `draft_job` block is re-anchored onto the chapter text via
`locate_span(quote, chapter_text)` and rewritten to `target_kind='chapter_draft'` with the new
`chapter_id`/`draft_version`. A block that won't locate → `orphaned`, surfaced, not dropped.

## 7 · Grounding — use the packer, not the cast bible

Self-heal grounds on `render_canon(cast)` (`engine/heal_canon.py`) — the planning pipeline's
designed cast plus a genre address convention. That is **not** what Q3 asked for.

**Decision: error-block fixes ground via `pack()` (`packer/pack.py:198`)** — the same path drafting
uses, which is where glossary + knowledge (KG) + canon rules + motifs + scene links + references +
entity overrides actually come from, already grant-aware, project-scoped and budget-bounded. It is
also strictly more grounded than the self-heal judge is today.

The `PackRequest` is built for the chapter (or the scene containing the span); the rendered blocks
go into `build_selection_messages(grounding=…)`, and the author's `note`/`desired` into `guide=`.
Both slots already exist — nothing new in the prompt builder.

## 8 · Agent path (MCP-first)

**One unified enum-dispatch tool**, matching the 11 existing `*_edit` atom families exactly — not
four tools, per the standing "don't make a new tool if the current tool can work and unify" rule:

```
composition_error_block_edit(op=…)
  op="list"     → the author's open blocks for a chapter   ← READ; the affordance gate
  op="create"   → the agent marks a block it noticed        ← confirm-gated
  op="resolve"  → close, with the proposal that fixed it    ← confirm-gated
  op="dismiss"  → close as won't-fix                        ← confirm-gated
```

**`op="list"` is not optional.** A write-only tool family is the exact bug E3 found in
`composition_structure_template_edit`: five write ops and no read, so the agent could never
discover an id to write to. Ship the read in the same commit as the writes.

**The fix path adds no new tool:**
- **one block** → existing `propose_edit(operation="replace_selection")` → ProposeEditCard → Apply.
- **many blocks at once** → the existing self-heal proposal/accept gate, entered with human
  findings instead of judge findings (§9).

Gap 3 (no MCP self-heal at all) is closed as a side effect: the human-findings entry point is
reachable by the agent, and exposing the judge path through the same tool is then a one-line op.

## 9 · Engine seam (the only engine change)

Factor steps 2–4 out of the self-heal orchestrator so both entry points share them:

```python
async def propose_from_findings(
    findings: list[Finding], text: str, profile: BookProfile, llm: LLMClient,
    *, grounding: str = "", **kw,
) -> list[EditProposal]: ...
```

- judge path becomes `judge(...) → propose_from_findings(...)` — **no behavior change**, so the
  existing self-heal tests remain the regression net for the refactor.
- human path is `blocks → [Finding(span=quote, issue=note, fix=desired)] → propose_from_findings(...)`,
  and `located` is pre-filled from the stored offsets, so the fuzzy step is skipped when they still
  validate.

## 10 · Invariants this design must not break

- **MCP-first** — the co-writer reaches error blocks only as an MCP tool on composition-service
  (the owning domain); `ai-gateway` federates, never implements.
- **No agent-driven GUI nav** — the agent proposes; the human applies. `propose_edit` is already
  human-gated and stays that way.
- **Server is SSOT** — blocks are Postgres rows. A mark made on a phone is visible on the desktop.
  No localStorage.
- **Tenancy** — per-book tier, `book_id` on every query, grant-gated cross-tenant access.
- **Non-lossy apply** — never rebuild the chapter document from flat text (§11b F11).
- **Closed-set args** — `kind`/`status`/`op` are enums, registered in `CLOSED_SET_ARGS`.
- **No silent no-op** — an unresolvable block orphans *visibly*; a resolver failure returns
  `result.error`.

## 11 · Open questions — CLEARED against code (2026-07-27)

| # | Question | **Resolved** |
|---|---|---|
| R1 | Tenancy scope key? | 🔴 **§4 above was WRONG.** Composition scopes by **`book_id`** (`-- tenancy scope key (25 M1/M2)`), *not* `owner_user_id`. `created_by` is an **actor stamp, explicitly never filtered on** (PM-5). Verified on `canon_rule` (migrate.py:265), `narrative_thread` (:334), `generation_correction` (:384) — all three identical. Corrected in §4. |
| R2 | Is `draft_version` usable as the anchor? | **Yes** — it is the **OI-2 OCC token**, monotonic (`draft_version + 1`), mirrored in book-service `chapter_drafts` and composition `work_chapter_draft`. `patchDraft` 409s on `expected_draft_version` mismatch (server.go:2635), so it doubles as the stale guard. Nullable in `SelfHealProposalResponse` — handle null. |
| R3 | Block on an unaccepted draft, after regenerate? | **Orphan them, visibly.** `generation_correction.job_id REFERENCES generation_job(id) ON DELETE CASCADE` is the house pattern; a `draft_job` block FKs the same way, so a deleted job cascades. A *regenerated* job is a new row ⇒ old blocks orphan rather than silently re-attach to prose they were never about. |
| R4 | Multi-block overlap/ordering | **Solved upstream — do not re-derive.** `self_heal.py:474-513` already enforces non-overlap (`occupied`), satellite-over-mechanical priority, rightmost-first splice, and a runaway-expansion guard. `propose_from_findings` (§9) inherits all of it. |

### R5 (new, found while clearing R2) — two coordinate systems

The editor's prose is a **ProseMirror/TipTap JSONB doc**; self-heal offsets are **flat-text code
points** over `tiptap_doc_to_text(doc)` (blocks joined by `\n\n`). These are *different coordinate
spaces*, and no round-trip exists from a flat offset back to a PM position.

**Consequence for the design:** an error block stores flat-text offsets + `quote` (§5) — consistent
with self-heal — and the *apply* goes through the editor's own transaction (`replace_selection`),
never through a rebuilt document. See §11b.

## 11b · 🔴 F11 — the existing Polish apply silently corrupts the chapter

Found while clearing R5. **This is a shipped data-integrity bug, not a hypothetical.**

`QualityHealPanel.healedTextToDoc` (`QualityHealPanel.tsx:30`) rebuilds the whole chapter as flat
paragraphs and PATCHes it:

```ts
text.split(/\n\n+/).map(para => ({ type: 'paragraph', content: [{ type: 'text', text: tx }] }))
```

Book-service **stores a `json` body verbatim** — `normalizeBodyToTiptap` passes it through
(server.go:2613) and the UPDATE writes it as-is (:2639). Nothing re-stamps the doc. So applying a
Polish drops, for that chapter:

- **`_text` block snapshots** — read by full-text search (`search.go:117`), chapter/block extraction
  (`server.go:2968/3030/3560`), and `migrate.go:1283`, all via `x.elem->>'_text'`. Without it those
  reads return NULL: **the chapter goes invisible to search and extraction.**
- **heading nodes + `attrs.sceneId`** — the Scene Rail / navigator anchors `prose_doc.py`
  deliberately attaches (`_attach_scene_ids`).
- **every mark** — provenance, glossary, formatting.

**The correct primitive already exists and is used everywhere else:** `addTextSnapshots`
(`lib/tiptap-utils.ts:18`), which `ManuscriptUnitProvider.tsx:277` calls with the comment
*"addTextSnapshots is REQUIRED before persist (chapter_blocks trigger)"*. The normal editor save
does it (`TiptapEditor.tsx:173`). **Polish is the one path that doesn't.**

This is this track's signature bug class *again* — a correct converter on one path
(`prose_doc.text_to_tiptap_doc`, which mirrors `tiptap.go` including `_text`, headings and sceneId)
and a naive twin on another that silently drops fields.

**Design consequence (load-bearing, not incidental):**

> **An error-block fix MUST be applied as a surgical span replacement inside the live document —
> never as a whole-doc text round-trip.**

That is precisely what the existing `propose_edit(replace_selection)` → `applyProposedEdit` path
does: a real ProseMirror transaction that leaves every other node untouched, followed by the normal
save (which stamps `_text`). The design's §8 choice to reuse it is therefore not merely economical —
**it is the only non-lossy option.**

**Disposition:** F11 is a genuine fix-now-sized defect (`_text` is a one-line wrap; the heading/mark
loss is inherent to the flat round-trip and argues for converging Polish onto the same surgical
apply). It lives in `QualityHealPanel.tsx` — the **concurrent session's quality surface**. Logged
here with evidence; **coordinate before touching it.** Error blocks do not depend on the fix, only
on not repeating it.

## 11c · Forward-compatibility: one ledger, one source at a time

`chapter_error_block` carries `source TEXT NOT NULL DEFAULT 'human'`
(closed set: `human · judge · critic · canon`).

Phase D populates **only `human`**. But the column costs nothing now and prevents a parallel track
later: self-heal findings are currently **ephemeral job results** — run Polish, walk away, they are
gone — and `getCanonIssues`/`getRuleViolations` are separate read-only lanes. If those are ever to
become durable and reviewable, they belong in *this* ledger, and `composition_error_block_edit(op="list")`
becomes the single "what's wrong with this chapter?" read for the co-writer.

Adding the column later would mean a migration plus a backfill plus an MCP contract change. Adding
it now is one word. **Do not, however, populate the machine sources in Phase D** — that is a
separate effort with its own dedup and volume questions.

## 12 · Build slices (D3)

| slice | content | proof required |
|---|---|---|
| **D3a** | migration + repo + closed-set enums | live DB row, scoped query |
| **D3b** | `propose_from_findings` seam | self-heal suite still green (unchanged behavior) |
| **D3c** | `composition_error_block_edit` (list first, then writes) | live MCP call, real book |
| **D3d** | editor surface: SelectionToolbar → mark → Decoration render | **browser** — mark, reload, still there |
| **D3e** | Draft Review surface + accept migration | **browser** — mark on draft, accept, block re-anchors |
| **D3f** | co-writer round trip | **live**: mark → agent lists → proposes grounded fix → apply → DB shows new prose |

**D3f is the gate.** Per this track's own drift log, four editors passed 1596 unit tests with no
door to open them. A green suite is not a working feature — the browser and the DB are.

---

## Coordination hazard ⚠️

Phase D lands on **Draft Review (`scene-compose`/`chapter-assemble`) and the chapter editor** —
the same compose/quality surfaces the concurrent chapter-quality session works in. Two agents
rebuilding `composition-service` against one working tree already produced the `439d9037a`
commit-sweep. **Agree file ownership before D3d/D3e.**
