# Round 2 — Newcomer feedback on the *fixed* build

**Origin:** a second dogfood pass, same brand-new-user hat, this time on the build that already
ships the M1–M6 polish fixes (static build served on `:5290`, gateway `:3123`, book *The Lantern of
Ell Marren*). Goal: keep using the Studio past the first-run maze — actually write more prose, then
poke the panels a newcomer reaches for next (Plan, Story Bible). This is the diary of that run.

> Companion to **[README.md](README.md)** (F1–F7). New findings continue the numbering: **F8–F10**.

---

## What the first-round fixes feel like now (verified live, not from the test suite)

These are the M1–M6 fixes experienced as a user, on `:5290`:

- **The manuscript tree reads like a book.** Three chapters showed as **"Chapter 1 / Chapter 2 /
  Chapter 3"** — no `editor-2d0fc71f-….txt` filename anywhere. (F4 ✓)
- **Writing → saving is smooth.** Opened Chapter 1, saw my real opening line, clicked into the prose,
  added a paragraph. A **"● unsaved"** dot appeared, `⌘S` flipped it to **"saved"** and disabled the
  button. This is the loop the first run never reached. (F2/F3 ✓ — the write door exists and the save
  state is honest.)
- **The rail says "Chapter" and "Part", not "＋" and "Act".** The Manuscript rail has real labelled
  **Chapter** / **Part** buttons, and the group header reads **"PART Part One: The Sinking Harbor"** —
  the Act/Arc homophone is gone. (F6 rename ✓)
- **Prerequisite empty states are, mostly, *well written*.** Divergence: *"This book has no plan yet —
  lay out its arcs and chapters first, then branch a what-if here."* Reference shelf: *"No writing
  project yet — set up a Work first…"*. These explain the gate instead of just being blank. That good
  copy is exactly what makes **F8 below** stand out as the one panel that *doesn't* do this.

The first-run path is genuinely fixed. The new friction is one layer deeper: the **Plan / Story
Bible** surfaces, which a newcomer reaches the moment they want to organize (not just type).

---

## New findings

