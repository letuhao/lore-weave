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
| 1.1 | `list_tool_decisions` + `revoke_tool_decision` + `get/set_tool_decision` in `app/db/tool_approvals.py` (owner-scoped) | [x] | new `decision` column ('allow'\|'deny') makes the two mutually exclusive on the existing PK; `_split_key` decodes the namespaced spend key back to (tool, kind) |
| 1.2 | `GET/PUT/DELETE /v1/chat/tool-permissions[/{tool}]` (JWT, owner from token — never the body) | [x] | **live through the gateway**: grant→200, list→visible, deny→200, revoke→**204**, re-revoke→**404** (no silent success), bogus enum→**422** |
| 1.3 | FE panel: list granted, revoke, **deny** (persistent "never allow") + block-a-tool-never-prompted-for | [x] | `PermissionsView` + `useToolPermissions` (MVC); new Extensions tab; 7 FE tests green; tsc clean |
| 1.4 | Consumed-by-effect: revoke ⇒ next Tier-A call **suspends again**; deny ⇒ call **blocked, never prompts** | [x] | drives the REAL `_stream_with_tools` loop, not a mock. **Negative control passed**: reverting `is_tool_approved` to existence-checking AND disabling the deny branch both go RED; revert → green |
| 1.5 | `/review-impl` + fix | [x] | 41 agents · **35 raised → 27 confirmed, 8 refuted** · **1 HIGH** (found independently by 4 of the 6 reviewers) + 8 MED + 5 LOW, **all fixed in-phase**. Negative control on the fix: re-introducing the exact bug turns 4 tests red; revert → 59 green |

