# MOBILE SHELL + HOME — BUILD RUN-STATE (the durable commitment)

## 0 · Resuming after a compaction — do THIS first
Re-read THIS file, then `git log --oneline -20`, then continue at the first ⬜ / 🔵 slice.
Plan (how): [`2026-07-15-mobile-shell-and-home-plan.md`](2026-07-15-mobile-shell-and-home-plan.md).
Spec (what/why, SEALED): [`../specs/2026-07-15-mobile-shell-and-home.md`](../specs/2026-07-15-mobile-shell-and-home.md).
**Never re-litigate a sealed decision from memory** — §9 seal (centre=Assistant · PWA-first · mobile-first
split · single-store feed · same-JWT+resume-refresh · phone-chrome-through-tablet) and the PLAN §1 seals
(H3 topic map · MB2 numbers). Re-read, don't remember.

## 1 · The GOAL (finish line RATIFIED by the human 2026-07-15 — full program, M5 waiver allowed)
Ship the sealed mobile spec end-to-end: the app is genuinely mobile-first with the Work Assistant as the
front door, a platform home + activity feed, a PWA, and content-free closed-app push. **Autonomous exit** =
every slice **M0–M5** ✅-with-evidence (pasted fresh green tests + a pasted cross-service live-smoke where it
crosses services + a cold `/review-impl` with HIGHs fixed), each slice committed with explicit pathspec.

**M5 exit (human-ratified waiver):** the closed-tab content-free push is proven **live** if bootable; if the
full push stack (VAPID + HTTPS/installed-PWA + a live push service) genuinely can't run at dev time, M5 may
exit with a pasted `live infra unavailable: <reason>` token **+ a tracked `D-PUSH-LIVE-SMOKE` row in
SESSION_HANDOFF**, with all Go/FE unit tests still green + pasted. The waiver covers **only** the closed-tab
demonstration — the content-free chokepoint (B1), exactly-once (B4), 410-prune (B3) and fail-closed (H2) are
unit-proven regardless.

**The `/goal` condition (transcript-forcing + bounded), set by the human:**
> Every slice M0–M5 in `docs/plans/2026-07-15-mobile-shell-and-home-RUN-STATE.md` §3 is ✅ with, IN THIS
> TRANSCRIPT, pasted fresh green test output + a pasted cross-service live-smoke where it crosses services
> (M5 = a real closed-tab content-free push, OR a pasted `live infra unavailable:` waiver + a D-PUSH-LIVE-SMOKE
> row) + a cold `/review-impl` with HIGHs fixed, and each slice committed. Claiming a check passed WITHOUT
> pasting its output does NOT satisfy this. Stop after 220 turns if not met.

## 2 · Standing invariants (never lower silently)
- Never `git add -A` (shared checkout — explicit pathspec per slice). Commit each slice promptly.
- Per slice: PASTED fresh green tests + a PASTED cross-service live-smoke (where it crosses services) + a cold
  `/review-impl` with findings fixed + re-verified. **Rebuild stale images before a live-smoke** (false-green).
- **FE MVC:** mobile views are VIEWS ONLY; logic stays in the REUSED hooks; **no conditional unmount across the
  breakpoint** (chrome-only swap around ONE persistent `<Outlet/>`). A view re-implementing hook logic is a bug.
- **SD-7:** the coaching SCORE stays quarantine-tier (shown-never-trended); a committed QWK / "safety passing"
  is a DRIFT VIOLATION. The mobile scorecard carries the quarantine badge, identical to desktop.
- **Content-free push:** the push payload is a pure function of `push_topic` — it NEVER reads title/body
  (`redact.Body()` scrubs secrets, not PII). This is the load-bearing privacy invariant (B1).
- Tenancy (owner from JWT `sub`, never a body field; scope key on `push_subscriptions`); Gateway invariant (all
  through api-gateway-bff); no hardcoded secrets (VAPID private in env, ≠ JWT_SECRET); Settings-Boundary
  (push pref per-user server-SoT, effective-value visible, closed-set enum-validated).
- Stop + ask ONLY if a sealed decision turns out wrong, an action is destructive/irreversible/risks real user
  data, or you reach the SD-7 human boundary. "Unbuilt" ≠ "blocked" — build it. Otherwise keep going.

