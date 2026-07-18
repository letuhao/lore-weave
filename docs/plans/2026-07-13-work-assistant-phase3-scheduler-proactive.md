# Phase 3 — Scheduler & Proactive · implementation plan

**Date:** 2026-07-13 · **Track:** Work Assistant · **Design spec:** [`11-scheduler-proactive.md`](../specs/2026-07-11-work-assistant-mode/11-scheduler-proactive.md) (+ [`08`](../specs/2026-07-11-work-assistant-mode/08-coaching-reflection.md) for the weekly reflection it unblocks) · **Status:** PLAN (pre-build) · **Depends on:** P1 (distiller) + P2 (spend lane) — both built.

> This is the *implementation* plan spec 11 lacked. Spec 11 answers **why** and **what constraints**; this
> answers **which slices, in what order, with what schema + seams**. It also folds in the pre-Phase-3
> hardening that was done 2026-07-13 so those guarantees are *inherited*, not re-litigated.

---

## 0. What Phase 3 is (and is NOT)

Phase 3 adds the **one true platform hole** (spec 11 Q1): a **per-user scheduler**. Everything else in the
Work Assistant reacts to a user action; this is the first thing that acts on a **clock**. It unlocks:

- **Auto end-of-day distill** — the diary writes itself at the user's local end-of-day, no "End my day" click.
- **A catch-up sweep** — a returning user's missed days are journaled (bounded, spend-capped — the P-10(d) tail).
- **Costed rollups** — weekly / whole-diary summaries (the md5 cache never hits at part/book level on a growing journal, so these cost real tokens and must be scheduled + capped).
- **The weekly reflection** (spec 08) — the first coaching-adjacent surface, gated behind Phase 3's scheduler.
- **Proactive nudges** — content-free reminders ("you have an unfinished entry").

Phase 3 is **NOT** coaching (that is Phase 5, spec-forbidden until its 4 prerequisites exist) and **NOT** an
always-on agent. Every proactive turn is a **scheduled, single, bounded** action.

---

## 1. Substrate already built (this plan stands on it — do not rebuild)

| Piece | State | Where |
|---|---|---|
| The distiller pipeline (read → map-reduce → draft write) | ✅ built, live-proven | `worker-ai/app/distill_job.py`, `distiller.py` |
| The "End my day" **trigger + consumer** (a `assistant.distill` Redis-stream job) | ✅ built | `worker-ai/app/distill_consumer.py` + the gateway `end-day` endpoint |
| **Draft-into-inbox** — the write seam produces a reviewable DRAFT, never auto-published/kept | ✅ **verified 2026-07-13** (`128c1935b`) | `book-service/diary_entry_handler.go` + `TestDiaryEntry_IsADraftNeverAutoPublished_DB` |
| **Spend-cap degrade** — the distiller pauses when the daily cap is hit (fail-open; provider-gateway is the hard backstop) | ✅ built (WS-2.8, `d313128ee`) | `worker-ai/distill_job.py` `daily_cap_exhausted` pre-check |
| **Content-free notifications** — notification bodies derive only from operation/status/error; no content field exists on the wire | ✅ **verified + tripwire-locked 2026-07-13** (`26344d97a`) | `notification-service/consumer.go` + `TestNotificationIsContentFreeByConstruction` |
| **tz-aware `local_date`** — a day buckets by the user's LOCAL day (needed so the scheduler fires at the *right* local midnight) | ✅ **built 2026-07-13** (`fd4702818`); effective once a tz is set | `chat-service` `compute_local_date` + `AuthClient.get_user_timezone` |
| **Actionable `model_no_output`** — a reasoning model's empty distill is surfaced (advisory + message), not silent | ✅ **built 2026-07-13** (`9658a64c6`) | `worker-ai/distill_job.py` |

**Net:** Phase 3 wires a **clock** onto seams that already exist and already honor the draft/spend/content-free
invariants. The genuinely net-new engineering is (a) the scheduler table + tick driver and (b) the
proactive-turn seam.

