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
| **M0** | Mobile chrome + one-Outlet shell + bottom tabs + addressable Sheet | M | — | ⬜ | chrome-only swap in DashboardLayout/ChatLayout; reuse+dedup `useIsMobile`; sheet `?sheet=`; test: resize keeps state + ONE subscription + one chrome |
| **M1** | Assistant mobile views (13-screen draft) bound to existing hooks | L | M0 | ⬜ | views only; SD-7 badge; consent default OFF; End-my-day a visible button; MB7 voice matrix here; live-smoke: one real assistant loop + one SSE across a rotate |
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
- (none yet — record near-misses, lowered-bar temptations, and any slice whose live-smoke had to be deferred)

## 7 · Milestone / SESSION checkpoints
- M1 ships "assistant is great on mobile" · M4 ships the PWA · M5 ships push. POST-REVIEW batched at each.
- Update `docs/sessions/SESSION_HANDOFF.md` at each milestone boundary (not per file).
