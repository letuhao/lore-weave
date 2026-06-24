# Tenant-Isolation / IDOR Sweep — Findings

- **Date:** 2026-06-20 · **Status:** ✅ COMPLETE (first sweep)
- **Method:** 6 parallel audit agents over ~22 user-data services + a NOT-APPLICABLE confirmation pass on 18 infra/ops services. Read-only; **no code modified.**
- **Source:** [gap-analysis](../../specs/2026-06-20-platform-ai-architecture-gap-analysis.md) §11 Task 1 (P0, XL).

> ⚠️ This is a first-sweep audit (breadth over exhaustive proof). Findings are grounded in `file:line` evidence but each should be confirmed + fixed under the normal workflow (failing test → fix → re-verify). Nothing here is fixed yet.

---

## 1. Headline

The tenancy *architecture* is sound and, in places, **exemplary** (book-service `authBook`, knowledge-service `assert_user_id_param`, usage-billing money paths, the envelope-not-LLM identity discipline). The famous **`entity_kinds` shared-mutable bug is substantively fixed.** But the sweep found **2 Critical + ~10 live High** cross-tenant defects — concentrated in **book-service media/audio handlers**, two **unauthenticated endpoint trees** (auth-service `/internal/users/*`, statistics-service `/v1/stats/*`), and a known-but-undeferred-visible translation-settings issue.

**The single recurring root cause is not bad architecture — it's an established guard not applied + a missing cross-tenant deny-test** (the exact `e0-grant-mapping-test-pattern` lesson). Every High below is "the correct pattern exists elsewhere in the same service; it just wasn't used here, and no deny-test caught it."

### Severity rollup
| Sev | Count | Where |
|---|---|---|
| 🔴 **Critical** | 2 | book-service F3, F7 (cross-tenant destructive delete: DB rows + MinIO objects) |
| 🟠 **High (live)** | 10 | book-service F1/F2/F4/F5/F6/F8 · auth-service F9 · statistics ST1/ST2 · translation F1 |
| 🟠 **High (latent)** | 2 | game-server F1/F2 (WS edge — no live resource yet; hard gate for V1) |
| 🟡 **Medium** | ~9 | auth F11 · statistics ST3 · provider PR1 · translation F2 · video-gen F3 · notification N1 · glossary F2/F3 · knowledge KS-1 · game-server F3/F4 · campaign C1 |
| ⚪ **Low / Info** | ~8 | auth F10/F12 · provider PR2/PR3 · video-gen F4 · glossary F1/F4/F5 · knowledge KS-2 · chat CS-1 · campaign C2 |
| 🔵 **Unverified high-risk surface** | 1 | A6-L5 per-PC retrieval filter — read-side consumer not yet built; **next audit target** |

---

## 2. Critical & High — the actionable cluster

### book-service — FINDINGS(8), incl. both Criticals
**Root cause:** `chapter_audio_segments` and `block_media_versions` have only `chapter_id` FK (no `book_id` column — `migrate.go:137,156`). The media/audio handlers call `authBook(bookID, need)` on the **URL book** but then read/write/delete child rows keyed by the **URL `chapter_id`** that is *never re-tied to the authorized book*. A user holding the stated grant on **any** book (e.g. their own) can act on another tenant's audio/media by supplying the victim's `chapter_id`/`segment_id`/`version_id`. The sibling upload handlers DO carry the `chapters WHERE id=$chapter AND book_id=$book` guard — it was simply omitted here.

