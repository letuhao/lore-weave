# Spec — AI-Task Standard (single-shot LLM generate: shared engine + composable UI)

Date: 2026-07-03 · Branch: `feat/studio-agent-raid` · Size: XL (cross-cutting; multi-milestone continuous run)

## Problem

Every feature that runs a **single-shot, non-agentic LLM generation** (a config dialog → one
LLM call → structured result the human reviews/confirms) re-implements the same plumbing.
Discovery (2026-07-03) found **21 FE surfaces + 10 BE engines** each hand-rolling slices of:

- **BE boilerplate**: `submit_and_wait(...) → status=="completed" → result["messages"][0]["content"]
  → empty-check → JSON extract/salvage → pydantic validate`. Duplicated per engine; the
  `_extract_json_object` tolerant parser exists as **5 divergent private copies**.
- **The empty-prose footgun** (a reasoning model burns its output budget on hidden thinking →
  empty content → JSON parse error). **4 BE engines are exposed** (no thinking-disable):
  `working_memory/executive.py` (max_tokens=500, nothing), `lore-enrichment` stream seam
  (no max_tokens at all), `loreweave_extraction/summarize.py`, wiki `generate.py` (uses
  `reasoning_wire_fields("none")` which is a **no-op**, not a disable). Only `schema_propose`,
  translation `fold`/`resummarize` disable it correctly today.
- **FE duplication**: spend-cap decimal input + regex (copied 3×: `DECIMAL_RE`/`DECIMAL_REGEX`/
  ad-hoc), cost-estimate fetch (bespoke per dialog), default-model preselect (3 different impls),
  busy state, reset-on-open, propose→review→confirm layout, error rendering. **No shared
  effort/reasoning control** anywhere (a `thinkingEnabled` checkbox ×2, a 5-option `<select>`
  in ComposeView). `GapsPanel` even **bypasses the shared `ModelPicker`** for raw `<select>`.

The one thing genuinely shared today: `loreweave_llm.reasoning.reasoning_fields` (BE) and the
FE `ModelPicker`. Everything else is re-derived — and re-broken (the footgun).

## Goal

One **AI-task standard** every single-shot generate consumes, so no surface hand-rolls
effort / spend-cap / json-extract / empty-check / submit boilerplate again, and the footgun is
closed by default. **Composable primitives**, not one monolithic shell (PO decision, Option 1).

## Non-goals / boundary (LOCKED — avoids duplicating the Agent Extensibility track)

- **This is NOT the Agent Extensibility Standard** (`docs/standards/agent-extensibility.md`).
  That track registers **agent-invokable capabilities** (subagent/skill/command/hook/MCP-server)
  in `agent-registry-service`, resolved per chat turn, consumed by chat-service. These AI-task
  generates are **non-agentic pipelines** (MCP-first-exempt, like translation/wiki-gen): no
  registry, no turn, no tenancy resolver. Different service, different files, different problem.
- **Agent-facing wrappers are OUT of scope here.** If the *chat agent* should later trigger a
  generate (e.g. "assistant, propose a KG schema"), that MCP-tool / subagent wrapper belongs to
  the extensibility layer and is built **on top of** this engine (federates it), not duplicated.
  Tracked as a deferred follow-up, built once the extensibility track lands.
- **Do NOT force-fit the wizard-class surfaces** (`BuildGraphDialog` 3-step + benchmark-gate +
  embedding-persist; `ComposePanel` 5-mode controller; `MotifMine` mint→confirm→poll) into a
  single shell — their local logic is real feature logic, not duplication. They **consume the
  shared sub-pieces** (EffortSelect, SpendCapField, readBackendError) and keep their structure.
- **Do NOT change `reasoning_wire_fields("none")` semantics** — it is deliberately a no-op for
  byte-identical legacy extraction callers. Footgun engines switch to `reasoning_fields(effort=
  "none")` / `structured_generate` explicitly instead.

## BE standard — `structured_generate` (in `sdks/python/loreweave_llm/`)

A shared helper that collapses the per-engine boilerplate. Takes any client satisfying the
existing `LLMClientProtocol.submit_and_wait` (per-service wrapper — unchanged).

```python
async def structured_generate(
    llm_client,
    *,
    user_id: str,
    model_ref: str,
    messages: list[dict[str, str]],
    model_source: str = "user_model",
    max_output_tokens: int,                 # REQUIRED — no silent unbounded budget
    reasoning: ReasoningEffort | ReasoningDirective = "none",  # default DISABLES thinking
    response_model: type[BaseModel] | None = None,  # None → raw text result
    salvage: bool = True,                   # drop malformed list items, keep the rest
    temperature: float = 0.3,
    job_meta: dict | None = None,
    transient_retry_budget: int = 1,
    trace_id: str | None = None,
) -> StructuredResult    # {content: str, parsed: BaseModel | None, job: Job}
```

Behavior:
- Spreads `reasoning_fields(...)` — `reasoning="none"` emits `chat_template_kwargs.{thinking:false}`
  (closes the footgun by default). A caller wanting graded effort passes `"medium"`/`"high"` or a
  `ReasoningDirective`.
