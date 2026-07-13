# 28 · Agent-Native Studio — the Cursor-parity capability layer

> **Status:** 📐 SEALED (multi-agent authored + adversarially reviewed 2026-07-10; PO ratified all product decisions same day — see 00B §6) — buildable
> **Scope:** `composition-service` (Python) + `book-service` (Go) MCP surfaces + chat-service discovery registration. **Zero new tables, zero migrations** — every tool below is a read or a write over shapes that already exist or that `22`/`23`/`25`/`26`/`27` already own. Decision prefix **AN-\***.
> **Prerequisites:** [`23_book_architecture.md`](23_book_architecture.md) Phase 0/A (`structure_node`, per-book re-key, via [`25`](25_package_migration_master.md)); [`25`](25_package_migration_master.md) PM-3/PM-4 + OQ-2 (Work partition key + canonical-Work resolution — every composition read in this spec scopes by them) and OQ-3 (the VIEW widening AN-2's `runs` block rides); [`22_scene_model_and_crud.md`](22_scene_model_and_crud.md) Phase A (scene index reads); [`26_structure_prose_indexing.md`](26_structure_prose_indexing.md) IX-8/IX-9/IX-14 (conformance state + status machinery).
> **Ownership boundaries honored:** `structure_node` MCP CRUD → **23 BA11** · scene CRUD + `book_scene_list/get` → **22 SC8/SC9** · conformance/staleness *mechanics* + `composition_conformance_status` → **26** (IX-14: this file **composes** it, never duplicates) · PlanForge pass surface → **27** · migration DDL → **25** · Plan Hub GUI wiring → **24** (PH20: one repo method, two front doors). This file owns only the **gap layer**: the agent-experience tools none of those specs claim.
> Follows [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6 / CAT-1..4), [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md), [`docs/standards/scope-separation.md`](../../standards/scope-separation.md), [`07S_studio_agent_standard.md`](07S_studio_agent_standard.md).

---

## Why

Cursor gives its agent the same capability envelope over a code workspace that the human has over
the IDE: see the tree, open any file, jump to a definition, find references, read the problems
panel, propose diffs, refactor, generate, obey `.cursorrules`, grep. The Writing Studio's agent is
close — ~160 federated tools cover most verbs — but the envelope has **holes exactly where an
agent orients itself**: there is no single read that shows the book-package's shape, no way to ask
"where is this character used in the plan", no problems panel it can read in one cheap call, no
literal grep over the manuscript, and the book's own steering rules (the `.cursorrules` analogue,
which already exists as a table and a GUI panel) are **invisible to the agent that is supposed to
obey them**.

The consequence is measurable, not aesthetic: the S06 flagship baseline showed a mid-tier model
that never *reaches* machinery, and every orientation question ("what's in this book so far?")
today costs the agent 3–6 tool calls across three services — each one a chance for a weak model to
stall, mis-chain, or hallucinate an answer instead. The 00A package model finally gives the book a
coherent shape; this spec gives the agent eyes on that shape, at the same altitude Cursor's agent
has on a repo: **one tree read, one references read, one diagnostics read, one grep, and
read/write access to the rules that steer it.**

---

## Investigation findings

Every claim verified against code at HEAD (`feat/context-budget-law`) on 2026-07-10.

### F-A1 — the steering store exists, has a GUI, and has NO agent surface

