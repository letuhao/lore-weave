# Derivative Manuscript Fork (D-S5-DERIVATIVE-MANUSCRIPT-FORK) — spec + product question

> Origin: S5 completeness audit + the inbound S1-A3 item (D-S5-DERIVATIVE-ACCEPT-ISOLATION).
> S5 shipped Switch-to, which makes "being on a dị bản" reachable. That surfaced a design
> question this spec exists to settle before it is built. **This needs a PRODUCT decision
> first — §1 — then, only if the answer is "fork", the design in §3.**

## 1 · The product question (decide this first)

Today a **dị bản (derivative)** is a **SPEC-LEVEL branch**: a branch_point + taxonomy +
entity_overrides + canon_rules, sharing the source book's chapters read-only under COW. Its
own divergent PROSE lives ONLY in the composition scene-draft store (via the what-if canvas →
Promote — isolated, source-clobber-guarded). The chapter manuscript editor is **book-scoped**:
editing a chapter while "on" a derivative writes the SHARED canon manuscript. v1 signals this
(the D-S5-DERIVATIVE-EDIT-GUARD banner) but does not prevent it.

**The question:** should a derivative be able to hold its OWN full manuscript (a fork), so a
writer can rewrite whole chapters in the branch without touching canon — or is the spec-branch
model (divergent prose only via promoted scenes; the manuscript stays canon) the intended
product?

- **Keep spec-branch (no fork).** Simpler; the derivative is an "what-if lens" over canon, not
  a parallel book. The edit-guard banner is the whole mitigation. **Recommended default** —
  it matches the COW design and everything shipped.
- **Fork the manuscript.** A derivative becomes a true parallel draft: its chapters can diverge
  wholesale. Powerful but large (§3) and raises real tenancy/storage/merge questions.

If the decision is "keep spec-branch", this item is **CLOSED** (v1 decision stands, banner
mitigates) and §3 is not built. Build §3 ONLY on an explicit "fork" decision.

## 2 · Why it can't just be bolted on

The editor edits `book-service` chapter drafts keyed by `(book_id, chapter_id)`. A derivative
shares the book_id (COW), so there is no per-work draft to write to — the draft is the canon
manuscript. Isolating it needs a **work-scoped draft layer**, which does not exist.

## 3 · Design (only if "fork" is chosen)

- **Work-scoped chapter drafts.** Add a draft dimension keyed by `(book_id, chapter_id,
  work_id)` — a derivative's edits land in ITS row; canon (work_id = canonical) is untouched.
  Options: (a) a `work_id` column on book-service's chapter-draft table with canonical as a
  sentinel; (b) a composition-side chapter-draft store the editor reads/writes when the active
  work is a derivative (mirrors how promoted scene-prose already lives composition-side).
  Prefer (b) — it keeps the COW/source-clobber guard that already isolates promoted prose, and
  avoids a book-service schema change touching every reader.
- **Editor work-scoping.** EditorPanel already resolves the active Work (resolveActiveWork).
  When it is a derivative, read/write the work-scoped draft instead of the book draft. Lazy:
  a derivative chapter with no work-scoped draft yet **inherits** canon (read-through), forks
  on first edit (copy-on-write at the chapter level, matching the branch model).
- **Merge / promote-to-canon.** A forked chapter needs a path back (promote a whole chapter
  from the derivative into canon) — reuse the C27 derivative-chapter approval → delta flywheel
  seam (already exists for derivative chapters).
- **Tenancy.** The work-scoped draft is per-book + per-work (the derivative's own scope) — same
  grant model as the derivative Work; no new cross-tenant surface.

## 4 · Acceptance (if built)

- On a derivative, editing a chapter + Accept writes the WORK-scoped draft; canon's chapter
  draft is byte-unchanged (a live derivative-work smoke: edit → save → confirm canon untouched).
- A derivative chapter with no fork yet reads canon (inherit); it forks on first edit.
- Switching back to canon shows canon's manuscript; switching to the derivative shows the fork.
- The edit-guard banner (v1) is replaced by the real isolation.

## 5 · Status

BLOCKED ON A PRODUCT DECISION (§1). Until then, v1 = spec-branch + the edit-guard banner
(shipped). Size if built: L (schema/store + editor work-scoping + merge path + smokes).
