# SPEC — Co-writer Newcomer-UX (clear all dogfood findings F2–F8)

> Brainstorm: [`00_BRAINSTORM.md`](00_BRAINSTORM.md) · RUN-STATE: [`RUN-STATE.md`](RUN-STATE.md) · Source dogfood:
> [`docs/dogfood/2026-07-18-jamie-cowriter-cursor-for-writing.md`](../../dogfood/2026-07-18-jamie-cowriter-cursor-for-writing.md).
> **F1 (rail stale after agent create) already shipped** (`b255cb62a`). This spec clears F2–F8, each an
> independently buildable + QC-able slice. Seams below are grounded in code (3 scout passes, 2026-07-18).
>
> **Coordination invariant:** a concurrent session owns studio FE (onboarding doors, structure-coherence). Before
> editing any file, `git status`/`git log` for collision; commit each slice via scoped pathspec. `ChatInputBar` /
> `AssistantMessage` / `Sidebar` are shared shell — check ownership before N1/N4.

---

## Guiding principle

The core loop already works (Gemma writes into the book at $0). Every slice serves **one** outcome: *a
first-time, non-technical writer succeeds unaided* — the AI's help reaches their book, the AI doesn't hijack or
overwhelm them, and the app's front door points at writing. Fix the **root causes**, reuse existing plumbing,
add no new global env flags (per Settings-and-Config), keep tenancy (server-persisted per-user state, default-safe).

---

## Slice N5 — F3: stop the co-writer over-reaching + de-jargon the confirm  *(BUILD FIRST — BE)*

**Why first:** this is the agent-behavior root cause the FE slices showcase. Fixing it makes the whole loop calmer.

