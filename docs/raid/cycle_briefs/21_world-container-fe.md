# Cycle 21: World container — FE (prose-less worldbuilding entry) ▶ M5

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** The **prose-less worldbuilding** front-end. A user creates a **world** (via C20's API) and then authors **entities / graph / timeline / canon** with **no manuscript** — all lore is linked to the world's auto-created **bible chapter** (the `sort_order 0` hidden chapter from C20). Extraction is **optional**; the bible chapter is the anchor that the existing chapter-keyed lore UIs hang off. Presents "a world" to the user, hiding the book/chapter mechanic.
- **Acceptance gate:** `scripts/raid/verify-cycle-21.sh` exits 0
- **Top 3 LOCKED decisions consumed:** G1 (world container), World-container locks (world created empty, bible book/chapter implicit), G5 (reuse `GraphCanvas`, read-only graph)
- **DPS count:** 2
- **Estimated wall time:** ~3h
- **Milestone:** ▶ **M5** — a prose-less world container exists.

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C20, C19
- Files expected to exist (grep-able paths): C20's `/v1/worlds` API + bible-chapter provisioning; C19's `GraphCanvas`-based visual graph canvas (reused/linked from the world view); frontend `features/` knowledge + book surfaces.

## Scope (IN)
- **Create-a-world entry:** a worldbuilding surface that calls C20 `POST /v1/worlds`, then lands the user in a **world workspace** (no manuscript/editor shown).
- **Author lore against the bible chapter:** wire the existing entity / graph / timeline / canon authoring UIs to the world's **bible chapter id** so authored lore (glossary entities, knowledge entities, timeline events, canon rules) anchors correctly. Resolve the bible chapter from the world (C20 provides it).
- **Extraction-optional messaging:** present extraction as optional; the bible chapter — not extracted prose — is the anchor. The worldbuilder can author entities directly with no draft text.
- **Hide the book mechanic:** the UI says "world" / "world bible"; it does not expose the underlying book/chapter scaffolding as a manuscript.
- **Graph reuse:** link/embed the C19 read-only graph canvas scoped to the world's project.
- `scripts/raid/verify-cycle-21.sh` (acceptance gate runner creates it).
- **Playwright MCP screenshot smoke** (test account `claude-test@loreweave.dev`): create a world with no manuscript → author lore against the bible chapter → screenshot filed with the brief.

## Scope (OUT — explicitly)
- **NO backend/schema/migration changes.** C20 owns the model + API + bible-chapter provisioning. If a needed endpoint is missing, record it as a finding — do NOT add BE here.
- **NO living-world timeline tree** (canon Work + dị bản branches) — that is C28 (M6).
- **NO dị bản / derivative** surfaces — C23–C27.
- **NO intent-fork onboarding** — that is C22.
- **NO graph editing** — the graph is read-only (G5); editing reuses the existing entity/relation dialogs.
- No world-level sharing UI (LOCKED deferred).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: frontend unit/component tests for the world-create flow + bible-chapter-scoped authoring wiring.
- Lints pass: frontend lint/typecheck clean.
- **Playwright screenshot smoke (REQUIRED — FE cycle, G4 LOCKED):** drive the running FE as `claude-test@loreweave.dev`, create a world with **no manuscript**, author at least one entity/canon item against the **bible chapter**, capture a screenshot. Evidence string contains `playwright smoke: worldbuilder creates a world with no manuscript and authors lore against the bible chapter` + screenshot path filed with the brief.
- Acceptance: a worldbuilder can create a world and author lore with **zero prose** and it persists against the bible chapter.

## DPS parallelism plan
- DPS 1: **World-create + workspace shell** — `features/world/` API layer (`worldsApi` over C20 routes) + create-world flow + world workspace shell that resolves the bible chapter id. Follows React-MVC (hooks own logic, components render). (return budget: 1500 tokens summary)
- DPS 2: **Lore authoring wiring + graph embed** — point the existing entity/timeline/canon authoring UIs + the C19 read-only graph at the world's bible chapter / project; extraction-optional messaging. Depends on DPS-1's bible-chapter resolution seam.
- **Serial tail (Raid Leader):** Playwright screenshot smoke + `verify-cycle-21.sh`.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **BE drift:** any schema/migration/endpoint added in this FE cycle → violation; C20 owns BE. Missing-endpoint = finding, not a fix.
- **Bible-chapter mis-anchor:** authored lore that does NOT link to the world's `sort_order 0` bible chapter → it will be orphaned / break chapter-keyed lore machinery. Confirm the authoring calls carry the correct chapter id.
- **Prose leak:** a manuscript/editor surfaced for a world (the book mechanic must stay hidden) → breaks the prose-less story.
- **Conditional-unmount / hook-state loss (CLAUDE.md FE rule):** ternary rendering that unmounts the graph canvas or authoring panels destroys hook/canvas state — use CSS hidden / internal branching.
- **useEffect-for-events / prop-drilling / context-split smells** per CLAUDE.md FE rules.
- **localStorage for user data:** world/lore data must be server-sourced (Postgres SSOT) — no localStorage persistence of user content.
- **Mock-only false-green:** confirm the Playwright screenshot reflects the real running FE creating a real world, not a stubbed view.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR iff: only frontend `features/world/` (+ minimal wiring of existing lore UIs) + `scripts/raid/verify-cycle-21.sh` changed; ZERO backend/schema/migration changes; lore anchors to the bible chapter; no manuscript/editor surfaced; graph stays read-only; Playwright screenshot smoke token + screenshot filed; `verify-cycle-21.sh` exits 0. Otherwise BLOCKED.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Row: `docs/plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md` — C21 row (▶ M5; prose-less worldbuilding entry).
- LOCKED: `docs/plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md` — §G1, World-container locks (world created empty; bible book/chapter implicit, FE hides it), §G5 (read-only graph reuse), Architecture-review locks (bible chapter is the anchor).
- Spec: `docs/specs/2026-06-13-writer-persona-use-cases-scenarios.md` §4A (N-B worldbuilder scenario).
- Spec: `docs/specs/2026-06-13-derivative-works-living-world-plan.md` (world container as living-world substrate).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **G1 / ARCH-REVIEW LOCKED:** lore is authored against the world's **bible chapter** (`sort_order 0`, hidden, created by C20). Authoring that does not anchor to it breaks the chapter-keyed lore machinery.
- 🔴 **World-container LOCKED:** a world is created empty; the bible book/chapter is implicit and the FE **hides the book mechanic** (presents "a world," never a manuscript). Extraction is OPTIONAL.
- 🔴 **FE-only:** NO backend/schema/migration changes — C20 owns the API + provisioning. Missing endpoint = record a finding.
- 🔴 **Acceptance MUST include:** Playwright screenshot smoke `playwright smoke: worldbuilder creates a world with no manuscript and authors lore against the bible chapter` filed with the brief (G4 FE-smoke rule).
- 🔴 **Do NOT touch:** dị bản/derivative surfaces, intent onboarding (C22), living-world tree (C28), world-level sharing; graph stays read-only; no localStorage for user data.
- 🔴 **Fresh session reminder:** this is a new `/raid 21` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
