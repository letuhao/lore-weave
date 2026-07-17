# S-05b · UX hardening — clear the dead-ends + raise the GUI score

> **Follow-up to S-05**, driven by the user-perspective audit ([`S05_UX_AUDIT.md`](S05_UX_AUDIT.md),
> overall ≈ 6.1/10). S-05 shipped a **real, operable** feature (empty-shells + zero-callers killed), but a
> novelist still hits **1 dead button** (re_target UUID prompt), **raw-JSON** leaks, **KG jargon**, and
> **CRUD-affordance gaps** (no fact edit/undo signposting). This spec clears every dead-end and lifts the
> weak metrics (ease-of-use, beauty, consistency). **Service:** knowledge-service (one tiny verb) + FE.
> **No HTML draft** (all changes live on existing S-05 surfaces — the triage panel + the entity-detail
> fact section). **Size:** M (FE-heavy, one small BE route).

## What the audit found → what this spec builds

| # | Finding (audit) | Fix in this spec |
|---|---|---|
| **F1** 🔴 | `re_target` `window.prompt`s for a raw entity **UUID** — unusable | **Entity-search-select dialog** (mirror `CreateRelationDialog`'s `useEntities({search})` picker) → resolves an `entity_id`. |
| **F4** 🟠 | `map` `window.prompt`s for a raw **schema code** | **Code-select** over the resolved schema (`getResolvedSchema` edge-types/vocab), not free text. |
| **F3** 🟠 | Triage evidence + drill-in show **raw JSON** | A pure `triageEvidence(item_type, payload)` **sentence formatter**; never `JSON.stringify`. |
| **F5–F7** 🟡 | **Jargon**: predicate/object, 6 fact-types, triage labels | Plain-language relabels + one-line helper text; hide s/p/o behind an **"Advanced"** disclosure. |
| **F8** 🟡 | Facts have **no UPDATE** + no signpost | A **"Replace"** action = the two existing verbs composed (invalidate old → open the add-fact form prefilled → author new); a one-line "facts are corrected by replacing." |
| **F9** 🟡 | mark-wrong has **no Undo/history** (asymmetric w/ archive) | `POST /facts/{id}/revalidate` (clear `valid_until`) + an **Undo toast** mirroring entity-archive. |
| **F10** 🟡 | "+ Add fact" buried | The create-entity path **already exists** (`CreateEntityDialog` in `EntitiesTab`) — so this shrinks to: verify it's reachable + (optional) cross-link it from the entity-less state, no new build. |
| **F11** 🟡 | Empty triage panel gives **no orientation** | A richer empty state (one sentence: what triage is + that a clean graph is good). |
| **F2** 🟠 | `window.confirm` for mark-wrong / schema-write | **Kept** — the app already uses `window.confirm` (entity archive/unlock), so these are CONSISTENT. A themed AlertDialog is a **repo-wide** polish item, tracked separately (NOT S-05b — it'd touch every confirm site). Only the `prompt`s (F1/F4) are S-05b. |

## SEALED decisions (CLARIFY — do not re-litigate)

| # | Decision | Rationale |
|---|---|---|
| CV-1 | **re_target/map get in-panel Radix pickers, NOT new backend.** The resolve route already accepts `params.target_entity_id` / `params.map_to`; only the FE input changes. | The dead-end is a FE input problem, not a contract gap. |
| CV-2 | **F1 reuses `CreateRelationDialog`'s entity-search-select** (`useEntities({search: debounced})` → pick → id). No new picker component invented if that one is extractable. | One home for entity-picking; proven pattern. |
| CV-3 | **F9 undo needs a real `revalidate` verb** (clear `valid_until`). It is owner-scoped, mirrors relations' `recreate` resurrection, emits nothing (a self-undo isn't a learning correction). | merge_fact's MATCH never clears `valid_until`; re-authoring can't undo. A 1-route add. |
| CV-4 | **F8 "Replace" = compose invalidate + author** (no new in-place UPDATE — bitemporal stays). The form prefills from the old fact; on save it invalidates the old id then authors the new. | Honors the by-design no-UPDATE while giving the user the edit they expect. |
| CV-5 | **De-jargon is COPY + disclosure, not a data change.** Fact-type *values* stay the closed 6 (`FactType`); only labels/helpers change. s/p/o inputs move under an "Advanced" toggle (default collapsed). | Don't churn the contract; reduce cognitive load. |
| CV-6 | **F2 window.confirm stays** (consistent w/ existing app); a themed confirm is a separate repo-wide track. | Scope discipline — replacing every confirm is not S-05's job. |
| CV-7 | **Evidence formatter is PURE + per-item_type** (a closed set), returns a sentence; unknown item_type → a safe generic sentence, never JSON. | Testable; no raw machine data ever reaches the user. |

## Slices (each: done = tests green)

### S5b-1 · re_target entity-picker (F1) — the dead-button killer
- Extract/reuse the entity-search-select from `CreateRelationDialog` into a small `EntityPicker` (or a
  `TriageRetargetDialog` that embeds it). Radix dialog; `useEntities({projectId, search: debounced})`.
- `TriageQueue.handleAction('re_target')` opens the dialog instead of `window.prompt`; on pick →
  `resolve({ signature, action: 're_target', params: { target_entity_id } })`.
- **Tests:** dialog opens; typing searches; picking fires resolve with the id; cancel fires nothing (no
  silent no-op); the UUID prompt is gone.

### S5b-2 · map code-select (F4)
- `getResolvedSchema(projectId)` → the valid edge-type / vocab codes; render a `<select>` (or combobox) of
  them for `map` instead of the free-text prompt. Blank/"keep detected" stays an explicit option.
- **Tests:** the select lists real schema codes; picking fires `resolve(map, { map_to })`; keep-detected
  sends `{}`.

### S5b-3 · humanize triage evidence (F3)
- Pure `triageEvidence(item_type, payload): string` — one sentence per item_type (unknown_edge_type →
  «the relationship "…" isn't in your schema»; unknown_vocab_value → «the value "…" isn't in the "…" set»;
  edge_kind_mismatch, unknown_node_kind, edge_cardinality_conflict likewise). Drill-in rows use it too.
  Never `JSON.stringify`.
- **Tests:** each item_type → a sentence (no `{`/`}`); an unknown type → the generic sentence, not JSON.

### S5b-4 · de-jargon (F5–F7)
- Fact form: relabel the 6 fact-types to plain language + a one-line helper ("What kind of thing is this?");
  move predicate/object under an **"Advanced"** `<details>` (default closed) with relabelled placeholders
  ("relationship" / "related to"). i18n copy only.
- Triage: relabel actions + item-type headers to a novelist's words (keep the enum values); each row keeps a
  short description.
- **Tests:** the Advanced block is collapsed by default; the s/p/o inputs still POST when expanded; the new
  keys exist in all 17 locales (i18n gate).

### S5b-5 · fact Replace + mark-wrong Undo (F8, F9)
- **BE:** `POST /v1/knowledge/facts/{fact_id}/revalidate` — clear `valid_until` (owner-scoped; idempotent;
  no event). Mirrors `invalidate_fact`.
- **FE:** on invalidate success, a toast with **Undo** → `revalidate` → the fact reappears (mirror the
  entity-archive toast). A **"Replace"** action on a committed fact → opens the add-fact form prefilled from
  that fact; on save → invalidate the old id, then author the new (CV-4). A one-line "to correct a fact,
  replace it."
- **Tests:** BE revalidate clears valid_until + is owner-scoped (404 cross-user); FE Undo re-shows the fact;
  Replace prefills + composes invalidate→author.

### S5b-6 · discoverability (F10, F11)
- Create-entity **already exists** (`CreateEntityDialog` in `EntitiesTab`) — verify it's reachable; the
  only net-new is (optional) a hint from the empty facts/entity state pointing to it. No new create flow.
- Triage empty state → one orienting sentence.
- **Tests:** empty-state copy renders; (if a hint is added) it opens the existing create dialog.

## Adherence (repo invariants)
- **Frontend-Tool-Contract:** re_target/map still send closed-set `TriageAction`; the pickers only change
  HOW `params` are gathered — the contract is unchanged. No new panel_id.
- **Tenancy:** the `revalidate` route is owner-scoped (`user_id=caller`), 404 on cross-user (KSA §6.4),
  exactly like `invalidate`. The entity picker searches only the caller's own entities (`useEntities` is
  user-scoped).
- **i18n:** all new copy in the `knowledge`/`studio` namespaces, en-first + `i18n_translate.py` gap-fill
  (17 locales) — the ML-7 gate enforces.
- **No new MCP tool** (CV-2 of S-05 stands — agent parity already exists; these are human-surface UX only).

## Out of scope / by-design
- In-place fact UPDATE (bitemporal — Replace is the path). Do not build.
- A repo-wide themed-confirm to replace every `window.confirm` (F2) — separate cross-cutting track.
- Touch-first drag/gesture redesign — the S-05 surfaces are click/tap already (no HTML5-drag here, unlike
  the parts navigator the audit's sample scorecard described).

## Expected score lift (targets)
Usability 6.5→8.5 (dead button gone), Ease-of-use 5→7.5 (de-jargon + pickers), Beauty 5.5→7.5 (no JSON/no
prompt), Consistency 5.5→7.5 (app pickers not OS prompts), Discoverability 6→7.5. **Overall ≈ 6.1 → ≈ 7.8.**
