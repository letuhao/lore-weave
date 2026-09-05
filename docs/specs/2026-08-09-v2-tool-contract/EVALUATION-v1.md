# CP-5 SPEC v1 — the evaluation that killed it, kept as the record

*Four of these six findings are the spec committing the defect it was written to prevent. v2 exists
because of them; deleting them would destroy the reason v2 looks the way it does.*

## 0.5 · EVALUATION, 2026-08-09 — six findings against this spec, before anything was built

The PO asked for CP-5 to be evaluated rather than started. It does not survive intact. **Four of the
six findings are the spec committing the defects it was written to prevent.**

### E1 · The prioritisation was wrong — ranked by events, not by journeys

4,175 failed calls span **358 sessions**, and the **top 3 sessions alone hold 1,180 of them
(28.3%)**. The median session has **3**. Ranking members by call count therefore ranks a handful of
pathological loops. By **sessions affected** the order inverts:

| member | calls | sessions | % of 358 |
|---|---|---|---|
| **typed inputs** | 703 | **91** | **25.4%** |
| **argument supplier** | 401 | **85** | **23.7%** |
| preconditions | 417 | 58 | 16.2% |
| **repeat semantics** | **2039** | 46 | **12.8%** ← *was ranked #1 at 48.8%* |
| registry name source | 198 | 42 | 11.7% |
| partial outcome | 88 | 37 | 10.3% |
| consent | 36 | 20 | 5.6% |
| closed vocabulary | 25 | 10 | 2.8% |
| output contract | 40 | 6 | 1.7% |
| **concurrency** | 17 | **1** | **0.3%** |
| **empty-change** | 16 | **1** | **0.3%** |

**`typed inputs` + `argument supplier` are the two that break the most user journeys**, and together
they are one problem: *the model could not supply the right value.* That is the problem CP-3's
executor already solves for planned steps.

### E2 · Member 6 as specified is metric laundering — the defect this board exists to catch

`tool_list` produced **1,180 repeat errors across 3 sessions — 393 per session.** Declare it
idempotent and serve the cache, and those become **393 silent successes**. Errors go to zero; the
loop runs exactly as long, burns exactly as many passes, and now emits no signal at all.

**That is converting loud failures into quiet ones**, which is the precise question V-METRIC was
built to ask. Corrected requirement: a repeat may be served from cache to remove its *cost*, but it
**must still be counted and must still escalate** — the breaker stays; only the wasted dispatch goes.

### E3 · No required-vs-optional distinction — and two members have a population of one

`concurrency` and `empty-change` each affect **1 session in 358**. Requiring all 17 members of every
tool makes migration impossible and is over-engineering. Members must be **conditional on lane and
shape** (concurrency for writes; partial-outcome for batch tools) — which is ironic, since member 16
is *conditional parameters*.

### E4 · 🔴 The enforcement ladder governs 2.8% of the tools

Rungs 1–5 (`ABC`, `__init_subclass__`, frozen dataclass, private token, site-counting gate) are
**Python-class mechanisms**. chat-service implements **9** tools in Python. The catalogue holds
**315** federated from Go and Python services — composition 107, glossary 54, book 35, kg 31.

**9 of 324 = 2.8%.** I specified a mechanism whose subject is almost the whole point, and it is not
there. **This is the same clause-with-no-subject failure that produced CP-5**, committed inside the
document correcting it.

Corrected: the contract is a **language-neutral declaration carried in the MCP tool's `_meta`** —
a mechanism that already exists and is already proven, since `_meta` carries `tier`, `ambient_book`
and `superseded_by` today. **Rung 6 is the enforcement for the 97.2%.** Rungs 1–5 apply where
chat-service owns the implementation, as the reference implementation and nothing more.

### E5 · No measurement plan

The spec assumes that declaring a member fixes the failure. Today's own lesson refutes that: the
executor was built, measured null, and the null was a **placement bug** — the supply ran after the
check that rejected the shape it repaired. Every member needs a stated before/after with a control,
and the metric must be **sessions affected**, not events.

### E6 · The residual is larger by journey than by call

`other` is 5.1% of calls but **21.2% of sessions** (76 of 358) — third-largest by the honest
denominator. It is not classified, and CP-5 cannot claim coverage while a fifth of affected journeys
sit in it.

### Verdict

**CP-5's direction holds; its priority, scope and enforcement do not.** Revised order:
**typed inputs → argument supplier → preconditions**, with repeat semantics reframed per E2 and
demoted, `concurrency`/`empty-change` dropped to optional, the ladder replaced by `_meta` +
rung 6, and E6 closed before any coverage claim.

**Do not start 5.1 as written.**

---
