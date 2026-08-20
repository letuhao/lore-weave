# Build or integrate — the 2026 landscape against our six primitives

**Question (PO, 2026-08-04):** what we are building is a framework with enterprise-scale layers. By
2026 there may be mature frameworks that only need integrating. Find them, and compare.

**Answer in one line:** **buy P4 and P5, mostly buy P1, build P2 and P3** — because the three clauses
that own our two largest measured failure classes are precisely the ones the 2026 state of the art has
*not* solved, and everything else is solved better elsewhere than we would solve it.

---

## 1 · What the field settled between our cutoff and today

| finding | source | what it does to our design |
|---|---|---|
| **Routing at 584 tools / 110 agents: F1 drops 16–23pp.** Decomposed into a **Retrieval Gap** (wrong tool surfaced) and a **Confusion Gap** — *even with perfect retrieval the oracle ceiling drops 10pp*. Embedding shortlisting recovers +10–11pp; absolute stays 10–15pp below small scale | [Scaling Enterprise Agent Routing, 06/2026](https://arxiv.org/pdf/2606.17519) | **Independent answer to our A1 argument.** Fixing the advertised set is necessary and **provably not sufficient** — a 10pp floor survives perfect surfacing. Matches our 61.8% carry-forward class being untouched by any shape |
| **"Progressive disclosure buys context, not intelligence."** Flat index wins; **two-level hierarchy never recovered the gain and sometimes collapsed accuracy — 0.9126 → 0.6398.** Gains "sharpest on English open QA and **absent on Chinese**" | [Is Progressive Disclosure All You Need, 07/2026](https://arxiv.org/html/2607.17598) | 🔴 **Kills `SPEC.md` R14's hierarchical group tree.** Depth is a penalty, not a scaling strategy. And the CJK null result is a direct warning for this product |
| ~150k → ~2k input tokens (**98.7%**) loading tool defs only when used; **>10,000 enterprise MCP servers** by 04/2026 | [Anthropic, via Wire](https://usewire.io/blog/progressive-tool-loading-mcp-context-pattern/) | lazy loading is now the mainstream answer at catalog scale — our instinct was right, our *implementation* (silent budget deletion) was the defect |
| **Retrieval errors ≈50% of agent failures across 527 tools**; 7–85% degradation at 49–741 tools | [Progressive Disclosure MCP benchmark](https://matthewkruczek.ai/blog/progressive-disclosure-mcp-servers.html) | corroborates our 57% identifier / 54% failure figures — we are not an outlier, we are typical |
| MCP registry governance gap: *"any AI agent can connect to any registered server without access control, no audit trail for which agent accessed which tools"* | [MCP Governance Framework](https://blog.gitguardian.com/mcp-governance-framework/) · [MintMCP registry comparison](https://www.mintmcp.com/blog/mcp-registry-tools) | **P3 Admission has no off-the-shelf answer.** The gap we identified is the gap the field reports |
| OTel **GenAI + MCP semantic conventions**: span names, attributes, metrics for model calls, **tool executions**, agent runs, retrieval, memory. Still *Development* status; v1.42.0 (12/06/2026) moved `gen_ai.*` into a dedicated repo with its own cadence | [OTel GenAI observability](https://opentelemetry.io/blog/2026/genai-observability/) · [Greptime](https://greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions) | **Adopt for P5** — with eyes open that it is pre-stable and names may move |
| MCP ships **`outputSchema`** (structured, validated tool output) and **`ResourceLink`** — return a *reference*, not inline content | [FastMCP tools](https://gofastmcp.com/servers/tools) · [Extending ResourceLink](https://arxiv.org/pdf/2510.05968) | **references-first is already in the protocol.** A5's mechanism does not need inventing — only adopting |
| **Pydantic AI toolsets**: composable, runtime-swappable, filterable; tool metadata *"not sent to the model, but used for filtering and behaviour customisation"*. **FastMCP Tool Transformation** rewrites/restricts any MCP server's tools. `FastMCPToolset` works against **any** MCP server | [Pydantic AI toolsets](https://ai.pydantic.dev/toolsets/) · [Pydantic AI 🤝 FastMCP](https://gofastmcp.com/integrations/pydantic-ai) | **P4 Assembly, off the shelf** — and the metadata-not-sent-to-model channel is exactly our `_meta` |
| **Microsoft Agent Framework 1.0 GA 03/04/2026** (AutoGen + Semantic Kernel merged, .NET/Python); **Google ADK 1.0** (Java/Go); **LangGraph** 47M monthly downloads; **Pydantic AI** the type-safety choice. **A2A** for cross-framework delegation | [LangChain 2026 survey](https://www.langchain.com/resources/ai-agent-frameworks) · [Morph 8-SDK comparison](https://www.morphllm.com/ai-agent-framework) | orchestration is a solved, crowded market. **Building our own orchestrator would be the worst use of this effort** |

---

## 2 · The comparison, primitive by primitive

| | primitive | best off-the-shelf | verdict | why |
|---|---|---|---|---|
| **P1** | Identity | MCP registries + `outputSchema`; OTel resource attrs | **mostly BUY** | catalogue/versioning is commodity. Our `superseded_by` many-to-one **consolidation** edge (measured 54 → 17 targets, 3.2:1) has no equivalent — that sliver we keep |
| **P2** | **Contract** | JSON Schema · `outputSchema` · Pydantic types · `ResourceLink` | 🔨 **BUILD the three novel clauses** | schema validation is commodity and we should use it. But **nothing in 2026 has C-4 `accepts`-provenance, C-5 no-silent-substitution, or C-6 `emits` carry-forward.** These are exactly the Confusion Gap the routing paper measures and does not close |
| **P3** | **Admission** | *nothing* — the registry literature reports this as **the** open gap | 🔨 **BUILD** | this is the membrane. It is also small: five gates, one of them an import-graph check |
| **P4** | Assembly | **Pydantic AI toolsets + FastMCP Tool Transformation** | ✅ **BUY** | composable, swappable, filterable, works against any MCP server, and its metadata channel is our `_meta`. We would be rebuilding this badly |
| **P5** | Observation | **OTel GenAI/MCP semantic conventions** | ✅ **BUY** (pre-stable) | our five fields map onto `gen_ai.*` tool-execution spans. Adopting gives us vendor-neutral tooling free. **Two of ours have no convention — `withheld_tools` and the wrong-object counter — so they ride as custom attributes** |
| **P6** | Permission | our tier/scope/confirm/spend + gateway OAuth scopes | ✅ **KEEP** | already sound, already audited, already serving third-party keys |

---

## 3 · The finding that decides it

> **Our unsolved problem is the field's unsolved problem — and everything else is solved better than we
> would solve it.**

The routing paper's **Confusion Gap** (10pp lost *with perfect retrieval*) and our **61.8% carry-forward
failures** are the same territory: the model has the right tool and still cannot complete the call.
Nobody ships an answer. C-4, C-5 and C-6 are an answer, and they are cheap — three declaration clauses
plus generation-time checking.

Meanwhile orchestration, disclosure, schema validation and telemetry are all commodity in 2026. **Every
hour spent building those is an hour not spent on the only part that is ours.**

**Corollary on scope.** This reframes the effort from *"build an enterprise framework"* to *"build a
thin contract-and-admission layer on top of Pydantic AI / FastMCP toolsets, instrumented with OTel
GenAI."* That is a much smaller thing, and it is the part that survives the red team.

---

## 4 · Corrections this forces on the existing spec

1. 🔴 **R14's hierarchical group tree is withdrawn.** Measured: two-level disclosure never recovered
   the gain and collapsed one configuration 0.9126 → 0.6398. **Flat index, no depth.** This also
   retires the group-directory-depth open questions (Q15–Q17) rather than answering them.
2. **A5 needs no invention.** `ResourceLink` is protocol-native; the work is adoption plus the CJK
   folding defect (our search path folds nothing while the write path folds 60 honorifics).
3. **The CJK caveat is now explicit.** The disclosure gains were *"absent on Chinese."* Every benchmark
   we import must be re-run on our own corpus before it is believed.
4. **P4 stops being ours to design.** `SPEC.md` R4's *"one explained tool surface"* becomes *configure
   a toolset and add the `excluded_by` reason channel*, not *write an assembler*.

---

## 4a · Dify, read at source (`D:\Works\source\dify`, `99ed826a55`, 2026-07-25)

**Does it solve the many-tool problem? No — it refuses to have one.**

| what we looked for | what is there |
|---|---|
| a cap on the agent's tool set | **`NEXT_PUBLIC_MAX_TOOLS_NUM`, default `10`** (`web/env.ts:118`), enforced in the UI (`agent-tools/index.tsx:191`) |
| per-turn assembly | `_init_prompt_tools` (`api/core/agent/base_agent_runner.py:190-216`) iterates `app_config.agent.tools` and puts **every one** on the wire. No budget, no ranking, no dedup, no limit |
| tool retrieval / semantic search over a catalog | **none.** `grep -rln "tool_retriev\|retrieve_tools\|tool_search"` over `api/core/` → **zero files** |
| who chooses | **a human, at app-configuration time** |

So the most-deployed open LLM app platform in 2026, at 315× our per-agent scale in ambition, answers
the question by **bounding it at ten and handing the choice to a person.** Our catalog is **31× that
maximum**, aimed at one general assistant rather than one narrow app.

**Dify's coherent thesis, visible across three subsystems: every hard agent problem is solved by a
human at configuration time.** Tool selection → a person picks ≤10. Sequencing → a person draws the
workflow DAG. And argument sourcing → the find below.

### The one thing worth taking — and it corrects §2

`ToolParameter.form` (`api/core/tools/entities/tool_entities.py:328-331`):

```python
class ToolParameterForm(StrEnum):
    SCHEMA = auto()   # should be set while adding tool
    FORM   = auto()   # should be set before invoking tool
    LLM    = auto()   # will be set by LLM
```

**This is argument provenance, declared per parameter** — and §2 claimed nothing in 2026 has it. That
claim was too strong and is corrected here. **Prior art exists**, on a different axis:

| | axis | answers |
|---|---|---|
| **Dify `form`** | **which actor** supplies the value | developer at install · human before the call · the model |
| **our C-4 `accepts`** | **where the model obtains** the value | the user's own words · the declaration that emits it · a name/ordinal it can use instead |

They compose rather than compete, and Dify's is the more fundamental of the two: **a parameter the
model cannot know should not be the model's to supply.** Measured against our data, `book_id`,
`entity_id` and `chapter_id` — **660 of our identifier failures** — are `FORM`-class parameters that
this repo hands to the model as `LLM`-class. That reframing is free and it is available today.

**The gap Dify does not close** is the one our 61.8% lives in: a value that *is* obtainable, because a
previous call in the same session already returned it. No `form` value describes that. C-6 `emits`
remains ours to build.

## 4b · Plan persistence — how the mature systems store it *(surveyed 2026-08-04)*

**Every one of them separates the specification from the execution state. None puts execution state in
the document.** That independently confirms `ARCHITECTURE.md` §0.11's SPEC/STATE split, which was
derived from our own constraints *before* this survey ran.

| system | stores | how |
|---|---|---|
| **[Kiro](https://kiro.dev/docs/specs/)** (AWS) | the **SPEC** | three markdown artifacts — `requirements.md`, `design.md`, `tasks.md`; human review gates each stage; **a separate hook watches for drift** against `requirements.md` |
| **[LangGraph](https://eastondev.com/blog/en/posts/ai/20260424-langgraph-agent-architecture/)** | the **STATE** | checkpoints graph state **at each node transition**, organised by thread |
| **[Temporal](https://medium.com/data-science-collective/langgraph-vs-temporal-for-ai-agents-durable-execution-architecture-beyond-for-loops-a1f640d35f02)** | the **STATE** | **event sourcing** — replays history to reconstruct, resumes at the failed step **without re-running completed work** |
| the 2026 production combination | both | a durability layer plus compute; split the graph into one activity per node for finer checkpointing |

Reported: checkpointing cuts wasted processing **60%+** on multi-step workflows *(vendor-blog figure —
indicative, not verified)*.

**Two findings that land directly on us:**

- **We already pay for a checkpointer and collect none of the benefit.** Turns checkpoint per tool call
  at `finish_reason='streaming'`, and **nothing ever reads a `'streaming'` row back** (S3-M6). The write
  half exists; the recovery half does not.
- **LangGraph documents the same hole we found.** *Checkpointers save state between nodes, not inside a
  node* — precisely S3-M3 (timeout, effect commits later) and S3-M1 (the effect already happened).
  **The field has not solved this**, so C-13 `re_runnable` and the completed-effects ledger are not
  re-invention; they patch where the mature systems declare a limit.

### Is markdown the right format for a plan a human reviews and edits?

**Yes for the human surface; no for the execution authority — and that split is the 2026 convergence,
not a local invention.**

> *"Every AI coding tool, from Cursor to GitHub Copilot to Claude Code, defaults to markdown for plans,
> specs, and documentation."* · *"For machine-parsed pipelines, JSON is usually more reliable."* · the
> emerging practice is **markdown for definition, a compact structured format for runtime**.

Markdown is also the **most token-efficient** of the formats compared — which matters, because the
projection is read every turn.

**One caveat, and it is §0.12 applied to this very survey.** The comparison finding that *"two models
performed best with YAML"* measured comprehension of **nested data** — and a plan's `accepts`/`emits`
bindings *are* nested data. Different models, different task. **Do not import it: measure the binding
format on our own model.** That measurement belongs to brick 0.

## 5 · What is still worth proving before integrating

- **Does `FastMCPToolset` survive our federation shape** (10 services, 3 languages, a public gateway
  with 170 policy entries)? One spike against two real servers.
- **Does OTel GenAI's tool-execution span carry enough** for `advertised`/`withheld`, or do both ride
  as custom attributes? Read the convention, do not assume.
- **Pre-stable risk on P5.** `gen_ai.*` moved repos in June 2026 and names may still change. Pin a
  version; put the mapping in one adapter so a rename is one file.
