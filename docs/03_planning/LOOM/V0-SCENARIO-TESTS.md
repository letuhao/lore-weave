# LOOM V0 — Scenario Test Plan (manual)

> Acceptance scenarios for **Composition V0** (M0–M9) + its **Canon Model Cycle 0** foundation + the **Chapter Revision Compare** feature. Two lenses: **User** (real end-to-end journeys — does it deliver value?) and **Tester/QA** (what breaks — edge cases, negatives, boundaries, isolation, regressions).
>
> These are written to be run by a human against a running stack, and to be the source script for the deferred Playwright automation (**D-COMP-M8-PLAYWRIGHT**). Each scenario: **Pre** (preconditions) · **Steps** · **Expect**.

---

## 0. Environment & test data

**Stack up:** `docker compose up -d` (book/knowledge/worker-ai/composition/api-gateway-bff/provider-registry healthy); **LM Studio** running with at least 2 chat models (one for the drafter, a *different* one for the critic — anti-self-reinforcement); frontend via `npm run dev` (Vite :5174 → gateway :3123).

**Account:** `claude-test@loreweave.dev` / `Claude@Test2026`. A second account is needed for isolation tests (B9.1) — register `claude-test2@loreweave.dev` or use any other owned login.

**Seed data:**
- A book owned by the test account with ≥3 chapters (the **封神演義 demo** works), at least one chapter with **≥2 saved revisions** (for Compare), and at least one with **0 composition scenes** (Classic-only).
- A **registered chat model** (BYOK, via provider-registry) so the co-writer can generate. Without it, Generate cannot run — generation scenarios become **blocked**, not **failed**.
- The critic model is configured in the Work's `settings` (`critic_model_source` / `critic_model_ref`) and **must differ** from the drafter.

**Key invariants under test (traceability):**
| Code | Invariant | Primary scenarios |
|---|---|---|
| canon=published | Extraction fires on publish, never on draft-save | U7, U8, B1.5, B7.6 |
| OI-1 chapter-gate | Publish enabled only when ALL chapter scenes `done` | U7, B7.* |
| OI-2 / PS2 | `expected_draft_version` concurrency → 409 | B1.4 |
| SC4 | Ghost prose never autosaved until Accept | U3, B4.5 |
| A2 spoiler | No future-canon leak in grounding | U5, B6.2 |
| A1 / SEC2 | User- + project-scoped isolation | B9.1, B6.3 |
| §4 critic | Critic model distinct from drafter; advisory (never blocks) | U4, B5.* |
| telemetry | `composition.scene_committed` on status→done | B3.3 |

---

## Part A — USER journeys (góc nhìn người dùng)

> A novelist using LoreWeave to co-write a chapter grounded in their book's canon, then publish it so it feeds the knowledge that grounds the next chapter.

### U1 — First-time co-writer setup
**Pre:** logged in; open a book's chapter in the editor (`/books/:bookId/chapters/:chapterId/edit`); the book has no co-writer Work yet.
**Steps:** Open the right panel → **Compose** tab (pen icon). The panel shows "No co-writer Work for this book yet." Click **Set up co-writer**.
**Expect:** a Work is created (POST /work); the panel switches to the scene/model selectors + Compose/Grounding/Canon sub-tabs. Re-opening the tab later goes straight to the panel (no re-setup). No duplicate Work on a second click.

### U2 — Plan a chapter with scenes
**Pre:** Work exists; a chapter open.
**Steps:** In the Compose panel, click **+ Scene** twice to add two scenes. They appear in the scene dropdown.
**Expect:** two scenes listed; each starts at status `empty` (no ✓). Selecting a scene targets it for generation/grounding.

### U3 — Co-write a scene (ghost → accept)  *(needs a drafter model)*
**Pre:** a scene + a drafter model selected.
**Steps:** (1) Type optional guidance. (2) Click **Generate** — prose streams into the **Ghost draft** preview. (3) Read it. (4) Click **Accept**.
**Expect:** while streaming, there is **no Accept button** and the ghost is **not** in the editor doc (SC4). On Accept, the prose is inserted at the cursor in the chapter editor (which then autosaves the draft), the ghost clears, and an advisory critique runs. **Discard** / **Regenerate** instead of Accept must leave the editor doc untouched.

### U4 — Read the advisory critic
**Pre:** just accepted a draft (U3); critic model configured + distinct from drafter.
**Steps:** Look at the Critic (advisory) panel under the compose bar.
**Expect:** four scores (coherence / voice / pacing / canon) + any canon-rule violations. It is **advisory** — nothing is blocked. If the critic is unconfigured or equals the drafter, it is **skipped with a warning**, not an error.

### U5 — Check grounding before writing
**Pre:** a scene selected.
**Steps:** Open the **Grounding** sub-tab.
**Expect:** context blocks (present entities, recent prose, beats, canon) + a token count + a **"Grounded / Grounding thin"** signal. If the book has no knowledge graph yet, the signal is honest ("thin/unavailable") rather than pretending. **No content from later/unpublished canon appears** (spoiler safety).

