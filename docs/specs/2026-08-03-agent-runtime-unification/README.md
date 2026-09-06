# Agent Runtime Unification

Pulling MCP tool loading, skills, rails/guards, and workflows into one architecture.

**Why this exists.** Thirteen successive mechanisms for *"which tools does the model see this turn"*
were built between 2026-06-10 and 2026-08-03. **One was ever retired.** Beneath them, nothing
anywhere — code, database, contract, or document — assigns a tool to a skill; the finest granularity
ever specified is a name prefix. The result is the reported symptom: the tool exists, the model can
name it, and it still is not on the wire, for a reason no single place can report.

| Document | What it is |
|---|---|
| [`AUDIT.md`](AUDIT.md) | **Read first.** The comprehensive audit: the numbers, the five structural defects, what is already good, why previous attempts did not converge. |
| [`SPEC.md`](SPEC.md) | The unification spec: the lane boundary, the three-layer lifecycle (R9), the tool error contract (R10), R1–R12, phases, non-vacuity obligations. Status DRAFT. |
| [`audits/`](audits/) | Six per-layer reports with `file:line` on every claim — the evidence base. |

## The two numbers

| Invariant | Today |
|---|---|
| Every MCP tool belongs to one skill group | **98 / 202** (≈49%) |
| Every MCP tool sits in ≥1 workflow | **30 / 223** (≈13%) — see `SPEC.md` §1.2, this one is amended to be lane-scoped |

## The three layers

The audit's static findings all reduce to one missing distinction, added to the spec as **R9** after
PO review:

| Layer | Changes when | Example state | Does LoreWeave separate it? |
|---|---|---|---|
| **Artifact** | at deploy · has history | `deprecated`, `superseded_by` | skills ✅ · workflows ✅ · **tools ❌** (no version, no revision, no table) |
| **Policy** | when the rule changes | *deprecated ⇒ by-name only, never hot-seeded* | **does not exist anywhere** |
| **Runtime** | every turn · no history | budget filled, rail gate, breaker | exists — 18 filters, 13 of them silent |

`_meta.visibility:"legacy"` is read directly at **seven runtime filter sites** with nothing in
between. That missing middle layer is why two code paths could disagree about whether a deprecated
tool is hidden or labeled, and why the public edge grants four deprecated `book_*` tools while denying
their replacements.

## Why this is a re-architecture, not a cleanup

Two PO constraints (`SPEC.md` §1.3) invalidate assumptions rather than adding scope:

- **C1 — the catalog is expected to reach thousands of tools.** Measured from this repo's own figure
  (~375 tokens per tool schema): **3,000 tools = 1.125M tokens of schema, 150k tokens for a bare
  name+description index, and 214 tools per group** under the flat 14-group taxonomy. `tool_list`
  returning a whole category stops being a listing and becomes a context dump.
- **C2 — this repo is maintained for years**, so adding or renaming a tool must be routine. Today a
  rename must be hand-propagated to `GROUP_DIRECTORY` ×3, two prefix maps, `TOOL_POLICY`, 43 intent
  regexes, skill prose and `workflows.steps[].tool` — **none of them compiler-checked**.

Every one of the audit's thirteen mechanisms is a *constant-factor* improvement on an approach whose
cost is linear in catalog size. **That is why local patching cannot save it** — the budget trims
harder and the breakers fire sooner, but nothing changes the exponent. R13 (a generated migration
chain, on Entity Framework's model) answers C2; R14 (discovery that does not scale with the catalog)
answers C1.

## Why the agent loops

The reported symptom — *the agent calls a tool, cannot tell what went wrong, and loops forever* — has a
named cause. **No tool tells its caller whether a failure is worth retrying**, so the retry decision
falls to the model's guess. LoreWeave answered this with six reactive breakers in the orchestrator;
all six treat the symptom.

Our own code contains the proof: `fail_by_tool_error` is keyed on the *error signature* rather than the
args, because *"a weak model varies the args each retry (measured: `book_get_chapter` ×19, each a
DIFFERENT hallucinated `chapter_id`) yet hits the IDENTICAL error."* That is a permanent failure the
model is treating as retryable. **R10** makes the tool say so.

## Method note

Six parallel read-only auditors over disjoint file sets, plus a single main-session read of
`stream_service.py` (7,818 lines — the spine every layer meets in, deliberately read once rather than
six times). Load-bearing findings were independently re-verified; one auditor claim was found inverted
and is corrected in `AUDIT.md` §2.3.
