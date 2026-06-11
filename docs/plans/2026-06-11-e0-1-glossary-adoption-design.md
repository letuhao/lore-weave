# E0-1 — Glossary adoption of the grant model · DESIGN

> **Date:** 2026-06-11. **Phase:** DESIGN (loom, L→XL, no AMAW per PO). **Epic:** E0 collaboration-permissions, slice 1 (see [`-plan`](2026-06-11-e0-collaboration-plan.md)). **Depends on:** E0-0 (`grantclient`, `/internal/books/{id}/access`). **Unblocks:** campaign F1 (share-grant guard).

Migrate glossary-service's two ownership helpers off "is-owner (via book projection)" and onto the graded grant model (`none<view<edit<manage<owner`) resolved through `grantclient`. Every book-scoped call-site is assigned an explicit minimum `need`. **PO-locked at CLARIFY:** (1) close the pre-existing **genres IDOR** in this slice; (2) hard-delete of child records (evidence/translation/chapter-link) = **edit**; (3) **include the lifecycle gate** (deny edit/manage on a trashed/`purge_pending` book).

## Design points

### D1 — `/access` carries lifecycle (additive to E0-0)
The lifecycle gate needs the book's `lifecycle_state`. Rather than make glossary do a second upstream call (grant + projection), extend the single authority:
- **book-service** `GET /internal/books/{id}/access` response gains `lifecycle_state` (alongside `grant_level`). New helper `resolveAccess(ctx, bookID, userID) (GrantLevel, lifecycle string, err)` — one query `SELECT owner_user_id, lifecycle_state FROM books WHERE id=$1`; missing book → `(GrantNone, "", nil)` (lifecycle `""` = absent, R4 preserved — still no oracle since grant is `none`). `resolveGrant` stays for the owner-only collaborator gate (lifecycle-irrelevant there).
- Response: `{"grant_level":"edit","lifecycle_state":"active"}`.

### D2 — `grantclient.ResolveAccess`
- New `type Access struct { Level GrantLevel; Lifecycle string }`.
- `ResolveAccess(ctx, bookID, userID) (Access, error)` — the cached call (positive-only, 60s); `ResolveGrant` becomes a thin wrapper returning `.Level` (E0-0 callers unchanged). Cache entry stores the whole `Access`, so lifecycle shares the grant's 60s staleness window (a just-trashed book may still read `active` for ≤60s — consistent with the revoke-lag contract, acceptable).
- New helper `(Access) Active() bool { return a.Lifecycle == "active" }`.

### D3 — glossary helper rewrite (the 2 chokepoints)
Both helpers gain an explicit `need GrantLevel` and enforce the lifecycle gate for **edit|manage** (reads are allowed on a trashed book):

