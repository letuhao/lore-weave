# 11 · Scheduler & Proactive — detailed design

**Date:** 2026-07-11 · **Phase:** P3 · **Status:** DESIGN · Depends on P1+P2.

---

## Q1. Why is this its own phase?

**The per-user scheduler is the one true platform hole.** Everything else in this feature adapts something
that exists; this does not exist *anywhere*:

- campaign-service sagas are **event-driven**, one-shot;
- workers **poll job tables**;
- backup-scheduler's cron is an **ops file**, not a user-facing facility;
- the registry's own scheduled re-scan is an **open deferral** (`D-REG-P3-SCHEDULED-RESCAN`) *precisely
  because* no scheduler primitive exists.

That is why **D8 deliberately decouples P1/P2 from it** — distillation triggers on explicit user action and a
catch-up sweep, so the MVP ships without a scheduler at all.

## Q2. What it unlocks

Auto end-of-day distill · hourly rollups (optional) · the **weekly reflection** ([`08`](08-coaching-reflection.md)) ·
weekly/whole-diary summary rollups (which are **not** free — the md5 cache never hits at part/book level on a
growing journal) · proactive nudges.

## Q3. Design

A `scheduled_agent_runs` table (`owner_user_id`, cadence, `job_kind`, next_fire_at, lease) + a **tick driver**,
copying two shapes that already work: the **authoring-run driver** (heartbeat, budget cap, pause, breaker) and
**campaign dispatch**. Execution, fairness (P5 WFQ), spend metering, job projection, and SSE progress all exist
— only the **time trigger** is missing.

## Q4. 🔴 The architectural constraint that shapes everything here

**Scheduled runs cannot pass Tier-A/W confirm gates.** The eval harness has to auto-approve suspended approval
cards just to finish a headless run.

→ **Every unattended write must be draft-into-inbox or pre-allowlisted.** A scheduled distill produces a
**draft entry** the user later confirms; it must never auto-canonize. This is D4, and it is *why* D4 exists.

## Q5. 🔴 Proactive turns are a new seam, not a config flag

Nothing in the platform **initiates an LLM turn unprompted**. notification-service *delivers* events, but no
agent *composes* them, and chat is strictly request/SSE-driven. An "agent-initiated message into a session" is
genuinely net-new in chat-service (sessions only grow from user turns today).

## Q6. 🔴 Notifications must be content-free (T26 / D16)

A nudge like *"You haven't journaled about the layoff conversation with Sarah"* lands on a **lock screen**, a
mirrored watch, or an **employer-hosted inbox**. This is the most likely real-world leak of the whole feature —
over someone's shoulder, not over the network.

→ **Diary-sourced notifications carry no content.** *"You have an unfinished entry."* The content lives only
behind auth. **A test, not a prompt instruction.**

## Q7. 🔴 Don't nag a person on holiday (T25/X25)

`08`'s detectors include **journaling gaps** — so two weeks off produces ten "you skipped a day" signals and a
weekly reflection that scolds someone on vacation.

→ A **"time off / away" marker**; detectors exclude declared-away periods; a gap detector must never fire on a
*declining engagement* trend without asking why. **An empty week is a valid, good output.**

## Q8. Acceptance

A scheduled distill produces a **draft** (never auto-confirmed) · a nudge notification contains **zero** diary
content · an away period produces **no** gap patterns · a scheduled run that hits the spend cap **pauses and
says so** ([`10`](10-cost-spend-lane.md) §Q3) · the driver survives a restart (heartbeat/lease).
