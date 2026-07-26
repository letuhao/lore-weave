# Mobile shell + platform home — CLARIFY / spec

**Date:** 2026-07-15 · **Status:** ✅ SEALED (2-reviewer cold pass applied; §9) · **Type:** [FS] full-stack, but FE-heavy.
**Design drafts (the visual source of truth):**
- Platform home / super-app shell — [`design-drafts/mobile-home/index.html`](../../design-drafts/mobile-home/index.html)
- Work Assistant, full feature parity (13 screens, rev.3) — [`design-drafts/work-assistant/mobile/index.html`](../../design-drafts/work-assistant/mobile/index.html)

---

## 1 · Goal & framing

LoreWeave is a **super app** — one identity over several workshops (write · worlds · translate · explore ·
read · **assistant** · coaching). It has **no mobile design today** (the assistant home strip is literally
`md:block` — desktop-only). This spec turns the two approved mobile drafts into a shippable plan.

**Two product commitments (from the drafts, ratify at CLARIFY):**
1. **The Work Assistant is the mobile front door** — the hero card on Home and the **raised centre tab**.
   Journaling on the go is the thing a phone gets opened for.
2. **Redesign, not responsive squish** — mobile gets its own shell (bottom tabs, sheets, thumb-zone
   primaries), NOT the desktop three-column layout narrowed.

**Non-goals (this spec):** a native app (React Native), an offline-first editor, writing a full novel on a
phone (compose stays desktop-first — mobile is continue/review), and any NEW domain feature. The scorer
stays quarantine-tier (SD-7) on mobile exactly as on desktop.

---

## 2 · The two architecture decisions (the questions this spec answers)

