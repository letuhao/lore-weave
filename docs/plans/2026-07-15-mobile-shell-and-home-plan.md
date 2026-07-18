# Mobile shell + platform home — IMPLEMENTATION PLAN

**Date:** 2026-07-15 · **Status:** ✅ SEALED (PLAN) · **Spec (SoT):** [`docs/specs/2026-07-15-mobile-shell-and-home.md`](../specs/2026-07-15-mobile-shell-and-home.md) (SEALED §9)
**Design drafts (visual SoT):** [`design-drafts/mobile-home/`](../../design-drafts/mobile-home/index.html) · [`design-drafts/work-assistant/mobile/`](../../design-drafts/work-assistant/mobile/index.html)
**Durable tracker (read on resume):** [`2026-07-15-mobile-shell-and-home-RUN-STATE.md`](2026-07-15-mobile-shell-and-home-RUN-STATE.md)

This plan turns the sealed spec into a slice-by-slice build. The spec decided *what* and *why* (D-MOB-1..4,
8 blockers, §9 seal). This plan decides *how, in what order, proven by what evidence* — and closes the two
items the seal left "open at PLAN" (H3, MB2). **Nothing in the spec is re-litigated here.**

---

## 0 · Size & shape

**Classification: XL** (13+ semantic changes across 6 slices; side-effects: 1 new table, 1 new BFF surface,
1 new push-delivery leg, a service-worker, an auth-redirect change). Per CLAUDE.md this is **one coherent
EFFORT / one continuous run**, not 6 tasks — checkpoints fall at **risk boundaries** (each slice's commit),
POST-REVIEW batched per shippable milestone (M1 alone ships; M4 ships the PWA; M5 ships push).

**Program shape:** a **frontend program with a thin BFF seam + one small push-delivery leg.** No new
microservice, no new domain schema. The one genuinely-new backend is M5's push leg on the *existing*
notification-service.

**Build order (from spec §4, dependencies locked):** `M0 → M1 → M2 → M3 → M4 → M5`.
`M2` depends on `M1` (Home hero consumes live assistant status). `M5` depends on `M4` (needs the SW).

---

## 1 · The two PLAN-open items — now RESOLVED & SEALED

The spec §9 left exactly two things "open at PLAN, not blockers". Both are engineer-decidable; resolved here.

### 1a · H3 — `push_topic → (category, subtype)` map (pin before M5)

The 5 design toggles do **not** 1:1 the 9 backend categories (verified in
[`category.go:29`](../../services/notification-service/internal/category/category.go#L29):
`translation · social · wiki · system · llm_job · mcp_approval · campaign · billing · assistant`).
"Weekly" and "End-of-day" are **both** the `assistant` category, split only by `message_key`
(`notif.assistant.<subtype>`). "Jobs" spans three categories. Sealed mapping:

| `push_topic` (FE toggle / pref key) | Backend `category` (+ `message_key` subtype) | Push default | Rationale |
|---|---|---|---|
| `assistant_weekly` | `assistant` where `message_key` ∈ `{notif.assistant.reflection*}` | **ON** | the proactive value; opt-out-able |
| `assistant_endofday` | `assistant` where `message_key` ∈ `{notif.assistant.proactive_checkin, .end_of_day}` | **ON** | same |
| `jobs` | `translation` ∪ `llm_job` ∪ `campaign` | **ON** | "your work finished" |
| `billing` | `billing` | **ON** | spend/quota is time-sensitive |
| `social` | `social` | **OFF** | low-signal; user opts in |
| `mcp_approval` | `mcp_approval` | **ON** | security-sensitive; a pending approval must reach the owner |
| `system` / `wiki` | `system`, `wiki` | in-app only (no push default) | informational; feed is enough |

- **Storage:** the push preference is keyed by **`push_topic`** (the 7 rows above), NOT raw category — this is
  the user-facing granularity the toggles show. The map above lives in **one place** (a Go table in
  notification-service `internal/prefs`, the pref SoT) and is the *only* translator category→topic.
- **Resolution at send time:** sender computes `push_topic` from `(category, message_key)` via this table →
  looks up the per-user `push_enabled` for that topic (default from the table when the user has no row) →
  fail-**closed** (H2). `assistant` rows with an unrecognised `message_key` fall back to `assistant_endofday`
  (the safer, on-by-default bucket) so a new subtype is never silently un-pushable.
- **Not a new closed-set arg on the wire** — `push_topic` is a server-internal enum; the FE toggle sends the
  same enum but it's validated server-side (Settings-Boundary: closed-set enum-validated on write).

### 1b · MB2 — home degrade timeout / cache numbers (tune under load later)

Spec §D-MOB-1 fixed the *contract* (allSettled, per-tile status, never blank); the numbers were left to PLAN.
Sealed starting values (all env-overridable ceilings, tune under real load — the *contract* is the invariant,
the numbers are not):

| Knob | Sealed value | Why |
|---|---|---|
| Per-source timeout | **800 ms** | a slow tile degrades to skeleton/last-known well within a snappy home paint |
| Total wall-clock cap | **2000 ms** | the page resolves in ≤2s even if two sources hang; late tiles fill via re-fetch |
| Per-user cache TTL | **45 s** | inside the RQ 30s staleTime band; absorbs a flaky downstream as stale-with-timestamp |
| Stale-serve max age | **5 min** | a downstream down >TTL still serves last-known (timestamped) rather than an empty tile |
| Source criticality | `assistant status` = **critical**; books/jobs/worlds = **optional** | a critical miss shows a retry affordance; an optional miss just hides its tile |

Cache store: **Redis** (already a platform dependency) keyed `home:v1:<owner_user_id>`; in-BFF LRU fallback if
Redis is unavailable (degrade, don't fail). One `/v1/home` ≈ 5 downstream calls → the TTL caps fan-out
amplification.

---

## 2 · Grounding — the fix-sites verified against code (not the doc)

Per the anti-laziness rule, every "buildable" claim below was checked against source this session:

| Slice | Fix-site (verified) | What's there today |
|---|---|---|
| M0 | [`DashboardLayout.tsx`](../../frontend/src/layouts/DashboardLayout.tsx) + `ChatLayout`/`EditorLayout`/`FullBleedLayout` | each already renders **one** `<Outlet/>`; chrome swap goes *inside* the layout (keep the Outlet) |
| M0 | [`useIsMobile.ts`](../../frontend/src/hooks/useIsMobile.ts) (767px, matchMedia, SSR-safe) + a **duplicate** in `features/knowledge/hooks/` | reuse the root one; **delete/re-export the dup** (one-name-one-concept) |
| M2 | [`assistant.controller.ts`](../../services/api-gateway-bff/src/assistant/assistant.controller.ts) | the exact fan-out pattern to mirror: validate JWT → derive `sub` → forward Bearer to public APIs |
| M4/MB4 | [`auth.tsx:128`](../../frontend/src/auth.tsx#L128) | `state={{ from: location.pathname }}` — **drops `?search`/`#hash`**; fix = full `location` |
| M5/B4 | [`consumer.go:313`](../../services/notification-service/internal/consumer/consumer.go#L313) | INSERT discards the CommandTag (`_, err :=`) — **the exactly-once fix site** |
| M5/H2 | [`consumer.go:303`](../../services/notification-service/internal/consumer/consumer.go#L303) | `prefs.Suppressed()` fails **open** — correct for in-app, must fail **closed** for push |
| M5/H3 | [`category.go`](../../services/notification-service/internal/category/category.go) + `prefs/prefs.go` | 9-category SoT + the one-bool pref; H3 map + `push_enabled` land here |
| M5 | (grep: no `PushManager`/`vapid`/`web-push` anywhere) | push is **all-new**; no legacy to reconcile |

---

## 3 · Slice-by-slice build plan

Each slice: **TDD** (failing test → impl → green) · **VERIFY** (pasted fresh output + the cross-service token
where it crosses services) · **cold `/review-impl`** (fix findings, re-verify) · **commit** (explicit pathspec,
never `-A`). A11y VERIFY is per-slice on M1/M2/M3 (M4 is the *consolidated* audit, not the first check).

### M0 · Mobile chrome + one-Outlet shell + bottom-tab nav + addressable Sheet — size M, deps —

**Goal:** the app renders a mobile bottom-tab chrome (Home · Create · **Assistant**(raised centre) · Library ·
You) under < 768px, a sidebar chrome above it, around a **single persistent `<Outlet/>`** — no route subtree
remount at the breakpoint.

**Build:**
1. Extract the current `Sidebar` chrome into `DesktopChrome` (thin — it *is* today's `DashboardLayout` body).
2. Add `MobileChrome.tsx`: bottom tab bar (safe-area insets, ≥44px targets, raised centre), a sheet host.
3. Refactor `DashboardLayout` (and `ChatLayout` — the assistant's layout) to: `useIsMobile()` picks
   **which chrome wraps the SAME `<Outlet/>`** (chrome-only swap). The other chrome's feature tree is never
   mounted (not CSS-hidden) → MB6/H2 (no double-SSE) satisfied by construction.
4. Reuse root `useIsMobile`; delete the `features/knowledge` duplicate (re-export from root).
5. `components/ui/Sheet.tsx` — the bottom-sheet primitive; **route-/searchparam-addressable** (`?sheet=today`)
   so a deep-link restores it and hardware Back closes the sheet (MB4 half-1).
6. Boundary hysteresis on the breakpoint (no thrash on a slow desktop-window drag).

**TDD / tests:** a resize across 767px (a) preserves a live mounted child + its state (render a probe child
holding state; assert same instance / state survives), (b) keeps **exactly one** subscription (spy an
effect-subscribe), (c) mounts exactly one chrome. Sheet: `?sheet=x` opens it; Back closes it not the route.

**VERIFY:** `pnpm -C frontend test` (M0 files) pasted green + `pnpm -C frontend tsc --noEmit` clean.
**Cross-service:** none (FE-only) → no live-smoke token required.
**Review:** cold `/review-impl` on the shell diff — focus MB1/MB6 (one SSE, no remount), a11y of the tab bar.

### M1 · Assistant mobile views (the 13-screen draft) — size L, deps M0

**Goal:** every assistant surface from the draft, as **mobile views bound to the EXISTING assistant hooks**
(the reuse thesis, proven on the hardest surface). Views only; zero new logic/state/api.

**Screens → reused controller (verbatim):**
Home/chat → chat hooks + `useCaptureRail`; voice → the voice stream hook (MB7 matrix applies); today sheet →
`useCaptureRail`; end-of-day + keep-all/budget → `useEndOfDay`; recall → chat recall; journal timeline+entry →
diary-entries hook; correct/forget → the D17 correct/forget hooks; weekly + dismiss chips → `useReflection`
(R1); practice + scorecard → `useScorecards` (R2, **SD-7 quarantine badge carried verbatim**); "what I know" →
knowledge entities/facts + forget; You&data → prefs + `DELETE /v1/assistant/data`.

**Build:** `features/assistant/components/mobile/*` — one view per screen, each ≤100 lines (split if larger),
consuming the hook's return. No `useEffect` for user actions (callback handlers). Both themes, reduced-motion,
tap-alt for every swipe (End-my-day is a **visible button**, not a buried gesture — draft rev.2 fix).

**TDD / tests:** per view — renders from a mocked hook return; the primary action calls the hook's callback;
SD-7 quarantine badge present on the scorecard view; consent toggle **defaults OFF** (draft rev.2 fix — matches
the fail-closed guarantee). A11y assertions (roles, labels, target size) inline per view.

**VERIFY:** `pnpm -C frontend test` (M1 files) pasted green + tsc. A11y VERIFY (targets/labels/themes/
reduced-motion/tap-alt) enumerated. **Live-smoke (browser, cross-service via the reused hooks):** on the built
image / vite :5199, drive one real assistant loop on a phone viewport — capture → today sheet → end-of-day →
a diary entry renders; **one** SSE across a rotate (MB1/MB6 in the live DOM). (Playwright, per the mobile-web
recall recipe.)
**Review:** cold `/review-impl` — the reuse boundary (does any view re-implement logic that belongs in the
hook?), SD-7, consent-default, MVC (no logic in views).

### M2 · BFF `/v1/home` + Home dashboard + BFF `/v1/activity` + Activity feed — size L, deps M0, **M1**

**Goal:** the platform front door (hero assistant card + jump-back-in + launcher + recent) and the unified feed,
each backed by a new **read-only BFF aggregation** (no new truth, no write).

**Build — BE (`api-gateway-bff`, mirror the assistant controller):**
1. `GET /v1/home` — owner from JWT `sub` (SEC-1, never a body field). Fan out with **`Promise.allSettled`**,
   per-source **800 ms** timeout, **2 s** total cap; each tile → `{status: ok|degraded|empty, data|error}`.
   Sources: assistant status (**critical**), recent books, translation jobs, worlds/enrichment (**optional**).
   Short-TTL Redis cache (**45 s**, `home:v1:<owner>`), stale-serve ≤5 min timestamped. **Never blanks.**
2. `GET /v1/activity` — **single-store** keyset cursor over notification-service (the sealed feed SoT, MB3).
   `?cursor=&limit=`; `unread_count`; `POST /v1/activity/mark-all-read` (global-per-owner). **Verify (grep,
   not the doc)** every feed source the draft shows already emits a `notifications` row; **any that does not is
   buildable work — add the emit at that producer**, do NOT merge a second store at read time. (Enumerate the
   check in VERIFY; add emits as a sub-task if a gap is real.)
3. Per-lane usage tile on You reuses **B1** via a BFF proxy (no new billing surface).

**Build — FE:** the Home view + Activity view (both mobile-first), bound to a new `useHome`/`useActivity`
hook that calls the BFF routes; per-tile degrade UI (skeleton / last-known + quiet retry); the unread badge.

**TDD / tests:** BE — a down/slow source degrades **its tile only** (page still 200s, other tiles `ok`);
total-cap honoured (two hung sources → resolves ≤2s); owner derived from JWT not body; feed keyset has no
page-boundary dup/drop; mark-all-read is per-owner. FE — degrade states render; unread badge from the endpoint.

**VERIFY:** BFF jest + FE vitest pasted green + tsc. **Cross-service → live-smoke (PASTED, required):** on a
stack-up, `/v1/home` composes real assistant-status + a real book + a real job with the test account's JWT,
and one source killed degrades only its tile; `/v1/activity` pages a real notification set. **Rebuild stale
images first** (false-green rule).
**Review:** cold `/review-impl` — tenancy (owner from JWT on both), the degrade contract (does any path let one
source blank the page?), the single-store claim (no read-time merge), keyset correctness.

### M3 · Other-workshop mobile-viewable passes — size L, deps M0

**Goal:** read/continue (NOT compose) mobile views for Library (books + reading), Translate review, Worlds/
Explore browse, the All-apps drawer, You/account. Lighter than M1 (browse/continue, no authoring).

**Build:** mobile views bound to the existing library/translation-review/worlds/browse hooks. Novel-writing +
heavy world-building stay **desktop-first** (spec §9 #3) — mobile shows a "best on desktop" affordance, not a
broken squeeze. All-apps drawer = the launcher grouped by workshop. You/account = prefs + usage (B1) + privacy.

**TDD / tests:** each view renders from its hook; the "continue" action navigates; desktop-first surfaces show
the affordance, not a crippled editor.

**VERIFY:** vitest + tsc pasted green; a11y VERIFY per view. **Cross-service:** reuses existing hooks (already
smoked); browser spot-check on phone viewport for the drawer + one continue path.
**Review:** cold `/review-impl` — MVC, no desktop-only control leaking into a mobile view.

### M4 · PWA (manifest + SW + install) + consolidated a11y audit — size M, deps M1–M3

**Goal:** installable PWA (icon, splash, offline **shell** — not offline data), and the a11y audit as the
exit gate.

**Build:** Vite PWA plugin — web manifest + icon set + a service worker. **Workbox precache is
versioned/revisioned; `/v1/*` is NEVER cache-first (network-first)** (MB5). **No silent `skipWaiting`** — a
`waiting` SW surfaces a "new version — refresh" prompt applied on user action / next cold nav (MB5). Install
prompt (value-first, not day-one). The `:5174` baked nginx build serves it (rebuild the image).
**MB4 half-2 (fold in here):** fix `RequireAuth` to preserve the **full `location`** (not just `pathname`)
through login, and have `LoginPage` resume to it — so a cold deep-link `/entry/123?sheet=today` survives a
logged-out tap. **MB8:** proactive `refreshAccessToken()` on `visibilitychange`/resume **before** re-subscribing
SSE/voice (streams bypass the reactive-401 single-flight).

**TDD / tests:** manifest validates; SW registers; `/v1/*` is network-first (a cached stale API is never served
first); a `waiting` SW does not auto-activate; `RequireAuth` round-trips full location incl. `?search`/`#hash`
(MB4); resume triggers a refresh before re-subscribe (MB8, spy).

**VERIFY:** vitest + tsc + a Lighthouse/installability check pasted; the **consolidated a11y audit**
(Dynamic-Type, targets ≥44px, SR labels, both themes, reduced-motion, tap-alt) as the exit gate — enumerated
with evidence. **Cross-service:** MB4/MB8 touch auth flow → a browser smoke of a logged-out deep-link + a
background→foreground token refresh.
**Review:** cold `/review-impl` — MB5 (no cache-first `/v1`, no silent skipWaiting), MB4 (full-location), MB8.

### M5 · Push delivery (D-MOB-4) — size M, deps M4 (SW)

**Goal:** a **content-free** push reaches a **closed** phone. The one genuinely-new backend leg, additive to
notification-service. All 8 push blockers (§8) are build requirements, not options.

**Build — notification-service (Go):**
1. **Migration:** `push_subscriptions (owner_user_id, endpoint, keys, ua, created_at, last_success_at,
   fail_count)`, **`UNIQUE(owner_user_id, endpoint)`** (per-user scope key; endpoint = device key; upsert). Add
   `push_enabled`/channel dimension keyed by `push_topic` to the prefs substrate (H1).
2. **Routes:** `POST /v1/me/push-subscriptions` (**owner = JWT `sub` only**, H4, upsert on owner+endpoint),
   `DELETE /v1/me/push-subscriptions/{endpoint}` (sign-out teardown, B2), `GET /v1/push/vapid-public-key` (S2).
   Rate-limit register + send (H4).
3. **`PUSH_COPY` content-free CHOKEPOINT (B1 — load-bearing):** the payload is built **exclusively** from
   `(push_topic)` via a static per-topic i18n-string table; it **never reads** the row's `title`/`body`;
   `message_params` are allow-listed enum tokens only. **Unit test: the builder's output is a pure function of
   topic and does NOT reference title/body** (the only thing keeping PII off the lock screen for every producer).
4. **Sender (added to the consumer / a push dispatcher):**
   - **Exactly-once (B4):** enqueue a push **only when the INSERT actually happened** — capture the CommandTag
     at [`consumer.go:313`](../../services/notification-service/internal/consumer/consumer.go#L313)
     (`tag.RowsAffected()==1`); the existing `(user_id, dedup_key)` unique index makes push exactly-once under
     redelivery.
   - **410-prune (B3):** `404/410 Gone` on send → **hard-delete** that subscription (idempotent GC, the primary
     GC); `429/5xx` → backoff, keep. A periodic sweep drops rows failing N days.
   - **Fail-CLOSED push gate (H2):** unlike `Suppressed()` (fails open), a prefs-lookup error → **do NOT push**
     (the in-app row is already stored; nothing is lost).
   - **H3 topic resolution:** category+message_key → `push_topic` (the §1a table) → per-user `push_enabled`.
5. **VAPID (S2):** private key in **env** (service fails to start if missing — platform infra, not a user
   setting; **never `JWT_SECRET`**); public via the GET route.
6. **Teardown (B2):** an **account-deletion erasure-event consumer** → `DELETE … WHERE owner_user_id=$1`.
   Dies on **account-deletion + sign-out**, NOT on assistant-data erase.

**Build — FE:** SW push handler (`push` → `showNotification` from the content-free payload; `notificationclick`
→ auth-gated route via route-key + opaque id, S5); `PushManager.subscribe()`; **capability gate** (offer only
when SW+PushManager exist, perm ≠ denied; iOS also installed-PWA — else hide, show "Add to Home Screen", fall
back to in-app, S3); **value-first** prompt (S4); the toggle's displayed state = **effective** =
`AND(OS-permission, server-intent, live-subscription)` recomputed on mount + `visibilitychange`; `denied` →
disable + settings deep-link, never re-`requestPermission()` (S4).

**TDD / tests:** Go — PUSH_COPY is content-free (pure fn of topic, no title/body ref); exactly-once
(RowsAffected gate); 410 deletes / 429 keeps; fail-closed on prefs error; H3 topic map (assistant subtypes
split; unknown subtype → endofday bucket); account-deletion consumer deletes owner's rows; register derives
owner from JWT not body. FE — capability gate hides on unsupported/denied; effective-state recompute;
sign-out DELETE fires before JWT clear.

**VERIFY:** Go `go test ./...` (notification-service) + FE vitest pasted green. **Live-smoke (PASTED, the HARD
path — a mock does NOT satisfy it):** a real browser subscription receives a **VAPID push with the tab
CLOSED**, payload **content-free end-to-end** (assert 0 diary/PII text in the delivered notification); a 410
prunes; a sign-out DELETE removes the device. **Rebuild images first.**
**Review:** cold `/review-impl` — B1 (content-free chokepoint proven, not asserted), B4 (exactly-once at the
real fix site), B2 (teardown scope: not on assistant-erase), H2 (fail-closed), H4/tenancy, VAPID ≠ JWT_SECRET.

---

## 4 · Standards gate (per `/review-impl`, applied every slice)

| Standard | Where it bites | Slice |
|---|---|---|
| **Gateway invariant (I1)** | home/activity/push-register all through `api-gateway-bff`; no new public entry | M2, M5 |
| **Tenancy / User Boundaries** | owner from JWT `sub` on every aggregation + push register; `push_subscriptions` carries `owner_user_id` scope key; `UNIQUE(owner_user_id, endpoint)` (NOT a bare unique) | M2, M5 |
| **Settings & Config Boundary** | `push_enabled`/topic is **per-user server-SoT** (not env); VAPID private key IS env (platform infra ceiling); effective-value + source visible; closed-set `push_topic` enum-validated on write | M5 |
| **No hardcoded secrets** | VAPID private in env, fail-start if missing, **≠ `JWT_SECRET`** | M5 |
| **No provider/model/pricing touch** | pure aggregation; per-lane usage reuses B1; push is not an LLM call | M2, M5 |
| **FE MVC** | mobile views are **views only**; logic stays in reused hooks; **no conditional unmount across the breakpoint** (chrome-only swap) | M0–M3 |
| **Data persistence** | user data server-only; per-device UI state (tab/sheet, input-draft IndexedDB) MAY be local | M0, M4 |
| **SD-7** | scorecard on mobile is shown-never-trended, identical to desktop; quarantine badge carried | M1 |
| **Frontend-Tool Contract** | no new agent→GUI tool here; `push_topic` is a server enum, validated server-side | M5 |

---

## 5 · Risk register (parked with a gate, per the anti-defer-drift rule)

| ID | Item | Gate / trigger |
|---|---|---|
| R-MB-VOICE | MB7 voice-on-mobile-web full matrix (permission-denied, recorder.onerror, backgrounding, mime detect, length cap) | built **in M1** (voice is the front-door thesis) — not deferred; listed so it isn't dropped |
| R-MB-OFFLINE | MB9 offline input-draft persistence (IndexedDB) + "not sent yet" + offline banner | **medium** — build in M4 with the SW; a half-typed entry must survive a drop |
| R-MB-NATIVE | Capacitor wrap (native push / background / store) | **won't-build** unless a D-MOB-3 trigger fires (iOS push unreliable / store required / always-on voice). PWA-first stands. |
| R-MB-FEED-EMIT | a feed source the draft shows that does NOT yet emit a `notifications` row | **M2 VERIFY** enumerates the grep; a real gap → add the emit at that producer (buildable, in-scope), not a read-time merge |
| R-MB-TABLET | dedicated tablet chrome | **won't-build** v1 (phone-chrome-through-tablet, sealed §9); revisit post-launch |

---

## 6 · Definition of Done (the autonomous exit condition)

The program is DONE when **every slice M0–M5 is ✅-with-evidence** in the RUN-STATE board, meaning for each:
1. **Pasted fresh green tests** (the actual command output in the transcript — a claim of "passes" does not
   satisfy this).
2. **A pasted cross-service live-smoke** where the slice crosses services (M1 reuse-loop, M2 `/v1/home`+feed,
   M5 the **closed-tab content-free push** — the hard path, not a mock); or an explicit `live infra
   unavailable: <reason>` token where the full stack isn't bootable.
3. **A cold `/review-impl`** with findings triaged (HIGH fixed + re-verified; MED fixed-or-tracked; LOW
   tracked), pasted.
4. **Committed** with an explicit pathspec (never `-A`), SESSION_HANDOFF updated at each milestone boundary.

Shippable checkpoints (POST-REVIEW batched here): **M1** ("assistant is great on mobile"), **M4** (PWA), **M5**
(push). The R-MB-NATIVE + R-MB-TABLET parked rows stay parked with their gate; **SD-7 stays quarantine-tier**
(a committed QWK / "safety passing" is a drift violation, unchanged).

Bounded: if a slice hits a genuinely-external blocker (not "unbuilt" — see the anti-laziness rule), park it in
the RUN-STATE register with its gate and continue; stop-and-ask ONLY if a sealed decision turns out wrong, an
action risks real user data, or the SD-7 boundary is reached.