### U6 — Add a canon rule
**Pre:** Work exists.
**Steps:** **Canon** sub-tab → type a rule ("Magic always has a blood cost"), pick a scope, **Add rule**. Generate again.
**Expect:** the rule lists; it is folded into grounding; the critic flags a draft that violates it. **Archive** removes it from the active set.

### U7 — Finish & publish (the chapter-gate → canon)
**Pre:** a chapter whose scenes you've drafted.
**Steps:** (1) Try to **Publish** (editor toolbar) while a scene is still not `done` → it's **disabled** with a tooltip ("N of M scenes not yet done"). (2) For each scene: select it, click **Mark done** (the option shows ✓). (3) When all scenes are done, **Publish** enables. (4) Click Publish.
**Expect:** publish is gated until every scene is done; once published, the badge flips to **Published**, the pinned revision advances, and extraction runs on the published revision (canon = published). Accept earlier wrote only a **draft** — it did **not** canonize.

### U8 — The flywheel
**Pre:** U7 done for chapter 1.
**Steps:** Move to chapter 2, open Grounding.
**Expect:** entities/relations extracted from the now-published chapter 1 appear as grounding for chapter 2 (the "Grounded" signal strengthens). Nothing from **unpublished** chapter 3 leaks.

### U9 — Compare two revisions
**Pre:** a chapter with ≥2 saved revisions.
**Steps:** Right panel → **History** → **Compare** → the standalone compare page opens with the two newest revisions diffed. Toggle **Side by side** ↔ **Inline**. Re-pick either side. If many revisions, **Load more**.
**Expect:** side-by-side shows left/right with changed **words** highlighted; inline shows a git-style +/− view; identical revisions show "no differences"; **Back to editor** returns. Load-more reveals older revisions in the pickers.

### U10 — Unpublish (retract canon)
**Steps:** On a published chapter, **Unpublish** → confirm the destructive dialog.
**Expect:** badge → Draft; the chapter's extracted knowledge + passages are retracted; the chapter no longer grounds others.

### U11 — Multi-device continuity
**Steps:** Set up a Work + scenes on device A; log in on device B (or another browser), open the same book/chapter.
**Expect:** the Work, scenes, scene statuses, and canon rules are all present on B (server is the source of truth — nothing user-meaningful lives only in localStorage).

---

## Part B — TESTER / QA scenarios (góc nhìn tester)

### B1 — Canon Model / publish lifecycle
- **B1.1 Publish an empty chapter** → expect a sensible error (no crash), publish not silently succeeding on nothing.
- **B1.2 Publish while the editor is dirty** → Publish is **disabled** ("save first"); publishing would snapshot the stale server draft. Save → enabled.
- **B1.3 Re-publish** an already-published chapter after an edit+save → the pinned `published_revision_id` **advances**; a new `chapter.published` event fires.
- **B1.4 Stale concurrency (OI-2):** open the chapter in two tabs, save in tab A, then publish in tab B with the old `draft_version` → **409 `CHAPTER_DRAFT_CONFLICT`** toast, not a silent clobber.
- **B1.5 Draft-save does NOT canonize:** edit + save (not publish) → no extraction; the knowledge graph is unchanged. Only publish extracts.
- **B1.6 Unpublished/pre-CM book:** on a book whose chapters predate the editorial lifecycle, the publish control degrades gracefully (renders nothing rather than a misleading affordance).

### B2 — Composition Work resolution
- **B2.1 Book with no knowledge project** → Set up co-writer creates a project + Work.
- **B2.2 Book with an existing knowledge project (unmarked)** → Set up **binds** to it (no duplicate empty project).
- **B2.3 Idempotent POST /work:** click Set up twice fast → exactly one Work (UniqueViolation re-resolves, not a 500).
- **B2.4 Cross-user:** user B cannot resolve/see user A's Work for the same book.

### B3 — Outline / scenes / mark-done (M9)
- **B3.1 Mark done / reopen:** select a scene → **Mark done** (✓ appears) → **Reopen** (✓ clears, status back to drafting).
- **B3.2 ✓ markers:** done scenes show a ✓ prefix in the dropdown so remaining work is visible.
- **B3.3 Telemetry once:** marking a scene done emits exactly one `composition.scene_committed` outbox row (verify in `loreweave_composition.outbox_events`); re-marking an already-done scene emits **no** new row; marking a non-scene node emits none.
- **B3.4 Archived scene** drops out of the chapter-gate count.

### B4 — Co-write engine
- **B4.1 Generate gated:** Generate is **disabled** until both a scene and a model are picked; the missing-piece hint shows ("Pick a scene" / "Pick a model").
- **B4.2 Stop mid-stream** → streaming halts; the partial ghost remains; no job left "running" forever.
- **B4.3 Rapid re-generate (supersede):** click Generate, then Generate again before the first finishes → the **newer** stream wins; the superseded one does not clobber state (the streaming flag + ghost reflect the latest only).
- **B4.4 Discard** clears the ghost without touching the editor; **Regenerate** replaces the ghost.
- **B4.5 SC4 hard rule:** at no point before Accept does the ghost appear in the saved draft (check the draft on the server / reload — the ghost is gone, nothing autosaved).
- **B4.6 Thinking/zero-output model:** a model that emits only reasoning tokens (no prose) is handled — metering never records 0 tokens for produced prose; the UI doesn't claim success on empty output.
- **B4.7 Budget pre-check:** an over-budget request is rejected before streaming (413), not mid-stream.

