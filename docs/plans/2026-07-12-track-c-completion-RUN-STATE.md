# RUN-STATE — Track C completion (autonomous run)

> ## 📌 READ THIS FILE FIRST after any compaction, and at every checkpoint.
> This file — not my memory of the conversation — is the source of truth for the run.
> Context is lossy. Disk is not.

**Started:** 2026-07-12 · **Branch:** `feat/context-budget-law` · **Mode:** long autonomous run, self-checkpointing.
**Audit that scoped this run:** [`TRACK-C-AUDIT.md`](../specs/2026-07-09-agent-discoverability-and-workflow/tracks/TRACK-C-AUDIT.md) (every claim verified against code) ·
**Track brief:** [`TRACK-C.md`](../specs/2026-07-09-agent-discoverability-and-workflow/tracks/TRACK-C.md) ·
**Contracts (frozen):** [`contracts.md`](../specs/2026-07-09-agent-discoverability-and-workflow/contracts.md)

---

## 1. The goal (one sentence)

**Finish Track C: close the consent defect, make the flagship S06 actually ship, author the buildable
workflow catalog, and build the user-facing surfaces — every phase `/review-impl`-clean, nothing marked done
without observed behavior.**

## 2. Autonomy contract (agreed with PO 2026-07-12)

| | Rule |
|---|---|
| **Don't stop** | Work continuously through the phases. No pause for approval between slices or phases. |
| **Self-checkpoint** | I checkpoint myself (commit + update this file). **No human gate.** The PO is not watching and will not confirm anything mid-run. |
| **`/review-impl` per phase** | **Mandatory, self-invoked.** Findings are **fixed in the same phase**, not deferred. A phase is not done until its review is clean. |
| **I decide** | Every ordinary technical decision is mine. Record it in §6 with the reasoning, so the PO can review the *set* at the end. |
| **Blocked ≠ stop** | If I cannot solve something: **park it in §7, move to other work, keep going.** A blocker becomes a Deferred row, not a full stop. |
| **STOP only if** | A **critical blocker that blocks ALL of Track C** and genuinely needs a human decision — or an action that is destructive/irreversible or risks real user data. Nothing else. |
| **Cannot decide?** | Do not stall. Make the **best reversible call**, ship it, and log it in §6 flagged `⚠ NEEDS-PO-REVIEW` with the alternatives. The PO adjudicates at the end. |
| **Final audit** | Decisions · parked · debt · drift · completeness (§6–§10), built incrementally so the audit is a *byproduct*. |

## 3. Standing invariants (the bar — never lower these silently)

1. **A slice is DONE only when its evidence string exists in §5.** Compiling is not done. Green units are not
   done. **Evidence = the behavior was observed.**
2. **Ground truth beats self-report.** For any scenario claim, the proof is a **DB query on a fresh, provably
   empty book** — never the agent's own words, never the tool-call log. (S06's entire history is a lesson in
   this: it once "persisted" nothing while claiming it had.)
3. **Live-smoke any slice touching ≥2 services.** Unit-green has hidden cross-service bugs repeatedly here.
4. **Verify the code is IN the container before believing a live run.** A silently-failed `docker build`
   already made one "WS-3" run a lie this week (`grep` the running container).
5. **No silent no-op / no silent success** — a success with no work done is a bug; a truncation, a dropped
   pin, an unknown enum value must **log**.
6. **Consumed-by-effect** — a setting/flag gets a test asserting the *behavior*, not the stored value.
7. **Tenancy**: every new row carries a scope key; System-tier is admin-seeded + read-only to users.
8. **A test that cannot fail on its own bug class is worse than none** — ship a negative control. (The
   migration lint shipped tautologically green.)
9. **Never `git add -A`** — enumerate files. This checkout is **shared with concurrent agent sessions**; a
   red test in someone else's file is theirs to fix (flag it, don't touch it).
10. **Grep before trusting any list** — including this one. The audit found 2 of 3 defer rows already stale.