### D-MOB-1 · Backend: **reuse existing domain BE; add ONLY a thin BFF aggregation.**
No new microservice, no new domain schema. Verified: every surface in both drafts maps to an endpoint that
already exists (see §3). The single new BE-ish piece is a **BFF composition layer** in `api-gateway-bff`
(NestJS) — the exact pattern the assistant *provision orchestrator* already uses (fan out to public service
APIs with the caller's JWT, compose the result). Two new BFF routes:

| New BFF route | Composes (all existing) | Why it's BFF, not domain |
|---|---|---|
| `GET /v1/home` | assistant status (chat capture count / proactive-enabled + a pending reflection), + "jump back in": recent **books** (book-service last-updated), **translation jobs** (jobs/translation status), **worlds/enrichment** (glossary/knowledge), each owner-scoped | pure read-composition across services; no new truth, no write |
| `GET /v1/activity` | the unified feed — **notification-service** (already the platform's notification home; R3 added the `assistant` category) + optionally jobs terminal events | notification-service already aggregates; the BFF just shapes + paginates for mobile |

- **Tenancy:** both routes derive the owner from the JWT `sub` (SEC-1), never a client field — same as the
  assistant controller. Every composed read is already owner-scoped server-side.
- **Gateway invariant:** all of it goes through `api-gateway-bff` (I1). No new public entry point.
- **Optional tiny state:** a per-user "pinned workshops / last-active order" is a **preference**
  (`/v1/me/preferences`, existing) — NOT a new table. Settings-Boundary: per-user, server-SoT.
- **No provider/model/pricing touch** — aggregation only. Per-lane usage on the You screen reuses **B1**
  (`GET /internal/billing/usage/by-lane`, shipped) via a BFF proxy.
- **`/v1/home` degrade contract (cold-review B3, blocker) — the front door must NEVER blank.** Fan out with
  `Promise.allSettled` under a **per-source timeout (~800ms)** and a **total wall-clock cap (~2s)**; each tile
  returns `{status: ok|degraded|empty, data|error}`. A slow/down service degrades **its tile only** (skeleton
  / last-known + a quiet retry), never the page. Classify sources **critical** (assistant status) vs
  **optional** (worlds). Add a short-TTL per-user cache (~30–60s, Redis/in-BFF) so a flaky downstream serves
  stale-with-timestamp and foreground re-fetches don't multiply fan-out (1 home ≈ 5 downstream calls/user).
- **`/v1/activity` source model (cold-review B2, blocker) — ONE feed SoT, not a read-time merge.** Decision:
  **notification-service is the single feed store.** VERIFY (grep, don't trust the doc) that every source the
  draft shows — jobs-terminal, book "draft saved", billing "lane near cap", social follows, knowledge
  enrichment — already emits a `notifications` row; **any that does not is buildable work (add the emit at the
  producer), NOT a reason to merge two stores at read time.** The feed is then a clean keyset cursor over one
  owner-scoped table (no cross-store page-boundary dup/drop). Pin: "mark all read" is global-per-owner; the
  topbar unread badge is `count(unread)` from that one endpoint.

### D-MOB-2 · Frontend: **one FE (the current app); a mobile VIEW layer over the existing controllers. PWA-first.**
Not a separate app, not a `md:hidden` squish. The codebase's **MVC rule is the enabling fact**: hooks own
logic + state, components only render. So the mobile screens are **new views bound to the SAME hooks/api/
context** — the assistant's `useReflection`, `useScorecards`, `useTimezone`, `useEndOfDay`, `useCaptureRail`,
`useDiaryFactInbox`, the chat hooks, `useSessions`, etc. are reused verbatim; only the JSX changes.

```
frontend/src/
  app/
    shell/
      MobileChrome.tsx       ← NEW: bottom tab bar (raised centre = Assistant), safe-area, sheet host
      DesktopChrome.tsx      ← the current Sidebar + PageHeader, extracted
      AppShell.tsx           ← renders ONE persistent <Outlet/>; useIsMobile picks which CHROME wraps it
                                (chrome-only swap — never a shell ternary that remounts children)
    routes.tsx               ← same routes, mounted once; only the chrome differs by viewport
  features/<name>/
    hooks/ · api.ts · context/   ← REUSED unchanged (the controllers)
    components/mobile/       ← NEW mobile views (the drafts), e.g. assistant/components/mobile/*
    components/              ← existing desktop views stay
  components/ui/Sheet.tsx    ← NEW: the bottom-sheet primitive the drafts lean on (today panel, etc.)
```

- **Viewport strategy — chrome-only swap, NOT a shell ternary (cold-review B1, blocker fixed).** The earlier
  "pick the shell at the top" sketch WAS the remount bug this rule forbids: a top-level
  `<MobileShell> : <DesktopShell>` ternary re-instantiates the **entire route subtree** at the breakpoint,
  killing the chat SSE stream, voice `AudioContext`/`MediaRecorder`, and any unsaved text on a tablet rotate
  or a desktop-window drag. Correct design: the feature route tree is mounted **once** under a single
  persistent `<Outlet/>`; `AppShell` swaps only the **chrome** (bottom tabs vs sidebar) around it. Exactly
  one chrome's feature tree is ever live — the other chrome is inert, never CSS-hidden-but-mounted (kills the
  double-SSE / double-`proactive-turn` bug, cold-review H2). **Reuse the EXISTING
  `frontend/src/hooks/useIsMobile.ts`** (matchMedia, SSR-safe, 767px) — do NOT add a parallel `useViewport`
  (one-name-one-concept); extend it if a tablet band is needed. Add boundary hysteresis so a slow drag
  doesn't thrash. **Test:** a resize across the breakpoint preserves a live chat stream + a half-typed input,
  and keeps exactly ONE SSE subscription.
- **PWA-first:** add a web manifest + a service worker (Vite PWA plugin) → installable, app-icon, splash,
  offline shell. The `:5174` baked nginx build serves it. Native (Capacitor wrapping the PWA, or RN) is a
  **later** decision, out of scope here.
- **Server is SoT** everywhere; per-device-only UI state (which tab, sheet open) MAY use localStorage; user
  data never does (existing rule).
- **A11y carried from the drafts' review:** ≥44px targets, real `<button>`/`<input>`, aria-labels on icon
  controls, rem/Dynamic-Type, both themes, reduced-motion, a tap alternative for every swipe.

---

### D-MOB-3 · "Long-running app" on the browser — **PWA is sufficient, because the long work is server-side.**
The key realization: **this app's long-running work does NOT run in the browser.** The distiller, the weekly
reflection, the proactive check-in, catch-up sweeps — all run on the **backend** (`worker-ai`,
`scheduler-service`, the reflection/distill consumers). The phone is a **thin client**. So we never need the
browser to "run long" in the background — a thing browsers correctly forbid.

| Client need | Web/PWA answer | Caveat |
|---|---|---|
| **Receive the proactive check-in when the app is CLOSED** (R3) | ✅ **Web Push API + Service Worker** — a server push wakes the SW and shows a notification with the tab closed | **iOS**: only for a PWA **added to the Home Screen**, iOS **16.4+**. Android/Chrome: full support. This is the one real constraint. |
| **Long foreground session** (a long chat / voice turn) | ✅ Normal web — SSE/WebSocket streams, `MediaRecorder`/Web Audio for voice | none |
| **Retry a queued action after connectivity returns** | ✅ Background Sync API (Chrome) / an IndexedDB outbox | iOS support weak; not core (server-SoT + online-first) |
| **Arbitrary background JS / guaranteed periodic wakeups / always-on background audio** | ❌ Not a web capability | …and **not needed** — the backend does the periodic work; the client just receives a push |

**Decision: PWA-first.** It covers every real need because the heavy lifting is already server-side and the
only closed-app client need — a content-free push — is a supported PWA capability. **Escape hatch (not a
rewrite):** if iOS push reliability proves insufficient, app-store distribution is required, or *always-on
background voice* ever becomes a product goal, wrap the **same web codebase in Capacitor** to get native
push + background modes + store presence. **Flutter / React Native are explicitly NOT chosen** — they are a
full rewrite of every view for a background capability this architecture doesn't require. Revisit only if
one of those three triggers fires.

### D-MOB-4 · Notifications: **yes — and PUSH delivery is the one genuinely-new BE leg mobile needs.**
Two layers, and only the second is missing:

| Layer | State today | Mobile role |
|---|---|---|
| **In-app** — a stored notification + a bell/feed | ✅ **Exists**: `notification-service` (rows, per-category opt-out) + FE `useNotificationStream` (SSE while the app is OPEN) | becomes the **Activity feed** (draft screen 2) |
| **Push** — a buzz on the device when the app is CLOSED | ❌ **Missing entirely** — no Web Push / VAPID / device tokens / service worker anywhere | the delivery channel for the proactive check-in + finished jobs |

**Why it's needed, not optional:** the whole value of a *proactive* assistant is that it reaches you when
you are **not** in the app (the weekly reflection, a finished translation). R3 (D-PROACTIVE-DELIVERY) built
the notification *emission* — a content-free row — but on a phone that row only surfaces if the user opens
the app (SSE), which is the exact "only if they open it" problem R3 set out to solve. **Push completes R3's
delivery half for a closed app.** This is also why D-MOB-3 works: the server does the long work, and push is
how the closed thin-client hears about it.

**What push delivery requires (additive to notification-service, NOT a new service). The cold review made
these non-negotiable — details + rationale in §8:**
1. **FE:** a service worker (part of the PWA, M4) + `PushManager.subscribe()` + a **capability gate** (offer
   push only when SW+PushManager exist and permission ≠ denied; on iOS also require an installed PWA — else
   hide the ask and fall back to in-app, §8-S3) + a **value-first** prompt (after value, never day-one, §8-S4).
2. **Registration + storage:** `POST /v1/me/push-subscriptions` — **owner from JWT `sub` only** (never a body
   field, §8-H4) — into a `push_subscriptions` table `(owner_user_id, endpoint, keys, ua, created_at,
   last_success_at, fail_count)`, `UNIQUE(owner_user_id, endpoint)` **upsert** (the endpoint IS the device key;
   multi-device = multiple endpoints, §8-S1). Per-user scope key (User Boundaries).
3. **The content-free CHOKEPOINT (blocker §8-B1) — the load-bearing fix.** ⚠ `redact.Body()` is a *secret*
   scrubber, **not** a PII/content scrubber (its own doc: it does not touch names/emails) — so the stored
   `title`/`body` legitimately carry names/PII. The push payload is therefore built **exclusively from
   `(category, message_key)` via a static per-category `PUSH_COPY` table of fixed i18n strings** — it NEVER
   reads the row's `title`/`body`, and `message_params` are allow-listed enum tokens only (no free-text).
   A unit test asserts the builder's output is a **pure function of category** and does not reference
   title/body. This is the only thing that keeps diary/PII text off the lock screen for **every** producer.
4. **The sender is idempotent + prunes + fails closed:**
   - **Exactly-once (blocker §8-B4):** enqueue a push ONLY when the row INSERT actually happened
     (`tag.RowsAffected()==1`); the existing `(user_id, dedup_key)` unique index then makes push exactly-once
     under AMQP redelivery. (Today the consumer discards the CommandTag — that's the fix site.)
   - **410-prune (blocker §8-B3):** on send, a `404/410 Gone` from the push service **hard-deletes** that
     subscription row (idempotent GC); `429/5xx` → backoff, don't delete. A periodic sweep drops rows failing
     for N days. This is the PRIMARY garbage-collector.
   - **Fail-CLOSED suppression (§8-H2):** the existing `Suppressed()` fails **open** (fine for an in-app row);
     the PUSH gate must fail **closed** — a prefs lookup error → do NOT push (the in-app row is already
     stored, nothing is lost). Plus a **push-channel preference** — `notification_preferences` is one `enabled`
     bool today with no in-app-vs-push dimension; add a `push_enabled` (or `channel`) so "in the feed but no
     buzz" is expressible (§8-H1).
5. **Teardown (blocker §8-B2) — no stray buzzes on a lost phone.** No cross-DB FK is possible (notification-
   service owns its DB). So: (a) the FE calls `DELETE /v1/me/push-subscriptions/{endpoint}` **on sign-out,
   before clearing the JWT**; (b) **account deletion** emits an erasure event a **new notification-service
   consumer** turns into `DELETE … WHERE owner_user_id=$1`. Subscriptions die on **account-deletion + sign-out**,
   **NOT** on assistant-data erase (a user erasing their diary still wants translation-job buzzes) — the
   design screen-7 copy is corrected to "Signing out removes this device."
6. **VAPID config (§8-S2):** private key in **env** (service fails to start if missing — platform infra, not a
   user setting); public key served via `GET /v1/push/vapid-public-key` (it is meant to be public). Rotation
   invalidates all subscriptions → forces a global re-subscribe (the 410-prune absorbs it); rotate rarely.

This is the one place "no new domain BE" bends: a **new delivery leg + one small table + one config + one
erasure-consumer binding** on the *existing* notification-service — not a new microservice. Everything else in
this spec is still pure reuse/aggregation.

---

## 3 · Surface → existing-endpoint map (the proof that no new domain BE is needed)

| Mobile surface (drafts) | Existing API | Session ref |
|---|---|---|
| Chat (talk) | chat-service stream + sessions (`createSession`, SSE) | shipped |
| Capture rail / "today so far" | knowledge capture-decision + `useCaptureRail` | WS-1.6 |
| Consent toggle | `PUT /v1/knowledge/projects/{id}/capture-consent` | A2 |
| Voice | voice stream + STT/TTS (provider-registry) | WS-4.x |
| End-of-day distill + entry | `POST /v1/assistant/end-day` → distill; `listDiaryEntries` | A1 / WS-1.8 |
| Fact inbox (keep/remove) | `/v1/knowledge/pending-facts` confirm/reject | WS-2.5 |
| Recall / search | chat `run_chat_search_sessions` (recall-by-asking) | WS-1.9 |
| Journal timeline + entry | book-service diary entries (kind='diary', private-locked) | WS-1.10 / egress locks |
| Correct an entry / forget person | `POST /v1/assistant/correct` · `/forget` (D17 cascade) | WS-2.6 |
| Weekly reflection + dismissable patterns | `/v1/assistant/reflection-patterns` (GET) + `/reflection-dismiss` | **R1** |
| Coaching practice → scorecard | evaluate + `GET /v1/assistant/scorecards` (quarantine) | **R2** |
| Proactive check-in → lock-screen notif | `/assistant/proactive-turn` + notification-service (content-free) | **R3** |
| Time-zone confirm | `prefs.timezone` via `/v1/me/preferences` | **F2** |
| "What I know" memory | knowledge entities/facts read + forget | Ph2 |
| Erase everything | `DELETE /v1/assistant/data` (crypto-shred) | D-R27 / P4 |
| Per-lane usage (You) | `GET /internal/billing/usage/by-lane` (BFF proxy) | **B1** |
| Home "jump back in" + activity feed | **NEW BFF aggregation** (`/v1/home`, `/v1/activity`) over the above | this spec |

Everything except the home/activity **composition** already exists. That composition is BFF read-only work.

---

## 4 · Slice board (phased; each slice VERIFY + `/review-impl` + live-smoke where it crosses services)

| # | Slice | Size | Depends |
|---|---|---|---|
| **M0** | **Mobile chrome + one-Outlet shell + bottom-tab nav + addressable Sheet.** Extract `DesktopChrome`; add `MobileChrome` (raised centre = Assistant) around a single persistent `<Outlet/>` (MB1); reuse `useIsMobile`. Routes unchanged; sheets route-addressable (MB4). Placeholder per tab. | M | — |
| **M1** | **Assistant mobile views** (the 13-screen drab) bound to the existing assistant hooks: Home/chat, voice, today sheet, end-of-day + keep-all/budget, recall, journal timeline + entry, weekly + dismiss chips, practice + scorecard, "what I know", You&data. Reuses `useReflection`/`useScorecards`/`useTimezone`/… verbatim. | L | M0 |
| **M2** | **BFF `/v1/home` aggregation** + the **Home dashboard** view (hero + jump-back-in + launcher + recent) + **BFF `/v1/activity`** + the Activity feed view. Home degrade contract (MB2) + single-store feed (MB3). Cross-service → live-smoke. | L | M0, **M1** |
| **M3** | **Other-workshop mobile-viewable** passes (read/continue, not compose): Library (books+reading), Translate review, Worlds/Explore browse, the All-apps drawer, You/account. Squeeze-free but lighter than M1. | L | M0 |
| **M4** | **PWA**: manifest + icons + service worker (offline shell, not offline data) + install prompt; a11y audit (Dynamic Type, targets, SR) as the exit gate. | M | M1–M3 |
| **M5** | **Push delivery (D-MOB-4)** — `push_subscriptions` (upsert on owner+endpoint) + `POST/DELETE /v1/me/push-subscriptions` + the **content-free `PUSH_COPY` builder** (B1) + a VAPID sender that is **exactly-once** (B4), **410-prunes** (B3) and **fails closed** (H2) + a **push channel pref** (H1) + the **account-deletion teardown consumer** (B2) + FE SW handler + capability gate (S3) + effective-value toggle (S4). **Live-smoke: a real closed-tab push, content-free end-to-end** (not a mock). | M | M4 (SW) |

**Suggested order:** M0 → M1 (proves the reuse-the-controllers thesis on the hardest surface) → M2 → M3 → M4.
M1 alone is a shippable "the assistant is great on mobile" milestone.

---

## 5 · Open decisions → **now RATIFIED in §9** (kept here for the reasoning)

1. **Centre tab = "Assistant"** (assistant-first, current draft) **vs a neutral "＋ Create"** FAB. Ratify D-MOB-decision.
2. **PWA now, native later** — confirm PWA-first (vs jumping to Capacitor/React-Native). Affects M4 scope.
3. **Which workshops are mobile-*first* vs mobile-*viewable***: proposed — assistant/reading/translation-review
   mobile-first; **writing a novel + heavy world-building stay desktop-first** (mobile = continue/review). Confirm.
4. **Activity feed source**: notification-service only, or also fold in jobs terminal events? (affects `/v1/activity`.)
5. **Auth/session on mobile**: same JWT/refresh as web (assumed) — confirm no separate mobile auth.

---

## 6 · Standards touchpoints (for `/review-impl`)
- **Gateway invariant (I1):** home/activity aggregation lives in `api-gateway-bff`; no new public entry.
- **Tenancy:** owner from JWT `sub` on every aggregation; composed reads already owner-scoped.
- **Settings-Boundary:** the "pinned workshops / centre-tab" choice is a per-user preference (server-SoT), not env/global.
- **Data persistence:** user data server-only; per-device UI state (open tab/sheet) MAY be localStorage.
- **SD-7:** the coaching scorecard on mobile is shown-never-trended, identical to desktop (verified in the drafts).
- **No new provider/model/pricing surface;** per-lane usage reuses B1.
- **FE MVC:** mobile views are views only; logic stays in the reused hooks; no conditional unmount across the breakpoint.

---

## 7 · Estimate
- **BE:** ~1 BFF slice (`/v1/home` + `/v1/activity` + the B1 proxy, no migrations, no new service) **+ the push
  leg (M5)** — a small `push_subscriptions` table + a VAPID Web Push sender **added to** notification-service +
  registration route. That push leg is the only genuinely-new backend; everything else is composition/reuse.
- **FE:** the bulk — M0 shell + M1 assistant views + M2/M3 other surfaces + M4 PWA + M5 push handler. Reuses all existing hooks/api/context.
- **Net:** a **frontend program with a thin BFF seam + one small push-delivery leg**, not a backend project.
  The domain backend cleared this cycle is what makes it so; push is the one additive piece mobile genuinely needs.

---

## 8 · Edge cases & resolutions (from the 2-reviewer cold pass — all resolved before sealing)

Two cold reviewers (push/privacy + mobile/aggregation) read the spec **and the code**. 8 correctness/privacy
blockers surfaced; each is resolved here or inline above. **Nothing seals with an open blocker.**

### Push / privacy
- **B1 · Content-free is not free** *(blocker → D-MOB-4.3).* `redact.Body()` scrubs secrets, not names/PII.
  Push payload = static per-category `PUSH_COPY` only; unit-test it is a pure function of category.
- **B2 · Teardown** *(blocker → D-MOB-4.5).* No cross-DB FK. Sign-out DELETE (before JWT clear) + an
  account-deletion erasure-event consumer. Dies on account-deletion + sign-out, **not** assistant-data erase.
- **B3 · 410-prune** *(blocker → D-MOB-4.4).* `404/410 Gone` on send → delete the row; the primary GC + a
  stale sweep. `429/5xx` → backoff, keep.
- **B4 · Exactly-once** *(blocker → D-MOB-4.4).* Push only on `RowsAffected()==1`; the existing dedup_key
  makes it exactly-once under redelivery.
- **H1 · Channel dimension** *(→ D-MOB-4.4).* Add `push_enabled`/`channel` to `notification_preferences` so
  "in the feed, no buzz" is expressible (today it is one bool).
- **H2 · Fail-closed push** *(→ D-MOB-4.4).* `Suppressed()` fails open (right for in-app); the push gate fails
  **closed** — a prefs error → no buzz, the in-app row still stands.
- **H3 · Category mapping.** The design toggles (Weekly / End-of-day / Jobs / Social / Billing) do not 1:1 the
  9 backend categories ("Weekly" + "End-of-day" are both `assistant`; "Jobs" spans translation/llm_job/
  campaign). **Resolve at CLARIFY:** a `push_topic → (category, event-subtype)` map; `mcp_approval` push-on by
  default (security), `social` off by default. Pin the table before M5.
- **H4 · Tenancy.** Register owner = JWT `sub` only; `UNIQUE(owner, endpoint)`; rate-limit register + send.
- **S1 · Device dedup / multi-device.** The endpoint URL is the device key → upsert on `(owner, endpoint)`;
  many devices = many endpoints (native). No client device-id.
- **S2 · VAPID** *(→ D-MOB-4.6).* Private in env (fail-start); public via `GET /v1/push/vapid-public-key`;
  rotation = global re-subscribe absorbed by 410-prune.
- **S3 · iOS / unavailability.** Capability-gate before offering push (`serviceWorker`+`PushManager`, perm ≠
  denied; iOS also installed-PWA). Unavailable → hide the ask, show "Add to Home Screen to get nudges", fall
  back to in-app (the SSE feed already works). Never render a toggle the platform cannot honour.
- **S4 · Permission lifecycle / OS drift.** The toggle's displayed state = **effective** =
  `AND(OS-permission granted, server-intent on, live subscription present)` — recomputed on mount +
  `visibilitychange`. `denied` → disable + "enable in device settings" deep-link, **never** re-call
  `requestPermission()`. Store the pre-permission "intent" separately so "Not now" stays re-askable.
- **S5 · Deep-link security.** Push `data` carries only a route-key + opaque notification id (no content, no
  PII in the URL). `notificationclick` opens an **auth-gated** in-app route; logged-out → login then resume;
  the target screen re-fetches owner-scoped with the JWT (the id navigates, it does not authorize).

### Mobile shell / aggregation / PWA
- **MB1 · Viewport remount** *(blocker → D-MOB-2).* Chrome-only swap around one persistent `<Outlet/>`; reuse
  `useIsMobile`; boundary hysteresis; test a resize keeps the stream + one SSE.
- **MB2 · Home degrade** *(blocker → D-MOB-1).* `allSettled` + per-source timeout + total cap + per-tile
  status; never blanks; short-TTL cache; critical-vs-optional sources.
- **MB3 · Feed source** *(blocker → D-MOB-1).* One store (notification-service); verify each producer emits a
  row (add the emit if not — do not merge stores at read time); keyset cursor; defined "mark all read" + unread.
- **MB4 · Deep-link + login redirect** *(blocker).* `RequireAuth` today preserves `pathname` only → a cold
  deep-link (`/entry/123?sheet=today`) loses `?search`/`#hash`. **Fix:** preserve full `location` through
  login; **sheets must be route-/searchparam-addressable** so a push/feed tap restores tab+sheet and hardware
  Back closes the sheet (not navigates away). Test a cold-start deep-link while logged out.
- **MB5 · PWA update** *(high).* Versioned/revisioned precache (Workbox); **never** cache `/v1/*` cache-first
  (network-first); **no silent `skipWaiting`** — a `waiting` SW shows a "new version — refresh" prompt applied
  on user action / next cold nav; an app-version handshake header + the BFF stays back-compatible one version
  so a lagging iOS shell degrades, not breaks.
- **MB6 · Double-mount both shells** *(high → resolved by MB1).* Exactly one chrome's feature tree live; the
  other chrome inert (not CSS-hidden-mounted) — no double SSE / double `proactive-turn`. Test: one SSE across
  a resize.
- **MB7 · Voice on mobile web** *(high).* Matrix: permission-denied → text fallback + message; `recorder.
  onerror`/track `ended` (a call interrupts) → flush partial + offer resume; `visibilitychange` (backgrounded)
  → pause+flush (iOS suspends the recorder); resume `AudioContext` on a gesture; feature-detect mime; hard-cap
  length. Non-optional for the voice-front-door thesis.
- **MB8 · Token expiry across background→foreground** *(high).* `api.ts` has single-flight refresh for
  `apiJson` (DR-14), but voice/WS streams bypass it. **Require** a proactive `refreshAccessToken()` on
  `visibilitychange`/resume **before** re-subscribing SSE/voice; streams use proactive refresh + reconnect/
  resume, not the reactive 401 path.
- **MB9 · Offline draft-loss** *(medium).* A half-typed journal/chat entry lives only in the browser. Add
  per-device **input-draft** persistence (IndexedDB — allowed as per-device UI state) + a "not sent yet"
  indicator + send-retry; an explicit offline banner; define each tab's offline state ("showing last loaded",
  not a blank app).
- **MB10 · Tablet band + centre-tab.** The 767px cut gives a landscape tablet the phone chrome — sealed to
  **phone-chrome-through-tablet for v1**. The draft bottom bar has **both** a left "Create" tab **and** a
  centre "Assistant" — so decision #1 is *what the CENTRE is* (Assistant vs a generic ＋Create), "Create"
  staying a normal tab. Sealed: centre = Assistant.

### Slice-board corrections (folded into §4)
- **M2 depends on M1** (the Home hero consumes live assistant status — capture count / pending reflection).
- **Per-slice a11y VERIFY** on M1/M2/M3 (targets ≥44px, real controls + labels, rem/Dynamic-Type, both themes,
  reduced-motion, a tap-alt for every swipe) — M4's audit is the *consolidated* gate, not the first check.
- **M5 live-smoke** must prove the HARD path: a real browser subscription receives a VAPID push **with the tab
  closed**, and the payload is **content-free end-to-end** (B1) — a "row created" mock does not satisfy it.

---

## 9 · Seal

**Status: SEALED 2026-07-15** — the 8 blockers are resolved above; the CLARIFY decisions are ratified with the
defaults below (redirectable at PLAN, but the spec no longer depends on them being open):

| # | Decision | Sealed default | Rationale |
|---|---|---|---|
| 1 | Centre tab | **Assistant** (Home · Create · **Assistant** · Library · You) | commits to the assistant-first thesis; "Create" stays a normal tab |
| 2 | Runtime | **PWA-first**, Capacitor as the documented fallback (D-MOB-3 triggers) | covers every need; no rewrite; native only if a trigger fires |
| 3 | Mobile-first vs viewable | assistant · reading · translation-review **mobile-first**; novel-writing + heavy world-building **desktop-first** | matches what a phone is good for; the home reflects it |
| 4 | Feed source | **notification-service as the single store** (MB3) | clean paging; no read-time merge; add producer emits where missing |
| 5 | Auth | same JWT/refresh as web **+ proactive refresh on resume** (MB8) | no separate mobile auth; fixes the background-token gap |
| — | Tablet (MB10) | **phone chrome through tablet** for v1; revisit post-launch | ships sooner; tablet is not the target device |

Open at PLAN (not blockers): the H3 `push_topic → category` map (pin before M5), and the exact per-source
timeout/cache numbers in MB2 (tune under load). Everything else is decided.
