# DESIGN — Error Blocks (Phase D)

**Status:** 🔒 **SEALED 2026-07-27** — DESIGN + REVIEW complete, BUILD may begin at D3a.
**Track:** atom-edit · **Board:** [`CHECKLIST.md`](./CHECKLIST.md)
**Sealed input (Q3, CLARIFY 2026-07-26):** *both* surfaces — Draft Review (pre-accept) **and** the
chapter editor (persisted prose) — **sharing one block-marking primitive.**

> ## 🔒 SEAL
>
> This design is **sealed**: its decisions are not to be re-litigated from memory during BUILD.
> If BUILD contradicts something here, **re-read this file**, then amend it explicitly with a dated
> note — never drift silently.
>
> **Sealed decisions** (each was verified against code, not assumed):
> 1. An error block is a **human-authored self-heal `Finding`**; the located→edit→splice→review
>    machinery is reused, not rebuilt.
> 2. Tenancy scope key is **`book_id`**; `created_by` is an actor stamp, never filtered. (R1)
> 3. `quote` is the anchor, offsets are a hint, `source_fingerprint` decides which to trust; an
>    unlocatable block **orphans visibly**. (§5, E1, E3)
> 4. Re-anchoring picks the candidate **nearest the stored offset**, never the first match; a tie
>    orphans rather than guesses. (E1)
> 5. **No existing engine file is modified** — `engine/error_block_heal.py` composes public
>    primitives. `self_heal.py`'s `_snap_to_sentence` must never touch a human span. (§9, §11d)
> 6. The fix is applied as a **surgical span replacement in the live document** — never a whole-doc
>    text round-trip. This is a correctness requirement, not an optimization. (§11b/F11)
> 7. **One** unified `composition_error_block_edit(op=…)`; `op="list"` ships with or before the
>    writes; `op="create"` is cut. (§8, §11d)
> 8. Grounding comes from **`pack()`**, and a degraded pack must be **stated on the card**. (§7, E11)
> 9. **D3f (live co-writer round trip) is the completion gate**, and it precedes D3e. A green test
>    suite does not close this feature.
>
> **Explicitly NOT sealed — open, and fine to stay open:**
> - **F11** (§11b) — a real shipped bug in the *other* session's Polish path. Logged, not fixed,
>   **coordination required.** Error blocks do not depend on it.
> - **D3d / D3e file ownership** — needs the coordination conversation before those slices start.
>   D3a–D3c and D3g do not.
> - CJK re-anchoring stays degraded; the code-point↔UTF-16 offset mismatch stays inherited. Both
>   fail safe, both recorded.

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
  source_fingerprint TEXT NOT NULL, -- hash of the flattened text the offsets were computed over.
                                    -- Mismatch ⇒ distrust offsets, re-anchor by quote (E3).
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
-- E5: kill accidental duplicate marks without forbidding two DISTINCT notes on one span.
CREATE UNIQUE INDEX IF NOT EXISTS idx_ceb_dedup
  ON chapter_error_block(project_id, chapter_id, start_offset, end_offset, md5(note))
  WHERE status = 'open' AND NOT is_archived;
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
  op="resolve"  → close, with the proposal that fixed it    ← confirm-gated
  op="dismiss"  → close as won't-fix                        ← confirm-gated
