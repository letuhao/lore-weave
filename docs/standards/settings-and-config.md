# Settings & Configuration Boundary Standard

**When to read:** you are adding *any* configurable behavior — a toggle, a model choice, a
threshold, a mode, a persona, a voice, a limit. Before you reach for an env var, a global
flag, or a shared row, decide **whose setting this is**. This standard draws the line
between a **user setting** (tiered, resolved, per-user/per-book) and **platform
configuration** (global, env, deploy-owned) — and bans the abuse of the latter for the
former.

These rules are not theory: every one **caught a real bug** in the Chat & AI settings
unify (`docs/specs/2026-07-05-chat-ai-settings.md`, the reference implementation) — the
context-budget tiers shipped as process-global env flags (same for every user, invisible,
unchangeable); grounding was always-ON with no toggle; the behavior blob was stored but
consumed by zero turns; the PATCH accepted `mode:"banana"`.

**Relationship to existing standards:** this is the *decision procedure + boundary* that
sits on top of **[User Boundaries & Tenancy](../../CLAUDE.md)** (the 3-tier scope model),
**[Data Persistence Rules](../../CLAUDE.md)** (server-is-SSOT), **[Frontend-Tool
Contract](./README.md#frontend-tool-contract)** (closed-set ⇒ enum), and **[Data & Logic
Scope Separation](./scope-separation.md)** (one owner per concept). It does not restate
them; it tells you *when* each applies to a setting.

---

## SET-1 — Classify first: is this a user setting or platform config?

Before building, answer: **would two different users reasonably want different values?**

- **Yes → it is a USER setting.** It gets a tenancy tier (Per-user or Per-book/project), a
  scope key, and resolves through the cascade (SET-2). It does **not** live in an env var
  or a global flag.
- **No, it is identical for the whole platform → it may be platform config**, but *only*
  when it is also **load-bearing / infrastructural**: a service URL, port, secret, DB DSN;
  a deploy-time capability **ceiling / kill-switch** (SET-3); or a genuine platform
  invariant. Reserve env/global config for these.

> **The abuse this rule kills:** "it was one line to add an env flag." Env flags are
> attractive because they skip the tenancy + UI + resolution work — which is exactly the
> work that makes a setting a *setting*. A behavior that a power user would want to tune,
> shipped as a process-global env flag, is **the same for every user, invisible, and
> unchangeable without a redeploy** (the context-budget T5/T4/D13a tiers, pre-fix). If you
> catch yourself adding `SOME_BEHAVIOR_ENABLED` to a service's config to gate a *user-
> facing* behavior, STOP — it is a user setting wearing an env-var costume.

**Global config is an important, deliberate act, not a default.** A new global/env setting
implicitly claims "this affects the entire platform the same way." Treat adding one with
the weight of a platform-wide change: it should be rare, reviewed, and justified — not the
path of least resistance for a per-user choice.

## SET-2 — A user setting declares its scope tier and resolves through the cascade

Per **[User Boundaries & Tenancy]** (LOCKED): every user-settable field declares a **tier**
(System / Per-user / Per-book·project), carries a **scope key** (`owner_user_id` and/or
`book_id`), and is resolved **most-specific-wins**:

```
Tool/turn override ▸ Session override ▸ Book/project ▸ Account (per-user) ▸ System default
```

- **Never a shared, global, user-mutable row** — a `UNIQUE(code)` on a scope-less table is
  the tenancy-bug smell (the `entity_kinds` bug); use `UNIQUE(owner_user_id|book_id, code)`.
- Resolution is **field-by-field** (a book overriding one field does not shadow the others).
- The **System tier is the ONLY place a literal default lives**, and it is admin/deploy-
  owned, read-only to regular users.

## SET-3 — Env/global config is a CEILING, never a per-user knob

When a behavior genuinely needs *both* a platform-wide safety valve *and* per-user control
(e.g. an experimental, expensive, or risky tier), the env flag is the **deploy MAX**, and
the per-user setting decides **within** the allowed envelope:

```
effective = AND(deploy_allows, cascade_resolved(user_enables), dependencies_met)
```

- An operator can force a tier **OFF** platform-wide; a user can only turn it **on** if the
  ceiling permits, and can always turn it **off**. The env flag is **never overridden
  upward** by a user.
- Surface "**disabled by deployment**" in the UI (distinct from user-off) when the ceiling
  or a dependency blocks it — never a silent no-op.

The env flag answers "*is this available at all here?*"; the user setting answers "*do I
want it?*". Do not conflate the two — an env flag that means "on for everyone" is the
SET-1 abuse.

## SET-4 — No silent fallback: the effective value AND its source are observable

A setting read returns the **effective value + which tier supplied it** (`{value,
source_tier}`), never a bare `null` that a downstream layer silently fills with a hidden
literal. The user (and the next engineer) must be able to **see what was chosen and why**.

> **The bug class:** a behavior chosen by an implicit default nobody can see — grounding
> unconditionally ON (a global engine flag), reasoning silently `off`, tool authority
> silently `write`, TTS voice silently `af_heart`, `temperature` unset → an opaque provider
> default. Each was "working as coded" and invisible. Surfacing the effective value + tier
> is what turns a hidden default into an honest setting.

