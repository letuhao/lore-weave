# Round 3 — Newcomer feedback after the Parts→Arcs merge (live stack)

**Origin:** a third dogfood pass, newcomer hat, on the freshly-rebuilt live stack (the Parts→Arcs merge
is deployed: parts now live ONLY in composition as `structure_node kind='part'`). Goal: confirm the
merge works in real use, and keep an honest eye out for what it broke or exposed.

> Companion to [round-2-feedback.md](round-2-feedback.md) (F8–F10). New finding: **F11**.

## ✅ What works (verified live, not just tests)
- **The Parts→Arcs merge is real and functional.** On a Work-less book I created a part through the UI
  path (`POST /v1/composition/books/{id}/parts` → "Volume I", sort_order 1) and read it straight back
  (`GET …/parts` → `{items:[Volume I]}`). Part create → read now flows through the single composition
  SSOT — no book-service parts table, no two-system split. The composition `/parts` endpoint is live
  (was 404 pre-rebuild). 0 console errors on the studio surfaces.
- F1–F10 (rounds 1–2) all still hold in live use.

## 🔴 F11 (HIGH) — creating a Work makes an un-decomposed book's chapters VANISH from the Manuscript rail

**What the newcomer sees.** Open a book that has chapters. The Manuscript rail says **"No chapters yet.
＋ Start your first chapter"** — as if the book were empty. The chapters are *not* lost (the editor
opens them; `GET /v1/books/{id}/chapters` returns all of them), but the manuscript navigator hides them.
Reproduced on TWO books this session (The Lantern of Ell Marren = 3 chapters; S-11 Smoke Book = 1
chapter) — both show "No chapters yet."

**Root cause (grounded).** [useManuscriptTree.ts:74](../../../frontend/src/features/studio/manuscript/useManuscriptTree.ts#L74):
```ts
const source = work.isLoading ? 'pending' : projectId ? 'outline' : 'chapters';
```
A book with a composition **Work** switches the navigator to the **outline** source (composition
`outline_node`, project-scoped). But a book whose chapters were **never decomposed into the outline**
has an empty outline → the rail renders empty, even though book-service holds the chapters. It's the
mutual-exclusivity assumption: "has Work ⇒ read the outline" with no fallback to the actual chapters.

**Why this is newly URGENT (and partly my own doing).** Before this session a newcomer rarely created a
Work by accident. The onboarding door I shipped changed that: **"Set up writing"** (F10) and **"Or set up
this book completely"** (Part B) both create a Work in one click — and that is exactly what tips an
existing, un-decomposed book into the empty-rail state. I verified it: the Works on both test books were
created via those very buttons this session, and now their chapters are invisible in the rail. The
onboarding door fixed a dead end and opened a trap door.

**Severity.** HIGH — it reads as **data loss** to a newcomer ("where did my chapters go?"), the scariest
possible signal, and the onboarding flow now leads straight into it. (No data is actually lost.)

**Fix options (for the spec/brainstorm):**
1. **Outline source falls back to book-service chapters when the outline is empty** — show the real
   chapters (flat) instead of "nothing," so a Work with no plan still browses its manuscript. (Smallest,
   safest — mirrors the F10 "a Work-less book still browses" principle, extended to "an un-planned Work
   still browses.")
2. **Seed the outline from the book's chapters when the Work is created** — "Set up this book" imports
   existing chapters into the plan so the outline isn't empty.
3. **Merge the two** — the rail always shows the book's chapters, annotated with plan/outline structure
   when present. (This is the real end-state and dovetails with the Parts→Arcs unification.)

Recommend **#1 now** (stops the scary vanish), **#3** as the coherent follow-up.

## Honest carry-overs (not new bugs, but open)
- **Import flat-grouping regression** — when I retired book-service parts (C4 cleanup) the import path
  now creates chapters FLAT; a multi-part source no longer auto-groups. Re-add via a composition-side
  part-create on import. Tracked in the structure-coherence RUN-STATE.
- **F7c** — chat co-writer context bloat (~22.6k tok/msg), still deferred to `context-budget-law`.

## Status
`FEEDBACK` — round-3 dogfood on the live post-merge stack. The Parts→Arcs merge is verified working
end-to-end. One HIGH finding (**F11**: Work-creation hides un-decomposed chapters — the onboarding door
leads into it) captured with a code-grounded root cause + fix options. No code changed in this round.