## 4. The DoD bar for the flagship (S06) — defined up front so it cannot be softened later

S06 is the track's Definition of Done. It **passes** only when, on a **fresh, provably empty book**
(0 kinds / 0 entities / 0 chapters, verified by SQL *before* the run):

- **≥ 4 of 5 artifacts** exist in the DB afterwards — world categories · cast entities · connections
  (kg project+nodes) · arc plan · a drafted chapter — **in ≥ 2 of 3 consecutive runs** (the variance is the
  adversary: a single lucky run is not a pass);
- **0 forbidden vocabulary words** reach the user (the §1 list: workflow, glossary, ontology, entity, kind,
  attribute, schema, spec, NovelSystemSpec, PlanForge, pipeline, engine, job, token, any tool name);
- **0 false-persistence claims** (`persist_claims_without_write == []`);
- **0 async jobs left unpolled**.

If S06 cannot reach this bar, that is **not** a reason to stop — park the residual in §7 with the measured
numbers and continue. A partial, honestly-measured flagship beats a stalled run.

---

## 5. Slice board — `[ ]` todo · `[~]` in flight · `[x]` done (needs an evidence string) · `🅿️` parked (§7)

### Phase 1 — the consent defect (`D-C-ALLOWLIST-WRITE-ONLY`, HIGH) — do this FIRST
> A user grants an autonomous agent a standing "Always allow" on a tool and can **never see it or take it
> back**. `tool_approvals.py` has `is_tool_approved` + `approve_tool` and nothing else. A consent mechanism
> with no withdrawal is broken by design. It is small, and it is the one item I would not ship without.

| # | Slice | Status | Evidence |
|---|---|---|---|
| 1.1 | `list_approvals` + `revoke_approval` in `app/db/tool_approvals.py` (owner-scoped) | [ ] | |
| 1.2 | `GET /v1/chat/tool-approvals` + `DELETE /v1/chat/tool-approvals/{tool}` (JWT, owner derived from token — never the body) | [ ] | |
| 1.3 | FE panel: list granted tools, revoke one, **deny** (a persistent "never allow") | [ ] | |
| 1.4 | Consumed-by-effect test: revoke ⇒ the next Tier-A call **suspends for approval again** (assert the behavior, not the row) | [ ] | |
| 1.5 | `/review-impl` + fix | [ ] | |

### Phase 2 — the flagship blocker: nothing DRIVES the rail (the DoD)
> Post-WS-3 the mechanism is done: discovery is dead (0 `find_tools`), the assent lands on the rail, the step
> tools are advertised (even across a confirm gate), and errors are honest enough to drive self-correction.
> What is missing is that the **model must hold a 12-step recipe across a 17-turn conversation** while doing
> the emotional work of the scene — and it drops it. Measured: kinds 5/12/0/5 · entities 0/0/0/0 · plan 0/1/0/0.

| # | Slice | Status | Evidence |
|---|---|---|---|
| 2.1 | **Spec** the rail driver: server-side progress ("you are at step N; N−1 succeeded; the next call is X") + **book-state grounding** (answer "what is already done?" from the SSOT, not from memory) | [ ] | |
| 2.2 | Book-state probe — cheap, cached per turn: categories/cast/connections/plan/chapters counts for the pinned rail's book | [ ] | |
| 2.3 | Rail progress state + the next-step directive rendered into the pinned block | [ ] | |
| 2.4 | S06 re-run ×3 on fresh empty books; DB ground truth each time | [ ] | |
| 2.5 | Residual jargon (`D-C-JARGON-PLANFORGE`): give the plan_forge skill prose + tool descriptions a vocabulary owner | [ ] | |
| 2.6 | `/review-impl` + fix | [ ] | |

