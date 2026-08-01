# Motif translate — the user-paid runtime path

**Date:** 2026-07-29 · **Size:** XL (files 16, logic 14, side-effects 3: MCP surface, billing, worker op)
**Branch:** `feat/frontend-tools-mcp-migration`
**Spec:** [`docs/specs/2026-07-29-motif-i18n.md`](../specs/2026-07-29-motif-i18n.md) §5 — the policy this implements
**Follows:** `1381370c7` (identity re-arch) · `70b355421` (17 platform locales) · `68e9cf4c9` (audit)

## The gap

Three cycles landed the *storage*, the *resolution* and the *platform corpus*. §5 of the spec says a
user pays for their own demand languages — and today **there is no way to pay**. A user-authored motif
has `original_language = <whatever they wrote in>` and zero translations, forever. Every read falls
back with `text_fallback: true` and nothing anywhere can clear it.

So the policy is implemented in the half that *refuses* (we never spend tokens on a user's motif behind
their back) and absent in the half that *permits* (they may spend their own). That asymmetry is the bug:
"we don't translate for you" currently reads as "you can't translate".

## Decisions

**D1 · Tier-W propose/confirm → worker job**, mirroring `composition_motif_mine` exactly.
Not a lazy read-through fill (the KG-TL M3 pattern): a lazy fill *is* translating on our own
initiative, which §5 forbids. The spend must be an explicit, confirmed, human act.

**D2 · A new W-class MCP tool `composition_motif_translate`.** The repo rule is "don't add a tool if an
existing one can carry it" — the candidate was `composition_motif_edit` (the unified motif-CRUD
dispatch), and it cannot: it is class **A** (auto-applied, no spend), while a translate is class **W**
(mints a confirm token + $ estimate, nothing runs until confirmed). Folding a W op into an A tool would
make one tool's ops disagree about whether they cost money — the exact ambiguity the class marker
exists to remove. No other W-class motif tool is a plausible home (`_mine` discovers patterns).

**D3 · The caller names the model** (`model_ref` + `model_source`), like every other Tier-W motif op —
not translation-service's saved translation preference. Two reasons: a motif is composition's own
domain object, and the craft prompt is narrative-specific (beat / reversal / motif), not the prose
translator's. The call goes through composition's `LLMClient` → provider-registry, so the
provider-gateway invariant holds and the user's BYOK model bills the user.

**D4 · Batch by motif_ids (1..50), one LLM call per motif.** Per-leaf calls would lose the motif's own
name/summary as context — the dev-time tool injects exactly that, and it is what makes the craft
translation good. One call per motif keeps the context and keeps the key-set verification meaningful.

**D5 · Tenancy — a user may translate only what they own.** `motif_translation` rows on a **system**
motif are System tier: admin/seed-only. A user-writable translation on a shared row is a tenancy
defect (the kinds bug, exactly). Allowed: `owner_user_id = caller`, or a `book_shared` row with EDIT on
the book (book tier). A system motif is refused with a message pointing at the free 17 locales.

**D5b · A target language is a closed set** — the platform's supported locales, as a `Literal` on the
tool arg. Frontend-Tool-Contract IN-rule, and it is also what stops `language="auto"` reaching the read
path (`D-MOTIF-AUTO-LANGUAGE-ZEROES-RETRIEVAL` was that bug once already).

**D5c · Echo is detected and reported, not retried.** The dev-time tool self-heals with `--rounds`
because nobody is watching a 17-locale batch. At runtime the user is watching and has already paid for
one pass; a silent second pass would double their spend. So the job result carries `echoed` — the leaves
that came back byte-identical to their English source — and the FE says so. Cheap, honest, no extra
spend. (The predicate exists twice by necessity — `scripts/i18n_translate.py` cannot import from a
service — so a test binds the two implementations to one calibration table.)

**D6 · Flatten/unflatten moves into `app/motif_i18n.py`.** `scripts/motif_translate.py` gets it from
`i18n_translate` today; the runtime engine cannot import from `scripts/`. Two copies of the key scheme
across the dev-time corpus and the runtime corpus is the drift this module was created to prevent —
so it becomes one definition in the shared contract module and the script imports it from there.

## Slices

| # | Slice | Files |
|---|---|---|
| **A** | `flatten_entry`/`unflatten_entry` → `app/motif_i18n.py`; script imports from there | `app/motif_i18n.py`, `scripts/motif_translate.py` |
| **B** | Engine `app/engine/motif_translate.py` — resolve targets, gate tenancy, build prompt, LLM, verify key-set, per-leaf fallback, upsert | new |
| **C** | `MotifRepo.upsert_translation` + `translation_status` read | `motif_repo.py` |
| **D** | MCP tool `composition_motif_translate` (W, async_job) + size-derived estimate | `mcp/server.py` |
| **E** | Descriptor `composition.motif_translate` + dispatch + `_execute_motif_translate` | `routers/actions.py` |
| **F** | Worker op `translate_motif` + dispatch branch | `worker/constants.py`, `worker/job_consumer.py` |
| **G** | FE api propose/confirm/poll + hook + drawer affordance + badges + i18n | `motif/api.ts`, `hooks/useMotifTranslate.ts`, `components/MotifTranslateAction.tsx`, `MotifDetailDrawer.tsx`, `types.ts`, locales |
| **H** | **`original_language` is never authored** (found at design review) — FE create sends it, BE lets it be corrected | `MotifEditorForm.tsx`, `useMotifEditor.ts`, `api.ts`, `models.py`, `motif_repo.py`, `mcp/server.py` |

### Slice H — the defect this feature was about to be built on top of

`grep original_language frontend/src/features/composition/motif/**` returns **nothing**. The FE create
path never sends it, so every user-created motif takes the model default `"en"` — including one a
Vietnamese author wrote entirely in Vietnamese.

That is the wrong-language bug again, moved into the user tier. A vi-authored motif stamped `en`:
- asked for `vi` → we "translate" Vietnamese into Vietnamese, and the user pays for it;
- asked for `en` → returns Vietnamese text labelled `text_language: "en"`, `text_fallback: false` —
  a caller (model prompt included) is told it is English. Silent, exactly like the bug the spec opens with.

`MotifPatchArgs` also refuses `original_language`, under a comment written when language *was* identity
("identity/lineage are immutable post-create"). It is not identity any more — the whole point of the
re-arch was that language is a view. So it becomes patchable, and the create form authors it
(defaulting to the UI language, which is the best available guess at what the user is typing in).

Not scope creep: without it, the paid path's very first question — "what language is this motif in?" —
is answered by a default nobody set.

## What must be proven, not asserted

1. A **system** motif refuses the translate (tenancy) — and the refusal is reachable through the MCP
   tool, not only the engine.
2. A motif the caller does **not** own refuses.
3. A key the model drops or renames does **not** blank the leaf — it falls back to source wording.
4. A drifted `beats[].key` from the model does **not** silently fail to merge (the structural gate).
5. The upsert **cannot overwrite an `authored` row** (the seeded Vietnamese) — same guard as the seeder.
6. `source_content_hash` is stamped from the source the translation was actually made from, so the
   staleness signal keeps meaning.
7. Live: a real LLM call against the test account's local model translates a real user motif, and the
   list route then returns it with `text_fallback: false`.

## Out of scope

- Arc templates (`arc_template.language` still inside `uq_arc_template_*` — the same defect, tracked).
- Re-translating on source edit (the `text_stale` badge tells the user; clearing it is their paid act).
- Auto-translate of anything, ever.
