# Spec — Full i18n Coverage (UI-6)

## Document Metadata
- Document ID: LW-SPEC-I18N-FULL
- Version: 0.1.0 (DRAFT — awaiting wave-order sign-off)
- Status: Draft
- Owner: Full-Stack Lead
- Created: 2026-05-30
- Branch: `mvp-release-debt`
- Size: **XL** (multi-wave, multi-session)
- Companion: [`docs/03_planning/MVP_RELEASE_DEBT.md`](../03_planning/MVP_RELEASE_DEBT.md) (UI-6), [`docs/plans/2026-05-30-mvp-release-improvement-plan.md`](../plans/2026-05-30-mvp-release-improvement-plan.md) (T6)
- PO decision (2026-05-30): **Full i18n across all 4 locales** (en, vi, ja, zh-TW) — not "lock English V1".

## 1. Problem

Selecting any non-English locale yields a **mixed-language UI**: the nav (translated `common`) renders in the chosen language while large parts of the app stay English. Two root causes:

1. **Namespace coverage gap** — `books.json` exists only for `en`; vi/ja/zh-TW fall back to English. Minor drift elsewhere (`common` ×2 keys, `profile` ×1 key).
2. **Hard-coded English** — many user-facing strings are never wrapped in `t()`, so NO locale translates them.

`fallbackLng: 'en'` masks (1) and (2) as "English text", producing the mix.

## 2. Findings (inventory 2026-05-30)

### 2.1 Namespace key-drift (existing files)
| namespace | en | vi | ja | zh-TW | gap |
|---|---|---|---|---|---|
| books | 21 | — | — | — | **file missing ×3** |
| common | 62 | 60 | 60 | 60 | 2 keys ×3 |
| profile | 41 | 40 | 40 | 40 | 1 key ×3 |
| auth, extraction, glossaryEditor, knowledge (550!), leaderboard, notifications, wiki | — | — | — | — | **OK** |

→ existing-file drift is tiny (~66 translations). `knowledge` is fully internationalized — use it as the reference pattern.

### 2.2 Hard-coded strings (heuristic scan, ~855 raw hits / 113 files; ~500–700 real after noise)
| Surface | approx | files mostly w/o `t()` | priority |
|---|---|---|---|
| "other" (entity-editor, usage/RequestLogTable, misc) | ~178 | 25/29 | mixed |
| book-detail-tabs (`pages/book-tabs/*`) | ~168 | 8/10 | **high** (core) |
| settings (`features/settings/*`) | ~155 | 9/10 | high |
| editor (`ChapterEditorPage`, `components/editor/*`) | ~123 | 13/13 | **high** (core) |
| chat (`features/chat/*`) | ~113 | 20/23 | high |
| reader (`ReaderPage`, `components/reader/*`) | ~42 | 12/12 | **high** (core) |
| glossary (`features/glossary/*`) | ~38 | 3/3 | med |
| public-catalog (`Public*`) | ~15 | 1/1 | med |
| translation (`features/translation/*`) | ~13 | 3/3 | med |
| knowledge | ~5 | — | low (already done) |
| layout-shared, auth, books-workspace | ~5 | — | low (mostly done) |

Worst single files: `ReadingTab.tsx` (42), `KindEditor.tsx` (34), `ChapterEditorPage.tsx` (33), `AttrEditorModal.tsx` (32), `ProvidersTab.tsx` (30).

## 3. Approach

Per surface: **extract** hard-coded user text → add keys to `en/<namespace>.json` → **translate** to vi/ja/zh-TW → **wire** `t()` in the component. Follow the `knowledge` namespace as the reference for structure (nested keys, interpolation `{{var}}`, plural `_other`).

- **Namespace mapping:** reuse existing namespaces where they fit (`books` for workspace+book-detail; new namespaces for `editor`, `reader`, `chat`, `settings`, `glossary` if not already present — check before creating). Register every new namespace in `src/i18n/index.ts` for ALL 4 locales (the `books` omission is the bug to never repeat).
- **Translation:** Claude authors vi/ja/zh-TW. **vi is PO-verifiable** (user is a native speaker) — surface vi for review. ja/zh-TW best-effort, flagged for later native review.
- **No behavior change** — pure string extraction; the rendered English must be identical before/after for the `en` locale (regression guard below).

## 4. Wave plan (ordered; each wave = 1+ commits, PO checkpoint between)

| Wave | Scope | Size | Why this order |
|---|---|---|---|
| **W0** | Infra + namespace gaps: create `books.json` ×3, fix `common`/`profile` drift, register in index.ts, add a **key-parity check script** | S | Closes the exact gap the user saw; establishes parity tooling first |
| **W1** | Workspace/Books list + layout/nav/sidebar/breadcrumb | S | Core entry surface; "My Books"/"Trash" the user reported |
| **W2** | Book-detail tabs (Chapters/Glossary/Sharing/Settings/Translate/Entity/Kind/Attr) | L | Highest-traffic authoring surface |
| **W3** | Chapter editor + `components/editor/*` | L | Core daily writer flow |
| **W4** | Reader + `components/reader/*` | M | Core reader flow |
| **W5** | Chat | L | |
| **W6** | Settings (account/providers/reading/translation/model modals) | L | |
| **W7** | Glossary + entity-editor + usage ("other" bulk) | L | |
| **W8** | Translation viewer + public-catalog + auth/leaderboard remnants + knowledge ×5 strays | M | Cleanup tail |
| **W9** | Regression guard (parity + no-hardcoded-string check in CI/lint) + per-locale live verification sweep | S | Lock it so it can't rot again |

## 5. Verification (per wave)
- `tsc --noEmit` clean.
- Key-parity script: every namespace has identical key sets across all 4 locales (0 missing).
- For the `en` locale, the surface renders byte-identical text to before (no accidental wording change).
- Live smoke: switch to vi (+ spot ja/zh-TW), open the wave's surface, confirm no English leakage.
- Unit tests where a component already has them; add for non-trivial extraction logic only.

## 6. Acceptance (epic complete)
- Switching to any of en/vi/ja/zh-TW shows that locale consistently on all core flows (workspace, book-detail, editor, reader, chat, settings, glossary, profile, notifications) — **no mixed-language screens**.
- Key-parity check passes (0 drift) and is wired as a guard.
- vi reviewed by PO; ja/zh-TW flagged for later native review (tracked, not blocking).

## 7. Risks / notes
- Scope is large; waves are independently shippable so the app is never left half-migrated for the chosen test locale within a committed surface.
- Pluralization & interpolation must be preserved (don't concatenate translated fragments).
- RTL not in scope (no RTL locale).
