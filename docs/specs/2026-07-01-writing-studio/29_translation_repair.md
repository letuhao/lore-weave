# 29 — Translation surfaces: defect audit + repair spec

Status: CLARIFY complete · DESIGN reviewed (edge cases resolved) · PO decisions taken
(2026-07-10). Ready for PLAN.
Size: L (10 confirmed defects across 2 services + 12 secondary findings; one — T3 —
carries a 3-table data migration that earns its own deferral).

Origin: user report against the shipped `translation` dock (spec
[17](17_translation_enrichment_sharing_settings_docks.md)):

> "the translation matrix have no button to translate compared with old GUI · translate
> mode translate panel have a translate button but pressing it does nothing · there is no
> modal to pick language to translate"

All three reproduced. They are **not one bug** — see T1, T5, T8.

---

## How this was verified (evidence, not inference)

Live browser smoke against a real stack (vite dev `:5199` → gateway `:3123` → docker
compose), account `claude-test@loreweave.dev`, books `Dracula` (`019eeb09-…`, 8 chapters,
2 languages with data) and `Ma Nữ Nghịch Thiên (POC)` (`019f1783-…`, 14 chapters, 0
translations). Both a **healthy** backend and a **deliberately stopped**
`translation-service` were exercised, because the two produce different symptoms and the
user hit both.

**Environment finding (not a code bug, but it is what the user saw first):**
`infra-translation-service-1` was `Exited (255)` for ~2h at the time of the report (clean
shutdown, no crash in logs — killed externally, alongside `infra-notification-service-1`).
Every `/v1/translation/*` call 500s in that state. Both were restarted during this
investigation and are healthy again.

**The through-line of this spec:** the translation UI has no degraded mode and no
end-to-end selection contract. An ordinary dependency outage (T4/T5/T6) and an ordinary
"I ticked three chapters" (T8) both terminate in a screen where nothing visibly happens.

---

## Confirmed defects

| ID | Sev | Surface | Symptom |
|---|---|---|---|
| **T1** | HIGH | `translation` matrix | No Translate CTA at all on a book that already has ≥1 translated language |
| **T8** | HIGH | `translation` matrix → `TranslateModal` | "Translate Selected (N)" **discards the selection**; on a fully-translated book every action in the modal opens disabled |
| **T2** | HIGH | `translation` matrix | Untranslated chapters are invisible — the matrix renders coverage rows, not chapters |
| **T4** | HIGH | `translation` matrix | Coverage failure ⇒ raw proxy-error string, no retry, no CTA; while loading, a textless skeleton |
| **T5** | HIGH | `TranslateModal` | Wedges on "Loading chapters…" with no language picker, no model picker, no error, no timeout |
| **T6** | MED | `ChapterTranslationsPanel` | Degrades silently: blank title, `??` language, zero targets, no error banner |
| **T3** | MED | matrix + BE | Free-text `target_language` ⇒ duplicate columns (`Vietnamese` **and** `vi`) |
| **T7** | MED | `VersionSidebar` | No way to add a *new* target language except through the Re-translate modal |
| **T9** | MED | matrix + BE | `VIEW`-grant collaborators are shown translate actions; job creation requires `EDIT` ⇒ late 403 |
| **T10** | MED | `translation` matrix | Chapter-list fetch failure renders "No chapters to translate" — a real error shown as an empty book |

### T1 — the matrix has no Translate button

`setTranslateOpen(true)` has exactly **two** call sites in
[TranslationTab.tsx](../../../frontend/src/pages/book-tabs/TranslationTab.tsx):
[:347](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L347) (the
`visibleLangs.length === 0` empty state) and
[:521](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L521) (inside
`FloatingActionBar`, which renders only when `selectedChapters.size > 0`).

The header row ([:284-297](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L284-L297))
holds only the language **Filter** button — itself gated on `allLanguages.length > 3`.