| # | Sev | Handler | file:line | Effect |
|---|---|---|---|---|
| F3 | 🔴 Crit | `deleteAudioSegments` | `audio.go:141-202` | cross-tenant **delete** of audio rows + MinIO blobs (`manage` checked on wrong book) |
| F7 | 🔴 Crit | `deleteMediaVersion` | `media.go:297-328` | cross-tenant **delete** of media version row + MinIO object |
| F1 | 🟠 High | `getAudioSegment` | `audio.go:105-137` | cross-tenant audio read |
| F2 | 🟠 High | `listAudioSegments` | `audio.go:57-101` | cross-tenant audio listing |
| F4 | 🟠 High | `generateAudio` | `audio.go:257-527` | cross-tenant audio write + destructive prior-segment delete |
| F5 | 🟠 High | `listMediaVersions` | `media.go:175-234` | cross-tenant media read (download URLs) |
| F6 | 🟠 High | `createMediaVersion` | `media.go:238-293` | cross-tenant media write |
| F8 | 🟠 High | `generateChapterMedia` | `media.go:381-553` | cross-tenant media write (victim's chapter) |

*Mitigant:* the ids are server-generated UUIDs (not enumerable) — but they leak via shared links, logs, exports, the catalog, or a revoked-but-once-trusted collaborator. **Fix shape (not applied):** add `JOIN chapters c ON c.id = X.chapter_id WHERE c.book_id = $book` (or the existing `EXISTS` guard) to every media/audio query; add cross-tenant deny-tests.

### auth-service — F9 (High)
`/internal/users/{user_id}/profile` and `/internal/users/by-email` mount with **no `requireInternalToken` middleware** (the adjacent admin subtree has it) — `server.go:65-69` + `handlers.go:1130-1189`. Anything reaching the port dumps any user's profile/email; `by-email` is a PII + existence oracle. A test (`users_internal_pg_test.go:42-65`) **codifies the unauthenticated behavior as correct** (F11, Medium) — so the gap passes CI. *(Self-service handlers are otherwise IDOR-proof — they derive `uid` from `claims.Subject`, the pattern others should copy.)*

### statistics-service — ST1/ST2 (High)
The entire `/v1/stats/*` tree mounts with **zero auth middleware** (`server.go:64-75`); the gateway injects no identity. Leaderboards are legitimately public, but `/v1/stats/authors|translators/{user_id}` and `/v1/stats/books/{book_id}` (+ 30-day `daily_book_rollups`) read the id straight from the URL — **any unauthenticated caller can enumerate any author's private engagement analytics and any book's daily traffic timeseries.** **Product decision required:** world-readable by design, or owner-only? If owner-only → real cross-tenant leak needing gateway auth + owner/grant filter. ST3 (Medium): `/internal/voice-stats/{user_id}` trusts caller-supplied `user_id`.

### translation-service — F1 (High, already deferred)
`book_translation_settings` PRIMARY KEY = `book_id` only; the PUT does `ON CONFLICT (book_id) DO UPDATE SET ... owner_user_id = $caller` (`settings.py:160-176`) while the read filters `WHERE book_id AND owner_user_id` (`effective_settings.py:76`). A collaborator with E0 **EDIT** flips the shared row's `owner_user_id` to themselves → the original owner's lookup misses → silently falls back to defaults. Already tracked as **`D-E0-4A-SETTINGS-PERUSER`** (fix = composite PK `(book_id, owner_user_id)`); confirmed real, surfaced for visibility. F2 (Medium): no VIEW-grantee deny-test.

---

## 3. Medium / Low (grouped)
- **provider-registry (sensitive — but no secret leaks on public routes):** PR1 (Med) `getModelContextWindow` unauthenticated + not owner-scoped, on the public `/v1` tree (`server.go:2453-2505`). PR2 (Low) `getInternalModelInfo` missing `owner_user_id`. PR3 (Low, by-design) internal endpoints decrypt any user's BYOK secret by caller-supplied `user_id` behind the internal token — blast radius if the token leaks.
- **video-gen:** F3 (Med) missing cross-user poll deny-test; F4 (Low) public-read bucket — generated media are permanent unauthenticated world-readable URLs protected only by UUIDv4 unguessability.
- **notification:** N1 (Med) code correct, but no cross-tenant deny-test on the 5 public handlers.
- **glossary:** F2 (Med, latent) `entity_kind_aliases` is a bare global `UNIQUE` namespace (no scope) — read-only today, **becomes Critical the day the SS-7 bulk-merge writer is wired to it**; F3 (Med, by-design) `/internal` select trusts caller `user_id` (SQL is book-scoped, so no cross-book leak). F1/F4/F5 Low/defense-in-depth.
- **knowledge:** KS-1 (Med) graph routes are owner-only and skip the E0 grant dependency — *under*-permissive (collaborator gets empty), not a leak. KS-2 (Low) unvalidated `project_id` tag, safe because all reads re-scope on `user_id`.
- **chat:** CS-1 (Low-Med, by-design) `/internal /turns/{message_id}/text` is internal-token-gated but tenant-unscoped. CS-2: glossary MCP tools take LLM-supplied `book_id` — **enforcement confirmed present in glossary-service** (the glossary agent verified every MCP tool runs `checkGrant`).
- **campaign:** C1 (Med, weak-test) isolation depends on `authorize_book` getting the campaign's *own* `book_id`; no test pins that. C2 (Low, deferred `D-E0-4B-LIST-CROSSBOOK-SHARED`).
- **auth:** F10 (Low) profile read returns soft-deleted accounts; F12 (Low/info) public follower graph — confirm intentional.

---

## 4. Latent — gated on unbuilt surface (game-server WS edge, PRR-20)
EchoRoom is a V0 echo placeholder; the real player handlers don't exist yet, so these are **latent, not live** — but they are **hard gates for V1's first real room** and align with the open **`D-GAME-WS-EDGE-CONTROLS`**:
- **F1 (High-latent)** ticket carries `allowedRealities` (`auth.ts:84-86`) but `onAuth`/`onJoin` never checks the joined reality/session against it (`EchoRoom.ts:111-197`).
- **F2 (High-latent)** no per-message scope/membership re-check (`EchoRoom.ts:160-174`).
- **F3 (Med)** connection cap is per-replica with a check→reserve TOCTOU; **F4 (Med)** join/leave/auth-fail audited only to stdout (`D-WS-AUDIT-EVENT-STREAM`).
*(The prod edge controls that DO exist are sound: atomic single-use ticket redemption, fail-closed prod gate, no anonymous socket, constant-time compare.)*

---

## 5. 🔵 Unverified high-risk surface — audit next
**A6-L5 per-PC retrieval isolation** (the cross-PC spoiler/leak defense): the design requires the `pc_id` + timeline-cutoff filter to live **in the retrieval query, not the prompt**. world-service only *writes* the embedding column — it contains no read-side similarity SELECT. **The retrieval consumer that runs that SELECT is not yet built/identified**, so this — the single highest-risk MMO isolation surface — could not be verified. **Make it the first audit target once roleplay-service (or whichever consumer owns retrieval) exists.**

---

## 6. Coverage — clean & not-applicable (audit completeness)
- **CLEAN (strong isolation, capture as reference patterns):** sharing-service · catalog-service · composition-service · lore-enrichment-service · jobs-service · learning-service · **usage-billing-service** (money paths tenant-clean) · world-service (internal worker, no user HTTP surface) · tilemap-service · campaign-service (2 minor).
- **Exemplary patterns worth propagating:** book-service `authBook` grant chokepoint (default-deny, no existence oracle, fail-closed) · knowledge-service `assert_user_id_param` runtime Cypher guard · auth-service self-service `claims.Subject`-only identity · the `/internal` + M4 owner-re-verification posture used by composition/translation/enrichment/video-gen/usage-billing.
- **NOT-APPLICABLE (confirmed system-only, no user-resource handler):** publisher · meta-outbox-relay · meta-worker · migration-orchestrator · admin-cli · worker-ai · worker-infra · alert-recorder · archive-worker · backup-scheduler · breach-notifier · canary-controller · incident-bot · integrity-checker · postmortem-bot · retention-worker · slo-budget-calculator · statuspage-updater. (travel-service: empty Cycle-0 scaffold.)

---

## 7. Cross-cutting themes
1. **Missing cross-tenant deny-tests are systemic** (auth F11, translation F2, video-gen F3, notification N1, campaign C1) — the exact `e0-grant-mapping-test-pattern` lesson. **A repo-wide "every owner/grant-scoped handler must have a non-owner-returns-404/403 test" lint/checklist would have caught most of these.**
2. **"Guard exists, not applied"** — the book-service cluster and auth F9 are not missing designs; they're places an established guard (the `chapter∈book` join, `requireInternalToken`) was skipped. A grep-style audit for handlers that take a child id without the parent-scope join would find the class.
3. **Unauthenticated trees mounted on `/v1`** (statistics `/v1/stats/*`, provider `getModelContextWindow`) — a gateway-edge "every `/v1` route asserts identity unless explicitly allowlisted public" check would close these.
4. **Latent-becomes-Critical scope keys** (glossary `entity_kind_aliases`, translation settings PK) — global `UNIQUE` without a scope column is the `entity_kinds` smell; safe only while read-only. Flag every such table before its writer lands.

## 8. Suggested priority (for a later fix session — not this one)
1. **book-service F3/F7 (Critical)** → then F1/F2/F4/F5/F6/F8 — one shared fix (the `chapter∈book` join) closes all 8.
2. **auth-service F9** → add `requireInternalToken` to `/internal/users/*` + flip the test to a deny-test (F11).
3. **statistics ST1/ST2** → PO decision (public vs owner-only) → gateway auth + owner/grant filter if owner-only.
4. **translation F1** → confirm `D-E0-4A-SETTINGS-PERUSER` on backlog (composite PK).
5. **provider PR1**, **notification N1**, **video-gen F3**, **glossary F2 (pre-SS-7)** → Medium batch.
6. **Systemic:** add the cross-tenant deny-test requirement + the `/v1`-asserts-identity edge check (themes 1 & 3).
7. **Audit A6-L5** once the retrieval consumer is built (§5).

> Suggested Deferred IDs to register when these enter the backlog: `D-BOOK-MEDIA-CHAPTER-SCOPE` (F1–F8), `D-AUTH-INTERNAL-USERS-UNGATED` (F9), `D-STATS-V1-NO-AUTH` (ST1/ST2), `D-KIND-ALIASES-TENANT-SCOPE` (glossary F2), plus the existing `D-E0-4A-SETTINGS-PERUSER`, `D-GAME-WS-EDGE-CONTROLS`, `D-WS-AUDIT-EVENT-STREAM`.