## 3 · SLICE BOARD (evidence string, not a checkmark)
`⬜ todo · 🔵 wip · ✅ done (evidence)` · order locked: M0 → M1 → M2 → M3 → M4 → M5.

| # | Slice | Size | Deps | Status | Evidence / note |
|---|---|---|---|---|---|
| **M0** | Mobile chrome + one-Outlet shell + bottom tabs + addressable Sheet | M | — | ✅ | `AppShell` (chrome-only swap around ONE persistent `<Outlet/>`, variant dashboard/chat) + `MobileTabBar` (centre=Assistant, raised) + addressable `Sheet` (`?sheet=`, open=push/close=replace) + `/home` `/you` placeholders; DashboardLayout/ChatLayout now thin AppShell wrappers; `useIsMobile` already a re-export shim (no dup to delete). **Tests (14 green, PASTED):** AppShell 3 (desktop↔mobile flip preserves the SAME feature instance — state intact + `mountCount===1` proving no remount / one subscription + exactly one chrome) + MobileTabBar 6 (5 real routes, aria-label+aria-current, prefix-active, centre=Assistant, **label-keys resolve in en locale**) + Sheet 5 (closed/deep-link-open/non-match/open-sets-param/close-strips). tsc clean; 712 assistant/chat/pages + 113 layout/shared unaffected. FE-only → no cross-service live-smoke (per plan). **Cold review (subagent, PASTED):** HIGH `nav.create`/`nav.you` didn't exist → raw keys shipped as labels (FIXED: reuse `common.create`/`nav.account`, both parity-present in all 18 locales, no sweep; + a test asserting keys resolve — the guard that would've caught it); MED dashboard `h-full` regressed bottom padding (FIXED → `min-h-full` for dashboard, `h-full` chat-only); L3 openSheet double-push broke Back-closes (FIXED: no-op if already open); L4 hardcoded `aria-label="Close"` (FIXED → `t('common.close')`); L5 weak a11y test (FIXED: real-key existence check). Reviewer confirmed the Outlet-preservation reconciliation SOUND + the test proves it (not happy-path). |
| **M1** | Assistant mobile views bound to existing hooks | L | M0 | ✅ | On mobile the assistant renders `<Chat>` (stable first child) + `MobileAssistantDock` (Today/End-my-day/Journal) instead of the `hidden md:block` desktop strip — chosen by `useIsMobile`, so Chat is never remounted on rotate. Dock binds the SAME hooks (useCaptureRail/useReflection/useScorecards/useTimezone/useDiaryFactInbox + a new thin `useDiaryEntries`) ONCE and hands them to addressable sheets: **Today** (`?sheet=today`) reuses CaptureRail/EndOfDayReview/ReflectionCard/CoachingScorecard/DiaryFactInbox/TimezoneConfirm + consent (fail-closed OFF); **Journal** (`?sheet=journal`) = timeline. voice/recall ride the reused Chat; End-my-day is a VISIBLE button. **Tests (18, PASTED):** AssistantPage.mobile 3 (dock↔strip swap keeps `chatMountCount===1` — no remount) + MobileTodaySheet 4 (consent OFF default, SD-7 quarantine badge shown) + MobileJournalSheet 4 (expand/kept/empty/error) + MobileAssistantDock 4 (visible End-my-day triggers distiller, Today/Journal open addressable sheets, review badge count) + useDiaryEntries 3; full assistant suite 48 green; tsc clean. **Live-smoke (PASTED, vite :5199 → gateway, test acct):** mobile chrome + dock render with REAL cross-service data ("3 to review" badge from glossary+knowledge); Today sheet opens (URL `?sheet=today`), shows real timezone (Asia/Bangkok), consent "Capture is off" (fail-closed live), CoachingScorecard "60/100 + Not-trended(in-review)" (SD-7 live), 3 real diary facts; close strips the param; resize 390→1280 swaps chrome (mobile→desktop) with chat persisting; 0 console errors throughout. **Cold review (subagent):** no HIGH; MED (rotate mid-distill remounted the dock → reset End-my-day to idle → duplicate costly distill) FIXED by lifting `useEndOfDay` into AssistantContext (survives the swap, like consent/provisioning); LOW sort-comparator (→localeCompare), LOW dead `hidden` class, COSMETIC CRLF split all FIXED. Reviewer verified no double-mount/double-fetch, Chat preservation, SD-7 no-trend-path, consent fail-closed, prop-shape parity. Crosses chat/knowledge/glossary/BFF (reused, already-shipped endpoints). |
| **M2** | BFF `/v1/home` + Home view + BFF `/v1/activity` + feed | L | M0, **M1** | ⬜ | allSettled 800ms/2s, tile status, 45s cache, never-blank; single-store feed keyset; owner from JWT; live-smoke: real compose + tile degrade + feed page |
| **M3** | Other-workshop mobile-viewable (read/continue) + All-apps drawer + You | L | M0 | ⬜ | library/translate-review/worlds/browse; novel-write + heavy world-build stay desktop-first (show affordance) |
| **M4** | PWA (manifest+SW+install) + MB4 full-location + MB8 resume-refresh + a11y audit | M | M1–M3 | ⬜ | Workbox versioned; `/v1/*` network-first; no silent skipWaiting; RequireAuth full location; refresh-before-resubscribe; a11y = exit gate |
| **M5** | Push delivery (D-MOB-4) — table+routes+PUSH_COPY+exactly-once+410-prune+fail-closed+teardown+SW+gate | M | M4 | ⬜ | ALL 8 blockers are build reqs; live-smoke: **closed-tab content-free push** (not a mock) + 410 prune + sign-out DELETE |

