# S8 · P6 PERMISSION + THE HUMAN BOUNDARY — coverage interrogation

**Module:** tier / scope / confirm-token / spend, and every path by which a run reaches a human.
**Against:** `ARCHITECTURE.md` §0.2 (*P6 — "kept unchanged; the spine is sound"*) · §0.3 (the Ceiling Test;
P6 is *"the ONLY legitimate ceiling"*) · §0.4 (plan ≠ execution) · §0.5 (needs-human; *"a model that asks a
question is behaving correctly"*; `awaiting_input` is a SUCCESS state).
**Mode:** coverage, not critique. Two questions: *what does the permission spine exist to solve, and does it
still hold under plans* — and *what will certainly occur that it has no defined answer for.*

**Method.** Read the machinery, not the design's description of it:
`services/chat-service/app/services/stream_service.py` (the deny gate, the combined consent gate, the H7 cap,
the suspend/resume path), `app/db/tool_approvals.py`, `app/db/suspended_runs.py`, `app/db/migrate.py`,
`app/services/tool_plan.py`, `app/services/subagent_runtime.py`,
`sdks/go/loreweave_mcp/confirm_token.go` + `plan.go`, `sdks/python/loreweave_mcp/confirm_token.py`,
`services/glossary-service/internal/api/action_confirm_token.go` + `action_confirm.go` +
`action_confirm_batch.go`, `services/knowledge-service/app/ontology/confirm.py` + `schema_edit_effect.py`,
`services/translation-service/app/mcp/estimate.py`, `services/usage-billing-service/internal/api/guardrail.go`,
`services/mcp-public-gateway/src/**` (`scope/tool-policy.ts`, `approval/approval-client.ts`,
`mcp/public-mcp.controller.ts`, `auth/key-resolver.ts`), `services/auth-service/internal/api/mcp_approvals.go`.

---

## 1 · What the permission spine exists to solve — and the exact shape of its assumption

### 1.1 The four axes, as built

| axis | where | keyed on | lifetime |
|---|---|---|---|
| **tier** | `tool_tier()` R/A/W/S in chat; `TOOL_POLICY` `read`/`paid_read`/`write_auto`/`write_confirm` at the public edge (`tool-policy.ts:18`, 170 entries) | the **tool** | deploy |
| **mode** | `permission_mode ∈ {ask, plan, write}` (`models.py:531`), enforced at advertise (`_filter_tools_for_ask`) *and* at execute (`stream_service.py:3677-3705`) | the **turn** | one turn |
| **standing decision** | `user_tool_approvals(user_id, tool_name, decision)`, `decision ∈ {allow, deny}`, kinds `mutation` \| `spend` (`tool_approvals.py:48-50`, `migrate.py:394-400`) | **(user, tool, kind)** | forever, until revoked |
| **confirm token** | HMAC-SHA256 over base64url claims; three codecs, one scheme (`confirm_token.go:38`, `action_confirm_token.go:32`, `confirm.py:51`) | **(user, resource, descriptor, params)** | **10 minutes**, single-use via a `jti`/hash ledger |

Plus **spend**, which is three unrelated things wearing one word: a per-tool *consent* (`spend::<tool>` row),
a per-user *guardrail* (`spend_guardrails.daily_limit_usd` / `monthly_limit_usd`, `guardrail.go:31-51`), and a
per-**job** *reservation* (`token_reservations`, keyed `job_id`, `guardrail.go:153-157`).

### 1.2 The situation it exists to solve

> A single tool call, issued by an agent acting on a user's behalf, that either **mutates durable state** or
> **spends money**, must not happen without *that* human's assent to *that* call — and the assent must be
> visible, revocable, and impossible to forge or replay.

Every clause of that sentence is implemented, and implemented well. The evidence that it is a *considered*
spine rather than an accreted one:

- **The two consents are orthogonal and separately persisted.** `tool_approvals.py:13` — *"Approving 'may
  write' is NOT approving 'may spend'."* A paid **read** (Tier R) prompts in **ask** mode, where neither the
  tier filter nor the mutation gate reaches (`stream_service.py:3958-3968`).
- **The degrades are asymmetric on purpose.** Mutation fails **open** on a DB blip (a reversible write must not
  brick tool calling); spend fails **closed** (`stream_service.py:3962-3966` — *"irreversible spend → prompt on
  doubt"*). And the standing-**deny** read fails **closed** for any tool with no downstream prompt arm
  (`stream_service.py:3399-3425`), because a non-paid Tier-R read has no second gate.
- **Refusal is ordered above every other arm.** `stream_service.py:3360-3374` places the deny check before the
  frontend-tool suspend, the H7 cap and the `require_approval` hook, with the reason written down: a card the
  user can click *"Always allow"* on would otherwise let one click overwrite a permanent refusal.
- **Consent is withdrawable.** `list_tool_decisions` / `revoke_tool_decision` (`tool_approvals.py:144,170`)
  exist because the table used to be INSERT-only — *"a permission the user cannot see is one they cannot
  withdraw."*
- **The token cannot be re-pointed or replayed.** Params ride *inside* the HMAC (`p`), not as a digest; the
  `jti` is claimed **before** the effect and is **not released** on failure (`action_confirm.go:176-185`);
  authority is re-checked before the `jti` is burned so a stranger cannot burn a victim's token
  (`action_confirm.go:160-161`).
- **Stale cards lose to later refusals.** The resume path re-reads the standing decision because *"a card can
  sit suspended indefinitely… The refusal is the LATER, more deliberate act; it wins"*
  (`stream_service.py:7366-7394`).

This is a sound spine. §0.2's *"kept unchanged"* is defensible **for what it was built for.**

### 1.3 The assumption underneath it — three clauses, all broken by plan/execute separation

Every one of the four axes resolves at **the instant of the call**, against **args that already exist**, with
**a human attached to the turn**. Written as one invariant:

> **One call = one consent decision, taken at the moment of the call, by a human who is present.**

| clause | why plans break it |
|---|---|
| *one call* | a plan is N calls, and the thing the user wants to assent to is the **job**, not each call |
| *at the moment of the call* | plan time ≠ execute time. Between them: a 10-minute token TTL, a revisable plan, and a moving world |
| *a human who is present* | a plan may run for hours, be delegated to a subagent that **cannot ask**, or run on a third-party key whose human is asleep |

**Two structural facts make this concrete, and both are load-bearing for everything in §2:**

1. **A turn has at most ONE suspend point.** The tool loop `break`s out with a single `suspended_call`
   (`stream_service.py:3777`, `:3831`, `:4035`); `chat_suspended_runs.pending_tool_call` is one `{id, name,
   args}` dict. One turn, one question, one answer, done.
2. **`awaiting_input` has exactly one vocabulary, and it is the vocabulary of consent.** The resume branches on
   `outcome ∈ {approved_once, approved_always, denied, denied_always, applied_saved, action_done, accept, …}`
   (`stream_service.py:7334-7364`), with unknown → **denied**. There is no shape for an *answer*. A "no" is fed
   back as `{"error": "denied by user"}`.

And the confirming absence: **`grep -riE "elicit"` across the repo returns zero hits.** §0.5 already says this
(*"no MCP `elicitation` anywhere in the repo"*) — what it does not say is that the built half is not merely
*wired to one thing*, it is **typed** for one thing.

---

## 2 · The Ceiling Test, applied where it actually bites

§0.3 grants P6 the one legitimate ceiling — a *should not*, not a *cannot know*. So the test is not *"is there
a ceiling"* but the two clauses §0.3 attaches to every constraint:

> Every constraint must be **visible to the model** and **appealable by the model**, unless it is P6.
> […] a bound is fine; an **invisible, unappealable** bound is not.

**Is the ceiling in the right place?** At call level — yes. Tier is a property of the declaration, the mode is
the user's own choice, the deny is the user's own act. Under plans — **no**, on one count: the ceiling is
*discovered at step 4, mid-execution, after steps 1-3 have committed.* A ceiling that moves the moment of
refusal to after the irreversible work is in the wrong place regardless of how legitimate the refusal is.

**Is it visible in advance?** **No, on three independent counts, and this is the finding that ties §2 together:**

| what the model cannot see before it plans | evidence |
|---|---|
| **which of its steps will gate** | tier is per-tool and readable, but nothing computes *"this plan will stop for a human at steps 4, 7 and 11"*. C-2 gives a workflow *"the max of its members"* — a scalar. Max tier tells you a gate exists, not where, nor with what |
| **which tools are permanently denied** | the deny is an **execution-time** refusal (`stream_service.py:3426-3444`), not an advertise-time withholding. The denied tool is still on the wire. The planner plans with it |
| **what the job will cost in total** | there is no plan-level estimate anywhere. Cost is per-call, on a card, and (except in translation) never re-checked |

The third one is the sharpest, because §0.1 already has the rule that would fix the second: *"a withholding
that does not register is a defect, not a policy."* A standing deny is the purest possible withholding — the
user has said *never* — and it registers **nowhere** in the advertised/withheld ledger, because it is not
implemented as a withholding at all.

> **P6 under plans does not fail the Ceiling Test on the ceiling. It fails on the visibility clause.**

---

## 3 · Situations with no defined answer

Ranked by severity. Each states the situation, the repo evidence, and what the design would have to say.

---

### S8-1 · CRITICAL — "the user approves A PLAN." Assent to the whole job is not representable.

**The situation.** The design's central act (§0.4: the plan is data, inspectable, revisable) invites the
obvious human gesture: *look at the plan, approve the plan.* Nothing in the system can store that.

**Evidence — assent exists at exactly two extremes, and the plan-shaped middle is missing:**

| existing shape | scope of assent | why it is not plan-assent |
|---|---|---|
| **confirm token** | ONE operation, params frozen in the HMAC | 10-min TTL, single-use, one descriptor |
| **`execute_plan`** (`plan.go:31`, `MaxPlanOps = 50`) — the closest thing in the repo | ONE token, N ops, per-op destructive opt-in via `enabled_ops` | it is a **typed, closed, single-domain op list executed by a deterministic Go executor inside the confirm handler** (`plan_confirm.go` `effectExecutePlan`). *"No LLM, no agent — pure code"* (`2026-06-25-glossary-assistant-planner.md:96`). It is assent to a batch of homogeneous **data ops**, not to an agent's multi-step, multi-service, LLM-driven plan |
| **`confirm-batch`** (`action_confirm_batch.go:111`, `maxBatchChildren = 50`) | N tokens, one card | children must share **one book and one proposer**; still N pre-minted single-op tokens |
| **H7 batch cap** (`stream_service.py:3717-3777`) | "the rest of this turn's writes" | *cap-triggered escalation*, not a declared scope — and its card carries `confirm_token: ""`. A UI gate with **no cryptographic binding at all** |
| **`user_tool_approvals` "Always allow"** | that tool, **forever**, every future plan | the only thing that spans steps, and it is strictly *worse* than plan-assent: unbounded in time, count, amount and context |

**The gap, stated plainly:** the system can express *"yes, this one call"* and *"yes, this tool, forever."*
It cannot express *"yes, this job."* Plan/execute separation makes that middle the **normal** case.

**What the design must add:** a first-class `plan_approval` — bound to a plan **hash/version**, scoped to a
step set, carrying a spend ceiling and an expiry, revocable, and *distinct from* both the per-call token and
the standing allowlist. Without it, the only ways to run an approved plan are to ask N times (S8-2) or to
push the user toward "Always allow" (which converts a bounded assent into an unbounded one — the worst
available outcome, and the one a friction-minimising UI will select).

---

### S8-2 · CRITICAL — the gate at step 4, discovered at step 4.

**The situation.** A 12-step plan whose step 4 needs a confirm token. The user launches it, leaves, and comes
back to a run that stopped three steps in, waiting.

**Evidence.** A turn has one suspend point (`break` out of the loop). A three-gate plan is therefore **three
suspends, three round trips**, each restarting the LLM pass. And nothing computes the gate set in advance:
`tool_tier()` is read *per call, inside the loop*, at `stream_service.py:3715` — after step 3 has committed.

**Why it is not merely a UX complaint.** §0.3 requires a P6 bound to be *visible in advance*. A gate the model
learns about at step 4 is invisible in advance to *both* parties: the model could not plan around it (e.g.
order the gated steps first, or choose an ungated alternative), and the user could not decide about it while
they were still present.

**What the design must add:** a **permission pre-flight** — computed from the plan before step 1, listing every
step that will gate, on which axis (mutation / spend / confirm / denied), with what it will ask. This is
cheap: every input is static declaration data (C-2 `tier`, `_meta.paid`) plus the user's standing decisions.
It is also the direct antidote to S8-1: a pre-flight is exactly the artifact a plan-approval would be taken
against. **Caveat that must be written into the design:** the pre-flight computes *the ask*; it must **not
cache the decision** (see S8-14).

---

### S8-3 · CRITICAL — the plan is revised after approval. *(the key one)*

**The situation.** The user approves a plan. Step 3 fails. §0.5 mandates a transition: `plan-invalid` →
**replan**. The executor now holds a plan the human has never seen, and an approval that points at a plan that
no longer exists.

**Evidence that the design has both halves and never makes them meet.** §0.5 specifies replan in detail — the
replan input is *"the plan + the completed steps + their emitted values + the failure"*, and the replan budget
is *"stated in the plan, so the model can see it."* §0.2 keeps P6 unchanged. Neither section mentions the
other. There is no `plan_version`, no approval-to-plan binding, and (per S8-1) no approval object to bind.

**Evidence the repo already knows the right instinct, twice, at call level:**

- **`enabled_ops` is a confirm-TIME input, not a mint-time one** (`action_confirm.go:96-106`,
  `2026-06-25-plan-action-kit.md:141`): the user's per-op veto is expressed against the thing they are looking
  at *now*, and destructive ops absent from it fail closed as `skipped: not_confirmed`.
- **Translation's re-price gate** is the only drift check in the repo that re-validates at redeem: fresh cost >
  `est × 1.25` or `est + $0.50` → **409 `TRANSL_REPRICE_REQUIRED`** (`estimate.py:226-257`, `config.py:126-127`),
  and it binds the approved **model** so a confirm cannot silently re-price a different one.

Both say the same thing: **assent attaches to a described thing, and a change to the description voids it.**
Neither has an analogue at plan level.

**What the design must add:** an approval bound to a plan hash, plus a **graded revision rule** — the whole
question is which revisions preserve assent. The defensible cut, and the one consistent with the two
precedents above:

| revision | assent |
|---|---|
| a step is **removed**, or its scope **narrows** (fewer items, smaller limit) | **preserved** — strictly less than approved |
| a step's **arguments** change within the same declaration and scope | **re-gate that step only** |
| a step is **added**, a declaration is **swapped**, a bound arg **widens**, or the spend estimate rises past a stated threshold | **voided** — re-approve the plan |

Without this rule, replan is a **permission-laundering machine**: approve a cheap plan, fail a step, replan
into something the user never saw, execute under the old approval. That is not a hypothetical — it is the
mechanical consequence of shipping §0.5's replan next to §0.2's unchanged P6.

---

### S8-4 · CRITICAL — needs-human and needs-permission are one channel, and the channel only carries permission.

**The situation.** §0.5 lists `needs-human` as *"the ambiguity cannot be resolved from anything available →
suspend and ask"*, and insists *"a model that asks a question is behaving correctly."* The model asks: *"there
are three entities named Kael — which did you mean?"* That question has no representation.

**Evidence.** `chat_suspended_runs.pending_tool_call` is one `{id, name, args}`. The resume outcome set is a
**closed set of consent verbs**, unknown → denied (`test_unknown_outcome_on_approval_treated_as_denied`). A
"no" becomes `{"error": "denied by user"}`. §0.5 correctly reports the machinery is *"wired to exactly one
thing"* — the sharper fact is that it is **typed** for one thing: there is no field anywhere in the suspend
row, the card, or the resume path that can hold a free-text answer.

**Should they be the same channel?** They share transport and should share it — durable suspend, owner
scoping, TTL, resume. They must **not** share semantics, for four reasons the repo's own code makes concrete:

| | needs-**permission** | needs-**answer** |
|---|---|---|
| what it produces | a **decision** about an action | **data** that binds into a later step's arguments — i.e. an `emits` source (C-6) the plan must record and verify |
| who may give it | only the **principal** (`action_confirm.go:136-141` — *"confirmation not valid for this user"*) | anyone with the context; delegable |
| "always" | meaningful (`user_tool_approvals`) | **meaningless** — an answer is about one ambiguity |
| a wrong one | a security event, irreversible | recoverable by asking again (S8-10) |
| fail-open/closed on doubt | **closed** (unknown → denied) | **closed is wrong** — silently killing the plan is not safe, it is just quiet |

**What the design must add:** two suspend *reasons* over one suspend *mechanism* — `awaiting_permission` and
`awaiting_answer` — with distinct payloads (a decision enum vs. a typed answer that binds to a named step
argument), distinct fail-on-doubt rules, and distinct UI. Today the model's only way to ask a question is to
launder it through the consent surface, where the FE will render it as approve/deny buttons.

---

### S8-5 · HIGH — "Never allow" meets a plan that needs the tool.

**The situation.** A plan's step 6 uses a tool the user has permanently refused.

**Evidence — the real error string** (`stream_service.py:3427-3431`):

> `'<tool>' is blocked: you chose 'Never allow' for it. It was NOT run. Do not ask to run it again — either
> achieve the goal another way, or tell the user they can re-enable it in Settings → Tool permissions.`

That message is **correct at call level** and **useless at plan level**, because by the time it is emitted,
steps 1-5 have committed. And the deny is invisible to the planner: it is enforced at execute
(`stream_service.py:3378-3444`), while the tool remains on the advertised wire.

**Two consequences:**

1. A plan containing a denied tool is **plan-invalid from the moment it is written** — the executor should
   never start it. Today it starts it and walks into the wall.
2. §0.1's rule (*"a withholding that does not register is a defect"*) does not currently reach the deny at
   all, because the deny is not modelled as a withholding. The purest expression of user intent in the whole
   permission system is absent from the observability ledger P5 exists to keep.

**What the design must add:** the standing-deny set is an **input to planning** and a registered **withholding**
(`{tool, stage: "standing_deny", reason}`), evaluated in the pre-flight (S8-2), producing `plan-invalid`
before step 1. This is also the *right* way for a P6 ceiling to be visible in advance per §0.3 — the model is
told *"you may not use this, here is why, here is where the user changes it"* while it can still plan around it.

---

### S8-6 · HIGH — nobody answers, and earlier steps already committed.

**The situation.** The plan suspends at step 7. The user never returns.

**Evidence — three unrelated clocks, set by three services, with no rule connecting them:**

| clock | value | where |
|---|---|---|
| confirm token TTL | **10 minutes** | `action_confirm_token.go:33`, `confirm.py:52`, `mcp_actions.go:46`, `confirm_token.py:63` |
| suspended run TTL | **6 hours** | `migrate.py:327` (`expires_at DEFAULT now() + interval '6 hours'`), swept by `sweep_expired_runs` |
| MCP task gate | 600 000 ms | `tasks.go:46`, `tasks.py:65` |

**A card can outlive its own token by 5 h 50 m.** For a `confirm_action` suspend the model is already holding
a minted token; the user clicks Approve at hour three and redeems a token that died in minute ten. For the
Tier-A `tool_approval` card the resume re-executes the tool (minting fresh), so it survives — meaning the
system's behaviour on expiry **depends on which card shape it happens to be**, which is not a rule.

**And the committed work.** `load_suspended_run_any` exists *precisely* because trapped content had to be
recoverable and materialised as `interrupted` (`suspended_runs.py:144-150`). §0.5 declares
*"`interrupted` is a defect, not an outcome."* Expiry is a straight path to it — and under plans it strands N
committed, irreversible steps with no record of what was completed and no disposition for it.

**What the design must add:** (a) one rule relating token TTL, plan-approval expiry and suspend TTL — the
plain one being *the token is minted at redeem, so only the approval's expiry matters* (S8-11); (b) a defined
terminal state for an unanswered plan that **names the completed steps and their emitted values** rather than
discarding them (§0.5 already requires exactly this input for replan — expiry should produce the same
artifact); (c) an explicit statement of whether partial work is rolled back, kept, or kept-and-flagged.

---

### S8-7 · HIGH — a plan's TOTAL cost. There is no plan-level budget.

**The situation.** Twelve steps at $0.40 each. Every tool is spend-allowlisted. Nothing asks.

**Evidence — every budget in the repo is scoped to something other than a plan:**

| control | scope | where |
|---|---|---|
| spend **consent** | `(user, tool)`, **unbounded in amount and count** once allowed | `tool_approvals.py` `spend::<tool>` |
| spend **guardrail** | user, **daily / monthly** | `guardrail.go:31-51`, `patchGuardrail:570` |
| **reservation** | one **job_id** | `guardrail.go:153-157`, `token_reservations` |
| key **cap** | one API key, forwarded as a header only | `public-mcp.controller.ts:224-229`; arithmetic downstream at `guardrail.go:247` |

**And the amount the user approved is re-checked at redeem in exactly one service.** Translation:
`reprice_exceeds_threshold` (1.25× / +$0.50). Everywhere else the estimate is advisory —
`knowledge-service`'s `kg_build_graph` / `kg_build_wiki` tokens carry **no cost field at all**
(`build_tools.py:93-100`), and `composition-service` passes the *claimed* `estimate_usd` straight into
`_precheck_or_402` as the reservation amount (`actions.py:755`), which reserves the estimate rather than
checking the actual against it.

**The asymmetry the design must name:** N per-call approvals are N decisions each of which looks cheap. The
quantity a human actually wants to bound is **the sum** — and the sum is the one number no surface shows.

**What the design must add:** a plan carries an **estimated total**, reserved before step 1 against the
existing guardrail machinery (which is per-job and could take a plan id), with a defined transition when
execution overruns it. The natural transition already exists in §0.5's vocabulary — overrun is
`needs-human`, not a silent stop and not a silent continue.

---

### S8-8 · HIGH — a third-party key runs a plan. Who is the human?

**The situation.** The public MCP edge, a plan, a gate.

**Evidence — the gateway has an approval *client* but no approval *loop*.** A `write_confirm` propose from a
default key is executed-as-propose, the token is **stripped**, and the caller receives
(`propose-detect.ts:122-132`):

```json
{"status": "pending_human_approval", "approval_id": "<uuid>"}
```

The run **ends there.** There is no polling tool in `TOOL_POLICY`, no elicitation, no suspend, no callback.
The owner acts hours later out of band (`mcp_approvals.go:322` — *"THE spend point"*), replaying the token
into the domain. The agent never learns the outcome in-band. Fail-closed if the queue is down
(`propose-detect.ts:150`): *"this action needs human approval but could not be queued — please retry."*

The alternative is worse for the design's purposes: `allow_self_confirm=true` makes the agent its own second
actor — `internalSelfConfirm` *"bypasses the OD-2 queue entirely"* (`mcp_approvals.go:164-165`). That does not
answer *who is the human*; it removes the human.

**Three further facts that make plans unrunnable at this edge as-built:** the gateway has **zero** occurrences
of `permission_mode`; `session_id ≡ key_id` permanently (`public-mcp.controller.ts:219`), so two concurrent
agents on one key are one session; and OAuth grants are hard-coded `allowSelfConfirm: false` **and**
`spendCapUsd: null` (`key-resolver.ts:64`) — no self-confirm and no cap.

**Why this is a design-level hole, not a gateway backlog item.** §0.5's invariant is:

> *No plan may terminate except by satisfying its `done_when` or by reaching a human.*

At the public edge **there is no path that reaches a human within the run.** The invariant is unsatisfiable
there, which means the design must either (a) declare plans out of scope for third-party keys, or (b) define
an out-of-band resume — the plan is durable even though the connection is not. (b) is close to buildable: the
suspend table is already durable, owner-scoped and TTL'd; what it lacks is a resume trigger that is not an SSE
turn. **Either way the design must say which**, because silence here defaults to (a) by accident while the
gateway advertises 44 `write_confirm` tools.

---

### S8-9 · MEDIUM-HIGH — a plan step delegated to something that cannot ask.

**Evidence.** Three separate arms refuse rather than suspend when `subagent_depth > 0`
(`stream_service.py:3997-4013` approval gate, `:3751-3764` H7 cap, `:3803-3817` `require_approval` hook), each
with a written rationale: *"a headless sub-run cannot raise an approval card… it returns a result.error the
sub-model can adapt to (no silent no-op) instead of suspending (which the parent would otherwise swallow)."*
`clamp_permission_mode` (`subagent_runtime.py:37`) additionally clamps the nested run.

**The gap.** Under plan-as-data, a step may be delegated. A delegated step **cannot be gated** — it either was
pre-approved or it fails. Nothing in the design says whether that is allowed.

**What the design must add:** either delegation is forbidden for gating steps, or the pre-flight (S8-2) must
resolve every gate on a delegated step's path **before** delegation — which is only possible if plan-approval
(S8-1) exists to carry the resolution. This is a second, independent argument for S8-1.

---

### S8-10 · MEDIUM — the human answers wrong, or ambiguously.

**Evidence.** Unknown outcome → **denied** (`stream_service.py:7364`, and the test that pins it). That is
correct fail-closed behaviour for a *permission*. It is exactly wrong for an *answer*: *"I'm not sure — the
second one?"* is not a refusal, and treating it as one kills a plan for a reason the user never intended.
There is also **no re-ask**: one suspend, one outcome, resume, done.

**What the design must add:** for `awaiting_answer` (S8-4) — a bounded **re-ask** loop, and a defined
transition for *"the answer did not resolve the ambiguity."* §0.5 already has the right precedent shape (the
replan budget is *"stated in the plan, so the model can see it and spend it deliberately"*); the ask budget
should be stated the same way. The transition on exhaustion must **not** be `plan-invalid` — the plan was
fine, the world is ambiguous.

---

### S8-11 · MEDIUM — a token minted at plan time, redeemed at execute time.

**The question, answered from the repo: it cannot survive, and it must not be attempted.**

| property | value | consequence for plan-time minting |
|---|---|---|
| TTL | 10 min | dead before most plans reach the step |
| single-use | `jti` ledger, claimed **before** the effect, **not released** on failure | a retried step cannot reuse it |
| params | frozen **inside** the HMAC | a replanned/rebound arg cannot be expressed |
| authority | re-checked at redeem (`authorizeAction`) | a grant downgrade correctly kills it — mid-plan |
| drift | **inconsistent**: knowledge-service has real optimistic concurrency (`expected_schema_version` → `SchemaEditDrift` 422, `schema_edit_effect.py:47-76`); **glossary has none** — it re-resolves the target and 422s only if the row *vanished* (`action_confirm.go:324-329`), so a row **edited** between mint and redeem is written against its new content, silently | the longer the mint→redeem gap, the more the weakest drift check governs |
| binding | user + resource only — **no session, no run_id, no conversation** | a token minted in plan A is redeemable from anywhere by that user for 10 min |

**What the design must state, out loud, as a rule:** *tokens are minted at **execute** time, never at plan
time. A plan may record that a step **will require** a confirm; it may never carry the confirm itself.* The
tempting alternative — mint at plan time so the user approves once — destroys every property the token has.
This makes S8-1 load-bearing rather than a convenience: the plan-approval is what carries assent across the
gap, and the per-call token stays a fresh, narrow, replay-protected receipt.

**Also worth stating:** the mint→redeem drift inconsistency is a pre-existing debt that plans *amplify*.
A non-consuming preview path already exists (`/actions/preview`, `action_confirm.go:520`) and re-renders the
card from current state — but it is advisory, and confirm never compares against it.

---

### S8-12 · MEDIUM — an autonomous run with no human present at all.

**The situation.** A scheduled or background plan run. §0.5's invariant permits exactly two termini:
`done_when`, or **reaching a human**. With no human, one of the two is unreachable.

**Evidence of the current answer, which is "fail the step":** the only existing no-human context is
`subagent_depth > 0`, and its answer is a `result.error` (S8-9). There is no background plan runner today, so
there is no worse evidence — which is exactly why the design must decide now rather than discover it.

**What the design must add:** a third terminal state — `suspended_awaiting_human`, **durable beyond the run**,
resumable later by the principal or a designate. Roughly 90% of it exists (`chat_suspended_runs` is durable,
owner-scoped, TTL'd, and already carries `permission_mode`, `pinned_step_tools` and `book_id` across the gap)
— but it is keyed to a live SSE turn and swept at six hours. And the design must state whether an unattended
plan may hold committed partial work indefinitely, which is a product decision, not an implementation one.

---

### S8-13 · MEDIUM — approving a plan is not approving its arguments.

**The situation, and it is intrinsic to C-6.** A step's arguments may be **bound from an earlier step's
`emits`** — that is the point of §0.4's carry-forward. So at plan-approval time, the arguments of step 7
**do not yet exist.** The user approves *"delete the duplicate entity that step 3 identifies."* Step 3
identifies the wrong one.

**Evidence that this inverts the spine's core habit.** Every consent surface in the repo shows **concrete**
arguments: the card carries `_card_args["args"] = args_obj` (`stream_service.py:4014-4019`); the confirm token
freezes resolved params in `p`; `enabled_ops` toggles **rendered rows**. Plan-level assent is, unavoidably,
assent to a **description**.

**What the design must add:** a rule for which steps are pre-approvable. The defensible cut, consistent with
`enabled_ops` and with translation's re-price:

- a step whose arguments are **fully literal at plan time** → pre-approvable by the plan-approval;
- a step with a **bound** argument → **re-gates at execute** on its resolved payload, unless the binding is
  exact-match verified against the producing step's declared `emits` (the C-6 assertion the executor performs
  anyway);
- a **destructive** step with a bound argument → **always** re-gates, per the `enabled_ops` precedent that
  destructive ops fail closed unless enabled against what is on screen.

Without this, a plan-approval silently converts *"I approve deleting a duplicate"* into *"I approve deleting
whatever step 3 returns"* — and the spine's one unbreakable habit (assent binds to a payload) is lost at
exactly the moment the payload matters most.

---

### S8-14 · LOW-MEDIUM — revocation mid-plan, and the optimization that would break it.

**Evidence the race is already handled at call level, correctly.** The resume path re-reads the standing
decision because a card can sit suspended indefinitely, with the reasoning written down
(`stream_service.py:7366-7394`): *"The refusal is the LATER, more deliberate act; it wins."* And the in-loop
gate re-reads per call, so revocation mid-turn works today by construction.

**The gap.** A plan executor with a **pre-flight** (S8-2) will be strongly tempted to resolve permissions once
and cache them — it is the obvious optimization and it silently reintroduces the exact bug the resume path was
hardened against, but over hours instead of minutes.

**What the design must add:** one sentence, stated as an invariant rather than left to the implementation —
**the pre-flight computes the ask; the execute-time gate still enforces.** A plan-approval is assent, never a
cached authorization, and a standing deny set between step 6 and step 7 stops step 7.

---

## 4 · Summary — is the spine still sound?

**For what it was built for: yes**, and the evidence in §1.1 is unusually strong for this repo — asymmetric
degrades chosen deliberately, refusal ordered above every other arm, consent that can be listed and withdrawn,
tokens that cannot be re-pointed or replayed.

**§0.2's *"kept unchanged"* is nonetheless the wrong verdict**, and precisely because §0.4 is right. The spine
is not *wrong* under plans — it is **incomplete along an axis that did not exist before**. Every one of its
four axes resolves at the instant of a call; a plan needs assent that spans calls, survives revision, arrives
before the irreversible work, and can be reached without a human sitting in the turn.

**Six things the design owes, in dependency order:**

1. a **plan-approval object** — bound to a plan hash, scoped to a step set, with a spend ceiling and an expiry (S8-1)
2. a **permission pre-flight** — every gate the plan will hit, computed before step 1 (S8-2, S8-5)
3. a **revision rule** — what a replan does to an existing approval (S8-3)
4. **two suspend reasons over one suspend mechanism** — `awaiting_permission` vs `awaiting_answer` (S8-4, S8-10)
5. a **plan-level spend estimate + reservation**, and a transition on overrun (S8-7)
6. a **durable, out-of-turn human boundary** — for third-party keys and unattended runs (S8-8, S8-12)

Items 1-3 are one coherent mechanism. Item 4 is independent and is the one §0.5 already asks for by name
without noticing that the existing machinery cannot carry it.
