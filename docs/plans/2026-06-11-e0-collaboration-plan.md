# E0 — Collaboration-permissions epic · PLAN (sliced)

> **Date:** 2026-06-11. **Phase:** PLAN (loom, XL, **no AMAW per PO**). **Inputs:** [`-clarify.md`](2026-06-11-e0-collaboration-clarify.md) (D-E0-A..E), [`-design.md`](2026-06-11-e0-collaboration-design.md) (design + R1–R5). The big-bang (D-E0-E, ~165 sites/8 services) is **sliced into deployable increments** — each its own loom BUILD→VERIFY→REVIEW→POST-REVIEW. Deploy order is dependency-driven; every consumer **degrades to owner-only** until it adopts (fail-safe), so partial deploy is safe.

## Open items — decided here (PO may override)
- **Invite mechanism:** **email-invite** (needs a thin auth-service `GET /internal/users/by-email`) — better UX; lands in **Slice 5 (FE)**, not blocking core. *(Default; raw-user_id-v1 is the fallback if you'd rather skip the auth endpoint.)*
- **Instant-revoke (Redis invalidate-key):** **defer to v1.1** — the 60s positive-cache TTL already meets AC4; instant-revoke is a nice-to-have that adds Redis pub/sub coupling to Slice 0. Ship the cache now, add the invalidate-key later if 60s proves too slow. *(Default; say so if you want instant-revoke in Slice 0.)*

## Slices (each = one loom cycle; deploy in order)

| Slice | Scope | Why / gates | Size | DoD |
|---|---|---|---|---|
| **E0-0 — book-service core** | migration `book_collaborators`; local grant resolver; `GET /internal/books/{id}/access` (returns `none` never 404, R4); **grantclient-Go** pkg (60s positive cache, fail-closed, mirrors glossary `ownerCache`); owner-only `GET/PUT/DELETE /v1/books/{id}/collaborators`; audit event emit. | **Foundational — gates all others.** Deployable alone (no consumer change → platform still owner-only). | L | real-PG: resolve (owner/each-role/none), endpoints (owner-only 403, can't grant self/owner, cascade on book-delete), audit emitted, `/access` no-404. |
| **E0-1 — glossary adoption** | re-impl `verifyBookOwner`/`checkBookOwnership` over grantclient (signatures stay → 57 sites barely move); **per-site `need`-mapping table** (read→view, create/edit/apply-edit/translations→edit, delete/merge/reassign/recycle-purge/destructive-schema→manage); MCP path; `ownerCache`→grant cache. | **Unblocks the coverage campaign / F1.** This is the slice the campaign actually needs. | L | glossary go green + the need-mapping table reviewed; **live-smoke: grant→B edits entity→revoke→denied ≤60s across book+glossary**. |
| **E0-2 — book-service self-adopt** | the ~35 SQL sites: single-book handlers = pre-check grant; list ("my books") = UNION owned+collaborated (R2/R3). **Book delete/trash/purge/transfer + visibility stay owner-only.** | book-service honors grants on its own endpoints. | M | reads/PATCH grant-gated; list returns shared-with-me; book-destructive still owner-only (tested). |
| **E0-3 — knowledge adopt** | verify `knowledge_projects.book_id` invariant (R1); resolve grant via project→book; widen repo-layer `WHERE user_id` to the grant set; owner-only fallback for book-less projects. | **Trickiest — IDOR risk.** Heaviest review. | L | grant-gated project access; cross-project IDOR blocked; book-less-project fallback. |
| **E0-4 — translation+campaign+composition** | swap `_verify_book_owner`/`_owner_verified_chapters`/`owns_book` → `require_grant(book, need)`. campaign also grant-checks the knowledge project. | straightforward adoptions. | M | each service grant-gated; campaign two-resource check. |
| **E0-5 — FE collaborators panel** | "Share / Collaborators" panel on the book surface (list/add-by-email/change-role/remove) + auth `GET /internal/users/by-email` (if email-invite). | owner UI (AC5). | M | panel CRUD; invite resolves user; vitest + tsc. |
| *(sharing, catalog, api-gateway)* | **no change** — visibility owner-only; catalog public; gateway transparent. | — | — | — |

**After E0-0 + E0-1 ship, F1 (the campaign's share-grant guard) is satisfied** — the rest (E0-2..5) extend coverage to other services and can land incrementally without blocking the glossary-assistant campaign.

## Verify strategy
- Per slice: unit (resolution + cache + need-mapping) → real-PG where state matters → **live-smoke for any slice touching ≥2 services** (E0-1, E0-3, E0-4 all do). The canonical live-smoke is the grant→edit→revoke flow across book + the adopting service.

## Risk register
- **R-need-mapping** (E0-1): one destructive op mis-mapped to `edit` = an editor can delete. Mitigate: explicit per-site mapping table, reviewed; default-deny (unknown op → manage).
- **R-knowledge-IDOR** (E0-3): loose repo-widening leaks cross-project. Mitigate: per-project book-grant resolution + IDOR tests.
- **R-book-destructive** (E0-2): book delete/transfer must stay owner-only. Mitigate: explicit owner-check on those handlers, tested.
- **R-fail-open** (all): a missed adoption stays owner-only (stricter) — fail-safe direction. Good.

## NEXT
BUILD **E0-0** (book-service core) first — bounded, foundational, deployable alone. Then E0-1 (glossary) to unblock the campaign.