So on a book with at least one translation the matrix renders **zero** translate
affordances until the user guesses that ticking a row checkbox reveals a floating bar.
Live on `Dracula`, the only visible buttons were per-cell status chips (`Done`/`Failed`)
and the `1 affected` legend chip. `Plus` and `AlertCircle` are imported at
[:6](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L6) and never used —
vestigial imports of a header CTA that does not exist in this tree.

### T8 — "Translate Selected" throws the selection away

[TranslationTab.tsx:300-305](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L300-L305)
renders the modal with **no `preselectedChapterIds`**:

```tsx
<TranslateModal open={translateOpen} onClose={…} bookId={bookId} onJobCreated={…} />
```

Both sibling call sites do pass it —
[ChapterBrowserTitleView.tsx:509-515](../../../frontend/src/features/studio/panels/ChapterBrowserTitleView.tsx#L509-L515)
and `TranslationTab`'s own
[ExtractionWizard:539-545](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L539-L545).
Only the translate path drops it.

Consequences, in order of severity:

1. The modal re-derives its own default selection as *"every chapter that needs work in the
   book's default language"*
   ([TranslateModal.tsx:131-137](../../../frontend/src/pages/book-tabs/TranslateModal.tsx#L131-L137)),
   so the user's chapter choice — and the language column they clicked — are silently
   replaced.
2. `Select affected` ([:244](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L244))
   → `Translate Selected` therefore does **not** translate the affected chapters. It
   translates whatever `needsIds` computes.
3. **On a fully-translated book, every action in the modal opens disabled.** `neededIds`
   is `[]`, so the primary CTA is replaced by the force-retranslate branch, whose button is
   disabled because `selectedChapters.size === 0`; the footer's `Translate 0 selected` is
   disabled for the same reason. The modal's own comment states the assumption that is
   being violated:

   > *"Offer a direct force-retranslate of the SELECTED chapters (**the per-chapter page
   > preselects this chapter**) so making a fresh translation is always one click"*
   > — [TranslateModal.tsx:399-404](../../../frontend/src/pages/book-tabs/TranslateModal.tsx#L399-L404)

   The per-chapter page does preselect. The matrix does not. So from the matrix, that
   safety net is itself a dead end — the user presses Translate and nothing can happen.

This is the healthy-backend half of "press it and nothing happens", and it is a one-prop
fix plus a language hand-off.

### T2 — untranslated chapters never appear in the matrix

The table body maps **coverage rows**, not chapters:
[TranslationTab.tsx:383](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L383).
Backend [`coverage.py:67+`](../../../services/translation-service/app/routers/coverage.py#L67)
derives rows from `chapter_translations` only, so a chapter with no translation yields no
row. Live on `Dracula`: legend reads **"Showing 4 of 8 chapters"**, `tbody` has 4 rows. The
4 untranslated chapters have no checkbox and cannot be selected.

Combined with T1 and T8, a partially-translated book shows no translate button, hides
exactly the chapters that need translating, and discards the selection if you find one.

### T4 — coverage failure leaves the panel unusable

[TranslationTab.tsx:251-260](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L251-L260):

```tsx
if (loading) return (<div className="space-y-3 p-6"><Skeleton .../><Skeleton .../></div>);
if (error)   return <div className="p-6 text-sm text-destructive">{error}</div>;
```

With `translation-service` stopped the panel renders, verbatim and permanently:

> `Error occurred while trying to proxy: localhost:3123/v1/translation/books/019eeb09-…/coverage`

No retry, no translate CTA, no human-readable message — a raw proxy string leaked to the
user. While the query retries, the skeleton branch renders **zero text** (measured
`innerText.length === 0` on a 1103×491 panel): an empty broken panel, which is precisely
how "the matrix has no button to translate" was first described.

### T5 — `TranslateModal` wedges on "Loading chapters…"

[TranslateModal.tsx:113-155](../../../frontend/src/pages/book-tabs/TranslateModal.tsx#L113-L155)
awaits a `Promise.all` whose two `.catch(() => null)` guards protect against **rejection,
not latency**. There is no timeout and no error branch, and while `loading` is true the body
renders only `Loading chapters…`
([:308-312](../../../frontend/src/pages/book-tabs/TranslateModal.tsx#L308-L312)) — so the
target-language `<select>`, the `ModelPicker` and the chapter checklist are all absent and
the footer shows a disabled `Translate 0 selected`.

Measured: with the service stopped, ~5-10 s frozen (proxy connect-timeout) before
recovering. In one run against a just-restarted service it stayed stuck past **9 s** while
the same endpoints answered a direct `fetch` in 36 ms. If the dependency *hangs* rather
than refuses, the state is permanent.

This is both "press it and nothing happens" **and** "there is no modal to pick language" —
the modal did open, it just never rendered its own controls.

### T6 — `ChapterTranslationsPanel` degrades silently

The component behind the editor's Translate workmode
([ChapterEditorPage.tsx:1190-1198](../../../frontend/src/pages/ChapterEditorPage.tsx#L1190-L1198))
and the studio `translation-versions` panel. `loadAll`
([:66-96](../../../frontend/src/features/translation/components/ChapterTranslationsPanel.tsx#L66-L96))
runs a `Promise.all` in which `versionsApi.listChapterVersions` has **no** `.catch`, so any
`translation-service` failure rejects the batch → one `toast.error` → `finally` clears
`loading`. The panel then renders a structurally-fine, factually-empty UI.

Live with the service down: chapter title blank (breadcrumb `— Translations`), original
language `??`, `LANGUAGES` containing only `Original`, zero versions, **no error banner
anywhere**. The toast is long gone by the time the user looks.

### T3 — free-text `target_language` pollutes the matrix

`GET …/coverage` returns `known_languages: ["Vietnamese", "vi"]`; the matrix renders two
columns for one language (`Vietnamese (Vietnamese)` and `Tiếng Việt (vi)`), because
`getLanguageName('Vietnamese')` has no entry and echoes the raw string.

`TranslateModal`'s `<select>` only ever emits codes, so the bad value entered through
another writer. The MCP tool declares the arg as an unconstrained string —
[`mcp/server.py:220`](../../../services/translation-service/app/mcp/server.py#L220):
`target_language: Annotated[str, "The target language code (e.g. 'en')."]` — which is a
`closed-set arg ⇒ enum` violation of [mcp-tool-io](../../standards/mcp-tool-io.md). The BE
stores whatever it is handed.

This is the **cross-service normalization bug class** already in project memory: a value
crossing a service boundary is stored unreconciled and later used as an identity key.

### T9 — `VIEW` collaborators are offered an action they cannot perform

Coverage requires `VIEW`
([coverage.py:59](../../../services/translation-service/app/routers/coverage.py#L59));
job creation requires `EDIT`
([jobs.py:55](../../../services/translation-service/app/routers/jobs.py#L55)). A `VIEW`-only
grantee therefore loads the matrix, sees `Translate Selected` (and, after T1, a header CTA),
and is refused at submit. The frontend has no signal to gate on: `Book`
([books/api.ts:6-24](../../../frontend/src/features/books/api.ts#L6-L24)) exposes
`owner_user_id` but no `role` / `grant_level` / `can_edit`. Comparing `owner_user_id` to the
current user is not sufficient — it would also hide the button from legitimate `EDIT`
collaborators.

### T10 — a failed chapter fetch is rendered as an empty book

`chapters = chaptersData?.items ?? []`
([:163](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L163)) and the
`chaptersData` query has no error surface, so a book-service failure falls through to
[:262-266](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L262-L266) →
`EmptyState "No chapters to translate. Create chapters first."` The same class as S3 below:
an error rendered as a benign fact.

---

## Edge cases resolved (design decisions)

Each decision below was forced by an edge case that the first draft of this spec did not
survive. `D#` are binding for BUILD; the three that need a product call are escalated to
Open questions.

**D1 — the header CTA is `Translate…`, unscoped, and outlives the early returns (PO,
2026-07-10).** The button opens `TranslateModal` with **no** preselection; the modal's own
summary block (`Translate what needs it (N)`) owns scope, because it only knows what "needs
work" *after* the user has chosen a language. A pre-scoped header button would have to
commit to the book-default language before the user picked one — the same mistake T8 makes.

Placement: T1's button is useless if it lives below `if (loading) return …` /
`if (error) return …`. Restructure so the header always renders, with the table region owning
the loading/error/empty branches. The CTA is enabled whenever `chapters.length > 0`; it does
**not** depend on coverage (the modal already tolerates `coverage === null`).

**D2 — the empty-state CTA stays.** Header `Translate…` and the empty state's
`Start Translation` coexist; they occupy different regions and the empty state is the
discoverable primary for a fresh book. Not a duplicate to remove.

**D3 — the matrix renders one row per *chapter*, left-joined onto coverage.** The component
already fetches the full chapter list
([:145-160](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L145-L160)); a missing
coverage row is a legitimate all-`—` row (`cellContent` already handles `undefined`). Every
derivation currently keyed off `coverage.coverage` moves to the chapter list:
`toggleAllChapters` ([:216-220](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L216-L220)),
`allSelected` ([:271](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L271)),
`summaryCounts` ([:224-237](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L224-L237)),
`staleChapterIds` ([:97-112](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L97-L112)),
`showing_chapters` ([:472](../../../frontend/src/pages/book-tabs/TranslationTab.tsx#L472)).
Rows sort by `sort_order`, so the `#` column becomes the true chapter number rather than a
coverage-row index.

**D4 — D3 needs pagination.** Today the matrix is bounded by coverage rows; one row per
chapter is unbounded, and this repo explicitly supports 2000+ chapter books
([TranslateModal.tsx:36-37](../../../frontend/src/pages/book-tabs/TranslateModal.tsx#L36-L37)).
Reuse the existing `usePagedList` + `Pager` (already paired in `TranslateModal`) at 100
rows/page. Selection is a `Set<chapter_id>` and survives paging; `toggleAllChapters` selects
**all chapters**, not just the visible page, and the label must say so.

**D5 — orphan coverage rows are surfaced, never silently dropped.** A left-join by chapter
hides coverage rows whose `chapter_id` is not in the active list (a trashed chapter that
still has translations). Silent truncation is the anti-pattern; render a footnote — *"N
translations belong to trashed chapters"* — instead of dropping them without a word.

**D6 — `TranslateModal` receives both the selection and the language.** Fixing T8 by
passing `preselectedChapterIds={[...selectedChapters]}` is necessary but not sufficient: a
cell click carries a *language* too. Add an optional `preselectedLang` so
`Select affected → Translate Selected` targets the column the user was looking at. When the
modal is given a preselection it must **not** re-derive the default selection on a language
change ([:205-209](../../../frontend/src/pages/book-tabs/TranslateModal.tsx#L205-L209)
already guards this — keep it).

**D7 — the modal seeds settings only once, and never clobbers a user's choice.** T5's fix
renders the language/model pickers immediately (they need no network), which introduces a
race: the in-flight `getBookSettings` would overwrite a language the user picked meanwhile
([:126-128](../../../frontend/src/pages/book-tabs/TranslateModal.tsx#L126-L128)). Seed
behind a `seeded` ref; skip seeding any field the user has already touched. Correspondingly,
`handleLangChange`/`handleModelChange` must not `PUT` book settings before the initial `GET`
resolves, or a fast click writes over the value it is about to read.

**D8 — the spinner is scoped to the chapter checklist, and it can time out.** Only the
checklist depends on the network. Wrap the loads in an `AbortController` with a timeout
(the abort must propagate into `fetchAllChapters`'s paging loop), and render an inline
error + `Retry` in the checklist region rather than replacing the whole dialog body. When
`preselectedChapterIds` is present the submit stays enabled even if the chapter list fails —
the ids are already known.

**D9 — errors are typed, not stringified.** T4/T6 must distinguish *retryable* (5xx,
network) from *terminal* (403 no grant, 404). A 403 renders "you don't have access to this
book's translations", never a `Retry` button. Never render `(error as Error).message`
directly — that is what leaked the proxy string.

**D10 — T9 splits across phases (PO, 2026-07-10).** Phase A keeps translate actions ungated
(status quo) but **must** surface the `EDIT`-grant 403 as a readable toast — a silent 403 is
the exact bug class this spec exists to kill, and leaving it silent while fixing T5 would be
incoherent. Phase C then adds the caller's effective grant to the book read
(`my_grant_level: 'view' | 'edit' | 'owner'`) and disables the affordance **with a reason**
rather than hiding it (a hidden button is indistinguishable from the T1 bug). This keeps
Phase A frontend-only and off the cross-service live-smoke gate.

**D11 — `translation-versions` becomes one singleton.**
[EditorPanel.tsx:351](../../../frontend/src/features/studio/panels/EditorPanel.tsx#L351)
opens `translation-versions:<chapterId>` with a `component` override while
[TranslationPanel.tsx:26](../../../frontend/src/features/studio/panels/TranslationPanel.tsx#L26)
opens the bare `translation-versions` id — two dock tabs for one panel, contradicting
`TranslationVersionsPanel`'s own "params-retargeting singleton" doc comment. The editor
adopts the bare id (S10).

**D12 — T3's write-side fix ships; T3's backfill is deferred with a row.** Stopping the
bleed is cheap; merging the data is not. See the next section.

### D12 in full — why the `Vietnamese` → `vi` backfill cannot ride along

`target_language` is an **identity key in three tables**, each of which collides on merge:

| Object | Key | Collision on merging `Vietnamese` into `vi` |
|---|---|---|
| `chapter_translations` | `UNIQUE (chapter_id, target_language, version_num)` ([migrate.py:172](../../../services/translation-service/app/migrate.py#L172)) | `Dracula` ch.1 has 2 `Vietnamese` versions and 1 `vi` version — `version_num` 1 exists twice ⇒ index violation. Requires renumbering. |
| `active_chapter_translation_versions` | `PRIMARY KEY (chapter_id, target_language)` ([migrate.py:176-180](../../../services/translation-service/app/migrate.py#L176-L180)) | Both languages may have an active version ⇒ two rows collapse to one PK. Requires choosing a winner. |
| `translation_chapter_memos` | `PRIMARY KEY (book_id, chapter_index, target_language)` ([migrate.py:222-227](../../../services/translation-service/app/migrate.py#L222-L227)) | Same shape. |

That clears defer-gate #2 (large/structural — needs a migration and a
which-version-wins product rule). **Write-side validation does not**, and ships in Phase C.

### D13 — the language registry is the SSOT; the closed set comes from it (PO, 2026-07-10)

**Decision: `LANGUAGE_REGISTRY` is the single source of truth for `target_language`. The
picker offers exactly the registry; the backend accepts exactly the registry. If you cannot
pick it, you cannot submit it. Adding a language is one registry row.**

Write path: **normalize, then validate against the registry.**

```
"VI"          -> normalize -> "vi"          -> in registry -> accept
"zh_CN"       -> normalize -> "zh-CN"       -> in registry -> accept
"Vietnamese"  -> normalize -> "vietnamese"  -> not in registry -> 400 invalid_target_language
"pl"          -> normalize -> "pl"          -> not in registry -> 400 (add a registry row to enable)
```

Normalization (case-fold, `_`→`-`, region upper-cased) runs first so a lenient client is
corrected rather than rejected; the registry check then closes the set.

An earlier draft of this spec argued a closed enum would be a regression because "an LLM can
translate into `th` and rejecting it would break users". **That objection is void** — the
registry was read, and `th` is in it
([languages.ts:58](../../../frontend/src/lib/languages.ts#L58)). All **18** entries carry
`translationTarget: true` *and* `uiLocale: true`, so today
`TRANSLATION_TARGETS === LANGUAGE_REGISTRY === keys(LANGUAGE_NAMES)`. Switching every picker
to `TRANSLATION_TARGETS` removes **zero** options from **any** picker. There is no
regression to trade against, and the closed set is strictly safer.

Two facts constrain the build:

- **There is no backend language registry.** `languages.ts:9-10` claims *"Backend mirrors
  this in Python; keep the two in parity (see loreweave language registry + its parity
  test)."* No Python registry and no parity test exist (`find -name languages.py` → nothing).
  The comment asserts a contract that was never built. Per the "missing infrastructure is
  unbuilt work, not blocked" rule, Phase C builds exactly what the comment already promises:
  a Python mirror + the parity test.
- **The MCP tool arg becomes a real enum**, generated from the same registry
  ([`mcp/server.py:220`](../../../services/translation-service/app/mcp/server.py#L220)),
  satisfying `closed-set arg ⇒ enum` in [mcp-tool-io](../../standards/mcp-tool-io.md). This
  is the writer that admitted `Vietnamese` in the first place.

Consequence to accept knowingly: until `D-TRANSL-LANG-BACKFILL` runs, `Dracula`'s legacy
`Vietnamese` column keeps rendering (coverage still returns it) and cannot be re-translated,
because the picker no longer offers that value. That is the correct behaviour — the column
is a record of data that exists — and `getLanguageName` already echoes unknown codes rather
than crashing. **The frontend must keep tolerating unknown codes in `known_languages`**;
D13 constrains what can be *written*, never what can be *read*.

### `TRANSLATION_TARGETS` and the three language inputs

`TRANSLATION_TARGETS` is exported at
[languages.ts:73](../../../frontend/src/lib/languages.ts#L73) and imported by **nobody** —
the `translationTarget` flag governs nothing today. D13 makes it load-bearing: it becomes
the one list every target picker reads, and the one list the Python mirror is generated from.

Three different language-input shapes currently coexist for one concept: the shared
`LanguagePicker` component, `TranslateModal`'s hand-rolled `<select>`
([:320-329](../../../frontend/src/pages/book-tabs/TranslateModal.tsx#L320-L329)), and
`BatchTranslateDialog`'s free-text `<input>` + regex (S7). Consolidating all three onto
`LanguagePicker` fed by `TRANSLATION_TARGETS` is the frontend half of D13 — and it fixes S7
for free, since a picker cannot emit an invalid code.

---

## Secondary findings (full sweep of every translate surface)

Audited: `SegmentDrilldownModal`, `TranslationViewer`, `SplitCompareView`,
`BlockAlignedReview`, `TranslationReviewView`, `ConfirmNameDialog`, `translation/hooks/*`,
`TranslationReviewPanel`, `translationEffects`, `BatchTranslateDialog` + `useBatchTranslate`,
`glossary-translate/*`, `EpisodeTranslationPanel`, `AttrTranslationRow`,
`TranslationReviewCard`, `settings/TranslationTab`, `profile/TranslationsTab`.

**No further click-to-nowhere handlers exist** — every button reaches a real effect, and
every LLM-job submit path has both a language and a model picker. What the sweep found is
one dominant class: **errors swallowed into states that look like "nothing happened"** —
the same root cause as T4/T5/T6.

| ID | Sev | Where | Finding |
|---|---|---|---|
| **S1** | HIGH | `useGlossaryTranslatePolling.ts:33-35` + `StepProgress.tsx:18` | `StepProgress` destructures only `{status, isTerminal}`; the hook's `error` **and** `stopPolling` are never consumed. A failing first poll ⇒ `status` stays `null` ⇒ **infinite spinner**, interval never cleared, error invisible. |
| **S2** | MED | `useSegmentDrilldown.ts:26-33,43` | `useMutation` has `onSuccess` but no `onError`; `retranslateError` is exposed and never rendered ⇒ re-translate failures are silent. |
| **S3** | MED | `settings/TranslationTab.tsx:70` | `.catch(() => {})` on the providers+models load ⇒ a fetch error renders as the benign "you have no models" empty state. |
| **S4** | MED | `ChapterTranslationsPanel.tsx:251-258` | `TranslationViewer`'s `onSaved` is never passed by its sole production caller ⇒ after a human edit creates a new version, the sidebar's version list does not refresh. |
| **S5** | MED | `TranslationReviewView.tsx:69-75,118` | All four initial fetches `.catch(() => null)` with no toast ⇒ silently falls back to `SplitCompareView`, dropping the language pair, stats and Confirm-name button. |
| **S6** | LOW | `SplitCompareView.tsx:32,76` | Failed `getDraft` ⇒ blank original pane, no fallback copy (the translation pane has one). |
| **S7** | LOW | `BatchTranslateDialog.tsx:26-29` | `if (LANG_RE.test(v)) …` with no `else` ⇒ an invalid code makes Load silently no-op. Free-text input, not a picker — folded into D-consolidation above. |
| **S8** | LOW | `useConfirmName.ts:59` | `catch { return 'error' }` discards the exception; generic message, no `console.error`. |
| **S9** | LOW | `ConfirmNameDialog.tsx:43-44` | Still a hand-rolled `fixed inset-0` Radix overlay — the one DOCK-9 leftover here (`TranslateModal` and `SegmentDrilldownModal` were correctly migrated per spec 17). |
| **S10** | LOW | `EditorPanel.tsx:351` vs `TranslationPanel.tsx:26` | Two dock ids for one panel — resolved by **D11**. |
| **S11** | INFO | `translationEffects.ts:28` | `/^translation_job_control/` does not match agent `resume`/`retry` (they dispatch via `confirm_action`), so those do not live-refresh the matrix. Scoped out by an existing comment; recorded so it is tracked. |
| **S12** | INFO | `GlossaryTranslateWizard.tsx:123-124` | "View glossary" and "Close" both wired to `handleClose` — the button navigates nowhere. `state.totalEntities` stored, never read. |

Reachability was checked for every component: **none are dead**. `BatchTranslateDialog` and
`AttrTranslationRow` correctly have no model picker (human-authored drafts, no LLM call).

One near-dead branch worth recording: `ChapterTranslationsPanel`'s "no translations yet →
Translate now" CTA
([:226-239](../../../frontend/src/features/translation/components/ChapterTranslationsPanel.tsx#L226-L239))
is unreachable on the common paths. `listChapterVersions` builds language groups from rows
([versions.py:97-124](../../../services/translation-service/app/routers/versions.py#L97-L124)),
so a group always has ≥1 version, and `selectedLang === null` renders `OriginalViewer`
instead. It is reachable **only** via a deep-link that seeds `initialLang` with a language
that has no versions. T7's fix should make it a real, reachable affordance.

---

## Proposed phasing

**Phase A — the reported bugs.** T1 (+D1: unscoped `Translate…`), T8 (+D6), T2 (+D3/D4/D5),
T4 (+D9), T5 (+D7/D8), T10, and the readable `EDIT`-grant 403 toast (D10, first half).
`TranslationTab.tsx` + `TranslateModal.tsx`, frontend-only, no contract change.
Independently shippable and is what the user asked for.

**Phase B — degraded mode + panel parity.** T6, T7, D11, S1, S2, S3, S4, S5. The shared
theme: every translate surface gets a typed error state with a retry (D9), and no
`.catch(() => null)` survives without a rendered consequence.

**Phase C — contract + hygiene.** T3/D13 write-side (normalize → registry-enum validation,
the Python registry mirror + its parity test, MCP `target_language` arg enum), the frontend
half of D13 (consolidate all three language inputs onto `LanguagePicker` fed by
`TRANSLATION_TARGETS` — fixes S7), T9/D10 second half (`my_grant_level` on the book read),
S6, S8, S9, S12.

Phase C is the first cross-service phase (translation-service + book-service + frontend), so
it carries the live-smoke gate; Phases A and B do not.

**Deferred (gate #2 — large/structural, earns its row):**
`D-TRANSL-LANG-BACKFILL` — merge legacy free-text `target_language` values into canonical
codes across `chapter_translations`, `active_chapter_translation_versions` and
`translation_chapter_memos`. Blocked on a which-version-wins rule and a `version_num`
renumbering strategy (see D12). Target: after Phase C lands the write-side validation, so
the set stops growing. Track in `docs/sessions/SESSION_HANDOFF.md`.

## Verify gate

- Unit tests that assert the **effect**, not the presence of a handler (per
  `checklist-is-self-report-enforce-by-tests`):
  - T1 ⇒ render with `visibleLangs.length > 0`, assert a translate button is in the document.
  - T8 ⇒ tick two chapters, open the modal, assert `preselectedChapterIds` reached it and
    the footer reads `Translate 2 selected` **enabled**; and that a fully-translated book
    still yields an enabled force-retranslate for the selection.
  - T2/D3 ⇒ a coverage fixture with fewer rows than chapters renders one row per chapter;
    D4 ⇒ 250 chapters paginate and selection survives a page change; D5 ⇒ an orphan coverage
    row produces the footnote.
  - T4/T5/T6/D9 ⇒ mock a rejecting **and** a hanging API; assert a localized message + a
    Retry control, and that a 403 renders no Retry.
  - D7 ⇒ pick a language before `getBookSettings` resolves; assert the choice survives.
- `dockablePanelHygiene.test.ts` stays green (S9 removes the last `fixed inset-0` here).
- Phase C / D13 ⇒ the FE↔Python language-registry **parity test** the source comment already
  promises; a BE test asserting `"Vietnamese"` → 400 and `"VI"` → normalized `"vi"` → 201;
  and a **read-side** test proving the matrix still renders a legacy unknown code
  (`Vietnamese`) without crashing — D13 constrains writes, never reads.
- **Live browser smoke, both states** — healthy backend *and*
  `docker stop infra-translation-service-1`. A mock-only pass cannot see T4/T5/T6; they were
  found only by stopping a real service. This is the cross-service live-smoke evidence bar.

## Decisions taken (PO, 2026-07-10)

| # | Question | Decision |
|---|---|---|
| 1 | `target_language` validation | **The language picker / `LANGUAGE_REGISTRY` is the SSOT.** Normalize, then validate against the registry as a closed set. Adding a language = one registry row. → **D13** |
| 2 | Header CTA scope | **`Translate…`, unscoped** — the modal owns scope, because scope depends on the language the user has not chosen yet. → **D1** |
| 3 | `VIEW`-grant gating | **Phase C, with a readable 403 toast in Phase A.** Keeps Phase A frontend-only; no silent 403 ships in the meantime. → **D10** |

No open questions remain. The spec is PLAN-ready.

## Out of scope

- Rebuilding the coverage endpoint to left-join chapters server-side — T2 is fixed FE-side
  from data the component already holds; changing the BE contract would ripple into the MCP
  tools.
- The editor's Translate workmode unmounting the manuscript editor
  ([ChapterEditorPage.tsx:1189](../../../frontend/src/pages/ChapterEditorPage.tsx#L1189)) — a
  real tension with `editor-workmode-and-compose-must-keep-editor-mounted`, but that is the
  legacy route, not the studio dock, and it is a separate spec.
- Deeper `glossary-translate` work beyond S1/S7/S12 (the wizard is otherwise correctly wired).
