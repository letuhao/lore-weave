# First-release readiness, and the GUI-parity metric

Reconciles: MCP Tool I/O Standard · Agent GUI Reconciliation (09) · Non-Vacuity (NV-1..6). Follows
[`2026-09-04-regression-fix-plan.md`](2026-09-04-regression-fix-plan.md), whose goal is met — the
writing loop works and a five-chapter run proved it. **This plan is about what that run did NOT
cover**, plus a new invariant the owner asked for.

---

## 0. The new invariant, in the owner's words

> *"we need a new metric that FE should have ability to help user fix llm weakness by edit manually
> on gui, so we avoid to ship feature that user cannot use and agent is dumb"*

**Every capability the agent can attempt must have a manual GUI path to the same effect.** When the
model fails at something — and it will, this month's runs measured three separate ways it loses an
author's chapter — the user must be able to finish the job by hand. A feature reachable *only*
through an unreliable agent is a feature that does not work.

🔴 **This repo has already paid for the narrow version of it.** LOOM M9 shipped a gate that disabled
Publish until every composition scene was `status='done'` — and the FE had **no control to mark a
scene done**. The backend was correct, the units passed, and the live smoke went green because it
PATCHed the status via curl. Every composition-enabled book got a permanently-disabled Publish
button. The generalisation is the metric below.

---

## 1. What is already measured, so this plan does not re-litigate it

| | |
|---|---|
| the writing loop | **works** — 5 chapters, 4,611 words, zero empty |
| lost-work defects | three shapes (refused / failed / never-attempted), all fixed and bitten |
| creates carrying the prose | **5/5** post-fix, against 4/11 before |
| consent | the Tier-A card held on every write across ~30 turns; P16 never broke |
| the long-form path | `generation_job` **461/465 completed**, last today — the scene engine is real |
| the write surface | **93 Tier-A + 35 Tier-W** tier declarations across the Go MCP servers |

⚠️ **And the honest limit on all of it: one user, one local model (Gemma-4 26B on localhost), ~30
turns.** That is not a release measurement, and this plan should not pretend it is.

---

## 2. The GUI-parity metric — definition, because a vague one is unfalsifiable

**Denominator.** Every **LIVE** write-tier tool (Tier A, Tier W). *Deprecated tools are dead and are
excluded from the count* — a census over the catalogue including them over-reports the problem.

**Numerator.** Those with a **declared and mechanically checked** UI affordance: a route plus a
`data-testid` that a gate greps for in `frontend/src`.

🔴 **The `data-testid` is the whole design, and it is what stops this becoming theatre.** A parity
record that only says *"the editor covers this"* is a claim in a document, and this repo's standing
rule is that a claim in a docstring is not the thing it claims. A record naming a testid that no
longer exists goes **RED** — so the metric decays loudly instead of silently.

**Three honest outcomes per tool, and the third is not a failure:**

| verdict | meaning |
|---|---|
| `UI` | a named control achieves the same effect by hand |
| `NONE` | **the gap this metric exists to find** |
| `AGENT-ONLY (declared)` | deliberately has no manual path — with the reason written in |

`AGENT-ONLY` is real: "run a grounded multi-scene generation" has no hand equivalent, and pretending
it needs one would be dishonest. But it must be **declared and argued**, never a silent `NONE`.

---

## 3. Board

- [ ] **P1** — **READ ONLY.** The parity census: enumerate LIVE Tier-A/W tools from the servers'
  own declarations (not a hand list), and for each record `UI` (route + `data-testid`) / `NONE` /
  `AGENT-ONLY`. Output a single number and the `NONE` list. **Decide the rest of this plan from what
  it returns** — scoping the fixes before the count is exactly the guess this repo forbids.
- [ ] **R1** — **the new-user run.** A fresh account with NO pre-seeded models, driven through the
  real UI: what does a stranger actually get? $0, touches nothing existing. **The cheapest check on
  this board and the one most likely to change the release answer.**
- [ ] **P2** — the gate in `scripts/`, with the baseline at whatever P1 measured and the reason
  written in. **NV-1..6 applies: bite it.** Delete a `data-testid` the census depends on and watch
  it go red for the right reason; restore byte-exact. A parity gate that cannot fail is worse than
  no gate, because it reports coverage and silences review.