## 4 · Decisions register (append as sealed calls are made mid-build)
- (PLAN) H3 `push_topic → (category, message_key)` map SEALED — plan §1a (7 topics; social OFF, mcp_approval ON).
- (PLAN) MB2 numbers SEALED — 800ms/2000ms/45s TTL/5min stale; assistant-status critical, rest optional.
- (SPEC §9) centre=Assistant · PWA-first · mobile-first split · single-store feed · same-JWT+resume-refresh ·
  phone-chrome-through-tablet. Do not re-open.

## 5 · Parked register (each with a gate — parked ≠ dropped)
| ID | Item | Gate |
|---|---|---|
| R-MB-NATIVE | Capacitor native wrap | won't-build unless a D-MOB-3 trigger fires (iOS push unreliable / store required / always-on voice) |
| R-MB-TABLET | dedicated tablet chrome | won't-build v1 (sealed §9); revisit post-launch |
| R-MB-FEED-EMIT | a draft feed source not yet emitting a `notifications` row | M2 VERIFY enumerates the grep; a real gap → add the emit at the producer (buildable) |

## 6 · Debt / drift log (append as you go — an empty drift log at the end is dishonest)
- **M0 near-miss:** a top-level grep made me believe `nav.create`/`nav.you` existed; they did NOT (they were
  top-level/other-namespace keys), so the mobile tab bar would have shipped raw keys ("nav.create") as labels
  in every locale. The M0 cold review caught it. Lesson: verify a nested i18n key by its FULL dotted path, not
  a bare `grep`. Fixed + added a key-existence test.
- **M1 near-miss:** the strip↔dock swap on a viewport rotate remounted `useEndOfDay`, resetting a running
  distill's guard → a duplicate (paid) distill was possible on a tablet mid-distill. Not caught by my own
  tests; the cold review found it. Fixed by lifting `useEndOfDay` into context. Lesson: when swapping a
  subtree by viewport, audit EVERY hook in it for in-flight/expensive state, not just the "must-survive" one.
- **Journal double-fetch (accepted LOW):** `useReflection` and `useDiaryEntries` both hit `listDiaryEntries`
  on a mobile open (2×), + the Journal button refreshes (3rd). Pure reads, idempotent, cheap — left as-is;
  revisit if the endpoint gets expensive.

## 7 · Milestone / SESSION checkpoints
- M1 ships "assistant is great on mobile" · M4 ships the PWA · M5 ships push. POST-REVIEW batched at each.
- Update `docs/sessions/SESSION_HANDOFF.md` at each milestone boundary (not per file).
