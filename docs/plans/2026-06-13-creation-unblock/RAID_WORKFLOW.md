# Creation-Unblock — RAID Workflow (per-task pointer)

This task uses the canonical RAID spec without amendment:

➡ **[../../raid/RAID_WORKFLOW.md](../../raid/RAID_WORKFLOW.md)**

## Task-specific parameters
- **task_id:** `creation-unblock` · **slug:** `2026-06-13-creation-unblock`
- **Branch:** `feat/auto-draft-factory-gaps`
- **Cycles:** C0–C28 (29 total; knowledge phase re-planned to the 2026-04-13 design draft after a backend audit; build wizard split into C12 target-typed + C13 pinning) — see [CYCLE_DECOMPOSITION.md](CYCLE_DECOMPOSITION.md).
- **bootstrap_cycle:** C0 (shared FE foundation: FormDialog scroll + AddModelCta + capability-string reconcile; smoke gates C0→rest).
- **Quota profile:** [../../../contracts/raid/quota-profile.yaml](../../../contracts/raid/quota-profile.yaml).
- **Locked constraints + open gates:** [OPEN_QUESTIONS_LOCKED.md](OPEN_QUESTIONS_LOCKED.md) · pre-flight [PRE_FLIGHT_CHECKLIST.md](PRE_FLIGHT_CHECKLIST.md).

## Task-specific notes
- **Run posture (locked G4): FULL autonomy C0→C28 in one invocation**, no mid-run human gate (halts only on
  escalation/quota/cost/secret). Design is fully cleared (G1–G5 + knowledge cycle design all locked).
- **Live UI smoke = Playwright MCP screenshots** (test account `claude-test@loreweave.dev`): every FE cycle +
  each milestone (M1–M6) is verified by driving the running FE and capturing a screenshot as VERIFY evidence.
- **Cross-service / live-smoke cycles** (real API live-smoke at VERIFY, *plus* a Playwright shot where a UI
  exists): **C2, C3, C8, C9, C12, C13, C16, C18, C20, C25, C27**. Rebuild touched service images before smoke.
- **Curation flywheel (C9–C11) = integrate, don't duplicate** lore-enrichment + glossary review queues.
- **Milestones:** M-DEMO-1 (C10) write+build-graph end-to-end · M-DEMO-2 (C12) visual graph · M-DEMO-3 (C14)
  world container · M-DEMO-4 (C21) living world.
- **dị bản is copy-on-write** — composition-only schema; no book/glossary/knowledge migration for derivatives.
- **Isolation:** additive/backward-compatible only to shared services; C0 platform-wide changes stay backward-compatible.
- **Provider/model rules (CLAUDE.md):** no hardcoded model names; all model/rerank/embed resolve via
  provider-registry; local-rerank reached only as a BYOK credential. The provider-rule gate must stay green.