```
// HTTP path — replaces verifyBookOwner. Writes the right error + returns false on deny.
func (s *Server) requireGrant(w, ctx, bookID, userID uuid.UUID, need grantclient.GrantLevel) bool
//   access,err := s.grantClient.ResolveAccess(ctx, bookID, userID)
//   err==ErrUnavailable      → 503 GLOSS_UPSTREAM_UNAVAILABLE
//   !access.Level.AtLeast(need) → 403 GLOSS_FORBIDDEN   (uniform; not-found also lands here as none)
//   need>=edit && !access.Active() → 409 GLOSS_BOOK_INVALID_LIFECYCLE
//   else true

// MCP/context path — replaces checkBookOwnership. Returns sentinel errors.
func (s *Server) checkGrant(ctx, bookID, userID uuid.UUID, need grantclient.GrantLevel) error
//   ErrBookUnavailable (unavail) | ErrNotAccessible (under-grant) | ErrBookInactive (need>=edit && !active) | nil
```
- `s.grantClient` wired in `NewServer` from `cfg.BookServiceURL` + `cfg.InternalServiceToken` (both already exist; that's what `fetchBookProjection` uses).
- **Delete** glossary's `ownerCache`/`ownerCacheEntry`/`checkBookOwnership` body + `verifyBookOwner` body — caching now lives in `grantclient`. `fetchBookProjection` stays (still used for wiki_settings/chapters, non-ownership).
- **404 semantics:** old `verifyBookOwner` returned a distinct 404 for missing book; the grant model collapses missing→`none`→**403** (no existence oracle, matches E0-0 R4). This is an intentional contract change; documented.

### D4 — per-site `need` mapping (the security crux)
Default-deny: any site not explicitly mapped → **manage**. Full table:

| need | sites |
|---|---|
| **view** | listEntities, getEntityDetail, listEntityNames, listChapterLinks, listEntityEvidences, exportGlossary, entity revisions list/get, listEntityTrash (recycle-bin list), listMergeCandidates, listWikiArticles, getWikiArticle, listWikiRevisions, getWikiRevision, listWikiSuggestions, getWikiGenJobStatus, **listGenres**, MCP `toolSearch`, MCP `toolGetEntity` |
| **edit** | createEntity, patchEntity, pinEntity, createChapterLink, updateChapterLink, **deleteChapterLink** (PO: child-delete=edit), patchAttributeValue, createTranslation, updateTranslation, **deleteTranslation** (PO), createEvidence, updateEvidence, **deleteEvidence** (PO), applyEntityEdit, restoreEntity (recycle restore), dismissMergeCandidate, createWikiArticle, patchWikiArticle, restoreWikiRevision, generateWikiStubs, reviewWikiSuggestion, wiki-job **resume**, **createGenre**, **patchGenre**, MCP `toolProposeNewEntity` |
| **manage** | deleteEntity (soft-delete), purgeEntity (recycle-bin permanent), mergeEntities, deleteWikiArticle, wiki-job **cancel**, schema `confirmSchema`, MCP `toolProposeNewKind`, MCP `toolProposeNewAttribute`, **deleteGenre** |

Notes:
- **Schema propose (MCP) = manage:** proposing a kind/attribute begins a structural schema change; gating the proposal (not just the confirm) stops a mere editor from minting confirm-tokens. `confirmSchema` is independently manage.
- **wiki-job resume vs cancel** share `wiki_jobs.go` — confirm they are separate handlers in BUILD; resume=edit, cancel=manage.
- **genres (4 handlers) — NEW checks** (currently `requireUserID`-only = IDOR): list→view, create/patch→edit, delete→manage.

### D5 — call-site migration shape
Each site currently:
```
if !s.verifyBookOwner(w, r.Context(), bookID, userID) { return }
```
becomes:
```
if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) { return }   // or GrantEdit / GrantManage
```
MCP sites: `if err := s.checkBookOwnership(ctx, …)` → `s.checkGrant(ctx, …, grantclient.GrantEdit)`; error-mapping switch extended for `ErrBookInactive` (where edit/manage).

### D6 — go.mod wiring
glossary `go.mod`: add `require github.com/loreweave/grantclient v0.1.0` + `replace … => ../../sdks/go/grantclient`.

## Test strategy
- **book-service:** extend `/access` unit tests — response includes `lifecycle_state`; bad-id paths unchanged.
- **grantclient:** `ResolveAccess` returns level+lifecycle; `Active()`; cache stores lifecycle; `ResolveGrant` wrapper still returns level.
- **glossary unit:** `requireGrant`/`checkGrant` — deny ladder (unavailable→503, under-grant→403, inactive+edit→409, view-on-trashed→allowed); genres now 403 a non-grantee. Rewire `ownership_test.go`.
- **Live-smoke (D-E0-LIVE-SMOKE, the hard gate):** grant B `edit` → B edits an entity → owner revokes → B denied ≤60s; B with `view` cannot create; trashed book → edit 409 but read OK. Across book-service + glossary on a real stack.

## Risks
- **R-need-mapping** (HIGH): a destructive op mis-mapped to a lower tier. Mitigation: the explicit table above (reviewed), default-deny→manage, and the manage-tier set is the audited destructive list.
- **R-404-contract** (LOW): missing-book now 403 not 404 for glossary book-scoped routes. Intentional (anti-oracle); note for FE (it already treats 403/404 as "no access").
- **R-access-cache-lifecycle** (LOW): 60s lifecycle staleness — a just-trashed book allows edits ≤60s. Same window as revoke-lag; accepted.
