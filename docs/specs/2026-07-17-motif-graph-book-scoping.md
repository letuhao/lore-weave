# Spec + Plan — Motif Graph Book-Scoping (clears D-MOTIF-GRAPH-BOOK-SCOPING)

> **Status:** ready to build once §3 is decided · **Size:** S (one SQL predicate + tests + a live re-smoke) · **Track:** Wave-4 follow-up · **Origin:** the B8 /review-impl DEBT on the motif graph canvas.

## 1 · Problem

The Wave-4 motif graph canvas ([`MotifGraphLayoutRepo.nodes_for_book`](../../services/composition-service/app/db/repositories/motif_graph_layout.py)) selects nodes with:

```sql
WHERE status = 'active' AND (owner_user_id = $1 OR (book_shared AND book_id = $2))
```

`owner_user_id = $1` matches **every** motif the caller owns — globals AND motifs they labelled to a *different* book. So a user's ENTIRE library appears in EVERY book's graph; only the `book_shared` tier is actually book-filtered. It is honest and bounded (node cap + truncation), but the "book" in the URL is cosmetic for own motifs — not "this book's graph".

## 2 · The canonical definition already exists — mirror it

The motif **library** already answers "what are this book's motifs" — the `book` scope tab → [`MotifRepo.list_in_book`](../../services/composition-service/app/db/repositories/motif_repo.py#L463):

```sql
(owner_user_id IS NULL OR owner_user_id = $1 OR (book_shared AND book_id = $2))  -- own + system + book-shared
AND (book_id IS NULL OR book_id = $2)                                            -- ← the book-relevance clause the graph LACKS
```

i.e. **the caller's globals (book_id NULL) + their motifs labelled to THIS book (book_id = $2) + this book's shared tier + system.** The graph should mean the same thing the library's "book" tab means — no new per-surface semantics.

## 3 · 🔴 THE ONE DECISION — what counts as "in this book"?

| Option | Predicate | Pros | Cons |
|---|---|---|---|
| **(A) Mirror the library `book` tab** (recommended) | add `AND (book_id IS NULL OR book_id = $2)` to the existing graph query (keep NOT including system — see §4) | consistent with the library UX; a 1-clause change; cheap; no join | a global motif still shows in every book (but that matches the library tab, so it is at least *consistent*) |
| **(B) Bound-in-this-book** | `EXISTS (SELECT 1 FROM motif_application WHERE book_id = $2 AND motif_id = motif.id)` (∪ book_shared) | the tightest "this book's story" graph — only motifs actually woven into the book | excludes motifs created/adopted for the book but **not yet bound** (a fresh book's graph is empty); needs a join + a product call on whether "planned but unbound" should show |
| **(C) Keep current** | (do nothing) | — | the debt stays; the graph is not book-scoped |

**DECISION (PO, 2026-07-17): (B) bound-in-book.** The graph is the book's STORY graph — only motifs actually woven into this book (a `motif_application` binding) plus the book's shared tier. A user's global library no longer floods every book's graph; a book you have not started binding shows the honest empty state (§5 E2), which is acceptable — the graph is about *this book's* woven motifs, not your whole library. (Option A is recorded above as the rejected alternative; a "show my whole library" toggle could revisit it later.)

## 4 · The change (Option B)

`nodes_for_book` becomes — the book's SHARED tier, plus the caller's OWN motifs BOUND in this book:

```sql
WHERE status = 'active'
  AND (
    (book_shared AND book_id = $2)                                       -- the book's shared authoring tier
    OR (owner_user_id = $1 AND EXISTS (                                  -- the caller's own, actually bound here
      SELECT 1 FROM motif_application ma WHERE ma.book_id = $2 AND ma.motif_id = motif.id))
  )
```

- **System (`owner_user_id IS NULL`) and public stay excluded** — you bind a *clone* (adopt) of a system/public motif, not the shared original, so a bound node is always own-or-book_shared; and the `motif_link_guard` forbids cross-tier edges, so a system node could only be an island. (One-line comment so nobody "fixes" it by adding system back.)
- **`motif_visible_in_book` MUST apply the SAME predicate** — a caller may only store a position for a motif that IS a graph node (bound-here-own or book_shared); anything else → 404 (no oracle). Keep the two BYTE-IDENTICAL via a shared SQL fragment (the one-predicate-two-callsites discipline) + a test that asserts they agree.
- **`edges_among` unchanged** — it already filters to edges whose BOTH endpoints are in the (now-tighter) node set, so no dangling edge to an unbound motif.
- The node cap + `truncated` flag are unchanged (they now bound the correctly-scoped, usually-smaller set).

## 5 · Edge cases

| # | Case | Behaviour |
|---|---|---|
| E1 | The caller's own motif NOT bound in this book (unbound / other book) | not a node here (that is the point of B); its stale position in this book's layout row is ignored on read (regenerable) — no orphan. |
| E2 | A book you have not bound any motif in yet | the graph is empty → the honest `motif-graph-empty` CTA ("create/adopt then link"). Correct for a story graph — not a bug. Its wording already fits ("no motifs to graph yet"). |
| E3 | A stored position for a motif that left the graph (unbound / re-scoped) | GET ignores unknown ids in `positions`; PATCH `motif_visible_in_book` returns false → 404. Both handled; the shared predicate keeps them aligned. |
| E4 | A book_shared motif with no binding | STILL a node — book_shared is the shared authoring tier, shown unconditionally (only the *own* tier requires a binding). The `(book_shared AND book_id = $2)` clause covers it. |
| E5 | A motif bound in this book but since ARCHIVED | `status = 'active'` filters it out (a retired motif is not a live node), even if a stale `motif_application` row remains. |

## 6 · Standards
- **Tenancy:** unchanged shape — still scope-keyed on `owner_user_id` + `book_id`; this tightens (never widens) what a caller sees. ✅
- **One-predicate-two-callsites:** `nodes_for_book` ⇄ `motif_visible_in_book` must share the exact clause (so a shown node is always position-able, and a non-shown one is always rejected). Enforce with a test.

## 7 · Plan (phases)
1. **BE:** rewrite the `nodes_for_book` / `motif_visible_in_book` predicate to the §4 bound-in-book form via a shared SQL fragment (book_shared-tier ∪ own-bound-here). One-line comment on why system stays excluded.
2. **Tests:** extend `test_motif_graph_layout` — an own motif BOUND in this book appears; an own motif NOT bound (or bound in another book) does NOT; a book_shared motif appears even with no binding; an archived-but-once-bound motif is excluded; and `motif_visible_in_book` AGREES with `nodes_for_book` (a returned node is accepted; a non-node is rejected → the PATCH 404s). Update the existing route/repo tests' fixtures (they mocked `nodes_for_book` — the mock shape is unchanged; the DB behaviour is what changes, covered by the live re-smoke since the repo query is DB-side).
3. **Live re-smoke:** seed a bound motif + a book_shared motif + an UNBOUND own motif, `GET /motif-graph` → the first two present, the unbound absent; re-run `studio-motif-graph.spec.ts` (bind the seeded motifs first so the graph is non-empty) — the CDP drag still green.
4. **/review-impl + close** the DEBT row in the Wave-4 RUN-STATE.

**Deferred (not this spec):** a "show my whole library" toggle (Option A behaviour) — revisit if users want to arrange unbound motifs too.
