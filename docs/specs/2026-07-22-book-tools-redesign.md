# Spec: Book MCP Tool Redesign — deprecate lifecycle, unify content, design the OUTPUT

**Status:** Part A + Part C/D **SHIPPED + live-verified** (`adec30a4b`, `656f6c105`); Part B (write-merge) **deferred — delicate, marginal** (see §4 Part B). · **Date:** 2026-07-22 · **Size:** L (single service, contract-shape change on one domain)

> **Progress 2026-07-22.** Book 31 → **~15 visible tools**, ~6.8K → ~3.5K schema tokens.
> - **Part A DONE** (`adec30a4b`): 9 lifecycle/destructive/priced tools → `_meta.visibility:"legacy"`. Live-verified: all 9 excluded from discovery (the agent can't create/delete/purge/publish/bill).
> - **Part C/D DONE** (`656f6c105`): `book_read` (cat) + `book_list` (ls) + the **output contract** (reference-first, `page` envelope with `is_complete`, prose `guidance` stop-signal). Live-verified by effect: complete/partial/miss guidance all correct, chapter body block-paged, reference-first (no bodies in a set), backward-compatible `book_list` default. 6 old reads → legacy.
> - **Part B DEFERRED** — see the finding in §4 Part B: the write-merge is more delicate than it looked (absent-vs-`null` `part_id` semantics, an internal composition validation call, per-setter undo, CAT-2 on `set_kg_exclude`) for a marginal −2-tool gain. Do it as a focused follow-up, not rushed.
**Origin:** Tool-catalog analysis 2026-07-22 (book = 31 tools / 6.8K schema tokens). The catalog-wide anti-pattern (one tool per entity-type × CRUD-verb, plus lifecycle/destructive ops the agent should never own) is worst-per-token in `composition`/`glossary`, but `book` is the right **second pilot** after glossary: small, self-contained, and the surface every co-writer turn touches.
**Builds on (do NOT re-derive):** `docs/specs/2026-07-06-tool-catalog-simplification.md` (the glossary pilot — proved CAT-4 legacy-visibility, `pinned_legacy_tools` escape hatch, upsert-via-implicit-discriminator, `items[]` batch) and `docs/standards/mcp-tool-io.md` (IN-1..8, OUT-1..6, CAT-1..4). This spec **reuses** that machinery; it does not reinvent it.
**Related:** [[context-budget-law-and-kernel]], `docs/FEATURE_INDEX.md` (book routes → book-service).

---

## 1. Problem (grounded in the 2026-07-22 catalog dump)

`book` ships **31 tools / 6,792 schema tokens**. Two distinct problems:

**(A) The agent owns things it should NOT own.** Book *lifecycle* and *destructive* and *priced* operations are deliberate human decisions, yet they're agent-callable:
- `book_create` (spawn a book), `book_purge` (irreversible book delete), `book_chapter_purge` (irreversible chapter delete), `book_chapter_delete` (trash a chapter) — creation + destruction.
- `book_chapter_publish` / `book_chapter_unpublish` — canonization is an *editorial* decision, not a co-write step.
- `book_set_cover`, `book_audio_generate`, `book_media_generate` — **priced** (spend money).

An agent has no business creating a user's books, permanently deleting their work, or spending their money unprompted. These belong on **UI buttons the human clicks**, not the agent's tool surface.

**(B) The content tools are spread thin — and their OUTPUT is a bloat risk.** After removing (A), what's left is read/write/curate — but it's fragmented (7 reads, 3 chapter-field setters, a singular+bulk create pair), and the *reads have no disciplined output contract*. The 146K-token turn that motivated the whole Context Budget Law was exactly a book/composition read (`composition_list_outline`) dumping every synopsis (OUT-1 violation). A redesign that only cuts tool *count* but lets `book_read`/`book_list` dump full bodies just moves the bloat. **The output design is the hard, load-bearing half of this spec.**

---

## 2. Guiding principle (the line this spec draws)

> **The agent owns CONTENT; the human owns LIFECYCLE.**
> The agent can *read, draft, edit, organize, and curate* a book's content. It cannot *create, delete, publish, or bill* — those stay manual UI actions.

Everything in §4 follows mechanically from this line.

---

## 3. Decisions requiring PO sign-off before implementation

### 3.1 — Which tools become "manual only" (deprecate → `legacy`, per CAT-4)

"Deprecate" = tag `_meta.visibility:"legacy"` (the proven glossary-pilot mechanism): the HTTP endpoint and tool registration stay (the **UI button keeps working**, existing callers unaffected), but the tool is **excluded from `find_tools`/`search_catalog`/hot-seed** — the agent can no longer discover or call it. The only path back is an explicit user pin (`pinned_legacy_tools`) or an explicit workflow-step activation.

| Tool | Class | Recommend |
|---|---|---|
| `book_create` | create a book | **legacy** — agent works within an opened book |
| `book_purge` | irreversible book delete | **legacy** |
| `book_chapter_purge` | irreversible chapter delete | **legacy** |
| `book_set_cover`, `book_audio_generate`, `book_media_generate` | **priced** media | **legacy** — user-initiated spend |
| `book_chapter_publish`, `book_chapter_unpublish` | canonization (editorial) | **legacy** (PO 2026-07-22). Workflow impact handled AFTER the new tools are proven (§9), not before. |
| `book_chapter_delete` | trash a chapter (soft, recoverable) | **legacy** (PO 2026-07-22) — full deprecation; chapter deletion is a human action. |

**PO decisions 2026-07-22 (RESOLVED):** all of the above → `legacy`. `book_chapter_delete` full-legacy (not confirm-gated). publish/unpublish → legacy now; the workflow audit is **deferred** (§9) — we prove the new tools work first, then decide any workflow update.

**Net:** **9 tools** leave the agent surface (`book_create`, `book_purge`, `book_chapter_purge`, `book_chapter_delete`, `book_chapter_publish`, `book_chapter_unpublish`, `book_set_cover`, `book_audio_generate`, `book_media_generate`). Every irreversible delete, money-spend, book-creation, and canonization is gone from the agent in one stroke — the biggest *safety* win, independent of token savings.

### 3.2 — How aggressively to unify the reads

The **ls / grep / cat** model (§4.C, §5). Alternative (keep 7 reads) rejected: fragmentation with no place to enforce the output contract.

### 3.3 — Stop-signal shape (RESOLVED 2026-07-22)

**Both** a structured `is_complete: true` boolean (deterministic machine-branch) **and** the prose `guidance` string (weak-model directive) — belt-and-suspenders against loops (§5 D-3).

---

## 4. Design — the tools

### Part A · Deprecations
Tag the §3.1 tools `_meta.visibility:"legacy"`, append one description sentence ("Manual/UI action — the agent does not <create|delete|publish|bill>; kept for existing callers."), exactly as the glossary pilot did (`WithVisibility` already exists in `sdks/go/loreweave_mcp/meta.go`). No handler changes. The CAT-4 drift-lock test that already asserts legacy exclusion extends to these names.

### Part B · Unified write — `book_chapter_update`
Merge the three per-chapter **field setters** into one (CAT-1 — same resource, same required shape `{chapter_id, fields}`, no divergent branch):

| Superseded (→ legacy) | New |
|---|---|
| `book_chapter_update_meta` (title/sort_order/language) · `book_chapter_set_part` (part_id) · `book_chapter_set_kg_exclude` (kg_exclude) | **`book_chapter_update`** |

```jsonc
{ "name": "book_chapter_update",
  "description": "Edit a chapter's properties in place — any subset of: title, sort_order, part_id (move into/out of a manuscript part; null detaches), kg_exclude (in/out of the knowledge graph), language. Only the fields you pass change. Does NOT touch prose (use book_chapter_save_draft) or lifecycle (publish is a manual UI action).",
  "_meta": { "tier": "A", "visibility": "discoverable" },
  "inputSchema": { "type": "object", "properties": {
      "book_id": {"type":"string"}, "chapter_id": {"type":"string"},
      "title": {"type":"string"}, "sort_order": {"type":"integer","minimum":0},
      "part_id": {"type":["string","null"],"description":"target part; null = detach"},
      "kg_exclude": {"type":"boolean"}, "language": {"type":"string"} },
    "required": ["book_id","chapter_id"], "additionalProperties": false } }
```
**⚠ BUILD FINDING (2026-07-22) — DEFERRED.** Reading the real handlers, the write-merge is more delicate than the read-merge, for a marginal (−2 tools) gain:
- **`set_kg_exclude` must NOT fold in (CAT-2).** `kg_exclude=true` **retracts already-extracted facts/passages** — a destructive side-effect a plain title/sort edit doesn't have. Merging it behind a field hides that. Keep `book_chapter_set_kg_exclude` a separate, discoverable tool.
- **`part_id` needs absent-vs-`null`-vs-value semantics.** In `book_chapter_update`, *absent* `part_id` = leave the chapter's part alone; `null` = un-home; a value = re-home. A plain `*string` (Go JSON) collapses *absent* and `null` to the same `nil` — so the merge needs a presence-aware wrapper type, not a bare pointer.
- **`set_part` does an internal composition validation call** (`validatePartTargetInternal`) + each setter mints its own `undo_hint`; a merged tool must combine them into one reversible `book_chapter_update` undo.
None of this is blocked — it's buildable — but it's **delicate for a −2-tool gain** and should be a focused follow-up (own design of the presence-aware type + CAT-2 branch + combined undo + per-branch tests), not rushed. `book_chapter_update_meta` already does title/sort/language cleanly today; `set_part`/`set_kg_exclude` work individually.

`book_chapter_create` would absorb `book_chapter_bulk_create` via `items[]` 1..N (CAT-3), matching `glossary_propose_entities` — clean (create-only, no side-effect, no absent-vs-null); the one Part-B slice with no delicacy, if a follow-up wants a safe start.

**Kept as-is** (already correct, single-purpose): `book_chapter_save_draft` (prose write), `book_chapter_restore_revision` (safe undo), `book_chapter_reorder` (book-level bulk order — a genuinely different shape from a per-chapter field set; NOT merged into `book_chapter_update`), `book_index_chapter`, `book_update_details` (edit book meta — NOT create), `book_steering_{set,list,delete}`, `book_task_provide_input`.

### Part C · Unified reads — the ls / grep / cat model
Treat the book like a filesystem the agent navigates, never dumps:

| Superseded (→ legacy) | New | Role |
|---|---|---|
| `book_get` · `book_get_chapter` · `book_scene_get` | **`book_read`** | `cat` — full content of **one** addressed item |
| `book_list` · `book_list_chapters` · `book_list_revisions` · `book_scene_list` | **`book_list`** | `ls` — **references only**, paged |
| `book_search` | **`book_search`** (kept, output-contract'd) | `grep` — content match, paged refs + snippet |

- **`book_read`** — implicit id-presence discriminator (CAT-1): the *deepest* id present decides what's read — `scene_id` → scene body · else `chapter_id` → chapter (block-paged, reusing the existing `truncated`/`next_offset`) · else `book` detail. One tool, no `kind` enum, no divergent required-fields.
- **`book_list`** — one `kind` enum `{books, chapters, revisions, scenes}` (IN-3, closed set) + the optional parent id that kind needs, validated server-side with a self-correcting error (IN-6: "kind=chapters needs book_id"). Reads tolerate an explicit discriminator here (unlike writes) because every branch is uniform "list refs + page".

---

## 5. Design — Part D: the OUTPUT contract (the hard part)

This is where the user's requirement lives: **paged, reference-first, and every result carries an EXPLICIT stop-guidance so a weak model never loops.** It composes with OUT-1..5 and adds one new, model-facing element.

### D-1 · Reference-first, never bodies in a set (OUT-1)
`book_list` / `book_search` items are `{id, title, ≤1-line, version/updated_at}` — **never** prose, synopsis, or full attributes. Full content comes only from `book_read` on **one** id. (This is the exact rule the 146K-token `list_outline` broke.)

### D-2 · Bounded + paged, uniform envelope (OUT-2, OUT-5)
Every set/read result carries a `page` block **with a structured `is_complete` boolean** (PO 2026-07-22 — the deterministic half of the stop-signal):
```jsonc
"page": { "returned": 20, "total": 47, "offset": 0, "next_offset": 20, "has_more": true, "is_complete": false }
```
`is_complete == true` ⇔ the model has the whole set/body and MUST NOT call again. Defaults small (`limit` 20, max 100 — already the book-service constants); a long chapter body pages by block (`truncated`,`next_offset`, already shipped). `total` present so the model knows the whole size up front.

### D-3 · **Explicit stop-guidance — the anti-loop element (NEW)**
Two halves, belt-and-suspenders (PO 2026-07-22): the structured `page.is_complete` bool (D-2, for deterministic machine-branching) **and** a prose `guidance` string — a single imperative, model-facing directive that says **what to do next, including STOP.** A weak local model that ignores a boolean still obeys the sentence; a strong model branches on the bool. The model is *told* when it's done, never left to infer.

| Situation | `guidance` |
|---|---|
| Complete set | `"complete — all 12 chapters returned. Do NOT call book_list again for this book."` |
| Partial | `"12 of 47 returned. Call book_list again with offset=12 ONLY if you still need more; otherwise stop."` |
| Empty | `"this book has no chapters yet. Do NOT retry — create one with book_chapter_create."` |
| `book_read` miss | `"no chapter with id=X in this book. Do NOT retry the same id — call book_list kind=chapters to get valid ids."` |
| Long body paged | `"chapter body truncated at block 300 of 812. Call book_read with offset=300 to continue, or stop if you have what you need."` |

Rules for `guidance`: (1) always imperative and terminal-aware ("Do NOT call again" on completion); (2) names the *exact* next call + args when continuation is legitimate; (3) on a miss/empty, points at the tool that *would* help instead of inviting a blind retry. This directly implements "explicit response để chỉ dẫn model khi nào nên dừng, đừng loop vô nghĩa."

### D-4 · grep before ls before cat (the intended usage the descriptions teach)
Each tool's description states the cheap path: to find something, `book_search` (grep) — don't `book_list` everything and scan; to read one thing, `book_read` by id — don't page a whole list. The `guidance` on a large `book_list` result actively redirects: `"47 chapters — if you're looking for a specific one, book_search is cheaper than paging this list."`

### D-5 · Wire hygiene (OUT-3, OUT-4)
Bare-payload success / `{success:false,error}` failure (OUT-4); serialized through the one Go tool-result helper with `ensure_ascii=false` + drop-empty (OUT-3) — Vietnamese/CJK titles must not inflate 2–3× via `\uXXXX`.

---

## 6. Net effect

- **Visible book tools: 31 → ~14** (`book_read`, `book_list`, `book_search`, `book_chapter_create`, `book_chapter_update`, `book_chapter_save_draft`, `book_chapter_restore_revision`, `book_chapter_reorder`, `book_index_chapter`, `book_update_details`, `book_steering_{set,list,delete}`, `book_task_provide_input`) + ~9 hidden legacy.
- **Schema tokens: ~6.8K → ~3.5K** visible (−48%), shrinking the cached prefix for *every* provider with no churn.
- **Safety:** the agent can no longer create/purge/publish a book or spend money.
- **Anti-bloat:** reads are reference-first + paged + self-terminating.

---

## 7. Edge cases (resolve before BUILD)
7.1 `book_read` with **no** id beyond `book_id` → returns book detail (not an error); with a `chapter_id` that isn't in the book → the D-3 "miss" guidance, `{success:false}` — never a 5xx.
7.2 `book_list kind=scenes` with a `chapter_id` → scope to that chapter; without → whole book (bounded). State which in `guidance`.
7.3 `book_chapter_update` with **no** editable field (only ids) → one-line reject "nothing to update — pass at least one of title/sort_order/part_id/kg_exclude/language" (IN-6), not a silent no-op.
7.4 `part_id` pointing at a part in a **different** book → reject, name the mismatch.
7.5 A legacy tool pinned alongside its replacement re-introduces ambiguity (glossary §8.10) — accepted, mitigated by the "superseded by X" description line.
7.6 `book_search` returning zero matches → `guidance:"no matches for '<q>'. Do NOT retry the same query — broaden it or use book_list kind=chapters."`

## 8. Governance / contract constraints (must hold)
- mcp-tool-io: `kind` (book_list), `level`-style enums are `enum` in schema (IN-3); parent-id requiredness validated server-side (IN-4/IN-6); one canonical arg name (IN-7); the Go tool-def schema sources move in lockstep (IN-8 — audit book-service's def sources, don't assume one).
- Tenancy: every read/write stays behind `mcpRequireGrant` (View for read, Edit for write); `book_list`'s public-key `ownerOnly` egress guard (diary exclusion, already present) is preserved on the merged tool.
- CAT-4: legacy exclusion verified on **both** federation surfaces (`tool_discovery.py` + `find-tools.ts`).

## 9. Workflow audit (DEFERRED — PO 2026-07-22: prove the new tools first)
Order per PO: build + prove the new tools, **then** address workflows. A workflow **step** activates its tool explicitly (like a pin), so a `legacy` tool *can* still be sequenced by a rail — legacy hides a tool from *discovery*, not from an explicit activation. So deprecating publish/unpublish is unlikely to break `autonomous-drafting`/`chapter-compose`, but that's a claim to **verify live after** the tools land, not a blocker before. Post-implementation task: run each rail that references a deprecated book tool, confirm the step still executes; if a rail can't reach it, make the rail pin it (or keep those two `discoverable`). Tracked as a follow-up, not a gate on this pass.

## 10. Rollout & verify (no A/B — the user is right that it's meaningless here)
Correctness, not comparison. Sequence:
1. **Part A deprecations + Part C/B new tools**, one glossary-pilot-shaped pass (new tool + legacy-tag + drift-lock test extension).
2. **Verify by EFFECT** (mcp-tool-io Part 3), per tool:
   - `book_read`/`book_list`/`book_search` — live `tools/call` on the real POC book: assert reference-first (no body in a list), the `page` envelope is honest against a book with > `limit` chapters, and the `guidance` string is present + correct for complete/partial/empty/miss. **DB cross-check** the counts.
   - `book_chapter_update` — live update of title+part+kg_exclude in one call; **DB verify** each field changed and prose is untouched.
   - `book_chapter_create` items[] — batch create, per-item results, DB verify.
   - **Output-bloat check:** measure the assembled tool-result token size of `book_list` on a 50-chapter book — must be reference-sized (≲1–2K), not a body dump.
   - **Anti-loop check:** drive a real turn ("show me all chapters") on the target model (Gemma-4) and confirm it calls `book_list` **once** (the `guidance` "complete — do NOT call again" lands) rather than re-paging.
   - **CAT-4 live:** `tools/list` shows the deprecated names `legacy` and the new ones `discoverable`; `find_tools "read a chapter"` ranks `book_read` #1, never the legacy `book_get_chapter`.
   - **§9 workflow audit** live before publish/unpublish deprecation.
3. **Follow-on (not this spec):** composition (89) + kg (27) get their own specs once this + the glossary pilot are validated in production.

## 11. Open questions — ALL RESOLVED 2026-07-22
1. ~~`book_chapter_delete`: legacy vs confirm-gated~~ — **RESOLVED: full legacy** (§3.1).
2. ~~publish/unpublish: deprecate vs keep~~ — **RESOLVED: deprecate (legacy)**; workflow impact handled after the tools are proven (§9), not before (§3.1).
3. ~~stop-signal: prose vs structured~~ — **RESOLVED: both** — structured `page.is_complete` bool + prose `guidance` (§5 D-2/D-3).