```

*(`op="create"` — the agent marking its own blocks — was **cut at REVIEW** as speculative scope;
§11d. The `source` column already admits it later without a migration.)*

**`op="list"` is not optional.** A write-only tool family is the exact bug E3 found in
`composition_structure_template_edit`: five write ops and no read, so the agent could never
discover an id to write to. Ship the read in the same commit as the writes.

**The fix path adds no new tool:**
- **one block** → existing `propose_edit(operation="replace_selection")` → ProposeEditCard → Apply.
- **many blocks at once** → the existing self-heal proposal/accept gate, entered with human
  findings instead of judge findings (§9).

Gap 3 (no MCP self-heal at all) is closed as a side effect: the human-findings entry point is
reachable by the agent, and exposing the judge path through the same tool is then a one-line op.

## 8b · The FE↔BE surface (added at SEAL — the design had only specified the agent's path)

The MCP path (§8) was specified in detail; the **browser's** path was left implicit. It is not the
same path — the FE cannot call MCP. Routes on composition-service, under the existing prefix:

```
GET    /v1/composition/works/{project_id}/chapters/{chapter_id}/error-blocks?status=open
POST   /v1/composition/works/{project_id}/chapters/{chapter_id}/error-blocks     → mark
PATCH  /v1/composition/error-blocks/{id}     (If-Match: version)                 → resolve/dismiss/edit note
DELETE /v1/composition/error-blocks/{id}                                         → soft-archive
POST   /v1/composition/works/{project_id}/error-blocks/propose                   → the grounded fix pass
```

> **AMENDMENT 2026-07-27 (D3c) — the batch `/propose` route is NOT built yet.** The other six
> routes shipped. Two findings deferred this one rather than rushing it:
> 1. **`pack()` needs a SCENE node** (`PackRequest.node`), and an error block is chapter-scoped.
>    Choosing which scene to pack against — the one containing the span? the chapter's first? —
>    is a real design question, and guessing it would silently ground the fix on the wrong scene.
> 2. **The agent does not need it.** Per §8 the co-writer lists blocks, composes the fix itself
>    using the glossary/KG tools it already has, and proposes via `propose_edit`. The batch route
>    serves the FE's future "fix all my marks" button — a convenience, not the loop.
>
> `engine/error_block_heal.propose_for_blocks` (D3b) is therefore built and tested but **not yet
> wired to a route** — stated here rather than left to be discovered, because "built but never
> wired" is the exact defect class this whole track exists to find. Its caller lands with the
> scene-selection decision, not before.

**Gateway work required: none.** Verified — `gateway-setup.ts:354` proxies by prefix
(`pathname.startsWith('/v1/composition')`), so a new route under it is reachable the moment it
exists. *(Do keep the passthrough honest about optional fields — a gateway that drops one is a
known past defect.)*

`PATCH` carries `If-Match: version` (the `canon_rule` precedent, `patchCanonRule`) → 412 on drift.
The propose route follows the existing `202 + poll` / inline shape of `proposeSelfHeal` and
`qualityReport` — same `_resolveJob` helper on the FE, no new async idiom.

**Contract-first** is ENFORCED only for glossary-service, so no route-conformance test will red
here — which makes it easier to forget. Document these in `contracts/api/composition-service/`
in the same commit anyway.

## 9 · Engine change — ~~a shared seam~~ **a new composing module**

> ⚠️ **SUPERSEDED at REVIEW (§11d).** The original plan — factor `propose_from_findings` out of
> the self-heal orchestrator so both paths share it — is **withdrawn**. `self_heal.py` is the
> concurrent session's most active file, and the human path wants almost none of that pipeline
> (notably it must *not* run `_snap_to_sentence`, which would silently widen the author's
> deliberate span). Kept here rather than deleted, so the reversal is visible.

**New module `engine/error_block_heal.py`. No existing engine file is modified.** It composes
public primitives already exported by `cowrite.py` / `self_heal.py`:

```python
async def propose_for_blocks(
    blocks: list[ErrorBlock], text: str, profile: BookProfile, llm: LLMClient,
    *, grounding: str = "", grounded: bool = True,
) -> tuple[list[EditProposal], list[SkippedBlock]]:
    # per block: re-anchor (E1/E3) → build_selection_messages(guide=note, grounding=…)
    #            → LLM → length guard → EditProposal ; every skip is REPORTED (E12)