## SET-5 — A setting must be CONSUMED, never write-only

A settings store that nothing reads is a **bug, not a feature**. Every user-settable field
has a **consumer** that reads the *resolved* value and changes behavior — and you prove it
**by EFFECT** (a test or live-smoke showing the setting changes the outcome), not by "it is
stored / the panel renders."

> **The bug (shipped, caught in `/review-impl`):** a whole Behavior settings section wrote a
> `user_chat_ai_prefs.behavior` blob that only the *display* endpoint read — zero chat
> turns consumed it. Setting "reasoning = high" changed nothing. The fix wired new-session
> seeding + a turn-seam fallback, each with an effect-test. **Storage + UI is half a
> feature; the consumer is the other half.** (Mirrors the Agent Extensibility
> "degrade-safe-consumer + live-E2E-by-effect" shape — see [agent-extensibility.md](./agent-extensibility.md) §1.)

## SET-6 — Closed-set setting values are enums, validated on write

A setting whose values are a finite set (a `mode`, `permission_mode`, `reasoning_effort`, a
`source`, a `status`) **declares the enum and rejects out-of-set values on write** (HTTP
422), on **both** the FE and BE. A free-string "closed set" silently stores garbage that the
consumer then treats as a default — a silent no-op.

Per **[Frontend-Tool Contract]** (the same discipline, applied to REST settings): closed-set
arg ⇒ `enum`; register/validate both sides; one name for one concept. (Bug: the ai-prefs
PATCH accepted `context.mode:"banana"`, which the resolver treated as `auto`.)

## SET-7 — Server is SSOT; localStorage is per-device UI state only

Per **[Data Persistence Rules]**: a user setting lives on the **server** and resolves through
the cascade, so it follows the user across devices. `localStorage` is for **per-device UI
state only** (sidebar collapsed, panel widths) — never for a preference the user expects to
see on another device, and never as the authoritative store. A setting split across two
client stores (the pre-fix chat-voice vs reading-voice localStorage split) fragments the
concept and drifts.

## SET-8 — One setting, one home, one name; consumers inherit, they don't re-store

The same concept has **one authoritative store + one resolution path**. Consumers **read the
resolved value**; they do not each keep their own copy.

> **The bug:** the chat model was pickable in **8 places** with no shared source — every
> studio tool re-stored its own choice, so a user re-picked everywhere. The fix was one
> shared resolver every consumer reads (`useEffectiveModel`). If a second surface needs the
> "same" setting, it **inherits** it (with an optional local override), it does not add a
> parallel store. See [scope-separation.md](./scope-separation.md) (one owner per concept).

---

## The checklist (apply before building any configurable behavior)

1. **Whose setting is this?** Two users want different values ⇒ **user setting** (SET-1) —
   not an env var.
2. **Which tier?** System / Per-user / Per-book — declare it + a scope key (SET-2).
3. **Global safety valve needed too?** Env flag = ceiling, `AND(deploy, user)` (SET-3).
4. **Can you see the effective value + its source?** No bare hidden default (SET-4).
5. **What reads it?** Name the consumer; prove the effect (SET-5).
6. **Closed set of values?** Enum-validate on write, both sides (SET-6).
7. **Where does it live?** Server SSOT, not localStorage (SET-7).
8. **Does it already exist?** One home, one name; inherit, don't re-store (SET-8).

## Enforcement

**Status: ACTIVE (rules; enforcement via review + the linked gates).** This standard is a
*decision boundary* — its teeth come from the standards it composes:

- **Tenancy half** (SET-2, SET-7) — [User Boundaries & Tenancy] + partial-`UNIQUE(scope,code)`
  schema pattern (review; the tenancy tests catch a scope-less shared row).
- **Enum half** (SET-6) — the [Frontend-Tool Contract] pattern (closed-set ⇒ enum, machine-
  checked); for REST settings, a dedicated validator + a rejects-bad-value test.
- **The env-abuse / silent-fallback / write-only checks (SET-1, SET-3, SET-4, SET-5)** are a
  **mandatory `/review-impl` gate**: a new `*_ENABLED`/`*_MODE` env flag in a *consuming*
  service that gates *user-facing* behavior is a SET-1 finding; a settings field with no
  effect-test is a SET-5 finding. These caught the real bugs above precisely because a
  passing unit test does not see them.
- **Candidate lint (SET-1):** flag a newly-added `settings.<x>_enabled: bool` / `<X>_MODE`
  env field in a domain/AI service whose only readers gate per-request behavior (heuristic:
  env flag read inside a request/turn path, not at startup/wiring). Not yet built — tracked
  as a future `settings-boundary-lint`.

**Reference implementation:** `docs/specs/2026-07-05-chat-ai-settings.md` +
`services/chat-service/app/services/settings_resolution.py` (the cascade) +
`app/routers/ai_settings.py` (the effective-value contract + enum validation).