### Phase 3 — the workflow catalog (WS-5): 8 buildable rails, every backing tool already exists
| # | Slice | Status | Evidence |
|---|---|---|---|
| 3.1 | **W2** populate-from-seed-doc · **W4** kg-build · **W5** translation-pass · **W9** canon-check | [ ] | |
| 3.2 | **W7** end-to-end build-a-book · **W12** autonomous drafting · **W6** chapter-compose | [ ] | |
| 3.3 | Fixtures for S04 (active lore + 0 prose) and S05 (partial translation coverage) — **buildable, NOT blocked** (the old "fixture blocked" note did not survive the audit) | [ ] | |
| 3.4 | Run S04 · S05 · S09 to ground truth | [ ] | |
| 3.5 | `/review-impl` + fix | [ ] | |

### Phase 4 — scenario coverage (WS-7): the cross-cutting + remaining journeys
| # | Slice | Status | Evidence |
|---|---|---|---|
| 4.1 | S00a `tool_list` deterministic · S00b `tool_load` progressive · S00c workflow runner honors gates | [ ] | |
| 4.2 | S00d mode→capability binding (the mechanism shipped — this is its *scenario*) · S00e permission UI (needs Phase 1) | [ ] | |
| 4.3 | S07 end-to-end build-a-book · S06b compose deep-dive | [ ] | |
| 4.4 | `/review-impl` + fix | [ ] | |

### Phase 5 — the user-facing surfaces (the half of Track C that is genuinely unbuilt)
| # | Slice | Status | Evidence |
|---|---|---|---|
| 5.1 | **Workflow rack** — see + run the curated workflows (consumer of `workflow_list`) | [ ] | |
| 5.2 | **Binding UI** (`D-WS3-BINDING-GUI`) — edit the mode→capability profile; effective value **+ source tier** shown | [ ] | |
| 5.3 | **W8** intent-branching onboarding fork (Write / Build a world / Translate / Explore) | [ ] | |
| 5.4 | **W10** world-container surface · **W11** reader/lore-seeker surface (Track B's backends are shipped) | [ ] | |
| 5.5 | `/review-impl` + fix | [ ] | |

### Phase 6 — close out
| # | Slice | Status | Evidence |
|---|---|---|---|
| 6.1 | Final audit: decisions · parked · debt · drift · completeness (§6–§10) | [ ] | |
| 6.2 | Update `TRACK-C-AUDIT.md`, the BOARD, `_INDEX.md`, `SESSION_HANDOFF.md` | [ ] | |
| 6.3 | The PO decision packet — every `⚠ NEEDS-PO-REVIEW` from §6 + every parked item from §7, each with my recommendation | [ ] | |

---

## 6. Decision register (I decide; the PO reviews the set at the end)
> Anything I could not confidently decide is shipped as the **best reversible call** and flagged
> `⚠ NEEDS-PO-REVIEW` with the alternatives — never stalled.

| # | Decision | Reasoning | Reversible? | Flag |
|---|---|---|---|---|
| | | | | |

## 7. Parked register (blocked → a Deferred row, NOT a stop)

| ID | What | Why parked (which defer gate) | What would unblock it | My recommendation |
|---|---|---|---|---|
| | | | | |

## 8. Debt register (things I knowingly leave imperfect)

| ID | Debt | Why acceptable now | Trigger to fix |
|---|---|---|---|
| | | | |

## 9. Drift log — the near-misses
> **A run that ends with an empty drift log is not clean — it is dishonest.** Record every time I was about to
> lower the bar: a green unit test I nearly took as behavioral proof, a live-smoke I nearly skipped, a defer
> row I nearly wrote for a one-line fix.

| # | Where I nearly lowered the bar | What I did instead |
|---|---|---|
| | | |

## 10. Completeness ledger (filled at the end — the honest scorecard)

| Deliverable | Claimed | Verified how |
|---|---|---|
| WS-3 binding | | |
| WS-3 permission-management UI | | |
| WS-3 MCP whitelist | | |
| WS-5 workflow catalog (13) | | |
| WS-7 scenarios (13) | | |
| **DoD: S06 ❌→✅** | | |
