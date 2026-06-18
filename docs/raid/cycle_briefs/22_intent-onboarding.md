# Cycle 22: Intent-branching onboarding (FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** A first-run **"What do you want to do?"** intent fork. The user picks one of **Write / Build a world / Translate / Explore**, and the app **routes to the tailored path + the right container** for that intent — Write → book/compose flow; Build a world → the C21 world container; Translate → the translation surface; Explore → the read-only graph/catalog surface. This is the front door that disambiguates the four personas before dropping the user into a generic shell.
- **Acceptance gate:** `scripts/raid/verify-cycle-22.sh` exits 0
- **Top 3 LOCKED decisions consumed:** BL-15 (intent fork), G1/World-container locks (Build-a-world → world container), G6 (knowledge IA — Explore lands in the project/graph surface)
- **DPS count:** 2
- **Estimated wall time:** ~3h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C20, C21
- Files expected to exist (grep-able paths): C20 `/v1/worlds` API; C21 world-container FE (the Build-a-world target); existing book/compose, translation, and read-only graph/catalog surfaces (the other three targets); frontend routing/onboarding entry.

## Scope (IN)
- **First-run intent screen:** "What do you want to do?" presenting four choices — **Write · Build a world · Translate · Explore**.
- **Routing per intent:**
  - **Write** → the write-from-scratch / continue-writing path (book + compose), with a book container.
  - **Build a world** → the **C21 world container** create-a-world entry (its own world container).
  - **Translate** → the translation surface (intent-fork routing only; no new translator flow — that is a non-goal).
  - **Explore** → the read-only graph / catalog browse surface.
- **Right container per intent:** each landing creates/opens the correct container (book for Write, world for Build-a-world, etc.) so the user is not dropped in a generic shell.
- **First-run gating:** show on first run; allow re-entry (e.g. a "start something new" affordance) without forcing it every session. Persist the "seen onboarding" signal **server-side** (preferences via `/v1/me/preferences`), not localStorage-only.
- `scripts/raid/verify-cycle-22.sh` (acceptance gate runner creates it).
- **Playwright MCP screenshot smoke** (test account `claude-test@loreweave.dev`): each of the 4 intents lands in the correct surface → screenshot(s) filed with the brief.

## Scope (OUT — explicitly)
- **NO backend/schema/migration changes** beyond using the existing `/v1/me/preferences` write-through for the onboarding-seen flag. No new BE endpoint.
- **NO new translator flow** — Translate just routes to the existing translation surface (translator-specific flow beyond routing is a LOCKED non-goal).
- **NO new world model/API** — Build-a-world reuses C20/C21.
- **NO new graph/catalog feature** — Explore routes to existing read-only surfaces (C19 graph etc.).
- **NO dị bản / living-world** surfaces — C23–C28.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: frontend unit/component tests for the intent screen + the four routing branches + first-run gating.
- Lints pass: frontend lint/typecheck clean.
- **Playwright screenshot smoke (REQUIRED — FE cycle, G4 LOCKED):** drive the running FE as `claude-test@loreweave.dev`; for **each of the four intents**, select it and confirm it lands on the correct surface; capture screenshots. Evidence string contains `playwright smoke: each of 4 intents (Write/Build-a-world/Translate/Explore) lands in the correct surface` + screenshot paths filed with the brief.
- Acceptance: each intent lands in the correct surface + right container.

## DPS parallelism plan
- DPS 1: **Intent screen + first-run gating** — `features/onboarding/` intent screen component + hook owning the choice logic + server-side seen-flag via `/v1/me/preferences`. React-MVC separation (hook owns logic, component renders). (return budget: 1500 tokens summary)
- DPS 2: **Routing wiring** — map each intent to its target route + container bootstrap (Write→book/compose, Build-a-world→C21 world create, Translate→translation, Explore→graph/catalog). Depends on DPS-1's choice contract.
- **Serial tail (Raid Leader):** Playwright screenshot smoke across all 4 intents + `verify-cycle-22.sh`.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Wrong-surface routing:** any intent that lands on a generic shell instead of its tailored path + correct container — defeats the cycle's purpose. Verify all 4 land correctly.
- **BE drift:** any new endpoint/schema/migration → violation; only the existing `/v1/me/preferences` write-through is allowed.
- **localStorage-only onboarding flag:** the seen signal must be server-synced (multi-device rule) — localStorage-only means the fork re-shows on another device.
- **Forced re-onboarding:** showing the intent screen every session (not just first-run) is a regression; confirm gating + a re-entry affordance.
- **Scope creep into translator/graph features:** Translate/Explore must only ROUTE; no new translator flow or graph feature (non-goals).
- **Conditional-unmount / useEffect-for-events / prop-drilling** per CLAUDE.md FE rules; routing should be explicit callback handlers, not useEffect reactions.
- **Mock-only false-green:** confirm screenshots reflect the real running FE routing per intent.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR iff: only frontend `features/onboarding/` (+ routing wiring) + `scripts/raid/verify-cycle-22.sh` changed; ZERO backend/schema/migration changes (only existing `/v1/me/preferences` used); all 4 intents route to the correct surface + container; onboarding seen-flag server-synced; first-run gated with re-entry; Playwright smoke token + screenshots filed; `verify-cycle-22.sh` exits 0. Otherwise BLOCKED.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Row: `docs/plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md` — C22 row (BL-15 / §6 #1 intent fork).
- LOCKED: `docs/plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md` — §G1 + World-container locks (Build-a-world → world container), §G6 (knowledge IA — Explore landing), Non-goals (translator flow beyond routing).
- Spec: `docs/specs/2026-06-13-writer-persona-use-cases-scenarios.md` §4A (persona use cases the four intents map to).
- Spec: `docs/specs/2026-06-13-derivative-works-living-world-plan.md` (world container as a routing target).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **BL-15 LOCKED:** four intents — Write / Build a world / Translate / Explore — each routes to its tailored path **+ the right container** (book / world / translation / graph), never a generic shell.
- 🔴 **G1 / World-container LOCKED:** Build-a-world routes into the C20/C21 world container — do NOT build a new world model or API here.
- 🔴 **Non-goal LOCKED:** Translate only ROUTES to the existing translation surface — no new translator flow. Explore only routes to existing read-only graph/catalog — no new graph feature.
- 🔴 **Acceptance MUST include:** Playwright screenshot smoke proving all 4 intents land correctly, filed with the brief (G4 FE-smoke rule); onboarding seen-flag server-synced via `/v1/me/preferences` (multi-device, no localStorage-only).
- 🔴 **Do NOT touch:** backend/schema/migration; dị bản/living-world surfaces (C23–C28); translator internals; graph internals.
- 🔴 **Fresh session reminder:** this is a new `/raid 22` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
