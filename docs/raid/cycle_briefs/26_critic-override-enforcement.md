# Cycle 26: Critic override enforcement (composition)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** **dị bản M3.** Add a **derivative critic dimension** to the composition critic: when critiquing a derivative Work's generated scene, **enforce the active `entity_override[]` + added canon rules** (the override must hold — e.g. a genderbent character isn't slipped back to canon) **and internal consistency** within the delta. The critic flags an **override slip** as a critique finding. BE unit cycle.
- **Acceptance gate:** `scripts/raid/verify-cycle-26.sh` exits 0
- **Top 3 LOCKED decisions consumed:** override scope (entity fields + canon rules, M0), G2 (delta partition = the consistency frame), override-at-retrieve (the enforced overrides are the same ones the packer applies)
- **DPS count:** 1
- **Estimated wall time:** 2–3h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C25
- Files expected to exist (grep-able paths): the composition critic dimension framework; the packer override-merge path (C25) that resolves the active `entity_override[]` + canon rules for a derivative; `composition_work.source_work_id`/`entity_override`/`divergence_spec` (C23).

## Scope (IN)
- **Derivative critic dimension:** a new critic check that activates only for derivative Works (those with `source_work_id`). It loads the **same active `entity_override[]` + added canon rules** the C25 packer resolves and verifies the generated scene **honours them** — an overridden entity field that reverts to its canon/base value is an **override slip** finding.
- **Internal consistency within delta:** the dimension also checks the scene against the derivative's own delta grounding (no contradiction with already-established delta facts).
- **Override-slip finding:** structured critique output naming the slipped override (entity + field + expected-vs-found) so the writer/regeneration loop can act on it.
- `scripts/raid/verify-cycle-26.sh` (acceptance gate) — asserts the critic flags an injected override slip and passes a compliant scene.

## Scope (OUT — explicitly)
- **NO override resolution logic** — C25's packer owns reading base+delta + applying `entity_override`. The critic **reuses** that resolution; it does not re-implement the merge.
- **NO schema/migration** (C23), **NO packer changes** (C25).
- **NO delta flywheel / what-if promotion** (C27), **NO living-world FE** (C28), **NO wizard/studio FE** (C24).
- NO relationship/event override enforcement (M0 = entity fields + canon rules only).
- NO new AI/provider imports in composition (LOCKED: composition has no AI imports).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: derivative critic dimension unit tests (`services/composition-service/.../test_critic_override*.py`) — flags an injected override slip, passes a compliant scene, checks delta internal consistency.
- Lints pass: composition linter; provider-gate green (no AI imports in composition).
- Integration smoke: **BE unit** is the verify for this cycle (per CYCLE_DECOMPOSITION C26 — verify: critic flags an override slip). No live cross-service token required; evidence string carries `unit: derivative critic flags override slip + passes compliant scene`.

## DPS parallelism plan
- DPS 1: **Derivative critic dimension** — activation on `source_work_id`; load active overrides + canon rules via the C25 resolution path; override-slip detection (entity+field expected-vs-found); delta internal-consistency check; structured finding output; unit tests covering slip + compliant + consistency. (return budget: 1500 tokens summary)

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Dimension never fires:** the new check wired but not actually invoked at the critique call site (the nil-tolerant-decorator bug class — add a wiring test asserting it runs for derivatives, else it silently no-ops while tests stay green).
- **Re-implementing the merge:** the critic computing overrides independently instead of reusing C25's resolution → two sources of truth that drift.
- **False positive on base entities:** flagging an INHERITED (non-overridden) entity as a slip — only overridden fields are enforced.
- **Activates on canon Works:** the derivative dimension firing on a non-derivative (no `source_work_id`) Work → spurious findings.
- **Scope creep:** enforcing relationship/event overrides (deferred) rather than entity-field + canon-rule only.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR iff: only the composition critic dimension + tests + `scripts/raid/verify-cycle-26.sh` changed; the dimension activates only for derivative Works, reuses C25's override resolution (no re-merge), flags override slips + checks delta consistency, has a wiring test proving it fires; NO schema/packer change, NO flywheel/living-world/FE, NO new override types, NO AI imports. Otherwise BLOCKED.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — **C26** row (dị bản M3; derivative critic enforces overrides + internal consistency).
- OPEN_QUESTIONS_LOCKED.md — **dị bản locks** (override scope M0 = entity fields + added canon rules), **§G2** (delta partition is the consistency frame), **Architecture-review locks** (override resolution provided by C25; composition has no AI imports).
- `docs/specs/2026-06-13-derivative-works-living-world-plan.md` — dị bản M3.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Reuse, don't re-merge:** the critic loads the **same active overrides** the C25 packer resolves — never re-implement override resolution (two-sources-of-truth drift).
- 🔴 **Wiring test (anti-no-op):** add a test asserting the dimension actually FIRES for derivative Works — a wired-but-uninvoked check passes all other tests while silently doing nothing.
- 🔴 **Scope (LOCKED):** enforce **entity-field + added canon-rule** overrides only; relationship/event overrides are deferred.
- 🔴 **Acceptance MUST include:** the critic **flags an injected override slip** AND passes a compliant scene — both branches.
- 🔴 **Do NOT touch:** schema (C23), packer (C25), flywheel (C27), living-world (C28), wizard FE (C24); no AI imports in composition.
- 🔴 **Fresh session reminder:** this is a new `/raid 26` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