- Runs `submit_and_wait`, maps SDK/transport exceptions and non-`completed` status to a typed
  `StructuredGenerateError` (a clean 502 at the router).
- Reads `job.result["messages"][0]["content"]` (the load-bearing path); **empty content →
  `StructuredGenerateError("empty response — the model may have spent its budget on hidden
  reasoning; try a different model or a more specific prompt")`** (the clear message, not a JSON error).
- If `response_model` set: shared `extract_json_object` (fence-strip + outermost `{}`) →
  `model_validate`; on failure with `salvage=True`, keep the individually-valid list items.

Also add **`extract_json_object(raw: str) -> dict`** to the SDK (consolidate the 5 private copies;
the divergent copies migrate to it opportunistically, not required this run).

### BE migrations (M1)
- `knowledge-service/app/schema_propose/engine.py` → thin caller of `structured_generate`
  (keeps `SchemaProposal`; drops local `_extract_json`, `_NO_THINKING`, empty-check).
- **Footgun fixes** (behavior-changing → each live-smoked or unit-guarded):
  - `working_memory/executive.py` — add `reasoning="none"` (was nothing; max_tokens=500).
  - `loreweave_extraction/extractors/summarize.py` — add explicit disable.
  - `lore-enrichment-service/app/generation/complete.py` — set a `max_tokens` + disable thinking.
  - wiki `generate.py` — default path must disable thinking (not the `reasoning_wire_fields`
    no-op). Careful: wiki output is **Markdown, not JSON** → use `structured_generate` with
    `response_model=None` (raw content) or just the reasoning-off + empty-check slice.

## FE standard — composable primitives (`frontend/src/components/ai-task/`)

- **`EffortSelect`** — extract the effort dropdown out of `ChatInputBar.tsx` into a standalone
  component (keep `EffortLevel`, `effortLevelFromGenerationParams`, `reasoningEffortForLevel`
  where they are or move to a shared module; `ChatInputBar` consumes the extracted component so
  it doesn't fork). Props: `{ value, onChange, supportsThinking?, compact? }`.
- **`SpendCapField`** — one decimal-validated USD input (consolidate `DECIMAL_RE`); props
  `{ value, onChange, invalidLabel?, hint? }` + an exported `isValidSpend(v)`.
- **`readBackendError`** — lift the knowledge util to a shared location (the
  `body.detail.message ?? body.message ?? e.message` chain that originated in GenerateSchemaDialog).
- **`useAiTask`** — a hook for the SYNC-INLINE propose→review→confirm flow: owns
  `{ config, result, busy, error, run, confirm, reset }`; wraps the API call + error read.
- **`<AiTaskDialog>`** — an OPTIONAL shell composing `ModelPicker` + `EffortSelect` +
  `SpendCapField` + error region + propose/review/confirm slots, for the clean-fit dialogs.

### FE migrations
- **M3 clean-fit** onto `useAiTask`/`AiTaskDialog` or the sub-pieces: `GenerateSchemaDialog`,
  `GenerateWikiDialog`, `RegenerateBioDialog`, `ProfileForm` (suggest), `PolishPanel`,
  `QualityReportSection`. **Fix `GapsPanel` to use `ModelPicker`** (kill the raw `<select>`).
- **M4 wizard-class** adopt the sub-pieces only (keep structure): `BuildGraphDialog`,
  `ComposePanel`/`ComposeConfig`/`ComposeView`, `MotifMinePanel`, `StepProfile`, `StepConfig`,
  `PlannerPanel` — swap hand-rolled effort/spend-cap for `EffortSelect`/`SpendCapField`.

## Milestones (continuous run; checkpoint+commit at each risk boundary)

| M | Scope | Risk boundary | Live-smoke |
|---|---|---|---|
| M1 | BE `structured_generate` + `extract_json_object`; migrate schema_propose; 4 footgun fixes | new shared SDK contract | schema-propose via gateway (local model, $0) + one footgun engine |
| M2 | FE `EffortSelect`/`SpendCapField`/`readBackendError`/`useAiTask`/`AiTaskDialog` | new shared FE contract | FE unit tests; no behavior change yet |
| M3 | Migrate clean-fit dialogs + GapsPanel fix | user-visible dialog change | browser smoke ≥1 migrated dialog |
| M4 | Wizard-class adopt sub-pieces | user-visible change | browser smoke ≥1 wizard |

Each M: VERIFY evidence (unit + tsc) + cross-service live-smoke token; commit with explicit
paths (parallel-agent index discipline — `git diff --cached --name-only` first, no `git add -A`).

## Acceptance

- No single-shot generate surface hand-rolls effort / spend-cap regex / json-extract /
  empty-check / submit boilerplate after the sweep.
- The 4 footgun engines disable hidden reasoning (or bound max_tokens) — reproduced-fix.
- `GapsPanel` uses the shared `ModelPicker`.
- `structured_generate` unit-tested (happy / empty-content / bad-JSON salvage / failed-job);
  schema-propose behavior byte-preserved (its existing tests stay green).
- Agent-facing MCP/subagent wrappers explicitly deferred (extensibility-track follow-up row).