```

Reused as-is: `build_selection_messages` (the `guide=` / `grounding=` slots), `EditProposal`,
`locate_span` (wrapped, never edited), and the rightmost-first `applySelfHealEdits` splice.

Deliberately **not** reused: the judge, `_snap_to_sentence`, verify-vote, the re-ranker, the
mechanical dup-word merge, the re-judge. A human finding is already located, already deliberate,
and already verified — by the author.

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

## 11d · DESIGN REVIEW (phase 3, 2026-07-27) — self-review + edge-case sweep

### 🔴 Reversal: do NOT refactor `self_heal.py` (§9 is withdrawn)

§9 proposed factoring `propose_from_findings` out of the self-heal orchestrator. **Withdrawn**, for
two independent reasons that both point the same way:

1. **`self_heal.py` is the concurrent session's most active file** — `04cb0840d fix(compose-quality)`,
   `b4aecf402`, `572379b1c`, `a39a58a31`, `b3565c851`, `40545a7f2`, all self-heal. Refactoring it is
   the highest-conflict edit available. *(This also corrects a claim made when the design was
   presented: D3b was described as safe backend work. It was not.)*
2. **The human path genuinely doesn't want most of the pipeline.** Reading the orchestrator
   (`self_heal.py:440-513`), a human finding must skip: the judge, `locate_span` (already located),
   **`_snap_to_sentence`** (it would silently widen the author's deliberate span!), the verify-vote,
   the re-ranker, the mechanical dup-word merge, and the re-judge. What remains is: per block →
   `build_selection_messages` → LLM → length guard → `EditProposal`. **~25 lines.**

**Decision:** new module `engine/error_block_heal.py` that *composes* the existing public
primitives (`build_selection_messages`, `EditProposal`, `locate_span`) and **touches no existing
engine file.** Cheaper than the refactor, lower risk, and honest about the two paths being
different rather than forcing a shared abstraction over them.

### Edge cases — swept and RESOLVED

| # | Edge case | Resolution |
|---|---|---|
| **E1** | 🔴 **Ambiguous re-anchor.** `locate_span` returns the **first** match (`text.index`). Author marks the 3rd "Nàng gật đầu."; prose drifts; the fix lands on the **1st**. Silently wrong prose — the worst failure mode here. | Re-anchor with a **nearest-to-hint** wrapper in the new module: enumerate all candidates, pick `min(abs(start − stored_offset))`. If two candidates are within a tie threshold ⇒ **orphan, don't guess.** Never modify `locate_span` (contested file). |
| **E2** | Two open blocks **overlap**. Self-heal silently drops the later one (`skip_reason="overlap"`). | For human marks, silently dropping is unacceptable. **Merge** overlapping open blocks into ONE finding over the span union with both notes concatenated — that is what an author marking a passage twice actually means. |
| **E3** | 🔴 **Offsets drift wholesale when `_text` is missing.** `tiptap_doc_to_text` reads `_text` per block and *falls back* to concatenating runs — a different string ⇒ **every stored offset shifts at once.** F11 (§11b) creates exactly this state. | Store `source_fingerprint` (hash of the flattened text the offsets were computed over). On read, fingerprint mismatch ⇒ **distrust offsets, re-anchor by `quote`** (via E1's wrapper). Catches the whole class, including F11 fallout, for one column. |
| **E4** | Author marks a huge span (or the whole chapter) — the satellite edit's surgical premise collapses. | Cap `quote` at the existing `SELECTION_MAX_CHARS` (8000, `cowrite.py:166`); FE disables **Mark** above it; server 422s a bypass. Reuse the constant, don't invent a second limit. |
| **E5** | Double-click / two devices ⇒ duplicate identical marks. | `UNIQUE` partial index on `(project_id, chapter_id, start_offset, end_offset, md5(note)) WHERE status='open' AND NOT is_archived`. Kills accidental twins; still allows two *distinct* notes on one span. |
| **E6** | Author fixes the prose **by hand**; the block's quote no longer exists. | ⇒ `orphaned`, surfaced as *"the text you marked is gone — did you fix it?"* with one-click Resolve/Dismiss. **Never auto-resolve** — we cannot know whether it was fixed or deleted. |
| **E7** | Agent calls `op="create"` with a quote absent from the chapter. | **Reject** with `result.error` naming the reason. An unanchored block is a silent no-op — forbidden. |
| **E8** | `op="list"` on a chapter with hundreds of blocks. | Cap the list and return a true `open_count` alongside it — the `listNarrativeThreads` precedent (capped list + uncapped count). |
| **E9** | Chapter or book deleted. `chapter_id` has **no cross-DB FK** (house convention: validated in app code). | Reads are chapter-scoped, so orphan rows are invisible — no correctness bug. Physical cleanup on a `chapter.deleted` event is **tracked debt**, not a D3 blocker. |
| **E10** | A VIEW-grant collaborator marks a block. | Marking is authoring input that drives prose changes ⇒ requires **EDIT** tier, matching `pack()`'s `authorize_book` (read-pack=VIEW, prose-gen=EDIT). Reading blocks = VIEW. |
| **E11** | knowledge-service down ⇒ `pack()` degrades to empty grounding (the C16 path) and the fix is produced **ungrounded but looks identical**. | Proposal carries `grounded: bool` + reason; the card says *"fixed without canon grounding"*. A degrade-safe guard must surface "unverified". |
| **E12** | The satellite edit fails or runs away in length. | `skip_reason` (`edit_failed`/`edit_expanded`) already exists — **surface it per block**. Returning fewer proposals with no explanation is a silent no-op. |

Two new columns fall out: `source_fingerprint TEXT NOT NULL` (E3) and the E5 unique index.

### Scope cuts (YAGNI)

- **Cut `op="create"` from D3.** The sealed need is *human marks → agent fixes*. An agent that
  marks its own blocks is a second feature with its own dedup questions, and it shrinks the
  confirm-gating surface to `resolve`/`dismiss`. Add later if wanted — `source` already allows it.
- **`op="list"` ships first and alone if needed.** It is the affordance gate (E3 lesson) and is
  independently useful.

### Honest weaknesses left standing

- **The `draft_job` arm carries most of the complexity for the least-proven half.** The accept-migration
  path (re-anchor every block onto the chapter) is the single hardest piece of the design and serves
  the surface the author uses *less*. **D3e is therefore explicitly optional to prove the feature** —
  D3d alone closes the loop end to end. Build it second, and only after D3d's live proof.
- **CJK re-anchoring stays degraded** (§5). E1's nearest-hint wrapper helps ordering but not
  matching; a CJK block whose surroundings changed still orphans. Accepted, recorded, not hidden.
- **The code-point ↔ UTF-16 offset mismatch is inherited**, not fixed. The `quote` guard makes it
  fail safe rather than corrupt.

## 12 · Build slices (D3)

Revised at REVIEW: no slice touches a file the concurrent session owns.

| slice | content | conflict risk | proof required |
|---|---|---|---|
| **D3a** | migration + repo + closed-set enums + `source_fingerprint` + E5 unique index | ⚠️ **LOW, not zero** — the table is new, but the DDL block lands in `migrate.py`, which the other session appended to hours ago (`9f9296c00`). Textual, easily resolved; append in one place. | live DB row; scoped query proves `book_id` filtering |
| **D3b** | `engine/error_block_heal.py` — re-anchor wrapper (E1) + `propose_for_blocks` | **none** (new file) | unit: nearest-hint beats first-match; overlap merge (E2); fingerprint mismatch re-anchors (E3) |
| **D3c** | REST routes (§8b) + `composition_error_block_edit` — **`op="list"` first**, then `resolve`/`dismiss` | **none** (new routes/tool) | live MCP call **and** a live HTTP call on the real book |
| **D3d** | editor surface: SelectionToolbar → Mark → `Decoration` render | ⚠️ `EditorPanel` — **coordinate** | **browser** — mark, reload, still there |
| **D3g** | **teach the co-writer** — skill prompt + tool surfacing | ⚠️ chat-service skills — low | the model **actually calls** the tool unprompted in a live chat |
| **D3f** | co-writer round trip | — | **live**: mark → agent lists → grounded proposal → apply → **DB shows the new prose** |
| **D3e** | *(optional, last)* Draft Review arm + accept migration | ⚠️ compose panels — **coordinate** | **browser** — mark on draft, accept, block re-anchors |

### D3g is not optional — it is the difference between shipped and invisible

This track spent an entire phase proving the point in both directions: a skill naming a **retired**
tool sends the model into a discovery loop (19 references across 6 skills, fixed), and a tool **no
skill names** is a tool the model never reaches for. `composition_error_block_edit` inherits both
risks. D3g covers:

- the co-writer skill learns the tool, its `op` set, and **when** to reach for it ("the author
  marked passages — read them before rewriting anything");
- surfacing: the tool must be reachable via the hot-set / `tool_list`→`tool_load` tail, not merely
  registered;
- the skill lint (`_KNOWN_LEGACY_TOOL_NAMES` / `_NONEXISTENT_TOOL_NAMES`) still passes.

**Proof is behavioural, not textual:** the gate is a live chat where the model calls the tool
without being told its name — the same standard applied to every other tool in this track.

**D3f is the gate**, and note it now sits *before* D3e: the feature is provable end-to-end on the
editor surface alone. Per this track's own drift log, four editors passed 1596 unit tests with no
door to open them. A green suite is not a working feature — the browser and the DB are.

---

## Coordination hazard ⚠️

Phase D lands on **Draft Review (`scene-compose`/`chapter-assemble`) and the chapter editor** —
the same compose/quality surfaces the concurrent chapter-quality session works in. Two agents
rebuilding `composition-service` against one working tree already produced the `439d9037a`
commit-sweep. **Agree file ownership before D3d/D3e.**