### N5a — Persona scope restraint (chat-service)
**Root cause (grounded):** on every editor/book WRITE turn, `skill_registry.resolve_skills_to_inject`
(`services/chat-service/app/services/skill_registry.py:349-350`) auto-injects the **full `glossary` skill** — whose
prompt (`glossary_skill.py:54-113`, esp. 61-63 "a book starts empty until standards are ADOPTED", 64-72/91-96 "do
not skip it — the single most common gap") actively pushes proactive ontology adoption — regardless of whether the
user mentioned glossary. Compounded by `co_write_skill.py:22-48` ("MATERIALISE it, don't stop, do BOTH in the same
movement"). Nothing tells the agent to stay within the user's explicit ask.

**Design (corrected per review HIGH-2 — `resolve_skills_to_inject` has NO user-message/intent input, only surface
flags + `permission_mode` + `enabled_skills`/`binding_skills`; the "mirror plan_forge intent-gating" idea was false):**
1. **Add a scope-restraint clause** to `CO_WRITE_SKILL_PROMPT` (`co_write_skill.py`): *"Do exactly what the writer
   asked, then STOP and OFFER next steps as a short list — do not execute unrequested setup. Never adopt glossary
   standards, create schema/kinds, or run multi-step world-setup unless the writer explicitly asks. One request =
   one focused action + an offer."*
2. **Guard-line at the top of the glossary shaping section** (`glossary_skill.py`, "## Shaping the book's ontology"):
   *"Only act on this section when the author EXPLICITLY asks to set up/build/expand their world/lore/glossary;
   otherwise do the one thing they asked and OFFER world-setup, waiting for a yes."*
   - **BUILD-TIME CORRECTION (drift, 2026-07-18):** the review's preferred "gate shaping on `enabled_skills`" was
     found FLAWED on implementation — `enabled_skills` means "user PINNED the glossary skill in the rack," which a
     newcomer never does; it is NOT a proxy for "user wants ontology work." Gating on it would REMOVE the shaping
     guidance even when a user legitimately asks "set up my world" in natural language (they don't pin), breaking the
     batching discipline that prevents propose-loops. Since the resolver has no message-text signal, the guard-line
     (which PRESERVES the guidance for when it's genuinely asked) + the co_write restraint clause are the correct
     defense-in-depth. Both are prompt-level; robustness comes from redundancy, not a structural registry split.
3. Keep the confirm **gate** (correct per cost-gated-mcp-tool discipline) — we're removing the *unprompted trigger*,
   not the safety rail.

**Files:** `services/chat-service/app/services/co_write_skill.py`, `glossary_skill.py`, `skill_registry.py`.
**Tenancy/Settings:** none (prompt text). **Contract:** none.
**Tests:** chat-service unit — `resolve_skills_to_inject` on a plain book/editor WRITE turn (glossary NOT in
`enabled_skills`) injects only the lean glossary core, NOT the shaping/adopt section; with `"glossary"` enabled it
DOES inject shaping. Assert the restraint clause is present in the assembled write-mode system prompt.
**QC / live-smoke:** on the isolated stack + Gemma — "create Chapter 1 and write the opening" → agent creates the
chapter and **stops with an offer**, NO unprompted `glossary_adopt_standards` / high-impact confirm. (This is the
exact over-reach the dogfood hit.)

### N5b — De-jargon the high-impact confirm copy
**Root cause:** header `ConfirmActionCard.tsx:345-346` ("This change is high-impact — please confirm.") + jargon
rows from glossary-service Go in **two** places: `book_tools.go:154-157` (`toolAdoptStandards`) and
`action_confirm.go:588-594` (`previewAdopt`) — `{Label:"kinds newly adopted", Note:"+ unknown (always)"}` etc.

**Design:** rewrite to human copy. Header → *"This sets up your book's world — review before applying."* Rows →
`Label:"Lore categories to add"`, human `Note` (e.g. *"Characters, Locations, Items, … (you can edit these later)"*),
drop "+ unknown (always)" / "+ universal (always)" developer tokens. **Both** Go sites must change together (they
feed the same card via the tool-mint path and the preview path). FE header via i18n key `actionConfirm.warning`.
**Build step (review LOW-8):** first `grep -rn "newly adopted\|(always)" services/glossary-service` to confirm these
are the ONLY two sites — a stray third preview row would ship un-de-jargoned.
**Files:** `glossary-service/internal/api/book_tools.go`, `action_confirm.go`; `frontend/.../ConfirmActionCard.tsx` +
`i18n/locales/*/chat.json` (key `actionConfirm.warning`, ×18 locales via the i18n tool).
**Contract-first (glossary):** these routes are covered by `TestOpenAPIRouteConformance` — copy-only change to
existing handlers, no route change, so no contract edit; run the conformance test to be safe.
**Tests:** glossary-service Go — the preview/adopt card rows contain the human labels, not "kinds/unknown (always)".
**QC:** if N5a lands, this card rarely shows unprompted — but force a genuine "set up my world" turn and eyeball the
card reads human.

---

## Slice N6 — F7: `book_chapter_create` idempotency  *(BE)*

**Root cause:** `mcp_tools_write.go:toolChapterCreate` (235-265)/`mcpCreateChapter` (269-306) has **no** dedupe;
`sort_order=0`→`MAX+1` per call, so two rapid identical creates get different slots → both pass the
`(book_id,sort_order,original_language)` unique index → duplicate-title chapters. Sibling
`book_chapter_bulk_create` is already idempotent on `original_filename` (the model to mirror).

**Design (corrected per review HIGH-3 — a bare Go SELECT-then-INSERT is racy: two concurrent calls both find
nothing, both INSERT with different `MAX(sort_order)+1` slots, both pass the `(book_id,sort_order,original_language)`
index → the very duplicate we're preventing. Must be a DB-level guard.):**
- **Migration:** add a **partial unique index** `uq_chapters_active_title ON chapters (book_id, lower(title),
  original_language) WHERE lifecycle_state='active' AND title IS NOT NULL AND title <> ''`. Empty-title "Chapter N"
  placeholders are exempt (they must stay distinct). ⚠ The `ON CONFLICT` predicate MUST match this index's WHERE
  exactly (repo lesson `postgres-partial-index-on-conflict-predicate-must-match`).
- **`mcpCreateChapter`:** `INSERT … ON CONFLICT (book_id, lower(title), original_language) WHERE <same predicate>
  DO NOTHING RETURNING id`; on no row returned (conflict), **re-SELECT the existing active chapter** with that
  (book, title, language) and return its `chapter_id` — idempotent. This closes the concurrent double-fire at the
  DB, not in app code.
- Backfill note: if existing data already has duplicate active same-title chapters in one book+language, the unique
  index creation will fail — the migration must first **de-dup or scope** (verify: newcomers rarely have dupes, but
  the migration must not red on existing books; use `CREATE UNIQUE INDEX CONCURRENTLY` guarded, or resolve dupes).
**Files:** `services/book-service/internal/api/mcp_tools_write.go`, `services/book-service/internal/migrate/migrate.go`.
**Tenancy:** scoped by `book_id` (already grant-gated). **Contract:** none (behavior of existing tool).
**Side-effect floor:** this slice carries a DB migration ⇒ min size S with a migration plan; treat with care.
**Tests (real DB):** two identical `book_chapter_create` calls (incl. a **concurrent** pair) → ONE chapter, second
returns the same `chapter_id`; empty-title creates still make distinct chapters; different-title creates unaffected;
the migration is idempotent and survives a book that already has a legit single same-title chapter.
**QC / live-smoke:** the exact dogfood repro — ask Gemma to create a chapter; confirm no duplicate row (pair with
N5a which also reduces the double-turn).

---

## Slice N1 — F2: make Ask/Plan/Write legible  *(FE)*

**⚠ PRE-BUILD VERIFY (review MED-5 — do this FIRST):** the code default is `write` (`useChatMessages.ts:66-73`),
but the dogfood reported Jamie saw **Ask** first-run ("my first request came back as a chat bubble; I only got a
chapter after I flipped Write"). Before building N1, **live-smoke a truly fresh account into the studio co-writer and
read what the chip actually says at first paint.** If it reads **Write** → the reframe below holds (legibility only).
If it reads **Ask** → a studio wrapper/`composeMode`/stale-localStorage override is presenting Ask, and N1 must ALSO
fix that (a first-run writer should default to a mode where the AI can help write). Do not build N1 on the unverified
premise.

**Reframe (grounded, pending the verify above):** if default is confirmed `write`, the newcomer is NOT locked out of
writing — the problem is the control is **opaque**: a color-only dropdown trigger (`ChatInputBar.tsx:382-402`), no
`aria-pressed`, state conveyed by hue alone; and the writer has no plain-language sense of what each mode does.
Right-sized: make the mode **legible + explained**, don't over-engineer.

**Design:**
1. Give the trigger an explicit **visible text label** ("Ask" / "Plan" / "Write") + icon (already `Pencil` for
   write) and `aria-pressed`-equivalent state so the current mode is unambiguous at a glance (it currently shows the
   label already at `:391-399` — verify; if only icon+color, add the word).
2. A **one-time inline hint** the first time the co-writer/chat is opened: *"You're in Write mode — the AI can create
   chapters and save drafts. Switch to Ask to just talk."* Dismissible; "seen" persisted **server-side** via
   `/v1/me/preferences` (a new pref key, per Settings-and-Config — NOT localStorage-only; mirror
   `hasSeenOnboarding`).
**Files:** `frontend/src/features/chat/components/ChatInputBar.tsx`; a small hint component; a pref key in the
onboarding/prefs pattern; `i18n chat.json` (×18).
**Settings-and-Config:** the "mode hint seen" flag is per-user, server-persisted, default unseen; effective state =
visible (the hint shows once). No global env flag. Mode itself stays per-conversation UI state (unchanged, still
localStorage per the existing `lw_chat_permission_mode` — acceptable as per-device UI pref).
**Tests:** ChatInputBar unit — the mode trigger exposes its current mode as text + accessible state; the hint renders
when the pref is unseen and hides after dismiss (pref write called).
**QC / live-smoke:** open the co-writer as a fresh user → hint shows once, explains modes; the mode chip legibly reads
"Write".

---

## Slice N2 — F4: per-message "Insert into chapter"  *(FE — the load-bearing newcomer fix)*

**Root cause:** the AI often replies with prose in chat (Gemma did); to use it a newcomer must Copy→paste. The
insert plumbing already exists (`firePasteToEditor`, `editorBridge.applyProposedEdit`, `useAcceptIntoEditor`) and
there's even a **buried** "Send to editor" overflow item (`AssistantMessage.tsx:459-466`) — but no first-class
per-message button.

**Design (corrected per review MED-4 — `AssistantMessage` renders in BOTH the studio co-writer AND standalone
`/chat`; `/chat` has NO `StudioHostProvider`, so `AssistantMessage` MUST NOT call `useAcceptIntoEditor`/`useStudioHost`
itself (rules-of-hooks / missing-provider throw). The handler is INJECTED by the parent):**
- `AssistantMessage` gains an optional prop **`onInsert?: (text: string) => void`** (and an `insertLabel`/enabled
  flag). The button renders in the hover row (`AssistantMessage.tsx:421-438`, beside Copy/Regenerate) **only when
  `onInsert` is provided**; hidden otherwise.
- The **studio co-writer wrapper** (`CoWriterChat`/`CompositionPanel`) supplies a host-aware `onInsert` built on
  `useAcceptIntoEditor(activeChapterId)` — which inserts into the open editor, or (when the editor isn't open on that
  chapter) `focusManuscriptUnit`s it and returns `false` with a "focused — Insert again" toast. Publish
  `manuscriptChanged` (F1-consistent) if it saves a draft.
- **Standalone `/chat`** supplies an `onInsert` = `firePasteToEditor({ text })` (already consumed by the editor
  page); if no editor is listening it's a no-op today — acceptable (out of studio there's often no editor). Optional:
  offer "Insert into a new chapter" via `useChapterDoor` — **park unless cheap**.
- Converge the existing buried overflow "Send to editor" (`AssistantMessage.tsx:459-466`) onto the SAME `onInsert`
  handler (One Name For One Concept) — don't leave two divergent insert paths.
**Files:** `frontend/src/features/chat/components/AssistantMessage.tsx` (new prop) + the message-list/ChatView plumbing
that passes `onInsert` down; the **studio wrapper** (`CoWriterChat.tsx`/`CompositionPanel.tsx`) and the `/chat`
wrapper each supply their handler. Reuse `useAcceptIntoEditor.ts`, `pasteToEditor.ts`.
**Tenancy/Contract:** none new. **Frontend-Tool-Contract:** not a tool arg; pure UI.
**Tests:** AssistantMessage unit — Insert renders only when `onInsert` present; click calls `onInsert(content)`;
absent-prop → no button (covers the `/chat`-without-editor + provider-safety case).
**QC / live-smoke (corrected):** studio co-writer with the chapter editor OPEN → ask Gemma for a paragraph (it replies
in chat) → click **Insert** → prose lands in the active chapter's editor (one click). With the editor NOT open on that
chapter → first Insert focuses+opens it (toast), second Insert lands the text (the real two-click behavior of
`useAcceptIntoEditor`) — QC accepts this, it is not a one-click guarantee.

---

## Slice N3 — F5: route a brand-new writer to the chooser  *(FE)*

**Root cause (corrected per review HIGH-1/MED-7 — a brand-new writer REGISTERS, they don't log in; `RegisterPage.tsx:44`
hard-codes `navigate('/books')` on success, never touching `resolveLoginRedirect` or `/onboarding`. So the true
first-run seam is registration, not login. Changing the LOGIN default to `/onboarding` would (a) miss the newcomer
and (b) regress every returning login with a pref-fetch round-trip + blank flash through the gate):**

**Design:** route **successful registration → `/onboarding`** (the "What do you want to do?" chooser). That is where
first-run genuinely begins. **Leave `resolveLoginRedirect` → `/books` unchanged** (returning users are unaffected;
no regression). The `/onboarding` gate already forwards already-seen users to `/books` (`OnboardingPage.tsx:14`), so
a returning user who somehow hits `/onboarding` still bounces correctly — but registration is a strictly first-run
event so the chooser is always the right landing.
- Bonus (small): the chooser's "Write" card routes to `/books` (the list), not into a studio — **park as N3-follow**
  (coordinate; intersects the other agent's onboarding-door work).
**Files:** `frontend/src/pages/auth/RegisterPage.tsx` (the post-register `navigate`). **NOT** LoginPage/gate.
**Tenancy/Settings:** none (registration is inherently first-run; no pref needed). No new flag.
**Tests:** RegisterPage unit — successful register navigates to `/onboarding` (not `/books`); failure path unchanged.
**QC / live-smoke:** register a fresh account → land on the "What do you want to do?" chooser; an existing account
logging in → still lands on `/books` (no regression).
**⚠ Coordination:** `RegisterPage.tsx` (pages/auth) is OUTSIDE the other agent's onboarding hot-area (lower collision
than LoginPage/gate — a second reason to prefer this seam). Still `git status`/`log`-check before editing.

---

## Slice N4 — F6: tame the sidebar  *(FE)*

**Root cause:** two flat arrays (`Sidebar.tsx:39-58` mainNav ×10, `:60-69` manageNav ×6), only Main/Manage headers,
whole-rail collapse; no "write with AI" entry; jargon labels. Mobile parallels (`MobileNav`/`MobileTabBar`/
`AllAppsDrawer`) must stay in sync.

**Design (right-sized):**
1. **Lead with writing:** a top group with **Workspace (your books)** + **Chat/Co-writer**; keep the entry labels
   plain. Ensure a first-run user sees "write my book" intent at the top (the chooser handles discovery; the sidebar
   just shouldn't bury it).
2. **Fold power-user items** (Standards, Campaigns, Roleplay, Extensions, Leaderboard) under a collapsible **"More"**
   group so the default rail is short. Keep Manage (Jobs/Trash/Usage/Settings) as-is.
3. De-jargon 1–2 labels if cheap (i18n `common.json nav.*`).
**Files:** `frontend/src/components/layout/Sidebar.tsx`; mirror in `MobileNav.tsx`/`AllAppsDrawer.tsx`; `common.json`.
**Tenancy/Contract:** none. **Tests:** Sidebar unit — the default rail shows the writing group; power-user items live
under a collapsible "More" (present but collapsed by default).
**QC / live-smoke:** post-login rail is short + writing-led; "More" expands to the rest; mobile nav matches.
**⚠ Coordination:** app shell is high-traffic — check ownership; this is the most collision-prone slice, sequence it
when the other agent isn't in the shell.

---

## Slice N7 — F8: polish batch  *(FE)*

- **Pop out disabled:** `⤢ Pop out` on the co-writer is disabled — either enable OS-popout (if supported) or hide it
  in-dock (don't show a dead control). Investigate the disabled condition; smallest honest fix.
- **Notifications SSE console error:** `/v1/notifications/stream` `ERR_INCOMPLETE_CHUNKED_ENCODING` — a benign
  reconnect surfacing as `console.error`. Handle the abort/stream-end cleanly (downgrade to debug or catch the
  expected disconnect) so a newcomer's console isn't red.
**Files:** co-writer panel header (pop-out), the SSE client. **Tests:** per-fix unit where meaningful. **QC:** eyeball
on the isolated build — no dead pop-out, clean console.
**Note:** N7 is a grab-bag; each item is independently shippable — do the cheap/clear ones, defer any that turn out
structural (with a tracked row), don't let it balloon.

### N8 (split out per review MED-6) — "99+ unread on a brand-new account" is a BE tenancy question, not an FE cap
The FE badge is **already capped** (`NotificationBell.tsx:118` renders `unread > 99 ? '99+' : unread`), so "cap the
display" is a no-op. The real question: **why does a brand-new user have >99 unread?** — investigate server-side first
(is the count real unread scoped to THIS `user_id`, or seeded/global/cross-tenant noise leaking in?). If it's real
per-user activity on the shared test account, it's expected (not a bug). If it's global/seed noise counted for a new
user, that's a **BE tenancy defect** with its own slice. **This slice is INVESTIGATE-FIRST, not a code change** —
outcome decides whether it becomes a real fix or a "no bug (test account has real activity)" close.

---

## Build order + per-slice gate

**Order:** N5 (persona+confirm) → N6 (idempotency) → N2 (insert — highest newcomer value) → N1 (mode legibility) →
N3 (routing) → N4 (sidebar) → N7 (polish). BE first (they change the behavior the FE showcases); N2 before N1
(insert matters more than mode-legibility given default is already write).

**Every slice:** BUILD (TDD where practical) → VERIFY (run tests, paste output) → **QC**: unit green **and** a live
observation on the isolated static build (+ Gemma for the agent-facing ones) proving the fix works by EFFECT → scoped
pathspec commit (only that slice's files) → tick the RUN-STATE board with the evidence string.

**Collision protocol:** before each FE slice, `git status`/`git log` to confirm the target files aren't mid-edit by
the other session; if they are, park + coordinate (RUN-STATE parked register), proceed to the next independent slice.

## Explicitly out of scope (won't-fix / later)
- Full Cursor-style inline diff/apply (N2 does append/new-draft, not a diff view).
- Role-based nav / full IA redesign (N4 is grouping only).
- Auto mode-switching magic (rejected in brainstorm).
- The "Write card → /books list not studio" deeper routing (N3-follow, coordinate with the other agent).
- **Tracked follow-up (review LOW-9):** the manuscript rail's own **Reload button** may still not refetch the
  hand-rolled tree (`invalidatequeries-cannot-reach-hand-rolled-state`) — the F1 fix wired the *bus* auto-refresh but
  the dogfood also noted the manual Reload did nothing. Verify + fix separately; do not let it silently vanish.

## Slice roster after review (updated)
N5 (persona+confirm), N6 (idempotency +migration), N2 (insert), N1 (mode legibility, verify-first), N3 (register→
onboarding), N4 (sidebar), N7 (pop-out + SSE console), **N8 (99+ badge — BE investigate-first, split from N7)**.