**The HIGH the review caught — I shipped the very bug this slice exists to kill.** I nested
the deny read *inside the prompt-eligibility conditions* (`if tier == "A" and permission_mode
== "write"` / `if tool_paid(...)`). A refusal is not a prompt: the result was that a Tier-R
tool, a plan-mode `plan_*` tool, and a frontend tool were all **listed in my own panel under
"Blocked — never runs" while the agent went on calling them**. My free-text "Block a tool" box
actively invited it, defaulting to the `mutation` axis. That is a *stored-but-unread setting on
a consent surface* — `D-C-ALLOWLIST-WRITE-ONLY` reintroduced wearing the deny hat, in the
commit that closes `D-C-ALLOWLIST-WRITE-ONLY`. A reviewer reproduced it against the real loop.
**Fixed by hoisting the refusal above every execution path** (the frontend-tool suspend, the H7
volume cap, the hook's `require_approval` arm, and the tier/mode gate), because a card the user
can click "Always allow" on would otherwise let one click silently overwrite a permanent refusal.

Other confirmed fixes: the mutation fail-OPEN degrade **turned a DENY into an ALLOW on any DB
read error** (now degrades to *prompt* — unknown must resolve to ask, never to run) · the resume
path never re-checked the decision, so a **stale approval card executed a since-denied tool and
`approved_always` overwrote the refusal** · `tool_name` was unvalidated, so `spend::web_search`
**forged a consent on an axis the caller never named** · an omitted `decision` **silently
created a GRANT** · the panel's free-text box let a typo create a phantom "Never runs" for a
tool that does not exist (now catalog-backed) · a stale-response race could repaint the consent
list with a decision the user had already changed · the eval fixture **deleted decisions it did
not create — it could erase a user's standing DENY** · the consent copy shipped English-only
(now all 18 locales).

**The defect, made visible.** The live smoke's first call is the whole argument for this
slice: the test account was already carrying **36 standing "Always allow" grants** —
including `glossary_entity_delete` and `glossary_ontology_delete` — accumulated across
three days of eval runs. Every one of them was invisible and permanent. Nobody granted
them on purpose; they were clicked through, once, and then owned the account forever.

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
| 4.2 | S00d mode→capability binding (the mechanism shipped — this is its *scenario*) · **S00e permission UI — MUST block a real tool call in a real LLM turn** (Phase 1 proved the mechanism + the HTTP surface; it did NOT prove the journey — see drift DR3) | [ ] | |
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
| D1 | **Model deny as a `decision` COLUMN on `user_tool_approvals`, not a second table.** | allow and deny are mutually exclusive answers to one question. One row per (user, tool, kind) on the existing PK makes contradiction *unrepresentable*; two tables would let both exist and force a precedence rule nobody would remember. Pre-existing rows were all grants, so the `DEFAULT 'allow'` backfill is exactly right. | yes (drop column) | |
| D2 | **Rename `approval_check` → `decision_check` instead of keeping the name and widening the return type.** | The return went `bool` → `'allow'\|'deny'\|None`. A leftover `bool(await approval_check(...))` would evaluate the string `"deny"` as **True** and silently invert a refusal into a grant — the worst possible failure for a consent gate. Renaming makes every un-migrated caller a loud `TypeError`. Cost: touched ~20 test sites. | yes | |
| D3 | **The approval CARD keeps its one-shot "Deny"; the persistent deny-list lives in the panel.** | The spec locates deny in the management surface ("the Claude-Code `/permissions` analogue"). Adding a 4th button to the card is an FE contract change to a component the concurrent session may be touching, for a capability the panel already provides in full. | yes (additive) | ⚠ NEEDS-PO-REVIEW — the natural moment to say "never" is when you are being *asked*. If you want "Never allow" on the card itself, it is ~8 lines of backend (`denied_always` outcome) + a button. |
| D4 | ~~Deny fails OPEN on a DB read error.~~ **REVERSED by /review-impl.** An unreadable decision now degrades to a **PROMPT**, never to a grant. | My original reasoning was wrong and the review proved it: the *same* read now carries the user's standing refusal, so "assume allow on error" lets a transient DB fault **execute a tool the user permanently denied**. An unreadable decision is UNKNOWN — and unknown must resolve to *ask*, never to *run*. DR-C2's original intent survives (a card is raised; tool calling is not bricked); what is gone is a DB error's ability to invent a grant nobody gave. | yes | This intentionally changes DR-C2's documented fail-OPEN. Cost: inside a subagent (which cannot raise a card) a DB blip now returns an error instead of auto-committing — correct, but noted. |
| D6 | **ANY deny row blocks the tool, whatever consent axis it was recorded under.** | The alternative (mutation-deny blocks always, spend-deny blocks only paid tools) leaves a dead corner: a spend-deny on a free tool would be a setting that GETs back as effective and does nothing — the exact write-only-behavior bug. The user was shown the words "Never allow"; a consent surface must mean them. Follows through to the UI: the block form has **no axis selector** (a block is tool-level), so nobody can pick the axis that does nothing. | yes | |
| D7 | **The tool-name is validated against the real catalog in the FE (picker), not in the PUT route.** | A route that hard-depends on knowledge-service being up to save a *setting* is a worse failure mode than a typo, and a deny on a not-yet-existing tool is legitimately useful. The route enforces the charset invariant (`::` rejected — that one is a real forgery vector); the panel prevents the typo at source. | yes | ⚠ NEEDS-PO-REVIEW — a reviewer wanted a 422 on an unknown tool at the route. I judged the availability cost higher than the benefit. |
| D5 | **Left the concurrent session's RED test alone** (`test_stream_service_story04::test_emit_chat_turn_persists_dirty_activation_state`). | Proven not mine: my diff adds **zero** lines to that write path, and the failing assertion is against SQL introduced by *their* commit `3f3856e92` (`persist_capture_status` now lands after the `activated_tools` write; the test asserts on the LAST `pool.execute`). Shared-checkout invariant #9: flag, don't touch. | n/a | 🚩 flagged to PO — theirs to fix (one-line: assert over the call list, not the last call) |

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
| DR1 | **I wrote the deny tests, saw them pass, and almost moved on.** A passing test proves nothing about whether it *could* fail. | Ran a real negative control: reverted `is_tool_approved` to the legacy existence-check AND disabled the `_denied_kinds` branch. Both went RED; revert → green. Only then did I count them. |
| DR2 | **My live smoke silently mutated the shared test account.** `book_create` was a *pre-existing* grant; my revoke step deleted it. I had already typed the summary sentence "fixture clean" before noticing the baseline count was 36 and my final read said 35. | Restored it (back to 36, 0 denies). Left un-fixed, a later S06 run would have suspended on `book_create` and I would have burned an hour debugging a ghost I created. |
| DR3 | **I nearly accepted "the unit test drives the real loop" as sufficient proof for the deny gate**, and skipped a live agent-loop check. | Kept the unit proof (it *is* the real loop + a negative control), but did NOT let it stand in for the live scenario: **S00e** ("view / revoke / deny an allowlisted tool") is now an explicit Phase-4 slice that must block a real tool call in a real LLM turn. The mechanism is proven; the *journey* is not, and I am not calling it proven. |
| DR4 | **The FE error path was a real bug my own test caught**, and my first instinct was that the test was too fussy. | It wasn't: `refresh()` clears `error` on entry, so setting the error *before* the resync wiped the only signal the user gets that their revoke failed. They would have seen the old row and assumed it was fine. Fixed the ordering. |
| DR5 | **The biggest one: I was about to commit Phase 1 as "done" with the HIGH still in it.** My own tests were green, my own live smoke was green, my negative control passed — and the deny gate was still unenforced for every tool that does not raise a card. I had *written* the invariant "no silent no-op / a stored-but-unread setting is a bug" at the top of this very file, and then shipped one. | The `/review-impl` is what caught it — 4 of 6 reviewers independently, one reproducing it against the real loop. This is the whole argument for the per-phase review being **mandatory and self-invoked** rather than a thing I do when I feel unsure. I felt *certain*. Green tests measured what I thought to check; the review measured what I forgot to. |
| DR6 | **I nearly "fixed" 5 red tests by bending them to the new behavior without asking whether the behavior was right.** They failed because they asserted the OLD contract (`check.assert_not_awaited()` for Tier-R; "fails open" on a DB error). | Stopped and re-derived each one from the requirement, not from the diff. Two were legitimately obsolete (the refusal *must* now be read for every tool). One — `test_allowlist_read_error_fails_open` — encoded a contract I was *deliberately reversing*, so I rewrote it under a name that states the new rule and says why, rather than quietly deleting the assertion. |
| DR7 | **A concurrent session committed my in-flight migration inside one of their commits** (`689bd8498`, "fix(distiller): audit findings") — they staged `migrate.py` wholesale while my `decision` column sat in the working tree. | Nothing to undo (the code is correct and in history), but it is the shared-checkout hazard biting in the *other* direction, and it is why I hand-staged this commit file-by-file instead of by directory. Their day-window/session tests are currently red from their own in-flight edits; I flagged them and did not touch them. |

## 10. Completeness ledger (filled at the end — the honest scorecard)

| Deliverable | Claimed | Verified how |
|---|---|---|
| WS-3 binding | | |
| WS-3 permission-management UI | | |
| WS-3 MCP whitelist | | |
| WS-5 workflow catalog (13) | | |
| WS-7 scenarios (13) | | |
| **DoD: S06 ❌→✅** | | |
