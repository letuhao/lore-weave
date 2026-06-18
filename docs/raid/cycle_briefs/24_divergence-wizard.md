# Cycle 24: Divergence wizard + derivative studio (FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** **dị bản M1** front-end. Build a **4-step divergence wizard** (Step 1 source/branch-point → Step 2 divergence type → Step 3 overrides preview → Step 4 name) that calls `POST /works/{id}/derive` to spawn a derivative Work, plus the **derivative studio banner** (you-are-in-a-dị-bản context) and the **2-layer grounding badges** that mark each grounded entity as **INHERITED** (from source/base) vs **OVERRIDDEN** (delta). Verify by spawning a genderbend dị bản end-to-end from the UI.
- **Acceptance gate:** `scripts/raid/verify-cycle-24.sh` exits 0
- **Top 3 LOCKED decisions consumed:** dị bản taxonomy (UX §7.1: POV shift · character transform · AU), override scope (entity fields + canon rules), G3 (chapter-level branch_point)
- **DPS count:** 2
- **Estimated wall time:** 3–4h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C23
- Files expected to exist (grep-able paths): `POST /works/{id}/derive` (composition-service, shipped C23) + `composition_work.source_work_id`/`branch_point`/`divergence_spec`/`entity_override`; the composition/writer FE feature dir; the existing grounding-badge render path the studio decorates.

## Scope (IN)
- **4-step wizard** (`features/composition/.../DivergenceWizard.tsx` or equivalent): Step 1 pick **source Work + branch_point** (chapter-level, G3); Step 2 pick **divergence type** (POV shift · character transform · AU — all reduce to `branch_point` + optional `pov_anchor` + `entity_override[]` + `canon_rule[]`); Step 3 **overrides preview** (entity-field overrides + added canon rules, editable); Step 4 **name** the dị bản → submit to `POST /works/{id}/derive`.
- **Derivative studio banner:** persistent context banner in the writing studio when the open Work is a derivative — shows source + branch_point + "adapting from canon (read-only reference)".
- **2-layer grounding badges:** in the grounding panel, tag each entity **INHERITED** (base, source project ≤ branch) vs **OVERRIDDEN** (delta / has an `entity_override`). Distinct visual treatment + legend.
- **Reference spine surfacing:** original chapters available **read-only** as adaptable reference (NOT auto-inserted — LOCKED).
- `scripts/raid/verify-cycle-24.sh` (acceptance gate) + a **Playwright screenshot** filed with the brief.

## Scope (OUT — explicitly)
- **NO BE schema/API changes** — `POST /works/{id}/derive` + the tables are C23. This cycle only consumes them.
- **NO packer override-merge** (C25) — the badges READ override state; they do not implement merge-at-retrieval.
- **NO critic enforcement** (C26), **NO delta flywheel / what-if promotion** (C27), **NO living-world view** (C28).
- NO relationship/event override UI (M0 = entity fields + canon rules only).
- NO chapter clone / copy-paste of source prose into the derivative (reference spine is read-only).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: wizard + badge unit/component tests (`frontend/.../DivergenceWizard*.test.tsx`, badge legend test).
- Lints pass: frontend lint + typecheck; React-MVC rules (hooks own logic, components render-only; no useEffect for the wizard step transitions — explicit callbacks).
- Integration smoke: **Playwright MCP** (test account `claude-test@loreweave.dev`) — drive the wizard, spawn a **genderbend (character-transform) dị bản**, land in the studio, capture a **screenshot** showing the banner + INHERITED/OVERRIDDEN badges. Evidence string carries `playwright: genderbend dị bản spawned + studio badges shown`.

## DPS parallelism plan
- DPS 1: **4-step wizard** — step state machine (explicit callback transitions, no useEffect), source/branch picker, type selector, overrides-preview editor, name + submit to derive. (return budget: 1500 tokens summary)
- DPS 2: **Studio banner + 2-layer badges** — derivative-context banner + INHERITED/OVERRIDDEN badge decorator on the grounding panel + legend + read-only reference-spine surfacing. Independent of DPS 1 until the submit lands; converge on the studio route.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **useEffect-for-events smell:** wizard step transitions or submit reacting via `useEffect(() => {...}, [step])` instead of explicit callback handlers (CLAUDE.md FE rule — always wrong here).
- **Conditional unmount of wizard state:** ternary-rendering steps (`{step===1 ? <A/> : <B/>}`) that destroys hook state mid-flow — use internal branching / CSS hidden.
- **Badge mislabel:** an OVERRIDDEN entity rendered as INHERITED (or vice-versa) — the badge must reflect the actual `entity_override` / base-vs-delta source, not a guess.
- **Auto-insert reference:** source chapters auto-pasted into the derivative instead of read-only adaptable reference (LOCKED violation).
- **Screenshot gap:** unit-only green with no Playwright shot proving the UI actually renders the banner + badges.
- **localStorage drift:** wizard progress / derivative state stored only in localStorage instead of server (server is SSOT).

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR iff: only composition/writer FE + `scripts/raid/verify-cycle-24.sh` changed; wizard is 4 steps ending in `POST /works/{id}/derive`; banner + INHERITED/OVERRIDDEN badges present with legend; reference spine read-only (no auto-insert); Playwright screenshot filed; NO BE schema/API change, NO packer/critic/flywheel/living-world logic. Otherwise BLOCKED.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — **C24** row (dị bản M1).
- OPEN_QUESTIONS_LOCKED.md — **dị bản locks** (taxonomy = UX §7.1, override scope = entity fields + canon rules, reference spine read-only, ownership), **§G2** (INHERITED base vs OVERRIDDEN delta), **§G3** (chapter-level branch_point), **Architecture-review locks**.
- `docs/specs/2026-06-13-derivative-works-living-world-plan.md` — dị bản M1.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **2-layer badges (G2):** INHERITED = base (source project ≤ branch); OVERRIDDEN = delta. The badge MUST reflect real override state, never a guess.
- 🔴 **Reference spine (LOCKED):** original chapters are **read-only** adaptable reference — NOT auto-inserted. Writer adapts manually.
- 🔴 **FE rules:** wizard step transitions via **explicit callbacks**, NOT useEffect; never conditionally unmount step state (use branching/CSS hidden).
- 🔴 **Acceptance MUST include:** a **Playwright screenshot** of a spawned genderbend dị bản showing banner + badges — unit-green alone is a false pass.
- 🔴 **Do NOT touch:** BE schema/API (C23 owns it); no packer merge (C25), critic (C26), flywheel (C27), living-world (C28).
- 🔴 **Fresh session reminder:** this is a new `/raid 24` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