`book_steering` shipped in RAID C1: DDL at
[`migrate.go:388-402`](../../../services/book-service/internal/migrate/migrate.go#L388-L402)
(`UNIQUE(book_id, name)`, `inclusion_mode CHECK IN ('always','scene_match','manual','auto')`,
`body ≤ 8000` chars); REST CRUD at
[`server.go:252-258`](../../../services/book-service/internal/api/server.go#L252-L258) (list =
VIEW, writes = EDIT); the internal fetch chat-service renders from at
[`server.go:193-195`](../../../services/book-service/internal/api/server.go#L193-L195); validation
+ caps (≤20 rows/book, rune-counted for CJK) in
[`steering.go:42-120`](../../../services/book-service/internal/api/steering.go#L42-L120); the
`<steering>` system part lands in every book-scoped turn
([`stream_service.py:3192-3220`](../../../services/chat-service/app/services/stream_service.py#L3192-L3220));
and a `steering` panel is already in the `ui_open_studio_panel` enum. But grep `steering` in
[`mcp_server.go`](../../../services/book-service/internal/api/mcp_server.go): **zero hits**. The
agent is *steered by* rules it can neither read, author, nor update — when Mai says *"write that
down: she never begs"* (S06 turn 9), the one durable place that instruction belongs is unreachable
from the loop that received it.

### F-A2 — manuscript lexical search is REST-only; the agent can only search semantically

[`search.go:247`](../../../services/book-service/internal/api/search.go#L247) (`GET
/v1/books/{book_id}/search`, VIEW-gated) and its internal twin
([`:298`](../../../services/book-service/internal/api/search.go#L298)) run `runLexicalSearch` —
escaped-ILIKE literal substring over drafts and/or canon, `surface ∈ {draft, canon, all}` (default
`draft`), `granularity ∈ {chapter, block}` (default `chapter`), limit/offset
([`:144-171`](../../../services/book-service/internal/api/search.go#L144-L171)). No MCP tool wraps
it. The agent's only prose search is `story_search` (semantic, knowledge-service) — it cannot
answer *"which chapters literally contain the phrase 'Thần Hồn'"*, the exact-match class of
question every rename, canon check, and consistency pass starts with.

### F-A3 — no single read shows the package; orientation costs 3–6 calls across 3 services

To answer "what does this book have so far", the agent today chains `composition_get_work` (does a
Work exist? what project?) + `composition_list_outline` (spec tree) + `composition_list_canon_rules`
+ `book_list_chapters` (manuscript spine) + `glossary_book_ontology_read` (lore shape) + optionally
`composition_authoring_run_list` / plan-run reads — and still cannot see index coverage or lockfile
pins. The 00A layout (§2) is a *filesystem* with no `ls`. Each extra orientation call is a
mis-chain opportunity for the weak-model loop (the S06 F1/F2 failure class), and several of the
layers (`.index/` freshness, `book.lock` pin drift) have **no read at any altitude** short of raw
row reads.

### F-A4 — entity back-references exist in seven composition shapes, none queryable by entity

An entity id appears in: `outline_node.pov_entity_id` + `present_entity_ids[]`
([`migrate.py:156`](../../../services/composition-service/app/db/migrate.py#L156)),
`structure_node.roster_bindings` (23 BA3), `canon_rule.entity_id`, `voice_profile.entity_id`,
`motif_application.role_bindings`, `entity_override.target_entity_id`, and
`scene_grounding_pins` pins. **No tool takes an `entity_id` and returns any of these** — the
packer resolves them per scene (forward), never inverse. The prose/graph side of the question is
served (`glossary_list_chapter_links`, `glossary_get_entity_evidence`, `kg_entity_edge_timeline`),
but the *plan* side — "where does my protagonist appear in the spec, the tests, the bindings" — is
unanswerable, which is exactly the read a rename, a merge, or a "have I under-used this character"
question needs first.

### F-A5 — the problems surface is fragmented across ≥6 reads, one of them REST-only

- **Conformance drift + index staleness:** durable + cheap after `26` — `arc_conformance_state`
  + the IX-9 poll-on-read predicate, exposed as `composition_conformance_status` (IX-14).
- **Canon contradictions:** `OutlineRepo.canon_issues`
  ([`outline.py:777`](../../../services/composition-service/app/db/repositories/outline.py#L777))
  — every scene whose latest completed generation left a CONFIRMED unresolved canon violation.
  Served **only** by `GET /works/{project_id}/canon-issues`
  ([`routers/outline.py:231`](../../../services/composition-service/app/routers/outline.py#L231))
  — a REST route the Quality tab reads; no MCP tool.
- **Thread debt:** `narrative_thread` with the hot partial index
  `idx_narrative_thread_open … WHERE status IN ('open','progressing')`
  ([`migrate.py:299`](../../../services/composition-service/app/db/migrate.py#L299)) — BA15's
  "rollup is a query" is directly implementable, but no tool runs the query.
- **Coverage gaps** (unplanned chapters, prose-deleted spec nodes): computed by `24` H1.3's
  plan-overlay and `26` IX-13's marker comparison — GUI aggregate only.

An agent asked "is this book healthy?" must know all six seams exist, call each, and rank the
results itself. Cursor's agent reads one problems panel.

### F-A6 — go-to-definition and go-to-prose are each one hop short

- *Mention → definition:* `glossary_search(q=<surface form>)` → `glossary_get_entity` works today
  — the fuzzy step is a feature (aliases, diacritics), not a detour.
- *Spec → prose:* after `22`/`26`, the map is `scenes.source_scene_id → outline_node.id` — but
  `book_scene_list` (22 SC9/A4) filters by `chapter_id`/`q`, **not** by `source_scene_id`, so
  "show me the prose that realizes this spec scene" has no direct read; and the final hop into
  the editor exists (`ui_focus_manuscript_unit(chapter_id, scene_id)` — studio-gated frontend
  tool, resolves via the SC7 `data-scene-id` anchor).
- *Prose → spec:* `book_scene_get` returns `source_scene_id` (22 A2) → `composition_get_outline_node`. Complete once 22 ships.

One missing filter arg, everything else is composition of existing pieces.

### F-A7 — the two context chokepoints are healthy; neither injects the spec into *chat*

Generation-time grounding is `pack.py`'s single chokepoint
([`pack.py:1-47`](../../../services/composition-service/app/packer/pack.py#L1-L47)): project
chokepoint → `owns_book` gate → nine parallel lenses → two-axis spoiler filter → budget ladder →
`PackedContext` with `grounding_available=False` honesty. 23 BA12 makes it read the resolved arc
chain/tracks/roster/promises — the spec steers *generation*. Chat-time injection is
`stream_service.py`'s ordered tail-blocks
([`:3293-3299`](../../../services/chat-service/app/services/stream_service.py#L3293-L3299)):
steering → skills → plan-mode nudge → catalog → group directory → book note. **Nothing injects
spec-layer state into a chat turn**, and per the context-budget law's measured lessons
(`m3-pullmode-measured-nogo`, the 4000-token hot-seed trim in S06 §12) adding a per-turn spec dump
would be the wrong move — the gap is *pull* affordances (cheap R tools + discovery scent), not
more push.

### F-A8 — the discovery layer is ready to receive; no new domain is needed

`GROUP_DIRECTORY` ([`tool_discovery.py:62-84`](../../../services/chat-service/app/services/tool_discovery.py#L62-L84))
carries 12 prefix-keyed domains (`composition`, `book`, `plan`, `research`, …); `CATEGORY_ENUM` is
single-sourced from it (`:89`); `tool_list` = catalog ∩ non-legacy ∩ policy-allowed, deterministic.
Every tool this spec adds lives under an existing prefix (`composition_`, `book_`) — registration
is `require_meta` + synonyms, no directory change, no 4th registry copy.

### F-A9 — the meta kit enforces the conventions at boot, both languages

Python: `require_meta(tier, scope, *, undo_hint, synonyms, async_job, paid, tool_name)`
([`meta.py:80-114`](../../../sdks/python/loreweave_mcp/meta.py#L80-L114)) — validated at
registration; `paid` orthogonal to tier. Go: `NewToolMeta` + `MustValidateToolMeta`, panics at
boot ([`mcp_server.go:46-58`](../../../services/book-service/internal/api/mcp_server.go#L46-L58)).
C-GW: the gateway **drops** any tool not carrying the service's registered prefix — book-service
documents this at [`mcp_server.go:13-18`](../../../services/book-service/internal/api/mcp_server.go#L13-L18)
(chapter tools are `book_chapter_*` for exactly this reason).

---

## The capability matrix (AN-1 — normative)

For each Cursor capability: what EXISTS (tool names), what is PARTIAL, what was MISSING → the
disposition. This table is the spec's contract; the gap layer is **exactly seven new tools + one
arg extension**, everything else is referenced.

| # | Cursor capability | EXISTS today | Verdict | Disposition |
|---|---|---|---|---|
| 1 | **Workspace tree** (solution explorer / `ls -R`) | `book_list`, `book_list_chapters`, `composition_get_work`, `composition_list_outline(detail=summary)`, `composition_arc_list` (23 B1), `glossary_book_ontology_read`, `kg_project_list` | **MISSING** as one read — agent stitches 3 services (F-A3) | **NEW `composition_package_tree`** (AN-2) |
| 2 | **Open / read file** | `book_get_chapter(include_body=true)`, `composition_get_prose`, `composition_get_outline_node`, `book_scene_get` (22 A4), `composition_motif_get`, `glossary_get_entity` | **EXISTS** (once 22 ships scene reads) | reference 22 SC9 |
| 3 | **Go-to-definition** | `glossary_search` → `glossary_get_entity`; `entity_dossier` prompt; `ui_focus_manuscript_unit` | **PARTIAL** — spec→prose hop lacks one filter (F-A6) | `book_scene_list` gains `source_scene_id` filter (AN-5, lands in 22 A4); recipe locked here |
| 4 | **Find-references** | prose/graph side: `glossary_list_chapter_links`, `glossary_get_entity_evidence`, `kg_entity_edge_timeline`, `story_search` | **MISSING** on the spec/tests side (F-A4) | **NEW `composition_find_references`** (AN-3), composition-scope v1 |
| 5 | **Diagnostics / problems panel** | `composition_conformance_status` (26 IX-14), `plan_validate`/`plan_self_check` (run-scoped), `kg_triage_list`, `glossary_list_unknown_entities`/`_merge_candidates`, canon-issues (REST-only, F-A5) | **MISSING** as one ranked read | **NEW `composition_diagnostics`** (AN-4) — composes, never recomputes |
| 6 | **Edit propose + apply** | FE `propose_edit`/`propose_record_edit`/`confirm_action`; Tier-A OCC writes (`composition_write_prose` + `expected_draft_version`, `book_chapter_save_draft` + `base_version`); Tier-W propose→confirm spine | **EXISTS** | §Edit discipline (AN-8) codifies the channel map; anchored/diff-shaped prose edits stay deferred (OQ-5) |
| 7 | **Refactors** | `glossary_entity_rename`, `glossary_propose_merge`, `glossary_propose_reassign_kind`, `composition_arc_move`/`composition_outline_node_move` (23 B3), `composition_motif_patch` | **PARTIAL** — no cascade rename over prose | decided **not built** v1 (AN-13): rename cascade = find-references (AN-3) + `book_search` (AN-7) + per-chapter proposed edits, human-gated; an auto-rewriter over prose violates DA-1's spirit |
| 8 | **Codegen** | `composition_generate`, `plan_*` v2 passes + link (27), `composition_motif_bind`, `kg_build_graph`/`kg_build_wiki`, `book_media_generate` | **EXISTS** (27 closes the linker) | reference 27; S06 holes W2/W4 stay umbrella-owned |
| 9 | **Rules / context injection** (`.cursorrules`) | `book_steering` table + GUI + chat render (F-A1); `composition_canon_rule_*`; `memory_remember`; steering panel | **MISSING** the agent surface | **NEW `book_steering_list` / `book_steering_set` / `book_steering_delete`** (AN-6) |
| 10 | **Search** | semantic: `story_search`, `glossary_search`, `memory_search`, `composition_motif_search`, `kg_*_query`; discovery: `tool_list`/`tool_load` | **MISSING** literal grep (F-A2) | **NEW `book_search`** (AN-7) wrapping `runLexicalSearch` |

---

## Locked decisions

| # | Decision | Why |
|---|---|---|
| **AN-1** | **The capability matrix above is normative.** The gap layer is exactly: 3 composition R tools (`composition_package_tree`, `composition_find_references`, `composition_diagnostics`), 3 book-service steering tools (`book_steering_list/set/delete`), 1 book-service search tool (`book_search`), and 1 arg extension (`book_scene_list.source_scene_id`, built in 22 A4). Nothing else is added; every other capability is referenced from its owning spec. | A closed, enumerated tool set is the same guard PH9 applies to reads: a tool not in this table is a new decision to review, not an incremental slip. Catalog hygiene (CAT) — at ~160 tools, every addition must earn its schema tax. |
| **AN-2** | **`composition_package_tree` is the agent's `ls -R`** — ONE Tier-R call rendering 00A §2's layout for one book: manifest, `deps/`+`book.lock` summary, `spec/` tree (per-arc one-liners), `tests/` counts, `manuscript/`+`.index/` coverage, `.runs/` recent. It resolves the book's **canonical Work** and scopes every spec/tests/lock/runs read by that Work's `project_id` (§Canonical-Work scoping — PM-3/PM-4, `25` OQ-2): a derivative's rows never merge into the source's tree. **Summary-shaped, hard-capped ≈2–4K tokens on a 10k-chapter book** — counts and per-arc lines, never prose, arcs capped at 50 with `arcs_capped`; drill-down goes through the existing per-layer list tools (`composition_arc_list`, the children route's MCP twin, `composition_motif_book_list`, …). Composition owns the tool; the manuscript block comes from the **existing internal book client** (the `pack.py` precedent, F-A7) via the chapter spine; the **`.index/` block composes `26` IX-14's status machinery** — the same one-computation server-side helper behind `composition_conformance_status`, extended with the `draft_indexed` count — never a re-derivation from raw IX-9 markers (26's law: no surface computes its own staleness; a marker fan-out would also cost O(n/200) sequential calls of the 200-id-capped batch at 10k chapters, killing the one-cheap-read claim). The `runs` block reads `.runs/` tables that are **owner-keyed today** (`25` F10): it is served to non-owner grantees only under `25` OQ-3's VIEW resolution — until that lands, a non-owner gets the block **absent + a warning**. Same posture if book-service is unreachable: the manuscript/index block is **absent + a warning, never zero-faked** (the OQ-8/plan-overlay posture). | F-A3. OUT-1/OUT-2 applied at package altitude: the 146K-token `composition_list_outline` incident is what happens when orientation and content share one tool. A single cheap orientation read is the highest-leverage anti-thrash lever for the S06 weak-model loop — one call replaces the 3–6-call stitch. Absent-not-zero: `fe-status-default-fallback-signals-backend-field-omission` — a faked 0 makes every consumer invent the wrong default. |
| **AN-3** | **`composition_find_references` is composition-scope v1.** Args: `book_id`, `entity_id`, optional `sources[]` (closed set — **eight** sources over the seven F-A4 shapes: the outline pov/present pair splits), `limit`. All eight queries run against the canonical Work's `project_id` (§Canonical-Work scoping). Returns per-source **exact counts** + capped refs (`{source, node_ref:{kind,id,title}, detail}`) + `has_more`. It does **not** federate to glossary/KG: the prose side is `glossary_list_chapter_links` + `glossary_get_entity_evidence`, the graph side `kg_entity_edge_timeline` — all existing; the tool's description names them so the agent composes the full picture itself. A cross-service federated backlink tool is consciously deferred (OQ-1). | F-A4. Composition is the only service where the inverse query doesn't exist at all; building federation into v1 would put one service in the business of proxying three others' reads (the scope-separation smell) for a composition the agent already performs. Counts exact + refs capped is OUT-5 verbatim. |
| **AN-4** | **`composition_diagnostics` is the problems panel: a read-only, ranked, severity-tagged aggregation that composes existing engines and computes nothing new.** Sources, each cited to its owner: **(1)** conformance dirty/never-run per arc + index-staleness rollup — **the same server-side machinery behind `26` IX-14's status route** (`arc_conformance_state` + the IX-9 predicate; one computation, four consumers — the IX-14 status route itself [which 24's Hub reads **directly** as its read surface #7 per the NC-1 resolution; drift never rides `plan-overlay`], the `composition_conformance_status` tool, AN-2's `.index/` block, and this tool); **(2)** canon contradictions — `OutlineRepo.canon_issues` (F-A5), which finally gets an agent-reachable caller; **(3)** open thread debt — the BA15 query on `idx_narrative_thread_open`; **(4)** prose-deleted spec nodes — `26` IX-13's marker detection; **(5)** unplanned chapters — the same coverage diff `24` H1.3 computes for the PH21 tray. Severity is a fixed map (below), items ranked error→warn→info then by recency; caps + `refs_capped` per OUT-5. **It never triggers an LLM and never runs conformance** — the refresh action remains `composition_conformance_run` (Tier-W), which the tool's description points at when `never_run`/dirty. Scene-level anchor-orphan detail stays on `22`'s browser union (it needs the book-service scenes read; chapter-level `index.stale` is the honest v1 rollup). | F-A5. IX-14's consumer note (final, NC-1) is the law: ONE server-side computation — the Hub consumes its route directly, the agent aggregates (AN-2/AN-4) compose its helper — per the CSS-var-duplication lesson. A diagnostics read that silently *ran* a Tier-W spend would collapse the spend gate (07S: reversibility determines autonomy; a read must stay a read). |
| **AN-5** | **Go-to-definition is locked as three recipes over existing tools + ONE arg.** (a) *mention→definition:* `glossary_search(q=<name as it appears>)` → `glossary_get_entity` — **no new tool**; the fuzzy step is the correct resolver for surface forms (aliases, CJK/VN variants), and a second "exact" tool would be the same call with worse recall. (b) *spec→prose:* `book_scene_list(book_id, source_scene_id=<outline_node.id>)` → `ui_focus_manuscript_unit(chapter_id, scene_id)` — the filter arg is the one missing piece; **it is specced here and built in 22 A4** (integrator note, OQ-3), riding the `idx_scenes_source` index 22 A1 already creates. (c) *prose→spec:* `book_scene_get` → `source_scene_id` → `composition_get_outline_node`. A NULL back-link renders the BPS-13 states ("not yet written" / "anchor lost"), never a silent miss. | F-A6. One arg beats a new tool (CAT hygiene); the index for it already exists in 22's DDL. The recipes go in the three tools' descriptions — the discovery layer's job is to make the hop *found*, not to mint a facade tool per hop. |
| **AN-6** | **The steering store gets its agent surface: `book_steering_list` (R) · `book_steering_set` (A) · `book_steering_delete` (A)** on book-service (prefix `book_`, C-GW). `_set` is an **upsert keyed on `name`** — CAT-1's implicit discriminator: `UNIQUE(book_id, name)` already makes name-absent ⇒ create, name-present ⇒ full replace (the REST PUT semantics). Result returns the **prior row** when one was replaced/deleted, and `undo_hint` names the verified inverse: `_set`'s undo = `_set` with the prior row (or `_delete` when created); `_delete`'s undo = `_set` with the deleted row. Server caps re-enforced (≤8000 rune body → 422-equivalent one-liner, ≤20 rows, dup name → actionable error); `inclusion_mode` is an **enum** (`always/scene_match/manual/auto`) registered in the closed-set contract, description carrying steering.go's v1-honesty note ("auto v1: triggered like manual (#name)"). Write gate = EDIT grant, identical to REST (F-A1's tier comment: an edit-collaborator CAN author steering). | F-A1. This is the `.cursorrules` parity AND the S06 F4 canon-persist lever in one: "write that down" becomes a durable, every-matching-turn rule the agent itself authored — through the same store, caps, and grants the human GUI uses (one home, one name — Settings & Config boundary). Tier A not W: a steering row is small, visible in the existing `steering` panel, and the inverse op is verified — reversibility determines autonomy (07S §5 verbatim). |
| **AN-7** | **`book_search` (R) wraps `runLexicalSearch` as MCP** — literal, escaped-substring search over the manuscript. Args: `book_id`, `q` (1..256 runes — `maxSearchQueryRunes`, [`search.go:21`](../../../services/book-service/internal/api/search.go#L21)), `surface: enum[draft,canon,all] = draft`, `granularity: enum[chapter,block] = chapter`, `limit` (1..100, default 20 — mirrors the route's `parseLimitOffset`). Returns the route's result rows (chapter_id, block refs, highlighted snippet) + `has_more`. Registered under the `book` group; description contrasts it with `story_search` ("meaning-alike") so a weak model picks the right one. | F-A2. The engine, gates (VIEW), pagination, and enums all exist — this is a ~50-line MCP adapter over `search.go:381`, and it closes the last search hole in the matrix. Enum defaults mirror the route so the two front doors can never drift (PH20's discipline applied to a read). |
| **AN-8** | **The edit-discipline table (§Edit discipline) is the safety contract** — every object class names exactly one agent channel, one confirmation tier, and one undo path, aligned with 07S §5's verbatim rule: *"reversibility determines autonomy — an undoable action auto-runs; an action that mutates durable state (publish, delete, spend, cross-service write) is gated behind a human."* No tool this spec adds mints a new write class: the three steering writes are Tier-A with verified inverses; everything else is R. | The table exists so the next agent adding a tool has one place to find which channel its object class already uses — the drift this prevents is a second confirm convention (DA-10 at the safety layer). |
| **AN-9** | **Chat-turn context stays PULL for the spec layer; generation context stays PUSH via `pack.py`.** The default studio-agent turn injects (all existing): steering (selected modes) + working-memory anchor + knowledge `build_context` world block + the CTX-1 book note + the skill/directory tail-blocks. **No per-turn spec dump is added.** The new R tools are the pull path, given scent by discovery registration (AN-10) and by one sentence appended to the *existing* studio `book_context_note` (static text, ~15 tokens: the tools' names — no per-turn fetch). Generation-time, the spec enters automatically through `pack.py` (23 BA12: arc chain, tracks, roster_bindings, open promises) — two chokepoints, no third. | F-A7. The measured lessons rule here: `m3-pullmode-measured-nogo` (blanket push/pull re-archs don't pay), the 4000-token hot-seed trim (S06 §12 — budget is the scarce resource), and 07S §1's "steering is taxed every turn — keep tight". A per-turn `package_tree` auto-call is OQ-2 (✅ ratified NO, P-15 — revisit only with AN-D3 replay evidence). |
| **AN-10** | **Discovery registration:** every new tool registers with `require_meta` synonyms and rides its **existing** category — `composition` for the three composition tools, `book` for the four book-service tools (F-A8: no `GROUP_DIRECTORY` change, no `_DOMAIN_ALIASES` entry, no enum edit). All seven are `tier` per the table, none `paid`, none `async_job`. As policy-allowed R tools, the five reads MUST appear in `tool_list(category=…)` output including ask mode — deterministic completeness is the Phase-1 contract. None are legacy; none replace an existing tool. | The tools are useless if the model can't find them at the moment of need — and the S06 baseline showed the failure is *no attempt*, not failed attempts. Synonyms are the recall lever (`find_tools` feeds on them); category correctness is the `tool_list` lever. |
| **AN-11** | **The S06 trace (§S06) is the acceptance scenario.** The spec ships only when the flagship replay on `gemma-4-26b-a4b-qat` shows: the orientation read replacing multi-call stitching (≤2 discovery calls per movement), the steering write landing Mai's turn-9 rule as a `book_steering` row, `composition_package_tree` used as the *verification read* before any "it's set up" claim (the F7 honesty guard), and zero §1-denylist words in progress-blocking prompts. | `prefer-e2e-and-evaluation-over-live-smoke-poc` — the flagship IS the product test, and three of its four top failure modes (F1 thrash, F4 canon loss, F7 false-done) are exactly what these tools exist to cut. |
| **AN-12** | **No new GUI surface.** Every capability here is agent-side; the human equivalents already exist or are owned elsewhere (steering panel — shipped; problems → 24's overlay + quality panels; tree → 24's Plan Hub + navigator; search → the existing search UI). No catalog rows, no `ui_open_studio_panel` enum change, no dockable work. | DOCK-2/DOCK-8: the GUI already has these organs; duplicating them as "agent panels" would fork. The two-front-doors rule (PH20) runs the other way here — these are the agent's front doors onto reads the GUI reaches by REST. |
| **AN-13** | **Cascade rename is consciously NOT built in v1.** The recipe an agent follows today: `glossary_entity_rename` (lore SSOT) → `composition_find_references` (spec-side hits) → per-node `composition_outline_node_update`/`composition_arc_update` → `book_search(q=<old name>, surface=all)` → per-chapter `propose_edit` diffs, **human-applied**. An automated prose rewriter is a bulk mutation of hand-edited manuscript — DA-1's protected class — and belongs, if ever, in an authoring-run unit with per-unit accept/reject. | Defer gate #2 (large/structural). The pieces this spec adds (AN-3, AN-7) are precisely what make the *safe, gated* recipe possible at all — v1 ships the capability as a composition, not an autonomous sweep. |

**Severity map (AN-4, fixed and testable):**

| Severity | Finding kinds |
|---|---|
| `error` | canon contradiction (unresolved, confirmed) · prose-deleted spec node |
| `warn` | conformance `dirty` (any reason) or `never_run` on an arc with prose · open thread debt (every `open`/`progressing` thread — ONE severity) |
| `info` | unplanned chapters · index-stale count (advisory, self-heals via IX-3) |

Thread debt is deliberately single-severity: the shipped CHECK `narrative_thread_payoff_paid`
(`payoff_node IS NULL OR status = 'paid'`,
[`migrate.py:295`](../../../services/composition-service/app/db/migrate.py#L295)) guarantees every
open/progressing thread has `payoff_node = NULL`, and no due/position column exists — an
"overdue vs not-yet-due" split is uncomputable from the schema. A real due signal would be new
schema, outside this spec's zero-migration scope; until one ships, all open thread debt ranks
`warn`, and the contract snapshot asserts exactly this vocabulary (no `info` thread-debt kind).

---

## AN-12 AMENDED (PO-1, 2026-07-12)

> **What changed:** AN-12's **"No new GUI surface"** clause is **LIFTED** for two of the three
> agent-native reads — `composition_diagnostics` and `composition_find_references`. **AN-12's
> architecture is UNCHANGED and still binding.**
>
> **Authority:** [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §0 **PO-1**
> (sealed 2026-07-12). **Consumed by:** [`37_issues_feed.md`](37_issues_feed.md) (Wave 7).
> AN-12's row in the Locked-decisions table above stands **as amended by this section** — read them
> together; do not "reconcile" one against the other by deleting either.

### Why the clause was lifted — AN-12's premise was checked, and it was false

AN-12 justified the zero-GUI rule with one claim: *"the human equivalents already exist or are owned
elsewhere (… problems → 24's overlay + quality panels …)."* The Wave-7 audit tested that claim source
by source, against the seven kinds in the `SEVERITY` map above:

| Diagnostic kind | Human surface at HEAD `9262ed53e` |
|---|---|
| `broken_canon_rule` · `canon_contradiction` | ✅ `quality-canon` — **but unranked** |
| `open_thread_debt` | ✅ `quality-promises` (read-only, correctly) |
| `conformance_dirty` / `_never_run` | 🟡 a **dot** on the Plan Hub — arc-scoped, no list |
| `unplanned_chapter` | 🟡 the PH21 coverage tray — a count, no work list |
| `index_stale` | ❌ **none** |
| `prose_deleted_spec_node` | ❌ **none — and it is `error`, the highest severity the map has** |

**≈2.5 of 5 sources have a human surface, not one of them is ranked, and the two with no surface at
all include the only ERROR class the author can act on.** A `prose_deleted_spec_node` (26 IX-13 —
the spec deliberately SURVIVES a prose delete) is a dangling plan node the author must re-link or
archive, and **no screen in LoreWeave will ever tell them.** The premise held for the *tree*; it did
not hold for the *problems panel*.

### What AN-12 still FORBIDS — this part STANDS, unamended

The clause AN-12 was actually protecting was never "no pixels". It was **no DOCK-2/DOCK-8 fork** —
no parallel rack of "agent panels" duplicating organs the GUI already has. That reasoning is intact
and is **binding on spec 37**:

1. **NO new dock panel.** Zero rows in `catalog.ts`, zero additions to the `panel_id` enum, zero
   `contracts/frontend-tools.contract.json` churn. The drift-lock (`py enum 57 == contract enum 57
   == openable 57`) must be **byte-identical** after Wave 7. Spec 37 §6 states how.
2. **Diagnostics ships into the EXISTING `StudioBottomPanel` Issues tab** — a stub string since
   spec 01 shipped the frame (*"frame real, content stub"* — the stub **is** the spec, not a
   regression). No new organ; the organ was drawn on day one and left empty.
3. **`composition_find_references` is a LENS, not a panel** — a right-click popover on an entity
   badge (`NodeBadges.tsx` cast chips, `EntityRefField`). It has no catalog id and no dock tab.
4. **The feed ROUTES; it never EDITS.** Every row deep-links into the panel that already owns its
   fix (`quality-canon` via the PH18 `focusRuleId` seam, `plan-hub`, `chapter-browser`,
   `quality-promises`). A row that could edit in place **would** be the fork AN-12 forbids.
5. 🔴 **`composition_package_tree` gets NO human surface. AN-12 stands for it, unamended.** Its
   human equivalents genuinely *do* exist (`plan-hub` = the tree · `chapter-browser` = the spine ·
   the PH21 tray = the coverage gap). A "book at a glance" panel would be **exactly** the DOCK-2
   duplication AN-12 exists to prevent. This is a **conscious won't-fix**, recorded so it stops
   re-surfacing as a gap (spec 37 IF-5 / D-1).

### The lifted clause, stated exactly

> ~~*"No new GUI surface. Every capability here is agent-side… No catalog rows, no
> `ui_open_studio_panel` enum change, no dockable work."*~~
>
> **AMENDED to:** *"No new **dock panel**, no catalog rows, and no `ui_open_studio_panel` enum change.
> `composition_diagnostics` and `composition_find_references` MAY have a human surface, provided it
> is (a) an **existing** frame — the bottom panel — or an in-place lens, and (b) a **read that routes**,
> never a second editor for an organ the GUI already owns. `composition_package_tree` keeps the
> original clause in full."*

Everything else in AN-12 — and every other AN row — is unchanged.

---

## New tools — the gap layer

All seven: identity from the envelope (IN-1), explicit `book_id` (IN-2 — the gateway drops
`X-Project-Id`), `TolerantArgs`/`relaxAdditionalProps` posture (IN-5), one-line rejections (IN-6),
OUT-3 via each service's existing serialization — composition tools return bare JSON-shaped dicts
that FastMCP serializes (the `app/mcp/server.py` house style; no helper is ported), Go tools
return through the lwmcp kit — success = bare payload (OUT-4), bounded returns carry partiality
flags (OUT-5). Book-scoped guards: VIEW for reads, EDIT for writes, H13 uniform "not accessible"
errors.

**Canonical-Work scoping (normative — all three composition tools).** Under `25` PM-3/PM-4 a book
carries N Works (the source + C23 derivatives/dị bản) partitioned by `project_id`; a read keyed on
`book_id` alone would merge a derivative's spec/tests/lock/runs/refs into the source's.
`composition_package_tree`, `composition_find_references`, and `composition_diagnostics` therefore
resolve the **canonical Work** (`source_work_id IS NULL AND status = 'active'` — PM-4's partial
unique) and scope every query by that Work's `project_id` (PM-3's partition key), per `25` OQ-2's
canonical-only resolution. Derivative introspection is a future optional `project_id` arg —
consciously not built in v1.

### `composition_package_tree` (AN-2)

```python
meta = require_meta("R", "book",
    synonyms=["book overview", "what's in this book", "package layout", "project tree",
              "plan status", "book structure summary"],
    tool_name="composition_package_tree")
# args
book_id: UUID                      # required, explicit (IN-2)
detail: Literal["summary"] = "summary"   # reserved; only summary exists in v1
```

Response (shape, not prose — every list capped, caps reported):

```jsonc
{
  "book_id": "…",
  "manifest": { "work_id": "…", "project_id": "…", "status": "active",
                 "is_derivative": false } | null,          // the CANONICAL Work (§Canonical-Work
                                                           // scoping); null = none (never an error)
  "deps":     { "arc_templates_applied": 1, "motifs_available": 12 },
  "lock":     { "motif_applications": 7, "stale_pins": 2 },   // pinned_version < live_version
  "spec": {
    "arcs": [ { "id": "…", "kind": "arc", "title": "The Price", "status": "outline",
                 "chapter_count": 6, "source": "planforge" } ],   // ≤50, rank-ordered
    "arcs_capped": false,
    "outline": { "chapters": 40, "scenes": 214, "unwritten_scenes": 30 },
    "sources": { "authored": 180, "decompiled": 20, "planforge": 54 }   // IX-11 provenance
  },
  "tests":    { "canon_rules": 9, "threads_open": 3, "threads_paid": 11 },
  "manuscript": { "chapters": 42, "published": 40, "words": 812345 },  // via internal book client
  "index":    { "fresh": 38, "stale": 2, "draft_indexed": 2 },          // 26 IX-14's status
                                                           // machinery (shared helper) — never
                                                           // re-derived from raw IX-9 markers
  "runs": { "last_plan_run": { "id": "…", "status": "planned", "at": "…" } | null,
             "active_authoring_run": { "id": "…", "status": "running" } | null },
                                                           // owner-keyed today (25 F10): served to
                                                           // non-owners only under 25 OQ-3's VIEW
                                                           // resolution; else absent + warning
  "warnings": []            // e.g. "manuscript/index block unavailable: book-service unreachable"
}
```

Budget gate: a unit test packs a 10k-chapter fixture and asserts the serialized result ≤ **4K
tokens** (o200k estimate) — the AN-2 cap is enforced, not aspirational.

### `composition_find_references` (AN-3)

```python
meta = require_meta("R", "book",
    synonyms=["where is this character used", "entity usages", "find references",
              "who references", "appears in plan"],
    tool_name="composition_find_references")
# args
book_id: UUID
entity_id: UUID                                    # glossary entity id
sources: list[REF_SOURCES] | None = None           # None = all eight (seven F-A4 shapes; pov/present split)
limit: int = Field(20, ge=1, le=100)               # cap on returned refs (counts stay exact)

REF_SOURCES = Literal["outline_pov", "outline_present", "roster_bindings", "canon_rules",
                      "voice_profiles", "motif_roles", "entity_overrides", "grounding_pins"]
# registered in CLOSED_SET_ARGS (IN-3)
```

Response: `{"entity_id": …, "counts": {<source>: int, …}, "refs": [{"source": …, "node_ref":
{"kind": "outline_node|structure_node|canon_rule|voice_profile|motif_application|entity_override|scene_grounding_pin",
"id": …, "title": "…"}, "detail": "pov" }], "has_more": false}`. All eight source queries run
against the canonical Work's `project_id` (§Canonical-Work scoping). Description names the sibling
reads for the other layers: *"prose mentions → `glossary_list_chapter_links`; graph relations →
`kg_entity_edge_timeline`; evidence → `glossary_get_entity_evidence`."*

### `composition_diagnostics` (AN-4)

```python
meta = require_meta("R", "book",
    synonyms=["problems", "issues", "book health", "what's wrong", "diagnostics",
              "canon violations", "unpaid promises", "drift"],
    tool_name="composition_diagnostics")
# args
book_id: UUID
severity: Literal["error", "warn", "info"] | None = None   # None = all
category: Literal["canon", "conformance", "threads", "coverage", "index"] | None = None
limit: int = Field(30, ge=1, le=100)
```

Response:

```jsonc
{
  "items": [   // ranked: error → warn → info, then most-recent
    { "severity": "error", "category": "canon",
      "summary": "Scene 'The rite' contradicts canon rule 'She never begs'",
      "ref": { "kind": "outline_node", "id": "…", "chapter_id": "…" },
      "action": null },
    { "severity": "warn", "category": "conformance",
      "summary": "Arc 'The Price' — canon moved since last conformance (2 chapters)",
      "ref": { "kind": "structure_node", "id": "…" },
      "action": { "tool": "composition_conformance_run", "args": { "scope": "arc", "arc_id": "…" } } }
  ],
  "counts": { "error": 1, "warn": 4, "info": 7 },     // exact, uncapped
  "refs_capped": false
}
```

`action` names the Tier-W refresh where one exists — the tool proposes, never runs (AN-4).
Every source query runs against the canonical Work's `project_id` (§Canonical-Work scoping).
Contract snapshot asserts the closed `severity`/`category` output vocabularies and the severity
map (including thread debt's single-severity rule).

### `book_steering_list` / `book_steering_set` / `book_steering_delete` (AN-6, Go)

```go
// book_steering_list — Tier R, ScopeBook (VIEW). Returns every row (≤20 by cap):
//   {id, name, body, inclusion_mode, match_pattern, enabled, updated_at}
lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil,
    []string{"rules", "style guide", "story bible", "steering", "writing rules"})

// book_steering_set — Tier A, ScopeBook (EDIT). Upsert by name (CAT-1: name absent
// in the book ⇒ create; present ⇒ full replace, PUT semantics). Args:
//   book_id (uuid, required) · name (1..200 runes) · body (1..8000 runes)
//   inclusion_mode enum: always|scene_match|manual|auto  (default always;
//     description carries the auto-v1 honesty note from steering.go)
//   match_pattern (string, only meaningful with scene_match) · enabled (bool, default true)
// Result: {row, replaced: bool, prior: <old row>|null} + undo_hint:
//   replaced ⇒ {tool:"book_steering_set", args:<prior row>}
//   created  ⇒ {tool:"book_steering_delete", args:{book_id, name}}

// book_steering_delete — Tier A, ScopeBook (EDIT). Args: book_id, name.
// Result: {deleted: <row>} + undo_hint {tool:"book_steering_set", args:<row>}.
// Unknown name ⇒ one-line error (IN-6), never a silent no-op.
```

Cap violations return the server's actionable one-liners (body >8000: *"body exceeds 8000
characters (steering is injected into every matching turn — keep it tight)"* — already written,
reused verbatim). Row-cap (>20) tells the agent to delete or merge a rule first.

### `book_search` (AN-7, Go)

```go
// Tier R, ScopeBook (VIEW). Wraps runLexicalSearch (search.go:381).
lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil,
    []string{"grep", "find text", "exact phrase", "literal search", "where does it say"})
// args: book_id (uuid) · q (1..256 runes — maxSearchQueryRunes; literal, LIKE metachars escaped)
//   surface enum: draft|canon|all (default draft)
//   granularity enum: chapter|block (default chapter)
//   limit (1..100, default 20 — mirrors parseLimitOffset) · offset (≥0, default 0)
// result: {query, mode:"lexical", results:[{chapter_id, block_ref?, snippet, hl_start, hl_end}],
//          has_more}
// Description: "Literal text match. For meaning-alike passages use story_search instead."
```

### `book_scene_list.source_scene_id` (AN-5b — built in 22 A4, requirement recorded here)

One optional arg on 22 SC9's read tool: `source_scene_id: UUID` — filters the index to rows
back-linking that spec scene (uses `idx_scenes_source` from 22 A1). This completes the spec→prose
hop: `composition_get_outline_node` → `book_scene_list(source_scene_id=…)` →
`ui_focus_manuscript_unit(chapter_id, scene_id)`.

---

## Edit discipline — the safety contract (AN-8)

07S §5, verbatim: *"reversibility determines autonomy — an undoable action auto-runs; an action
that mutates durable state (publish, delete, spend, cross-service write) is gated behind a
human."* Mapped over every object class the agent can touch:

| Object class | Agent channel | Tier / gate | Undo path |
|---|---|---|---|
| **Prose — interactive edit** (chat, editor open) | FE `propose_edit` (insert/replace) — human Apply | FE card | human rejects the card; turn checkpoint (07S §5c) |
| **Prose — direct draft save** | `composition_write_prose` (`expected_draft_version`) / `book_chapter_save_draft` (`base_version`) | A + OCC | `chapter_revisions` restore (`book_chapter_restore_revision`) |
| **Prose — bulk codegen** | `authoring_runs` (20_agent_mode): `_create/_gate/_start` | W propose→confirm, budget + allowlist at start-gate | per-unit accept/reject + `_revert_all` (dependency-ordered, 07S edge #3) |
| **Prose — publish / delete / purge** | `book_chapter_publish`, `book_delete`, … | W (mints `confirm_token` → `confirm_action`) | unpublish / restore where the domain offers it |
| **Spec objects** (`structure_node`, `outline_node`, `scene_link`, `canon_rule`, intent fields) | direct MCP CRUD (23 BA11, 22 SC8) | A + `expected_version` OCC | `undo_hint` per tool (`_delete`↔`_restore`, inverse move/assign) |
| **Steering rules** | `book_steering_set` / `_delete` (this spec) | A (EDIT grant) | `undo_hint` carries the prior/deleted row (AN-6) |
| **Lockfile** (`motif_application`) | `composition_motif_bind` / `_unbind` | A | verified `undo_token` inverse |
| **Registry** (templates/motifs: adopt, mine, import-analyze) | `composition_motif_adopt`, `_mine`, `composition_arc_import_analyze` | W (cross-tier clone / LLM spend) | n/a — propose→confirm is the gate |
| **Glossary lore** | `glossary_propose_entities` (draft inbox) / FE `glossary_propose_entity_edit` (base_version) | A-inbox / FE card | inbox reject; version history |
| **KG facts/edges** | `kg_propose_fact` / `kg_propose_edge` → triage | propose | triage reject |
| **Generation / plan spend** | `composition_generate`, `plan_run_pass` (27), `composition_conformance_run` | W propose→confirm; `async_job` honesty (status-read before any "done") | corrections/regeneration ledger; pass re-run |
| **All reads** (incl. the five new R tools) | direct | R — callable in ask mode | n/a |

The invariant to test: **no tool in this spec's gap layer introduces a new row in this table** —
the three writes slot into the existing Tier-A + undo_hint row; a reviewer finding a new
confirmation convention here has found a defect.

---

## Context injection — automatic vs on-demand (AN-9)

What a studio-agent turn on a fully-packaged book carries, and where each piece is budgeted
(07S §1 buckets):

| Enters automatically (push) | Bucket | Source | Budget posture |
|---|---|---|---|
| Steering rules (always ∪ `#name` ∪ scene_match) | `steering` | `stream_service.py:3192-3220` ← `book_steering` | small, taxed every turn — the 8000-char/20-row caps ARE the budget |
| Working-memory anchor | `anchor` | `resolve_anchor` (`:2942-2950`) | pinned, small |
| Knowledge/RAG world block (+ current chapter boost) | `world` | `build_context` (`:2873`) | recomputed per turn, budgeted by `context_length` |
| Book note (book_id ≠ project_id, CTX-1) + ordered tail-blocks (skills, directory, plan-mode nudge) | `system` | `:3163-3186`, `:3293-3299` | floor |
| **Generation only:** arc chain, merged tracks, pacing position, roster_bindings, open promises | (pack) | `pack.py` after 23 BA12 | priority-ladder trim, `grounding_available` honesty |

| Pulled on demand (tools) | When the model reaches for it |
|---|---|
| `composition_package_tree` | orientation: session start on a book, "where are we", before claiming anything is set up |
| `composition_diagnostics` | "is the book healthy", after a draft lands, before a publish |
| `composition_find_references` + `glossary_list_chapter_links` + `kg_entity_edge_timeline` | rename/merge prep, "have I used this character" |
| `book_search` / `story_search` | literal vs semantic prose lookup |
| `composition_conformance_status` (26) | plan↔prose drift, per arc |
| prose/spec/scene reads (matrix row 2) | drill-down after any of the above |

**The decided default recipe: push stays exactly as shipped; the spec layer is pull-only in
chat.** No new per-turn fetch is added (AN-9's rationale: measured budget lessons beat
speculative convenience). The one static addition: the studio `book_context_note` gains a fixed
sentence naming the two orientation tools — text, not data; ~15 tokens.

---

## S06 flagship trace — Mai's session over the new surface (AN-11)

Vocabulary law: every confirmation below is rendered in Mai's words; the §1 denylist (arc, spec,
template, entity, kind, token, pass, checkpoint, conformance…) never reaches a progress-blocking
prompt. Letters = S06 §4 movements; PlanForge v2 passes (27) run beneath movement E.

| Movement | What fires (agent side) | What Mai sees |
|---|---|---|
| **A** — "here's my idea" | `composition_package_tree(book_id)` — ONE orientation read confirms an empty package (manifest null, 0 arcs, 0 chapters). No probing chain, no `find_tools` detour. | nothing — warmth, a reflection of her story |
| **B** — the spine | no machinery; conversation + the server-persisted "Story so far" | "the shape of it" |
| **C** — world rules | the existing S01/S06 path: `glossary_list_system_standards` → `glossary_adopt_standards` (W) → `glossary_propose_kinds`/`glossary_ontology_upsert` — referenced, unchanged | ONE plain confirm: "want me to set up your world so I keep all this straight?" |
| **D** — cast + the hard rule | `glossary_propose_entities` (A-inbox, unchanged). **Turn 9 — "write that down: she never begs" → `book_steering_set(name:"She never begs", body:<the rule in Mai's words>, inclusion_mode:"always")`** — the instruction becomes durable steering, injected into every future turn of this book, surviving compaction and sessions (the F4 canon-persist guard, made concrete). The agent tells her plainly: "I'll hold that as a rule — if I ever write her pleading, call me on it." | her words, kept; a plain "keep these?" list for the cast |
| **E** — the plan | `plan_propose_spec` → 27's passes. Pass-2 blocking checkpoint surfaces as *"I've pulled your main people from what you told me — keep these?"* (`plan_review_checkpoint` beneath); pass-4 as *"here's the ride, top to bottom — this is clay, not stone"*. `plan_compile` → **skeleton link (27 PF-8a)** mints `structure_node` + chapter nodes. **Then the honesty read: `composition_package_tree` again** — the agent verifies `spec.arcs ≥ 1`, `outline.chapters = plan events` **before** saying "your plan's in place" (the F7 false-done guard, structural: claim only what the tree shows). | a chapter-by-chapter plan she can read; one "lock it in?" |
| **F** — draft + revise | `composition_get_work` → `composition_generate` (W: *"I'll spend a bit to draft this against your story — go?"*) → note-driven revision via `composition_get_prose`/`composition_write_prose` (same scene, surgical — never a re-roll). After the draft: **`composition_diagnostics`** — if the draft tripped a canon contradiction ("she cries" vs the steering/canon rule), the agent sees it as an `error` item and fixes it *before* Mai has to catch it; her turn-14 correction becomes a rule-check the machine also runs. | prose that matches her vision; "new version" to compare |
| any point — "where are we?" | `composition_package_tree` + the Story-so-far | a warm plain recap, backed by real counts — never invented |

Acceptance additions to the S06 gate (rides `scripts/eval/run_discoverability_scenario.py` +
the S06 fixture): the steering row exists after turn 9 with Mai's wording; every "it's set
up"-class claim is preceded in the transcript by a `composition_package_tree` or equivalent
status read; discovery calls ≤2 per movement; §1-denylist grep = 0.

---

## Discoverability registration (AN-10)

| Tool | Service / prefix | Category (`tool_list`) | Tier | paid / async | Synonyms (recall seeds) |
|---|---|---|---|---|---|
| `composition_package_tree` | composition | `composition` | R | no / no | book overview · what's in this book · package layout · plan status |
| `composition_find_references` | composition | `composition` | R | no / no | where is this character used · entity usages · find references |
| `composition_diagnostics` | composition | `composition` | R | no / no | problems · issues · book health · what's wrong · unpaid promises |
| `book_steering_list` | book-service | `book` | R | no / no | rules · style guide · story bible · writing rules |
| `book_steering_set` | book-service | `book` | A | no / no | add rule · remember this rule · always do · never do |
| `book_steering_delete` | book-service | `book` | A | no / no | remove rule · forget rule |
| `book_search` | book-service | `book` | R | no / no | grep · find text · exact phrase · where does it say |

No `GROUP_DIRECTORY`/`CATEGORY_ENUM` change (F-A8). Meta wire coverage asserted against served
`tools/list` output per the existing `test_mcp_meta_async_wire.py` pattern (both services).

---

## Task breakdown

**Prerequisites:** 23 Phase 0/A + 25's migration train (the spec layer must exist for the tree/
references/diagnostics to read) — including 25 PM-3/PM-4 + OQ-2 (the canonical-Work resolution all
three composition reads scope by) and OQ-3 (the VIEW widening AN-2's `runs` block rides); 26 Phase
B/C (canon-markers batch + `arc_conformance_state` + the status machinery AN-2/AN-4 compose); 22
Phase A (scene reads, for the AN-5b filter's home).
AN-B (book-service tools) has **no** composition prerequisites and can build first.

### Phase AN-A — composition read tools (Python)
| # | Task | Files |
|---|---|---|
| A1 | `PackageTreeService`: layer aggregators (manifest/deps/lock/spec/tests/runs from own DB, canonical-Work-scoped; manuscript via the internal book client; index rollup via the shared IX-14 status helper (26 C3) extended with `draft_indexed` — no raw-marker re-derivation, no per-200-id fan-out; runs gated per 25 OQ-3; degrade-to-absent + warning) | `app/services/package_tree_service.py` (new), `app/clients/book_client.py` |
| A2 | `composition_package_tree` tool + the 4K-token budget test on a 10k-chapter fixture | `app/mcp/server.py`, `tests/unit/` |
| A3 | `ReferencesRepo.find_by_entity` — eight source queries over the seven F-A4 shapes (pov/present split; indexed where indexes exist; `present_entity_ids` GIN check — add only if EXPLAIN shows a scan on the fixture, via 25) + `composition_find_references` tool (`REF_SOURCES` → `CLOSED_SET_ARGS`) | `app/db/repositories/references_inverse.py` (new), `app/mcp/server.py` |
| A4 | `composition_diagnostics`: compose `conformance_status` machinery (26 C3) + `canon_issues` + BA15 thread query + coverage diff (shared helper with 24 H1.3 — ONE implementation) + severity map + ranking; contract snapshot for output vocab | `app/services/diagnostics_service.py` (new), `app/mcp/server.py` |

### Phase AN-B — book-service tools (Go; independent of AN-A)
| # | Task | Files |
|---|---|---|
| B1 | `book_steering_list/set/delete` MCP tools: upsert-by-name, prior-row return, undo_hints, cap one-liners, `inclusion_mode` enum | `internal/api/steering_tools.go` (new), `mcp_server.go` |
| B2 | `book_search` MCP adapter over `runLexicalSearch`; enum args mirror the route validators | `internal/api/search_tools.go` (new), `mcp_server.go` |
| B3 | Tier/meta boot tests (the existing every-tool-has-meta suite picks them up) + Go unit tests per tool | `internal/api/*_test.go` |

### Phase AN-C — cross-spec wiring
| # | Task | Files |
|---|---|---|
| C1 | `book_scene_list.source_scene_id` filter — **built inside 22 A4's task**; this phase only carries the contract test proving the spec→prose recipe end-to-end (AN-5b) | 22's `scene_tools.go` + a recipe test here |
| C2 | Static sentence in the studio `book_context_note` naming the two orientation tools (AN-9) | `services/chat-service/app/services/stream_service.py` |
| C3 | Discovery registration checks: all 7 appear in `tool_list` for their category; synonyms land in `find_tools` recall (the S02-style scenario harness) | `services/chat-service/tests/`, `scripts/eval/` |

### Phase AN-D — verification
| # | Task |
|---|---|
| D1 | **Cross-service live-smoke** (≥2 services, mandatory): seeded packaged book → `composition_package_tree` returns all 8 layers with real counts (manuscript block live from book-service) → break book-service → tree returns block-absent + warning, never zeros → `book_steering_set` a rule → a real chat turn on that book carries it in `<steering>` (effect, not row) → `book_search` finds a phrase `story_search` ranks low → `composition_diagnostics` shows a seeded canon contradiction as `error` and the conformance `action` pointer. Rebuild images first. |
| D2 | Effect tests: steering-set → next-turn injection (the AN-6 loop closed by EFFECT per Part 3); diagnostics item disappears after the underlying fix (canon resolved ⇒ error gone) |
| D3 | S06 flagship replay gate per AN-11 (per-movement checkpoint table; steering row + verification-read evidence; denylist grep = 0) |
| D4 | New real-DB test files carry `pytestmark = pytest.mark.xdist_group("pg")` |

**Ordering.** AN-B first (no prerequisites, immediate S06 value: steering + grep). AN-A after 23-A/25/26-C land. AN-C1 rides 22's build. Per `fanout-independent-slices-parallel-build-serial-integrate`: A and B fan out on disjoint services, ONE serial VERIFY at D1.

---

## Open questions

| # | Question | Disposition |
|---|---|---|
| OQ-1 | Should `composition_find_references` federate glossary chapter-links + KG edges into one cross-service backlink read? | ✅ **RATIFIED (PO 2026-07-10) — decision: NO in v1** (AN-3). The three reads exist; the tool's description names them; a federating proxy makes composition a read-router over three services (scope-separation smell) and triples its failure surface. Revisit trigger: transcript evidence of agents failing to compose the three calls. |
| OQ-2 | Should the studio turn auto-inject a one-line *live* package digest (counts + dirty flag) instead of the static tool-name sentence? | ✅ **RATIFIED (PO 2026-07-10) — decision: NO** (AN-9). It costs a cross-service fetch on every turn for context that's task-dependent; the measured lessons (`m3-pullmode-measured-nogo`, the 4000-token trim) say don't add per-turn cost without a measured win. Revisit with S06 replay data if orientation reads aren't happening. |
| OQ-3 | **Integrator:** the `book_scene_list.source_scene_id` filter (AN-5b) must land in 22 A4's build — one optional arg + the `idx_scenes_source` predicate. 22's current SC9 text doesn't name it. | Recorded for the integrator; the recipe test (AN-C1) reds until it exists. |
| OQ-4 | **Integrator:** AN-4 and 24 H1.3 both consume the coverage-diff (unplanned chapters) computation. | ✅ **Resolved (NC-1, 2026-07-10):** conformance/staleness has ONE server-side computation with its transports fixed — 24's Hub reads the IX-14 **route** directly (read surface #7; drift never rides `plan-overlay`); AN-2/AN-4 compose the **helper** into their one-call agent aggregates. The **coverage diff** (unplanned chapters) is a separate, cheaper computation: one composition-side helper shared by 24 H1.3's overlay and AN-4 — A1/A4's tasks name it explicitly. |
| OQ-5 | Anchored/diff-shaped prose edits (matrix row 6's residual gap): should the agent get a hunk-level prose write tool instead of whole-body `write_prose`? | **Decided: not here.** 07S §5c owns hunk-level review on the FE card path; a server-side anchored-edit tool is a manuscript-mutation design (DA-1-adjacent) that needs its own spec. Deferred, gate #2, tracked at SESSION time. |
| OQ-6 | Should `composition_diagnostics` include plan-run lint (S1–S8 `plan_validate` findings) for the book's latest run? | **Decided: no.** Plan lint is *run*-scoped build-graph state, owned by 27's ledger (`plan_pass_status`); diagnostics is *book*-scoped desired-vs-actual health. Mixing them would put a `.runs/` build log in the problems panel — different lifecycle, different consumer. The description cross-references `plan_pass_status`. |
| OQ-8 *(added at clearance, 2026-07-10)* | **The `resource_ref` convention** — the agent↔canvas addressing contract that lets a chat turn point at ("highlight") a specific spec object on the Plan Hub canvas (21 PH8's AI-edit highlighting; 24 Phase 4's `ai-pending` ghost nodes; 24 OQ-7's canvas-native plan-agent). Previously the one unspecced contract in the cluster, owned by nobody. | **HOMED HERE.** It is an agent↔GUI contract — exactly this spec's domain. **Deferred, tracked, gated:** it is required by nothing in v1 (P-13 ✅ made "Ask AI" = Compose chat with a selection ref) and gates only 24 Phase 4. **Trigger:** when 24 Phase 4 is scheduled, this spec gains an AN-12 section defining `resource_ref` (shape sketch: `{kind: 'structure'\|'outline'\|'motif_application'\|'canon_rule'\|'thread', id, version?}` — the same ref vocabulary the frontend-tools contract + `ui_focus` tools would consume, one name per concept per DA-10) **before** any Phase-4 build task starts. A Phase-4 build without AN-12 is a spec violation, not a shortcut. |
| OQ-7 | Steering write tier — A (auto + undo) or W (confirm)? | **Decided: A** (AN-6). The inverse is verified (prior row returned), rows are small and visible in the shipped steering panel, and the write gate (EDIT grant) matches the REST surface. Forcing a confirm card on "write that down" would make the agent *worse* at the S06 F4 guard than a human with the panel open. The PO may override to W if steering abuse shows up in transcripts. |

---

## Risks

| Risk | Mitigation (lesson) |
|---|---|
| `composition_package_tree` grows into a prose dump as fields accrete ("just add the synopses") | The 4K-token budget test (A2) is a hard gate; drill-down tools are named in the description; OUT-1 reference-first is the review standard (`extraction-over-extracts-4x-and-eager-wholebook`, the 146K incident) |
| The manuscript/index block fakes zeros when book-service is down | AN-2: absent + warning, never zero-faked; D1 smokes the degraded path explicitly (`fe-status-default-fallback-signals-backend-field-omission`) |
| Diagnostics or the tree re-implements staleness and drifts from 26/24 | AN-2 and AN-4 both compose the IX-14 machinery + a shared coverage helper (OQ-4); a second staleness computation is a review-red (`css-var-duplicated-across-two-consumers-drifts`) |
| The new R tools ship but the model never calls them (the S06 baseline failure: no attempt) | AN-10 synonyms + `tool_list` completeness + the static note (C2); D3's replay gate counts orientation reads — shipped-but-unfound is a FAIL, not a soft miss (`checklist-is-self-report-enforce-by-tests`) |
| Steering upsert silently clobbers a collaborator's rule edit | `_set` returns `replaced` + the prior row and the undo_hint restores it; the caps keep the store small enough to list-before-write, which the description instructs (`worker-loaded-id-needs-parent-scoping` family — scope + visibility over blind writes) |
| `book_steering_set` proves the write but the rule never reaches a prompt | D2's effect test drives a real turn and asserts the `<steering>` block (`emit-wiring-live-proof-catches-bypass-chokepoint`, mcp-tool-io Part 3) |
| Mock-green, live-red on the tree's cross-service block | D1 drives the consumer path on a rebuilt stack (`new-cross-service-contract-needs-consumer-live-smoke`, `live-smoke-rebuild-stale-images-first`) |
| `find_references` scans on `present_entity_ids` at 10k-scene scale | A3: EXPLAIN on the fixture decides the GIN index, added via 25 if needed — profiling evidence, not speculation (defer gate #4 discipline) |
| A future agent adds an eighth tool "to be thorough" | AN-1's closed enumeration + the matrix's disposition column state where every capability lives — an addition is a spec change, not a build detail |
| Weak model confuses `book_search` and `story_search` | Both descriptions contrast the pair explicitly (IN-7 one-concept-one-name applied to the *pairing*); S06 replay watches for the misuse |
