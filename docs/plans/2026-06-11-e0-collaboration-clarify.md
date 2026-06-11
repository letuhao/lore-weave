# E0 — Collaboration-permissions epic · CLARIFY (locked)

> **Date:** 2026-06-11. **Phase:** CLARIFY complete (PO checkpoint passed). **Workflow:** `/loom`, size **XL**, **AMAW** (security-critical) to run at REVIEW + POST-REVIEW. **Branch:** `feat/glossary-assistant-coverage`. **Campaign context:** Phase -1 gating epic per D7/D10/D13 — see `docs/specs/2026-06-10-glossary-assistant-{scenario-coverage,extended-scenarios,architecture-review}.md`.
> **Goal (one line):** a platform-wide collaborative-permission model so the platform (and the assistant) can honor share-grants beyond single-owner.

## Current state (verified in CLARIFY)
- Whole platform uses **binary ownership** (`owner_user_id == caller`). **No** collaborator/grant/team/workspace/org anywhere (`user_follows` is social only).
- **Blast radius:** ~**180+ per-book endpoints** across 8 services; ~**165** must change. glossary alone = **57** `verifyBookOwner`/`checkBookOwnership` call-sites. Chokepoint = book-service `/internal/books/{id}/projection`.
- **JWT** = `sub`(user_id)+`sid` only, **no roles/permissions** (HS256; access 15 min, refresh 7 d; minted in auth-service `issueSessionAndTokens` → `authjwt.SignAccess`). Gateway forwards JWT (each service re-validates); MCP path uses gateway-injected **`X-User-Id`** header (NOT the JWT claims). Internal calls = `X-Internal-Token` + user_id param.
- **sharing-service** = visibility only (private/unlisted/public), owner-only writes — unrelated to write-grants.

## LOCKED decisions (PO, 2026-06-11; risks surfaced + re-confirmed)
| # | Decision | Notes |
|---|---|---|
| **D-E0-A** | **Home = book-service.** `book_collaborators` table + the grant/permission logic live in book-service. | It owns `owner_user_id` + the projection chokepoint. |
| **D-E0-B** | **Roles = owner (implicit) · manage · edit · view.** `manage` = destructive (delete/merge/reassign/purge, per D10); `edit` = create/edit; `view` = read. Owner is highest, derived from `owner_user_id` (not a stored row). | `book_collaborators` stores only **non-owner** grants. |
| **D-E0-C** *(revised 2026-06-11 → option B)* | **Propagation = per-request grant check, CACHED.** SoT = book-service `book_collaborators`; each service keeps an in-proc 60s positive cache (mirrors the existing `checkBookOwnership`); optional shared Redis cache + a Redis invalidate-key on revoke for instant revocation. **No grants in the JWT.** | Switched from JWT-claims after a perf analysis: a cache-hit ≈ a JWT-claim read (both ~free), and this is **literally the production path glossary already uses** (57 sites). Removes token-bloat, the auth↔book coupling, and the MCP gap. Revoke/grant effective ≤ cache TTL (~60s), or instant with the invalidate-key. |
| **D-E0-D** | **Grant authority = owner-only (v1).** A `manage`-grantee can do destructive ops but **cannot** grant/revoke to others. | Revisit "manage-can-grant" post-v1. |
| **D-E0-E** | **Scope = platform-wide big-bang.** All 8 services' ownership checks convert from owner-compare to grant-check in this epic (~165 endpoints). | XXL; AMAW + heavy review mandatory. (Lead recommended phased; PO chose big-bang.) |

## Acceptance criteria (amended per D-E0-C)
- **AC1** Owner can grant `edit`/`manage` to another user on a book, and revoke it.
- **AC2** A single fail-closed authority resolves a user×book grant level (owner/manage/edit/view/none).
- **AC3** Every per-book write across the 8 services honors the grant: `edit`→create/edit, `manage`→destructive; non-grantees denied uniformly (no enumeration oracle, per INV-8/H13).
- **AC4** grant/revoke takes effect within the **cache TTL (≤60s)** — or **instant** if a Redis invalidate-key is pushed on revoke. Both directions (new-grant AND revoke) propagate at this latency. *(Restored to ≤60s after switching D-E0-C → per-request cached; the JWT-claims ~15-min amendment is withdrawn.)*
- **AC5** Owner UI to invite/grant/revoke from a book surface (may be a sub-slice).
- **AC6** Single-owner case does not regress — owner retains full access with zero config.
- **AC-SEC** Grant/revoke is audited; only the owner can mutate grants; forging a grant requires `JWT_SECRET` (full compromise).

## Design points for the per-request cached check (D-E0-C = B) — DESIGN to specify
> Switching to (B) **dissolved** the three worst JWT wrinkles: no auth↔book coupling, no token bloat, no MCP-path gap. What remains is straightforward.
1. **book-service authority + contract.** Extend the chokepoint everyone already calls: either a dedicated `GET /internal/books/{id}/access?user_id=&need=view|edit|manage` → `{grant_level}` (or extend `/internal/books/{id}/projection` to carry the caller's grant-level). Fail-closed. **Single source of truth** for all services.
2. **Per-service cache.** Each service keeps a small `(user,book)→level` cache, 60s positive TTL — mirror glossary's existing `ownerCache` (fail-closed on book-service down; positive-only so revoke re-checks). **Optional:** a shared Redis cache for cross-instance, and a Redis invalidate-key pushed by book-service on grant/revoke for **instant** revocation (the user's blacklist idea used correctly — to *invalidate cache*, not to carry grants).
3. **MCP path is now natural (old wrinkle #4 dissolved).** The glossary MCP tools already resolve ownership per-request via `checkBookOwnership` (X-User-Id → book-service). They simply resolve **grant-level** on that same call — no JWT-claims gap.
4. **auth-service untouched (old wrinkles #1–3 dissolved).** No grants in the token → no coupling, no bloat, no re-mint storms. JWT stays `sub`+`sid`.
5. **Big-bang execution (D-E0-E).** 165 sites change `owner_user_id == caller` → `resolveGrant(user, book) >= needed`, via a **shared per-service helper** wrapping the book-service call + cache. Per-service: glossary (57 — replace `verifyBookOwner`/`checkBookOwnership` internals, signatures stay), book-service (~35 — it OWNS `book_collaborators`, so its own SQL can `JOIN`/sub-query directly, no self-RPC), knowledge (repo-layer `WHERE user_id` → widen to the grant set), translation (~15), campaign/composition/sharing/catalog. One helper shape per language (Go/Py/TS) to avoid 8 divergent impls — this is the main mechanical bulk of the epic.
6. **Migration.** Owner keeps implicit full access via `owner_user_id` (no backfill); `book_collaborators` starts empty, stores only **non-owner** grants. The grant resolver returns `manage`-or-higher for the owner without a row.

## NEXT (resume `/loom continue`)
DESIGN: book-service schema + grant resolver + auth-service claim population (wrinkle 1–3) + the MCP grant path (wrinkle 4) + the cross-service big-bang adoption plan with a shared grant-check helper (wrinkle 5) + migration (wrinkle 6) + audit. Then REVIEW (**AMAW** adversary, security-critical), PLAN, BUILD, VERIFY (live-smoke — ≥2 services), 2-stage REVIEW, QC, POST-REVIEW (human + likely `/review-impl`), SESSION, COMMIT, RETRO.
