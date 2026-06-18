# C21 PLAN — World container FE (prose-less worldbuilding) ▶ M5

Size **L** (FE feature + thin gateway passthrough). Two DPS. Builds on Step A
(`worldResponse.bible_book_id` + `bible_chapter_id`, committed `5fe9eb33`).

## Architecture decision (DESIGN, grounded)
- **Anchoring path:** lore authored against the world = a **glossary entity created in
  the bible BOOK** then **chapter-linked to the bible CHAPTER** via
  `POST /v1/glossary/books/{bibleBookId}/entities/{entityId}/chapter-links {chapter_id: bibleChapterId}`.
  This is the only FE path that writes a NOT-NULL `chapter_entity_links.chapter_id`
  (glossary `createEntity` body is `{kind_id}` only; the chapter-link endpoint is the
  real anchor). Confirmed: book-service `/internal/books/{id}/chapters` returns the
  is_bible sort_order-0 chapter (NOT filtered), so the glossary link-validation passes.
- **Resolve the handle:** create-world → `worldResponse.bible_book_id` + `bible_chapter_id`
  (Step A). Workspace shell holds both; lore-authoring uses them.
- **Graph embed:** reuse C19 `ProjectGraphView` (read-only) pointed at the world's
  knowledge project resolved by `listProjects({book_id: bibleBookId})` — null project ⇒
  the view's own empty state (graceful, no new BE).
- **Hide manuscript:** the workspace never renders a chapter/editor/manuscript surface;
  it presents "World bible" + lore authoring + read-only graph only.
- **Gateway gap:** add a thin `/v1/worlds*` passthrough → `bookUrl` (mirrors `/v1/books`),
  the only BE-side change (gateway invariant enabling work, NOT world business logic).

## DPS1 — world API + create flow + workspace shell
- `features/world/api.ts` — `worldsApi`: `createWorld`, `getWorld`, `listWorlds` over
  C20 `/v1/worlds` + `createGlossaryEntity` + `linkEntityToChapter` (glossary
  chapter-link). `types.ts` — `World` (incl `bible_book_id`/`bible_chapter_id`),
  `WorldListResponse`.
- `hooks/useWorlds.ts` — list + create (mutation, invalidate). `hooks/useWorld.ts` —
  single world resolve (holds bible handle).
- `components/WorldsBrowser.tsx` (HOME list + create), `pages/WorldsPage.tsx`,
  `pages/WorldWorkspacePage.tsx` (shell: resolves `bible_chapter_id`, no manuscript).

## DPS2 — lore authoring wiring + graph embed + messaging
- `hooks/useWorldLore.ts` — author a glossary entity in the bible book → chapter-link to
  the bible chapter (2-step mutation; anchors carry the bible `chapter_id`).
- `components/WorldLorePanel.tsx` — author entity form (kind + name) → persists against
  the bible chapter; extraction-optional advisory copy.
- `components/WorldGraphSection.tsx` — embeds `ProjectGraphView` resolved via
  `listProjects({book_id})`; read-only.
- `useWorldKinds` reuse glossaryApi.getKinds.

## Routes (App.tsx)
- `/worlds` → `WorldsPage`; `/worlds/:worldId` → `WorldWorkspacePage`.

## i18n — `world.*` in en/ja/vi/zh-TW.

## Tests (TDD, vitest, PowerShell runner)
1. world-create lands in a no-manuscript workspace (no editor/chapter surface).
2. authored lore carries the bible `chapter_id` (chapter-link called with bibleChapterId).
3. book/manuscript mechanic hidden (no manuscript testid).
4. graph read-only (ProjectGraphView embedded, no edit affordance).
5. worldsApi shape + lore 2-step ordering (entity then chapter-link).

## OUT (scope guard)
No BE model/schema/migration (beyond thin gateway passthrough); no living-world tree
(C28); no dị bản (C23-27); no intent onboarding (C22); no graph editing; no world-sharing;
no localStorage for user data.

## Gate
`scripts/raid/verify-cycle-21.sh` (model verify-cycle-6.sh) exit 0 + Playwright smoke.
