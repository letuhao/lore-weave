# POC findings — driving the journey with real tools + Gemma-4 26B QAT (Vietnamese)

> Live run 2026-06-30. Premise: ugly female MC, hated incl. parents, bad potential, near-death →
> succubus grimoire → self-perfection; dark xianxia, drama + twists; cultivation/combat focus.
> Model: Gemma-4 26B QAT (200K), local lm_studio, BYOK. Harness: [`poc_harness.py`](poc_harness.py);
> raw I/O in [`io/`](io/). Book `019f16d0-10a8…`, Work/project `019f16d0-11db-739b-9b14-f29b0f20a791`.

## Headline
**The engine CAN turn a one-paragraph idea into a structured, coherent, on-theme long-story outline
in Vietnamese — automatically.** The capability the PO felt was missing ("I feel empty, don't know how
to start") **exists and works.** The blocker is purely that the GUI never guides you to it and makes
you assemble prerequisites by hand. This validates the whole journey thesis (story 06).

## Phase-by-phase scorecard

### Setup (Book + chapters + Work) — ✅ APIs work / 🔴 no guided path
- `POST /v1/books` → 201; `POST /v1/books/{id}/chapters` ×12 → 201; `POST /v1/composition/books/{id}/work`
  → 201 (project_id minted). All clean.
- 🔴 **You must MANUALLY create a Book + N empty chapters + a Work before anything.** The Planner
  cannot mint chapters (§11.4 gotcha — **confirmed live**: decompose maps beats onto the 12 existing
  chapters). A non-writer in the GUI has no guided "start a new book → seed chapters → open Work" flow.

### Structure (decompose premise → outline) — ✅ STRONG
- `GET /v1/composition/templates` → chose **"Web Novel Arc" (6 beats)**.
- `POST …/outline/decompose` → 202 + job; polled ~13× (~26s) → completed.
- `…/decompose/commit` → 201. `GET …/outline` → **12 chapters decomposed, 41 scenes committed.**
- **Quality (Gemma, Vietnamese):** coherent + on-theme. E.g. Ch.1 "Sự ghẻ lạnh của gia tộc" (`hook`);
  Ch.3 succubus grimoire — "Tiếng Gọi Từ Vực Thẳm" / "Giao Ước Hắc Ám" (`establishment`); Ch.4–6 dark
  cultivation, bodily transformation, jealousy, public humiliation, humanity-vs-demon tension
  (`rising_conflict`). Beat roles map correctly. Captures ugly MC, family rejection, near-death,
  grimoire, dark drama.
- 🟡 **GUI gap:** this lives in the Planner sub-tab (#4 of 24), needs the user to already know to pick
  a template + write a premise + pick a model — none surfaced as a guided "next step". The power is
  there; the guidance is not.

### Draft (generate scene prose) — ✅ works, GOOD prose / 🔴 wrong language
- `POST …/generate` (mode=auto, draft_scene) → 202 + job; polled ~5× (~15s) → completed, k=2 candidates.
- **Quality:** strong, atmospheric prose nailing the theme — MC ignored at a cold dinner, "treated like
  an unexpected stain", "a ghost haunting their dwindling grandeur", the aching void of family inches
  away. (See `io/07_gen_*_poll4.json`.)
- 🔴 **LANGUAGE BUG (blocks the PO's goal):** output came out in **ENGLISH** despite a Vietnamese
  premise + Vietnamese outline + `book.original_language='vi'`. The `generate` body has **no language
  field** and the engine did not inherit the book/scene language → Gemma defaulted to English.
  → **Diagnosis CONFIRMED:** a Vietnamese `guide` → fluent, high-quality Vietnamese prose (even richer:
  named MC **Lâm Uyển**, parents **Lâm Chính**/**bà Lý**, brother's **Trúc Cơ Đan**, MC as **phế vật**
  with no **linh căn**). So **workaround = pass language in the guide; proper fix = the compose engine
  must inherit `book.original_language` (or a Work language setting) and inject it into the prompt** so
  the user never has to repeat "write in Vietnamese". Tracked fix candidate for the journey build.

### Write + persist (scene prose → chapter draft) — ✅ works
- Chapter 1 smoke: 3 scenes generated (Vietnamese, guided) → combined **7,468 chars** → `PATCH
  /v1/books/{id}/chapters/{ch}/draft` → 200. The draft now holds real Vietnamese prose. Persist + the
  draft OCC path both work.

### Glossary + KG — 🔴 blocked by genre/profile setup (real finding)
- `GET /v1/glossary/books/{id}/extraction-profile` → **`{kinds: [], saved_profile: null}`**. Extraction
  is **genre-driven**: `system_attributes.genre_id` + `system_kind_genres`/`book_kind_genres` resolve
  which kinds+attributes apply. A **fresh book has no genre ⇒ no kinds ⇒ nothing to extract**, so
  `extract-glossary` would no-op. A non-writer hits a hard setup wall here with no guidance.
- **Fix path:** the journey must set the book's **genre** so the extraction profile resolves — the FE
  `ExtractionWizard` StepProfile is where this lives today, but it's a separate manual flow, not part of
  the guided journey.
- **RESOLVED in POC (per-book, reusable):** the **xianxia** System genre is already seeded (7 genres,
  14 kinds). Adopting it onto the book — `POST /v1/glossary/books/{id}/adopt {genres:["xianxia"],
  kinds:[12]}` — took the extraction profile from **0 → 12 kinds**. The adoption **persists per-book in
  the DB** (reusable next session) and is **scripted** as `poc_harness.py ontology` (in the repo). No
  global seed migration needed — the ontology layer is genuinely per-book. **This is the missing
  "set genre / adopt ontology" journey step** (Story Bible / setup), confirmed live.
- **Then extraction FAILED — 2 new findings:** with the ontology resolved, `extract-glossary` on ch1
  failed fast (`'NoneType' object has no attribute 'strip'`, 0 tokens). Root cause:
  **extraction reads CANONICAL (published) chapter content, NOT drafts** (`extraction.py:342` "drafts
  skipped"). The POC wrote prose to chapter **drafts** (compose flow) but never published → empty
  canonical content. ⇒
  - 🔴 **Extraction ⟂ drafts:** a user who drafts via compose but hasn't published has nothing to
    extract; the journey must **publish** (or extraction must opt-in to drafts) before glossary/KG.
  - 🔴 **Empty-content crash:** extraction `.strip()`s `None` instead of skipping an empty chapter
    (small None-handling bug).
- **RESOLVED — root cause was the FORMAT (PO's hypothesis confirmed).** Re-persisting ch1 as proper
  **Tiptap JSON blocks** (`body_format='json'`, 53 blocks) → `extract-glossary` **SUCCEEDED: 20
  entities**, correctly typed, exactly the canonical cast: Characters (Lâm Uyển, Lâm Chấn Nhạc, Tô Yến,
  Lâm Tử Hàn, Cửu U Ma Cơ), Locations (Lâm gia, Thanh Vân Tông, Hang Động Tử Thần), Items (Cuốn cổ thư,
  Lệnh bài gia tộc), Events (Sự Ruồng Bỏ Của Gia Tộc, Sự phản bội của Lâm gia, …). So extraction reads
  the draft fine when it's valid blocks; the plain-string body was the crash. ⇒ **the universal
  formatter (#5) is the real fix.** Remaining: KG graph build (`kg_build_graph`) from these entities.

## Confirmed missing pieces (the POC's payload for the overhaul)
1. ✅ **Draft language default — FIXED** (branch `feat/editor-compose-overhaul`). Root cause: a new
   Work never inherited the book's language, so `BookProfile.source_language` stayed `'auto'`. Fix:
   `create_work_for_book` seeds `settings.source_language` from `book.original_language`
   (`services/composition-service/app/routers/works.py`). **Verified:** ch1 re-drafted with **NO guide**
   → fluent high-quality Vietnamese on its own (Work settings = `{"source_language":"vi"}`).
   _(Also surfaced: the MC is re-named every run — "Linh" vs "Lâm Uyển" → canonical-name fix next.)_
2. 🔴 **Genre/extraction setup** — glossary/KG can't run until the book has a genre; the journey must
   set it. Today it's a separate wizard, undiscoverable.
3. 🔴 **Cold-start orchestration** — every prerequisite (book, chapters, Work, template, premise,
   model, genre, language) is manual + scattered; the engine is capable but the GUI never sequences it.
   → exactly what the guided journey (story 06) + command-center fix.
4. 🔴 **Character naming — inconsistent + out-of-genre (NEW FEATURE).** The drafter re-invents the MC's
   name every run (Linh / Lâm Uyển) and gives supporting characters mundane modern names ("bà Lý",
   "ông Lâm") that break tiên-hiệp immersion. No canonical cast or naming convention feeds generation.
   **Feature needed:** a journey step (Story Bible / cast) that establishes a **canonical cast with
   genre-appropriate Hán-Việt names + a naming-convention steer**, persisted as canon so every scene is
   consistent + in-genre. Tracked in [`../stories/06-compose-journey.md`](../stories/06-compose-journey.md).
   **POC fix applied + VERIFIED:** cast + naming convention baked into the premise + a draft guide; 4
   motifs created (`POST /v1/composition/motifs`). Re-drafted ch1 → every supporting character now
   appears with the canonical in-genre name (**Lâm Chấn Nhạc / Tô Yến / Lâm Tử Hàn / Cửu U Ma Cơ /
   Thanh Vân Tông**) + tiên-hiệp honorifics; the mundane "ông Lâm / bà Lý" forms are gone. MC
   consistently **Lâm Uyển**.

## POC iteration 2 — quality stack (all verified on `feat/editor-compose-overhaul`)
1. **Language** — Work inherits `book.original_language` → auto-Vietnamese drafts (no guide).
2. **Canonical cast + naming convention** — consistent, in-genre Hán-Việt names across scenes.
3. **Motifs** — 4 dark-cultivation motifs seeded (xấu→mỹ, ma công phản phệ, phục thù, tiềm long tại uyên).
Ch1 prose: strong, atmospheric, on-theme (clan expulsion → death-cave hunters → pact with Cửu U Ma Cơ).
**The pipeline now produces a publishable-quality Vietnamese xianxia chapter from a premise.**

5. 🔴 **Universal content formatter (BUG — PO-requested fix).** Chapter content must be canonical
   **Tiptap JSON blocks** (`body_format='json'`) for read mode + the `chapter_blocks` trigger +
   extraction. book-service already has `plainTextToTiptapJSON` (`internal/api/tiptap.go`) applied on
   import / MCP-seed / parse paths — **but it's plain-text only** (splits on blank lines → paragraphs);
   it does NOT parse **markdown** structure. Compose emits markdown (`### scene`, lists), so headings /
   scene breaks become literal text, and a plain/markdown draft-write isn't normalized to structured
   blocks. ⇒ read mode can't render it; likely the extraction crash too.
   **Fix (bug):** make the formatter **universal** — detect + parse plain / markdown (→ headings,
   paragraphs, lists, scene splits) into canonical Tiptap blocks, applied at ALL ingestion points
   (draft-write `body_format` plain|markdown, chapter import). *We already have chapter import + the
   plain formatter — only need to make the normalizer universal* (PO). POC workaround proves the target:
   harness now builds Tiptap JSON client-side → **53 blocks** persisted ✓.

## POC Part 2 — glossary/KG exploitation for a later chapter (empirical, 2026-06-30)
Called grounding for a **chapter-2** scene (`GET .../scenes/{id}/grounding`) on the book whose chapter 1
was drafted + extracted:
- **✅ Glossary IS exploited** — the `present` lens pulled **all 20 chapter-1 entities by name**
  (Lâm Uyển, Lâm Chấn Nhạc, Tô Yến, Lâm Tử Hàn, Cửu U Ma Cơ, Cuốn cổ thư, Thanh Vân Tông, the events…).
  Cross-chapter entity awareness via glossary works **today**, in drafting grounding.
- **🔴 KG graph NOT built** — `grounding_available: false` + warning *"no knowledge-graph data for this
  scene/project (C3a)"*. So `present` gives **names only, not STATE** (location, possessions,
  relationships, timeline). Extraction populated the **glossary** but the **Neo4j KG graph** wasn't
  built (the flywheel's `kg_build` step didn't run). ⇒ confirms the PO point ("KG captures only some
  content") AND that the *valuable* KG layer (state/timeline) needs an explicit build to exploit.
- `beat` lens = the planned scene synopses (outline); `recent` lens = prior prose. Both work.
- **Next:** build the KG graph (`kg_build_graph`) from chapter 1 → re-check grounding →
  expect `grounding_available: true` + entity state/timeline. Only then is the full Part-2 latent state
  available. (Reusable harness phase: `poc_harness.py grounding`.)

## Implications for the overhaul (so far)
1. The **guided journey** (story 06) is the right and highest-leverage fix: the engine already does
   Idea→Structure; we just need the command-center + "next step" rail to walk a non-writer into it.
2. **Auto-create the first chapter(s)** on a fresh book (S/§11.4) is a confirmed must — the journey
   can't start without existing chapters.
3. The decompose→commit→outline pipeline is solid enough to anchor the "Structure" phase UI.