---

## 2. The four constraints that shape every slice (spec 11, LOCKED)

1. **Q4 — Unattended writes are draft-into-inbox.** A headless run cannot pass a confirm gate. A scheduled
   distill produces a **draft** (already true — §1). A scheduled *rollup* or *reflection* that writes must also
   be a draft or a content-free notification, never an auto-canonized fact. **This is D4.**
2. **Q6 — Notifications are content-free.** A nudge lands on a lock screen / a mirrored watch / an
   employer-hosted inbox — the most likely real-world leak. *"You have an unfinished entry."* not *"You
   haven't journaled about the layoff with Sarah."* **A test, not a prompt instruction** (already locked — §1).
3. **Q7 — Don't nag someone on holiday.** An **away marker**; gap detectors exclude declared-away periods; an
   empty week is a *valid, good* output. A declining-engagement trend must never auto-scold.
4. **Q5 — Proactive turns are a new seam, not a config flag.** Nothing in the platform initiates an LLM turn
   unprompted. This needs its own careful design → **§4 (the mini-spec)**.

---

## 3. The scheduler substrate (WS-3.1)

### 3.1 `scheduled_agent_runs` (new table, owning service = **worker-ai** or a new `scheduler` sidecar — see Q-open-1)

```sql
CREATE TABLE scheduled_agent_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id   UUID NOT NULL,                 -- tenancy scope key (User Boundaries)
  job_kind        TEXT NOT NULL,                 -- 'eod_distill' | 'catchup_sweep' | 'weekly_rollup' | 'weekly_reflection' | 'nudge'
  cadence         TEXT NOT NULL,                 -- 'daily' | 'weekly' | 'once' (an explicit next_fire drives it; cadence is for re-arming)
  next_fire_at    TIMESTAMPTZ NOT NULL,          -- WHEN (computed in the user's tz → UTC instant)
  lease_until     TIMESTAMPTZ,                   -- NULL = unleased; a tick sets it to now()+lease_ttl to claim the row
  lease_owner     TEXT,                          -- which tick worker holds it (heartbeat/breaker forensics)
  enabled         BOOLEAN NOT NULL DEFAULT true, -- the user setting (SET-* : a per-user toggle, server-side)
  last_fired_at   TIMESTAMPTZ,
  last_status     TEXT,                          -- mirrors the distiller status vocabulary (written/no_entry/paused/error/...)
  fail_count      INT NOT NULL DEFAULT 0,        -- breaker: N consecutive failures → back off / disable + notify
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- One active schedule per (user, kind): re-arming UPDATEs next_fire_at, never inserts a duplicate.
CREATE UNIQUE INDEX uq_sched_one_active_per_user_kind
  ON scheduled_agent_runs (owner_user_id, job_kind) WHERE enabled;
-- The tick's claim query: due + unleased, ordered by next_fire_at.
CREATE INDEX idx_sched_due ON scheduled_agent_runs (next_fire_at)
  WHERE enabled AND lease_until IS NULL;
```

**Tenancy:** `owner_user_id` is the scope key; every query filters by it (User Boundaries). `enabled` is a
**per-user setting** (SET-*): the user turns auto-EOD on/off, server-side, not an env flag. The deploy-time
kill-switch (a global "scheduler off") is a *ceiling* (`effective = AND(deploy_allows, user_enabled)`), never a
per-user knob.

### 3.2 The tick driver (copy the **authoring-run driver** shape — spec 11 Q3)

