# 02 · Assistant Mode & Session — detailed design

**Date:** 2026-07-11 · **Phase:** P1 · **Status:** DESIGN · Implements **D7, D12, D13**.
UI drafts: `design-drafts/work-assistant/assistant-home/`, `onboarding/`.

---

## Q1. What *is* an assistant session?

An ordinary `chat_sessions` row, created from a **System-tier assistant template**, rendered by the existing
ChatView. Not a new surface (D12).

⚠️ **A System-tier template cannot carry per-user ids.** System rows are `owner_user_id IS NULL` and shared
across all tenants, and `session_templates` has **no** project/book/skills columns. → the template carries only
**tenant-neutral** content (persona prompt, skill codes, capture defaults); the server **stamps** the caller's
`project_id` / `book_id` / `enabled_skills` onto the `chat_sessions` row at session-create (that row *does*
have those columns).

**Assistant-session discriminator:** `chat_sessions.book_id = the user's diary book` (or an additive
`session_kind` column — decide in PLAN). Needed by `chat_search_sessions` scoping, the day-window read, and
the voice-disable gate.

**D13 — no working-memory charter on the main session.** A charter fires an **executive tick every 4th turn**
(~N/4 extra LLM calls/day, stacked on capture's identical cadence). Persona/steering ride the system prompt +
book steering rules. The charter is reserved for **coach sessions** (bounded).

## Q2. Provisioning (idempotent, race-safe, identity-safe)

`POST /v1/assistant/provision` — orchestrated by **api-gateway-bff fanning out over the public APIs with the
user's own JWT** (book-service `/internal` is read-only; this avoids inventing a new internal write surface).

**Identity:** the provisioned `owner_user_id` for every row is the **gateway-authenticated principal**,
propagated end-to-end; every downstream route owner-keys/grant-checks it. A cross-user id in any body is rejected.

Every step is an **atomic upsert against an explicit idempotency key**, so two concurrent provisions converge:

1. **Diary book** — partial unique `(owner_user_id) WHERE kind='diary' AND lifecycle_state='active'`;
   `ON CONFLICT` repeats that exact predicate. `kind` server-set + DB-trigger-immutable.
2. **Work knowledge project** — one-per-user partial unique; additive `is_assistant` marker (the closed
   `project_type` CHECK is **not** extended). `chat_turn_extraction_enabled` **derived fail-closed** (D6).
3. **Work ontology** — adopt the System-tier work kinds + KG schema template.
4. **Extraction bootstrap** — store the project's extraction config (model + cap + status), else the
   save-triggered drain **silently no-ops** (the drainer skips job-less projects — E15/ARCH-6).
5. **Timezone** — seed from the client's `Intl` zone, **explicit user confirm** (D9). Unset ⇒ UTC + a visible
   warning + auto-distill **held**.
6. **Self entity** — seed the user's identity entity, `is_self`, excluded from capture ([`05`](05-work-capture-ontology.md) §Q5).
7. **Consent** — enabled **only** if the user turns it on. Never flipped as a provisioning side effect.
8. **Today's session** from the template.

### ⚠️ Partial failure leaves a visible half-state (T39)

Convergence under concurrency ≠ atomicity under failure. If steps 1–2 commit and step 4 fails, the user has a
real diary book **visible in their library** bound to a project that silently no-ops extraction.
→ an explicit **`provision_status`** the home strip reads, **re-driven idempotently on every `/assistant`
open** until all steps report done — **or** create the diary book **last** so a half-provision is invisible.
(Also: the diary is hidden from the library grid anyway — D16/T27.)

### Journal-book trash (E14)

Get-or-create matches **active-only** but **detects** a trashed diary and offers **restore vs. re-provision
fresh** — never silent resurrection, never a silent fork (which would strand the KG anchors). Trashing the
diary from the library triggers an assistant-aware confirm and pauses distill/capture.

## Q3. Multi-device concurrency (EDGE-5)

Every device funnels to "today's assistant session", so two live writers in **one** session is the **designed
steady state** — but `sequence_num` is assigned by `SELECT COALESCE(MAX(seq),0)+1` with **no lock**, under
`UNIQUE(session_id, sequence_num, branch_id)`. The loser's INSERT fails **inside the persist transaction**,
rolling back the assistant message **and** its outbox event — **the turn is silently lost.**

→ `pg_advisory_xact_lock(hashtext(session_id))` around seq-assign + insert, **retry once** on unique
violation. Advisory key is `session_id` (not `user_id`) so two different sessions never contend. Two-writer
live-smoke in S14.

## Q4. The entry points

- **Nav row** — `Assistant` in `mainNav` (auth-gated), trivial (the `/chat` pattern exists).
- **C22 onboarding intent fork** — first-run is gated via `/onboarding`, which offers **four fiction-shaped
  intents** (BL-15 LOCKED). A user who signed up *for the work assistant* is funneled into "write a novel".
  → add a **fifth intent** ("get help with my work" → `/assistant`, triggering provisioning), recorded as an
  explicit **BL-15 amendment**, not a silent edit. The nav row remains the re-entry door.

## Q5. The home strip (the transparency surface)

Above the chat: **capture-status chip** (effective value + **reason**, fed by the persisted CaptureDecision —
[`05`](05-work-capture-ontology.md) §Q7), a **"today so far"** live rail (people/projects/decisions noticed,
with *"nothing is saved until you review it tonight"*), the **pending-entry nudge**, inbox counts, and the
**week-1 empty state** (*"I still remember everything you've told me — just ask"* — the honest day-1 value,
since the KG is structurally empty until entries accumulate).

Failure states surfaced here, never silent: extraction not configured · model unresolved · **memory paused —
daily cap reached** ([`09`](09-settings-consent-privacy.md) §Q7) · capture off + reason.

## Q6. Voice in P1 (D11/EDGE-8)

Voice input is **hidden/disabled for assistant-bound sessions** until P4. The shared ChatView's voice overlay
would otherwise be reachable, and voice turns **persist to `chat_messages` (so the distiller journals them)
but never call capture and bill 0/0 tokens** — the "collecting" chip would say ON while half the day is
uncaptured and unbilled. See [`12`](12-voice-parity.md).

## Q7. Acceptance

First-run intent → provision → chat → home-strip states (desktop + mobile) · kill the provisioner after step 1
⇒ **zero** chat_turn extraction jobs and a visible half-state banner · two devices send simultaneously ⇒ both
turns persist · assistant session carries **no** charter (⇒ no executive tick) · voice affordance absent.