- [ ] **P3** — close the `NONE` gaps P1 finds, ranked by how often the agent actually fails at that
  tool. **Not scoped until P1 lands** — the list does not exist yet, and inventing rows for it now
  would be a plan built on a guess.
- [ ] **R4** — two concurrent sessions on one account, and a slow-provider run. Both are unmeasured;
  the blank bubble I fixed today came from the local model 500ing under my own load, and I do not
  know how that path behaves when a provider is merely slow rather than broken.
- [ ] **R5** — housekeeping: this all lives on `refactor/kal-and-mcp-runtime`, unmerged; PR #219's
  body is stale; 5 pre-existing FE reds in `DefaultModelsCard.test.tsx` and 18 in `scripts/`.
- [ ] **D3** — **STOP CONDITION.** `platform_models` is **empty (0 rows)**. The same fact that made
  every run this month provably $0 means **a brand-new user with no API key has no model at all**.
  What does a first-release user run on — a platform-provided model, BYOK-required onboarding, or a
  trial? Product decision, owner's call, and it gates R1's interpretation.
- [ ] **D4** — **STOP CONDITION.** One cloud-model run to cover the path most users would take.
  Everything proven this month was proven on a local model. **This costs money and needs an explicit
  yes plus a stated call count before it runs.**

---

## 4. Order, and why

**P1 and R1 first, together** — both are read-only or $0, and both produce numbers that decide
everything after them. P1 without its census is unscopeable; R1 is the cheapest thing on the board
that could change the release verdict.

Then **P2** (the gate, so the number cannot rot), then **P3** (the gaps it found).

**R4/R5 last.** **D3 and D4 are the owner's**, and D3 gates how R1's result should be read: a
stranger having no model is only a defect if the answer is "the platform provides one".

**RESUME: P1 — the parity census, read-only: every LIVE Tier-A/W tool, and the route + `data-testid` that lets a human do it by hand**

---

```goal-prompt
goal: every agent-attemptable write has a manual GUI path, measured by a gate that can go red — and the first-release gaps are measured rather than assumed
po_decisions: [D3, D4]
rules: |
  1 $0 unless the owner says otherwise. Local models only; a PAID run needs an explicit yes and its CALL COUNT stated first. platform_models is EMPTY, so there is no accidental paid fallback - keep it that way.
  2 Content-creating runs use a NEW throwaway book, never the dogfood book.
  3 Verify the DEPLOYED IMAGE before believing any live result. A green build log is not a rebuilt container, and check a whole-file property, not just the symbol you added.
  4 P1 is a READ. Decide P3's scope from what it returns; a fix list invented before the census is a guess.
  5 The parity census counts LIVE tools only. Deprecated tools are dead - out of every count, not just every fix.
  6 A parity record must name a data-testid or route a gate can GREP. A record that only asserts "the editor covers this" is a claim in a document, and this repo does not accept those as evidence.
  7 AGENT-ONLY is a legitimate verdict and must be DECLARED with its reason. A silent NONE dressed as agent-only is the failure this metric exists to catch.
  8 NV-1..6 on P2: break the guarded thing, watch it go red for the RIGHT reason, restore byte-exact, paste both outputs. A gate that cannot fail is worse than no gate.
  9 A ratchet or baseline moves in the SAME COMMIT as the code that moved it, with the reason written in.
  10 Attribute a red thing before fixing it - 5 FE and 18 scripts/ failures are already known to pre-date this work.
discipline: |
  Numerator and denominator must measure the same population - stratify before pooling.
  Verify the pointer before declaring evidence missing, and grep for the route before blaming a service.
  A pending Tier-A card reads as a hung turn on a database poll: watch outcome='awaiting_input' too.
  sed -i rewrites every line ending on this repo's CRLF files - edit with Python or Edit, and check cmp AND git diff --stat after a bite.
stop: |
  a write would touch a non-throwaway book or database
  a run would call a model that is not local
  a product decision is owed: D3, D4
  a sealed decision turns out to be wrong
```

---

## 5. What this plan deliberately does NOT claim

That the writing loop is unfinished — it works, and the previous plan's five-chapter run proves it.
That the composition path is untested — **461 of 465 generation jobs completed**, and I checked
before writing that down rather than assuming it. And that GUI parity is currently bad: **nobody has
measured it**, which is P1's entire point. The number could be 90% or 40%, and inventing an
expectation before the census would be the same defect as scoping P3 today.