A single loop (mirrors the authoring-run driver's heartbeat/budget/breaker and campaign dispatch):

```
every TICK_INTERVAL (e.g. 60s):
  claim = UPDATE scheduled_agent_runs SET lease_until=now()+lease_ttl, lease_owner=$me
          WHERE id IN (SELECT id FROM scheduled_agent_runs
                       WHERE enabled AND lease_until IS NULL AND next_fire_at <= now()
                       ORDER BY next_fire_at LIMIT $batch FOR UPDATE SKIP LOCKED)
          RETURNING *;
  for row in claim:
     enqueue the row's job_kind onto its existing Redis-stream consumer
       (eod_distill → the SAME `assistant.distill` stream the "End my day" endpoint uses)
     on enqueue-ok: re-arm (next_fire_at = next local occurrence), fail_count=0, lease cleared
     on error: fail_count++; if fail_count >= BREAKER_N → enabled=false + a content-free "auto-journal paused" notification
```

- **Restart-safe:** the lease + `next_fire_at` mean a crashed tick's row re-becomes claimable after `lease_ttl`
  (spec 11 Q8 acceptance: "the driver survives a restart").
- **`FOR UPDATE SKIP LOCKED`** so N tick replicas don't double-fire (the same discipline as the P5 WFQ /
  sweeper work already in the repo).
- **It does NOT execute** — it *enqueues* onto the existing consumers. Execution, spend metering, pause,
  breaker, SSE progress all already exist (spec 11 Q3). The tick is *only the time trigger*.

### 3.3 Firing at the right local time