### B5 — Critic
- **B5.1 Distinct model enforced:** if the critic model equals the drafter (or is unset), critique is **skipped + warned**, never silently self-grades.
- **B5.2 Critic degrades, never blocks:** with the critic provider down / a malformed critique JSON, the co-write flow still completes; the panel shows "Critic unavailable", Accept still works.
- **B5.3 Dismiss a violation** → it greys/strikes out and does not re-appear on the next critique of the same job.

### B6 — Grounding & spoiler safety
- **B6.1 No graph → honest signal:** a book with no extracted knowledge shows `grounding_available=false` + a warning, not a fake-full context.
- **B6.2 Spoiler cutoff (A2):** ground a scene early in reading order; facts/canon that belong to *later* (higher reading/chronological order) scenes must **not** appear. Unplaced scenes fail **closed** (no leak).
- **B6.3 Cross-user grounding** → 404 (cannot ground another user's scene/project).
- **B6.4 book-service down** → grounding returns **502** (not a generic 500).

### B7 — Chapter-gate (M9) — load-bearing
- **B7.1 Blocked until all done:** with any scene ≠ done, Publish is disabled + tooltip count.
- **B7.2 Zero-scenes chapter (composition book):** a chapter with no composition scenes is **blocked** ("create and complete at least one scene") — the PO rule for composition-enabled books.
- **B7.3 Classic-only book preserved:** a book with **no** composition Work keeps the normal (ungated) publish — the gate must not break CM-FE.
- **B7.4 Gate refreshes:** mark the last scene done in the panel → the toolbar Publish **enables without a page reload** (the gate query invalidates).
- **B7.5 Dead-gate regression (the /review-impl catch):** confirm the gate is satisfiable **from the UI** — Mark done is a real button; you never need an API call to unblock Publish.
- **B7.6 All-done → publish → extraction** fires on the pinned revision (ties B7 to canon=published).

### B8 — Revision Compare
- **B8.1 Correct diff:** two revisions differing by one paragraph → exactly that paragraph shows delete/insert; unchanged blocks are equal.
- **B8.2 Same revision** on both sides → all-equal, a "same revision — no differences" note.
- **B8.3 Word-level highlight:** in side-by-side, only the changed *words* tint, not the whole line.
- **B8.4 CJK highlight:** compare two Chinese/Japanese revisions differing by one character (e.g. `封神演義` vs `封神演功`) → only the changed **character** highlights (not the whole line). *(Regression lock for the space-tokenizer fix.)*
- **B8.5 Large chapter, small edit:** a long chapter (hundreds of blocks) with a one-line change → a clean one-line diff, **not** a full-replace (prefix/suffix trim).
- **B8.6 Huge fully-distinct revisions** → `truncated` warning + a full-replace view (perf guard), no hang.
- **B8.7 Pagination:** a chapter with >100 revisions → the picker shows newest 100 + a **Load more (loaded/total)** that reveals older ones until all are selectable.
- **B8.8 <2 revisions:** a chapter with 0–1 revisions shows the "needs at least two revisions" message; the Compare entry only appears at ≥2.
- **B8.9 Bad/cross-book revision id** (hand-edit the URL query) → the comparison errors cleanly (404/400), no crash, no leak of another chapter's content.
- **B8.10 Ownership:** user B cannot compare user A's revisions (404).

### B9 — Cross-cutting
- **B9.1 Isolation (A1/SEC2):** as user B, you cannot see/select user A's Work, scenes, canon rules, grounding, or revisions anywhere.
- **B9.2 i18n:** switch UI to vi / ja / zh-TW → the **publish**, **compare**, and editor strings localize. *(Known gap: the Composition Power panel `composition` namespace is en-only for vi/ja/zh-TW until D-COMP-M8-I18N — those strings fall back to English; this is expected, not a bug.)*
- **B9.3 Server is source of truth:** nothing user-meaningful (Work, scenes, statuses, rules, reading position) is lost by clearing localStorage / switching device.
- **B9.4 SSE through the gateway:** generation streams token-by-token through the gateway (not buffered into one chunk at the end).
- **B9.5 No lore-enrichment coupling:** composition features work with the lore-enrichment service stopped (it is a sibling track, not a dependency).

---

## Notes for automating (→ D-COMP-M8-PLAYWRIGHT)
- Generation/critic scenarios (U3–U4, B4–B5) need a live model — gate them behind a "model available" check or stub the `/generate` SSE.
- The telemetry assertion (B3.3) and spoiler/extraction checks (B6.2, U8) need DB / knowledge-graph inspection, so they live as integration/E2E-with-backend, not pure browser clicks.
- Pure-browser-clickable now: U1, U2, U7 (gate UI), U9, B1.2, B3.1–B3.2, B4.1, B7.1–B7.5, B8.1–B8.8.
