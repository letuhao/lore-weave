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

**Recommendation: (A).** It makes the graph *consistent with the library's own book definition* (the least-surprising behaviour), is a one-line change, and keeps a just-created/adopted motif visible (unlike B, which hides anything unbound). B is a plausible future enhancement (a "bound only" toggle) but changes the mental model and can render an empty graph for a book you're still planning.

## 4 · The change (Option A)

`nodes_for_book` becomes:

```sql
WHERE status = 'active'
  AND (owner_user_id = $1 OR (book_shared AND book_id = $2))
  AND (book_id IS NULL OR book_id = $2)
```

- **Keep excluding system (`owner_user_id IS NULL`)** — unlike the library tab, the graph omits system rows *on purpose*: the `motif_link_guard` forbids cross-tier edges, so a system node can only ever be an island in the caller's graph. (The library tab shows system for *browsing*; a graph shows *relationships*.) This is the one deliberate divergence from `list_in_book`, and it should carry a one-line comment so a future reader doesn't "fix" it by adding system back.
- `edges_among` and `motif_visible_in_book` are unchanged structurally, but **`motif_visible_in_book` must apply the SAME new clause** so the PATCH can't store a position for a motif that is no longer a graph node (a motif labelled to another book). Keep the two predicates BYTE-IDENTICAL (one helper or a shared SQL fragment) so a retrieved node is provably position-able — the same one-predicate-two-callsites discipline the motif read path uses.
- The node cap + `truncated` flag are unchanged (they now bound a correctly-scoped set).

## 5 · Edge cases

| # | Case | Behaviour |
|---|---|---|
| E1 | A motif labelled to a DIFFERENT book | no longer a node here (correct); its stored position in THIS book's layout row is ignored on read (regenerable) — no orphan. |
| E2 | A global (book_id NULL) motif | still a node in every book's graph — matches the library `book` tab (consistent, not a bug). |
| E3 | A stored position for a motif that left the graph (re-labelled to another book) | GET ignores unknown ids in `positions`; PATCH `motif_visible_in_book` now returns false for it → 404 (no oracle). Both already handled; the shared predicate keeps them aligned. |
| E4 | book_shared row | unchanged — `(book_shared AND book_id = $2)` already implies `book_id = $2`, so the new clause is a no-op for it. |

## 6 · Standards
- **Tenancy:** unchanged shape — still scope-keyed on `owner_user_id` + `book_id`; this tightens (never widens) what a caller sees. ✅
- **One-predicate-two-callsites:** `nodes_for_book` ⇄ `motif_visible_in_book` must share the exact clause (so a shown node is always position-able, and a non-shown one is always rejected). Enforce with a test.

## 7 · Plan (phases)
1. **BE:** add the `(book_id IS NULL OR book_id = $2)` clause to `nodes_for_book` AND `motif_visible_in_book` (shared fragment). One-line comment on why system stays excluded.
2. **Tests:** extend `test_motif_graph_layout` — a motif labelled to book-A does NOT appear in book-B's `nodes_for_book`, and `motif_visible_in_book` rejects it (so the PATCH 404s); a global + a book-A-labelled motif DO appear in book-A. Assert the two predicates agree (a node returned by `nodes_for_book` is accepted by `motif_visible_in_book`, and vice-versa).
3. **Live re-smoke:** re-run `studio-motif-graph.spec.ts` (the CDP drag) — still green — plus a `GET /motif-graph` on a book with a foreign-labelled motif confirming it is absent.
4. **/review-impl + close** the DEBT row in the Wave-4 RUN-STATE.

**Deferred (not this spec):** Option B "bound-only" view (a toggle backed by `motif_application`) — a product decision + a join; revisit if users ask for a story-only graph.