`next_fire_at` for `eod_distill` = the user's configured end-of-day (default e.g. 23:30) **in their tz** →
converted to a UTC instant. Reuses the DBT-11 tz resolution (auth `timezone`). A user with no tz set fires at
UTC end-of-day (degraded, consistent with `local_date`'s UTC fallback).

---

## 4. The proactive-turn seam — MINI-SPEC (WS-3.5) 🔴 the net-new architecture

**Problem (spec 11 Q5):** chat is strictly request/SSE-driven — a session only ever grows from a *user* turn.
A nudge or a proactive reflection needs the assistant to **compose a message into a session unprompted**. This
is genuinely new and must not become an always-listening agent.

### 4.1 Shape

An **agent-initiated turn** is a scheduled job (`job_kind='nudge'` or `'weekly_reflection'`) that:

1. Runs the LLM turn **headless** (no live SSE client) via the SAME `stream_response` path a user turn uses —
   so it inherits tools, capture gating, context-budget frames, **and** the spend lane. (Reuse, don't fork —
   the voice-parity plan makes the same call for the same reason.)
2. Writes its output as an **assistant message flagged `initiated_by='agent'`** (new `chat_messages` column,
   default `'user_turn'`). The FE renders it as an unread assistant message; the user reads it next time they
   open the session. **It is a draft-shaped artifact** — informational, never an auto-canonized fact.
3. Emits at most a **content-free notification** ("your assistant left you a note" / "you have an unfinished
   entry") — never the note's content (Q6).

### 4.2 Hard rules (LOCKED — these are the difference between a helper and surveillance)

- **One turn, bounded.** A proactive job composes exactly one message then stops. No loop, no follow-up unless
  the user replies. (Not always-on.)
- **Consent-gated + fail-closed.** Proactive turns require an explicit per-user `proactive_enabled` setting
  (default **false**, SET-* server-side). Off ⇒ the scheduler still runs `eod_distill` (that is the user's own
  data being organized) but emits **no** agent-initiated messages.
- **Spend-metered like any turn.** It goes through the assistant spend lane; a capped user's proactive turn
  **pauses and says so** (reuses WS-2.8), never silently overspends.
- **Away-aware (Q7).** A proactive nudge checks the away marker (§5) first; an away user gets nothing.
- **Never diary content on egress.** The message body lives behind auth in the session; the *notification* is
  content-free.

### 4.3 Why not just a notification?

A notification is one-way and content-free by construction. The proactive *turn* exists only where the value
is a composed, in-session message the user can reply to (the weekly reflection). For pure reminders, prefer the
**content-free notification** — cheaper, safer, no LLM spend. **Default to a notification; use a proactive turn
only for the reflection.**

---

## 5. The away marker (WS-3.4, spec 11 Q7)

A per-user `assistant_away_periods` (or a `prefs.away_until` for the simple case): declared "time off / away"
ranges. Gap detectors (spec 08) and nudges **exclude** declared-away days. **An empty week is a valid output**
— the reflection for an away week is "welcome back," not "you skipped 7 days." A gap/decline detector must
**never fire on a declining-engagement trend without asking why** (no auto-scold).

---

## 6. Slice breakdown (dependency order)

> ⚠️ **REVIEW-PATCHED 2026-07-15** (cold review R2 — see [`2026-07-15-phase-345-clean-seal.md`](2026-07-15-phase-345-clean-seal.md) §7). Changes: **new WS-3.0 prereq** (server-side distill-context resolution — auto-EOD is NOT "pure wiring"); **WS-3.5 + proactive-WS-3.8 DEFERRED** out of v1 (they have no consumer under the pull-only seal P3-D3); the Go scheduler **re-implements** the lease/breaker (the authoring-run driver is Python) and **enqueues via the HTTP trigger**, not a raw Redis XADD.

| # | Slice | Deliverable | Depends on | Gate/Risk |
|---|---|---|---|---|
| **WS-3.0** 🆕 | Server-side distill-context resolution | Per user, resolve the diary `book_id` + the distill **model via provider-registry BYOK** (no hardcoded model; handle empty `user_default_models`) + tz + language — a headless scheduled run has NO client to supply these (today they're client-args; gateway `endDay` 400s without them). This is the real "Q8 follow-up". | provider-registry, auth prefs (tz) | 🔴 Prereq for WS-3.2/3.3/3.7. Undersized before; collides with the empty-default-model gap. |
| **WS-3.1** | Scheduler substrate | New Go `scheduler-service`: `scheduled_agent_runs` table + tick-driver (claim/lease/re-arm/breaker) + per-user `enabled` setting. **Re-implement** the lease loop mirroring `usage-billing sweeper.go` / `publisher poll_loop` (Go precedents; the authoring-run driver is Python — not copyable). Scaffold: a `language-rule.yaml` row, its own Postgres DB, migrations, a docker-compose entry, internal-token auth, and the opt-in write path (who writes the row on toggle). `SKIP LOCKED` = anti-double-fire (NOT per-user fairness — that's downstream). | — | The load-bearing new infra + a full new-service scaffold. |
| **WS-3.2** | Auto end-of-day distill | The tick calls `POST /internal/chat/assistant/distill` (the existing HTTP trigger — NOT a raw Go XADD, which would be a 3rd copy of the stream field-list) at the user's local EOD, with the WS-3.0-resolved context. Draft-into-inbox inherited. | WS-3.0, WS-3.1, distiller (built) | Low ONLY once WS-3.0 exists. |
| **WS-3.3** | Catch-up sweep (P-10(d)) | A returning user's missed days journaled, **bounded** + **spend-capped** (period-digest for >5-day gaps, T20). | WS-3.0, WS-3.2, spend cap (WS-2.8, built) | Q4/T20 — MUST be cost-capped or a multi-day sweep blows the budget. |
| **WS-3.4** | Away marker | `assistant_away_periods` + **nudges** exclude away days. (The *detector* exclusion + the "no gap patterns" acceptance is **Phase 5** — those detectors don't exist yet. P3 CREATES the marker; P5 CONSUMES it.) | — | Small; unblocks safe nudges. Test = away-*nudge* exclusion. |
| **WS-3.6** | Content-free nudges | The `nudge` job → a **content-free** notification (unfinished entry, etc.). Reuses the locked+tested content-free path; the distiller failed-error suppression constraint (below) lands here. | WS-3.1, notification (content-free locked ✓) | Low — the invariant is already tested. |
| **WS-3.7** | Costed weekly rollup | A scheduled weekly summary DRAFT (not auto-canon), spend-capped; the md5 cache never hits at book level so it costs real tokens. | WS-3.0, WS-3.1, WS-3.3 | Cost — schedule + cap; a draft the user reviews. |
| ~~**WS-3.5**~~ ⏸ DEFERRED | Proactive-turn seam | §4 mini-spec: `chat_messages.initiated_by`, a headless entrypoint, `proactive_enabled=false`. **DEFERRED out of v1** (R2-M3): under the pull-only seal (P3-D3) nothing enables it, so building the 🔴 net-new architecture behind a false flag with no consumer is the built-but-unreachable anti-pattern. Also under-scoped: `stream_response` needs a user prompt threaded through grounding + a 15-col INSERT gains a column (positional ripple). Build it in the phase that turns it on. | — | Deferred — revisit when a proactive consumer is committed. |
| ~~**WS-3.8**~~ ⏸ DEFERRED | Proactive weekly reflection | The reflection as a **proactive turn** — rides WS-3.5, so deferred with it. **The v1 weekly reflection is a PULL-ONLY draft owned by Phase 5** (WS-5.3, X-1) — not built here. NOT the coaching scorer (P5). | WS-3.5 (deferred) | Deferred; the pull-only reflection is Phase 5's. |

**Producer-side content-free constraint (folds into WS-3.6, carried from the hardening pass):** when the
distiller emits a terminal event that becomes a notification, a **failed** diary distill must NOT echo diary
text via `error_message` — emit a generic `error_code` with no message, OR register the journal operation in a
notification body-suppression set. The tripwire `TestNotificationIsContentFreeByConstruction` guards the
success path; this is the failure-path tail.

---

## 7. Acceptance (spec 11 Q8 — the exit gate)

- A **scheduled distill produces a DRAFT** (never auto-confirmed) — inherit + a scheduled-path live-smoke.
- A **nudge notification contains ZERO diary content** — the content-free test extended to the nudge path.
- An **away period produces NO gap patterns** — an away-week reflection is "welcome back," not a scold.
- A **scheduled run that hits the spend cap PAUSES and says so** (reuses WS-2.8).
- **The driver survives a restart** (lease + `next_fire_at`; a killed tick's row re-fires, does not double-fire).
- A **proactive turn is consent-gated** (`proactive_enabled=false` ⇒ no agent-initiated messages) and
  **spend-metered**.
- **Live-smoke (≥2 services):** the tick enqueues → the distiller writes a draft → a content-free notification
  lands, on a rebuilt stack. `/review-impl` on the phase; every finding fixed.

---

## 8. Open questions — ✅ ALL SEALED (2026-07-15, see [`2026-07-15-phase-345-clean-seal.md`](2026-07-15-phase-345-clean-seal.md) §3 P3-D1..3)

- **Q-open-1 — Where does the tick driver LIVE? → SEALED: a small new `scheduler-service` (Go)** (P3-D1 / D-R28).
  One home for the clock; worker-ai stays a pure executor. Language rule: meta/domain infra ⇒ Go.
- **Q-open-2 — Default auto-EOD ON or OFF? → SEALED: OFF / opt-in** (P3-D2 / D-R29). SET-* user setting;
  revisit after the reflection ships.
- **Q-open-3 — Reflection as a proactive turn or a pull-only draft? → SEALED: pull-only weekly DRAFT for v1**
  (P3-D3); upgrade to a proactive turn only once the WS-3.5 seam is live-proven. Avoids the
  agent-initiated-message risk on day one.

> The other Phase-3 constraints (away marker P3-D4, content-free notifications P3-D5, draft-into-inbox P3-D6)
> are LOCKED in the master seal doc; nothing in Phase 3 is open. **Ready to build on greenlight.**

---

## 9. What this plan deliberately excludes

- **Coaching / scoring (Phase 5)** — spec-forbidden until its 4 prerequisites (commitment schema, judge≠actor,
  a platform safety layer, a numeric eval bar) exist. The weekly *reflection* (descriptive) is in; the weekly
  *evaluation* (scored) is not.
- **Always-on / ambient anything** — every proactive action is a single, scheduled, bounded turn.
- **Voice (Phase 4)** — a separate plan; the proactive-turn seam and the spend lane are the shared dependencies.