| ID | Severity | Finding (newcomer's words) | Root cause (file:line) | Rec. size |
|----|----------|----------------------------|------------------------|-----------|
| **F8** | 🟠 Med | "I clicked **Plan** and got a panel that just says *No arcs yet.* — with no button. Dead end again." | The Plan navigator rail's empty state is bare text with **no create/plan door**, unlike its own sibling panel which has guided copy. | S |
| **F9** | 🟠 Med | "Half the Story-Bible labels have Vietnamese in them — *Divergence (dị bản)* — is that a bug?" | `divergence.title` is a **hardcoded bilingual string baked identically into every locale** (en included). Not translated — the author's shorthand leaked into the UI. | S |
| **F10** | 🟡 Low–Med | "I wrote three chapters and Story Bible tells me *No writing project yet.* I *have* a project — I've been writing in it." | The Story-Bible surfaces gate on an internal **"Work" / "plan"** concept the newcomer never knowingly created; a book full of prose is labelled *not a project yet*, with no bridge to create one. | S–M |

### F8 · The Plan panel is a dead end (the same disease F2 fixed, one panel over)

**What happened.** With my 3-chapter book open, I clicked the **Plan** toggle in the panel-layout
strip. The left rail switched to a **"Plan"** header with a single line under it: **"No arcs yet."**
No button, no link, no "start planning here." To actually create an arc I'd have to *already know* to
go back to the Manuscript rail and press **"Plan this book."** This is precisely the dead-door pattern
M3 killed for chapters (Editor empty state → real "Start a chapter" door) — it just still lives in the
Plan rail.

**Root cause.** [PlanNavigatorRail.tsx:49-52](../../../frontend/src/features/plan-hub/components/PlanNavigatorRail.tsx#L49-L52)
renders `t('planNav.empty')` = `"No arcs yet."` as centered muted text with **no affordance**. The rail
has `onFocusNode` (focus a node on the canvas) but no create intent at all.

**The fix already exists in-repo.** The sibling
[ArcInspectorPanel.tsx:56](../../../frontend/src/features/studio/panels/ArcInspectorPanel.tsx#L56)
handles the identical "no arcs" case with *guided* copy: *"No arcs yet — the spec tree is what steers
generation. Extract a plan from the manuscript in the Plan Hub, or create an arc there."* The Plan rail
should adopt the same shape: a one-line explanation **plus a real door** — a **"Plan this book"**
button that fires the same plan-hub origin flow the Manuscript rail already wires. One small component
change; no new backend.

**Acceptance.** Opening **Plan** on a planless book shows a guided empty state with a working
create/plan button; clicking it lands the user in the plan-creation flow (not a blank canvas).

### F9 · `Divergence (dị bản)` — a bilingual label leaks into every locale

**What happened.** The Story Bible panel offers two tabs: **"Reference shelf"** and **"Divergence
(dị bản)"**. To an English-reading newcomer, the parenthetical `(dị bản)` looks like leftover
untranslated foreign text — i.e. a bug. It appears on the tab button, the panel title, *and* the
floating dock-tab title, so it's not a one-off.

**Root cause.** `divergence.title` is set to the **same literal string in every locale file** —
[en/studio.json:398](../../../frontend/src/i18n/locales/en/studio.json#L398) and identically in
`fr`, `tr`, `ms`, `bn`, `vi` (all line 398), plus the `defaultValue` in
[DivergenceManagerView.tsx:137](../../../frontend/src/features/composition/components/DivergenceManagerView.tsx#L137).
"Dị bản" is Vietnamese for *variant / divergent edition* — the developer's mental shorthand for the
feature, hard-coded into the display label rather than kept as an internal concept name. The same gloss
also rides along in placeholders/empty-copy ("Untitled dị bản", "New name in this dị bản (optional)…").

**Recommendation.** Pick one **user-facing** English term for the concept — **"Divergence"** alone, or
"What-if versions" / "Variants" — and set `divergence.title` to it (then gap-fill the 18 locales via
`scripts/i18n_translate.py --ns studio` so each language gets a *real* translation instead of the
baked bilingual literal). Keep "dị bản" only in code comments / internal identifiers, never in a
rendered string. Sweep the sibling placeholders too.

**Acceptance.** No rendered UI string contains "dị bản" in any locale; the Divergence panel title,
tab, and placeholders read in the active language only.

### F10 · "No writing project yet" — the *Work* concept is un-onboarded

**What happened.** Both Story-Bible surfaces refused to engage: Divergence said *"This book has no plan
yet…"* and Reference shelf said *"No writing project yet — set up a **Work** first…"*. But I had just
written three chapters of prose. Being told my book **isn't a writing project yet** — and to go set up
a **"Work"** (a word the UI never defined for me) — reads as either broken or gatekeeping.

**Root cause (conceptual, not a single line).** The Studio has a real internal layer — a **Work**
(canon vs. derivative/"dị bản") that Story-Bible features hang off — but there is **no onboarding bridge
from "I wrote chapters" to "you now have a Work/plan."** The empty states name the prerequisite
correctly but offer no verb to satisfy it from where the user is standing (same missing-door root as F8,
one concept up). The term **"Work"** is also internal jargon surfaced raw to a first-time user.

**Recommendation (cheap slice now; larger later).**
- *Now (S):* in these empty states, replace the passive "set up a Work first" with an **action** —
  a button that creates the canonical Work / plan for this book in place (the plumbing exists; it's the
  same object the Plan flow makes). And **stop calling it "Work" in first-run copy** — say "plan" /
  "this book's canon," matching the vocabulary the rest of the Studio already uses.
- *Later (gate #2, structural):* fold "a book with prose but no Work" into the same guided
  first-plan flow F8 opens, so the Plan panel, Divergence, and Reference shelf all share **one** door
  to "give this book its plan." Tracked alongside F6's unify-the-hierarchies track, not built here.

**Acceptance (now-slice).** From a prose-only book, the Story-Bible empty states offer a working button
that creates the plan/Work in place; no first-run string uses the bare word "Work" without explanation.

---

## Sizing & sequencing (proposed)

Whole add-on effort ≈ **S–M** (all three are FE-only display/empty-state work; F9 touches i18n
across 18 locales via the standard gap-fill script; no schema/route changes).

1. **F9** first — pure string/i18n fix, lowest risk, removes the most obviously "broken-looking" thing.
2. **F8** — small `PlanNavigatorRail` empty-state change reusing the existing plan-hub origin flow.
3. **F10 (now-slice)** — the Story-Bible empty-state action buttons + de-jargon copy; shares the F8
   plan-creation door.

Each slice: `en` copy + `scripts/i18n_translate.py --ns studio` gap-fill, unit test on the empty state,
and a **live QC on the isolated static build (`vite build` → `vite preview --strictPort`)** — never
`vite dev` — matching this track's constraint.

---

## Sealed decisions & build-ready fix plan (2026-07-18 brainstorm)

The brainstorm's key finding: **all three fixes compose around plumbing that already exists** — no new
backend, no schema/route change. The Studio already solved "give this book its plan/Work" once; it's
just mounted in too few places:

- `usePlanOrigin.start()` ([usePlanOrigin.ts](../../../frontend/src/features/plan-hub/hooks/usePlanOrigin.ts)) —
  idempotent, race-safe, outage-resilient *create-arc + ensure-Work*; already fires from plan-hub's empty state.
- `WorkSetupCta` ([WorkSetupCta.tsx](../../../frontend/src/features/studio/panels/WorkSetupCta.tsx)) —
  self-contained idempotent create-Work button; currently mounted **only** on Decompose + Quality panels.
- `host.openPanel('plan-hub', { focus: true })` — the exact door the Manuscript rail's `+` already uses.

**Sealed naming decisions (human, 2026-07-18):**
- **F9 term → "What-if versions"** (replaces `Divergence (dị bản)` everywhere it renders). "dị bản"
  survives only in code comments / internal identifiers / test names — never in a rendered string.
- **F10 term → "Writing setup" / "Set up writing"** for the *Work* concept in first-run empty states
  (and the shared `WorkSetupCta` button). Keeps the AI-chat term "Co-writer" distinct from the Work
  object (they are different things; the old CTA label conflated them).

### M7 · F8 — a real door on the Plan rail
- `PlanNavigatorRail.tsx`: add prop `onOpenPlan?: () => void`. Replace the bare `plan-nav-empty`
  ("No arcs yet.") with **guided copy** (lift the wording from the sibling
  [ArcInspectorPanel.tsx:56](../../../frontend/src/features/studio/panels/ArcInspectorPanel.tsx#L56))
  **+ a "Plan this book" button** (`data-testid="plan-nav-plan-cta"`, gated on `onOpenPlan`).
- `StudioSideBar.tsx`: pass `onOpenPlan={() => host.openPanel('plan-hub', { focus: true })}` — the
  same door the Manuscript `+` uses; plan-hub's own empty state carries the real origin verb.
- i18n: `planNav.emptyGuided`, reuse `manuscript.openPlan` ("Plan this book") for the button.
- Test: empty state renders the CTA and fires `onOpenPlan`; gap-fill 18 locales.

### M8 · F9 — kill the bilingual label
- `en/studio.json`: `divergence.title` → **"What-if versions"**. Sweep the sibling strings that carry
  the gloss: `divergence.unnamed` ("Untitled dị bản" → "Untitled version"),
  `divergence.overrideNamePlaceholder` ("New name in this dị bản…" → "New name in this version…"),
  `divergence.emptyDerivatives` (drop "dị bản"). Same defaultValues in
  [DivergenceManagerView.tsx](../../../frontend/src/features/composition/components/DivergenceManagerView.tsx)
  and `DivergenceSpecEditor.tsx`.
- `scripts/i18n_translate.py --ns studio` (+ `--ns composition` if touched) to gap-fill all 18 locales
  with **real translations**, not the baked literal.
- Verify: grep the locale dirs + rendered components — no "dị bản" in any string a user can see.

### M9 · F10 — mount the door that exists + de-jargon
- `ReferenceShelfPanel.tsx` (line 33-39) and `StyleVoiceStudioPanel.tsx` `noWork` gates: mount
  `<WorkSetupCta bookId={host.bookId} token={accessToken} />` under reworded copy — "No writing
  project yet — set up a Work first…" → **"Writing isn't set up for this book yet — set it up to
  curate its reference shelf / steer its style & voice here."** (`host` + `accessToken` are already in
  scope in both.)
- `WorkSetupCta.tsx`: button `quality.setupWork` "Set up co-writer" → **"Set up writing"** (shared
  across Quality/Decompose too — a consistent global rename of the Work-setup verb).
- **Divergence "no plan yet"** empty state → give it the **same plan-hub door as M7/F8** (it's a dock
  panel with `host` access) rather than a Work button — its gate is a *plan*, not a *Work*.
- The full "one shared door across Plan + Divergence + Reference shelf" unification stays **deferred**
  (gate #2, structural) — folded into F6's unify-the-hierarchies track. M9 is only the cheap mounts.

### Sizing & gates
Whole add-on ≈ **S–M**, FE-only. Build order **M8 → M7 → M9** (string fix first = removes the most
obviously-broken-looking thing; then the two door mounts). Each slice: `en` copy +
`i18n_translate.py` gap-fill, a unit test on the empty state/CTA, and a **live QC on the isolated
static build (`vite build` → `vite preview --strictPort`)** — never `vite dev`, per this track's
constraint. `review-impl` on M9 (it touches the shared `WorkSetupCta` across four panels).

## Status
`SHIPPED` (2026-07-18) — all three findings fixed, each QC'd on the isolated static build `:5290`:
- **M8 · F9** `9d7911bb5` — `Divergence (dị bản)` → **"What-if versions"** in en + 18 locales; QC: tab,
  dock region, and panel all read the new label.
- **M7 · F8** `baaa30bd8` — Plan rail empty state → guided copy + **"Plan this book"** door; QC: the
  button opens the Plan Hub origin flow (no longer a dead end).
- **M9 · F10** `8fbf76c02` — mounted the existing create-Work CTA on the Reference-shelf / Style-voice
  empty states + de-jargoned "Work" → **"Set up writing"**; QC verify-by-effect: clicking it created
  the Work and revealed the real shelf, 0 console errors. review-impl fixed a button/toast vocab drift.

**Deferred:** the divergence/what-if "no plan yet" states could get the same plan door, but they lack
host access and their copy is already guided — folded into F6's unify-the-hierarchies track.
