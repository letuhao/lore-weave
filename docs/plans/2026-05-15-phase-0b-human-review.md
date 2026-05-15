# Plan — Human-in-loop QA review of the AMAW Phase 0b batch

> **Task:** default v2.2 (12-phase, human-in-loop, NOT `/amaw`). Size M.
> **Subject under review:** commit `0e2732ac` — tilemap Phase 0b gateway tool-use
> contract + SSE parser + L3 harness (43 files, produced by an XL `/amaw` batch).
> **Deliverable:** a tracked bug list. **No code fixes in this task** — fixes are a
> separate follow-up task; actionable bugs land in `docs/deferred/DEFERRED.md`.

## Why this task exists

The session-prior AMAW-trust verdict: an autonomous AMAW batch *can confidently
mis-clear a real correctness bug* — for correctness-critical code an independent
human-led review afterward is mandatory. Phase 0b is correctness-critical (SSE
parser, LLM-contract conformance). This task is that independent pass.

## Two review layers

### Layer A — code correctness & quality

Independent re-review of all 43 changed files + one hop out. Per file-group:

| Group | Files | Lenses |
|---|---|---|
| SSE parser | `sse.rs` | chunk-boundary buffering, `[DONE]` skip, error/parse-fail termination, the post-error-leak fix, 16 MiB cap, CRLF, multi-`data:` lines, trusting the JSON `event` discriminator |
| Accumulator | `tool.rs` | interleaved/out-of-order indices, first-write-wins id/name, empty args, finish-on-error |
| Stream client | `client.rs` | async `next()` loop, `read_timeout` vs total timeout, terminal-`Err` contract, HTTP-status error path |
| Go streamers | `streamer.go`, `anthropic_streamer.go` | `tool_calls[]` fragment parse, empty-fragment skip, `Index` verbatim (no counter bleed), `stream_options.include_usage`, Anthropic `input_json_delta` mapping |
| Go adapters + handler | `adapters.go`, `stream_handler.go` | `SupportsTools()`, `hasToolDefinitions`, D8 guard placement, `tools`/`tool_choice` pass-through in all 3 openai-compat adapters |
| Contract | `openapi.yaml` | `ToolCallEvent` schema, `tool_choice`, discriminator.mapping |
| Python SDK | `models.py`, `client.py`, `__init__.py` | discriminator-idiom parity, `tool_choice`, dispatch |
| Harness | `harness/{prompt,validate,mod}.rs`, `main.rs` | L3 prompt fidelity to TMP_008b §3/§9, validators R1-R5 correctness, report logic, env handling |
| Tests | all `*_test.*` / `tests/*` | do they prove invariants or just happy-path? coverage gaps |

**Live re-verify (per user — full):**
1. Re-run `tilemap-service classify` against live lmstudio.
2. Raw-curl the gateway `/internal/llm/stream` with a tool request — inspect raw `tool_call` SSE frames.
3. **Anthropic path** — exercise `streamAnthropicSSE` tool_use → `tool_call` mapping (mock or real Anthropic).
4. **D8 reject live** — send `tools` to a provider whose adapter `SupportsTools()==false` → expect `400 LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER`.

### Layer B — AMAW process audit

Read `docs/audit/AUDIT_LOG.jsonl` + the 6 findings docs (design r1-r4, code-r1, post-review). Assess:
- Did the 4-round design loop **converge or thrash**? Each round found real BLOCKs — would a single careful pass have caught them?
- Any Adversary finding a **false positive**?
- Did the Scope Guard's CLEAR **miss** what `/review-impl` then caught (the MED SSE leak)? What does that say about the gate ordering?
- Did AMAW **confidently mis-clear a real bug** (the prior batch's B1 failure mode)? — cross-check Layer A findings against what the Adversary rounds examined.
- Is the 4-design-round cost justified by the bugs found?

## Severity rubric

HIGH (production bug) · MED (real risk, not exploitable today) · LOW (coverage/drift/doc) · COSMETIC.

## Output

`docs/audit/phase-0b-human-review-findings.md` — Layer A bug list + Layer B process
audit, findings ordered by severity with `file:line` refs. Every HIGH/MED that needs
code change → a `DEFERRED.md` row (the follow-up fix task picks them up). If a finding
is "nothing wrong, verified", it states the specific checks made.

## Phase notes

VERIFY = reproduce each finding (no speculative bugs). REVIEW = severity calibration +
dedup. QC = coverage (all 43 files + the 4 live checks done). POST-REVIEW = human vets
the bug list. COMMIT = findings doc + DEFERRED only — zero code changes.
