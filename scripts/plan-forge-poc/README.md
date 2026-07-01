# PlanForge POC

Headless CLI to evaluate the novel system-spec planner workflow.

**Status:** POC frozen — regression harness only. **Implement handoff:** [`docs/specs/2026-07-01-plan-forge/09_PLANFORGE_BLUEPRINT.md`](../../docs/specs/2026-07-01-plan-forge/09_PLANFORGE_BLUEPRINT.md)

## Quick run (rules)

```bash
python scripts/plan-forge-poc/run_poc.py
```

## LLM live run (LM Studio)

Requires LM Studio at `http://127.0.0.1:1234` with `google/gemma-4-26b-a4b-qat` (or set env).

```bash
python scripts/plan-forge-poc/run_poc_llm.py --compare-rules
# equivalent:
python scripts/plan-forge-poc/run_poc.py --llm --compare-rules
```

Env: `PLANFORGE_LM_BASE_URL`, `PLANFORGE_LM_MODEL`.

Outputs: `out/plan_analyze.json`, `out/novel_system_spec.llm.json`, `out/llm_io/`, `out/validation_report.llm.md`.

## HIL refine run

```bash
python scripts/plan-forge-poc/run_poc_hil.py --script fixtures/hil_eval_script.yaml
python scripts/plan-forge-poc/run_poc_hil.py --interactive
```

Outputs: `out/novel_system_spec.hil.json`, `out/hil_eval_report.md`, `out/hil_io/`.

## Fidelity + elaboration run

Phase A (fidelity phần đầu) then Phase B (elaboration phần sau):

```bash
python scripts/plan-forge-poc/run_poc_fidelity.py --script fixtures/hil_fidelity_script.yaml
python scripts/plan-forge-poc/run_poc_fidelity.py --phase elaboration   # requires Phase A gate PASS
python scripts/plan-forge-poc/run_poc_fidelity.py --interactive
```

Outputs: `out/novel_system_spec.fidelity.json`, `out/fidelity_report.md`, `out/fidelity_gate.json`, `out/novel_system_spec.elaborated.json`.

Rubric: `fixtures/story-plan-v1.fidelity.yaml`. Eval docs: `docs/specs/2026-07-01-plan-forge/06_FIDELITY_POC_EVAL.md`, `07_ELABORATION_POC_EVAL.md`.

## Chat HIL (vague feedback + orchestration)

Simulates main chat session calling planner with lazy user messages:

```bash
python scripts/plan-forge-poc/run_poc_chat_hil.py --rules-only   # CI-fast
python scripts/plan-forge-poc/run_poc_chat_hil.py                 # + LLM interpret
python scripts/plan-forge-poc/run_poc_chat_hil.py --interactive  # confirm cards
```

Requires `out/novel_system_spec.fidelity.json` from fidelity run. Fixture: `fixtures/chat_hil_vague_script.yaml`.

Outputs: `out/novel_system_spec.chat_hil.json`, `out/chat_hil_report.md`, `out/chat_hil_transcript.json`.

Eval: `docs/specs/2026-07-01-plan-forge/08_CHAT_HIL_POC_EVAL.md`.

## Step-by-step

```bash
python scripts/plan-forge-poc/ingest.py scripts/plan-forge-poc/fixtures/story-plan-v1.md -o scripts/plan-forge-poc/out/plan_document.json
python scripts/plan-forge-poc/propose.py scripts/plan-forge-poc/out/plan_document.json -o scripts/plan-forge-poc/out/novel_system_spec.json
python scripts/plan-forge-poc/decompose.py scripts/plan-forge-poc/out/novel_system_spec.json -o scripts/plan-forge-poc/out/plan_graph.json
python scripts/plan-forge-poc/compile.py scripts/plan-forge-poc/out/novel_system_spec.json -o scripts/plan-forge-poc/out --arc 2 --mock-llm
python scripts/plan-forge-poc/validate.py scripts/plan-forge-poc/out -o scripts/plan-forge-poc/out/validation_report.md --golden scripts/plan-forge-poc/fixtures/story-plan-v1.expectations.yaml
```

## Spec

- [`docs/specs/2026-07-01-plan-forge/01_PLANFORGE_ARCHITECTURE.md`](../../docs/specs/2026-07-01-plan-forge/01_PLANFORGE_ARCHITECTURE.md)
- Schemas: [`contracts/plan-forge/`](../../contracts/plan-forge/)

## Dependencies

- Python 3.11+
- PyYAML (`pip install pyyaml`) for validate step
- `requests` for LLM path

## Tests

```bash
pytest scripts/plan-forge-poc/test_plan_forge.py -q
pytest scripts/plan-forge-poc/test_plan_forge.py -q -m live   # requires LM Studio
```
