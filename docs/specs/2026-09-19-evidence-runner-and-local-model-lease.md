# Spec — An evidence-first suite runner, then one model at a time per local endpoint

- **Date:** 2026-09-19
- **Status:** 📝 **DRAFT — input to CLARIFY.** Not an approved design. CLARIFY, DESIGN and the PO checkpoint still apply.
- **Source idea:** [`docs/ideas/2026-09-19-leftovers-after-v010-plan.md`](../ideas/2026-09-19-leftovers-after-v010-plan.md) (IDEA-002: 26 ideas, 9 sources, scored shortlist)
- **Evidence it builds on:** [`docs/plans/2026-09-18-close-v010-leftovers.md`](../plans/2026-09-18-close-v010-leftovers.md) Cycles 7–10 (six full runs, every red traced) · [`DEFERRED.md`](../deferred/DEFERRED.md) #164, #165

## 1. Problem

The v0.1.0 leftovers plan ended green: **201 passed, 0 failed, 0 skipped** on the final images. It took six full runs of about 25 minutes each to get there. Every red cost a hand investigation, and the causes fell into families that no test in the product could have caught:

| # | Leftover | Measured | Today |
|---|---|---|---|
| P1 | **Reds nobody can replay.** A solo re-run wiped `test-results/`, and with it the only trace | 2 reds (flywheel, inline-correction) still without a cause after 6 runs | DEFERRED #165 |
| P2 | **The environment changes the verdict.** The dev VM's clock steps back 1.39 s every 30 s. The knowledge summary scheduler fires 10 min after a restart. Uncommitted locale edits get baked into test images | Cycles 8, 9 | plan text only |
| P3 | **One local model, many callers.** Two different models requested at once from one LM Studio → `Engine protocol startup was aborted` → `LLM_UPSTREAM_ERROR` → the per-kind circuit breaker opens → 20 × `LLM_CIRCUIT_OPEN` in 30 s → a user's extraction ends `completed_with_errors` | Run 4. The second caller was **another account's** `kg_summary` job | Cycle 9 text; filed as an operating constraint, not a product problem |
| P4 | **Test debt.** Two old composition unit reds (a 422 in `test_create_node_201_and_bad_reference_400`; `test_scene_beats` needs `git` in the image); no e2e tsconfig (two type errors); `go test ./...` deadlocks unless `-p 1` | Cycles 1, 2, 6 | plan text only |

## 2. Who it is for

- **The PO**, who decides on shipping from a suite result, and should be able to trust a single red or a single green.
- **Whoever runs the suite next.** Today a red means a manual investigation with no evidence guaranteed.
- **Self-hosters on one GPU** (P3). Several of their jobs, or several accounts on one box, share one LM Studio, and today the loser gets a silently degraded result.

## 3. Goals

- **G1:** every full-suite red leaves a replayable trace **and** the matching service-log window, and a solo re-run can never erase them.
- **G2:** before a full run, the known environment traps are measured and shown: clock steps, schedulers due in the next 30 min, models loaded, and a dirty working tree baked into an image.
- **G3:** one ledger of full runs, so "failed once in N runs" is a fact on record, not a memory.
- **G4:** on one local endpoint, requests for **different** models are sequenced, and a model-load abort caused by contention never opens the circuit breaker. A second caller waits; it does not fail.
- **G5:** the known test debt (P4) is cleared, so the gates mean what they say.

## 4. Non-goals

- **Loading or unloading models in LM Studio from the platform.** The PO's standing rule is that LM Studio manages its own models. G4 only *orders requests*. IDEA-002 idea 7 is dropped for this reason.
- **A per-chapter revision sequence (DEFERRED #164).** Production database clocks don't step back. It stays deferred with its recipe.
- **Fixing the host's WSL2 clock from the repo.** The runner detects it, and the fix is documented; it belongs to the machine.
- **Asynchronous critique (202 + poll).** It remains rejected for now (IDEA-001).
- **A flaky-test quarantine that hides reds.** Nothing in this spec turns a red into a pass. A test that fails once and passes on retry is recorded as exactly that.

## 5. Chosen options

### B — Evidence-first suite runner (score 4.4) — first

**Shape.** One wrapper, e.g. `scripts/e2e/run-suite.py`, that every full run goes through:

1. **Preflight** (target: under 2 min), each check printed, with its evidence:
   - a 60 s wall-clock-versus-monotonic probe inside one service container, flagging steps larger than 0.2 s;
   - scheduler start times from the running containers against their configured startup delays (e.g. knowledge summary regen at `DEFAULT_STARTUP_DELAY_S = 600`), flagging any job due within the run window;
   - the models loaded right now, read-only from LM Studio's `/api/v0/models`;
   - image freshness: each image's build time against the last commit touching its service, and whether the working tree was dirty at build time.
2. **The run**, with `--output runs/<timestamp>/`, outside `test-results/`, and `--trace=retain-on-failure`.
3. **A ledger**: `runs/LEDGER.jsonl` gets one line per test per run (status, duration, run id, image ids).
4. **`why-red <test>`**: for a failed test, it collects the trace, the service-log window by trace id (reusing `collect_run_evidence.py`), the `llm_jobs` rows in that window, and any clock steps. The output is one folder.

It also absorbs P4 as its first rows, and adds a clean-tree image build (refuse, or build from a clean worktree, when the working tree is dirty).

**Bite.**
- Delete a run's `test-results/`: the evidence in `runs/<ts>/` survives.
- Start the preflight right after restarting knowledge-service: it names the summary job due in 10 min.
- Break a test on purpose: `why-red` returns its trace and log window.

### A — One model at a time per local endpoint (score 4.1) — second

**Verified premise (2026-09-19).** provider-registry already has:
- a concurrency governor and circuit breaker per **provider type** (`internal/ratelimit/breaker.go`);
- a durable per-type work queue behind a semaphore, "wait-not-fail" (`internal/api/server.go`);
- an optional concurrency cap per **credential**.

What it lacks:
1. the cap counts **requests, not distinct models**, so two requests for different models pass even under a cap of 2;
2. it's keyed per **credential**, but in run 4 two accounts with separate credentials pointed at **the same endpoint**;
3. the load abort comes back as `provider permanent error: HTTP 400 … Engine protocol startup was aborted`, is counted as a failure, and opens the breaker for everyone on that provider type.

**Shape.**
- **Model lease:** for a local provider type (LM Studio first), at most one distinct `provider_model_name` in flight per **normalized endpoint URL**. Requests for the leased model run under the existing semaphore; requests for another model **wait** (FIFO, with an aging bound so neither side starves) until the lease is released. That's the "sequential" fix the upstream reports recommend.
- **Contention is not failure:** a response matching the load-abort signature is classified as retryable contention. It's retried with backoff under the lease and is **not** counted by the breaker.
- Behind a config flag, default on for `lm_studio`. Hosted providers are unaffected.

**Bite.**
- Unit: two leases for different models on one endpoint → the second waits; the same model → both run.
- Unit: a load-abort response → retried, breaker count unchanged; restore the classification → the breaker opens.
- Live: replay run 4's collision (a 26B `kg_summary` and a 12B glossary extraction at the same moment on `lw-iso`). Today it ends `completed_with_errors`; with the lease, both complete.

## 6. Rejected alternatives (from IDEA-002's scoring)

| Option | Score | Why not now |
|---|---|---|
| Per-chapter revision sequence (#164) | 2.4 | Hardens against a clock problem production does not have; migration + ~15 writers |
| Sign-in sweep watermark or batch call | 3.2 | ~130 cheap requests per sign-in; no user-visible cost measured. B's ledger measures it first |
| Debt sweep as its own phase | 3.9 | Worth doing, but it is housekeeping. Folded into B's first rows |
| Platform loads/unloads models | — | Conflicts with the PO rule that LM Studio manages its own models |
| Chaos mode (step the clock, collide models nightly) | — | Valuable later; needs B's evidence runner first |

## 7. Invariant notes

- **B:** tooling only; no product code, so no product invariant applies. The preflight's LM Studio call is a read (`/api/v0/models`) and never loads or unloads a model.
- **A:**
  - It stays inside provider-registry, the single gateway every LLM call already goes through; no new direct LLM imports.
  - The service stays in Go (the language rule).
  - User-data scope is unchanged: the lease keys by endpoint and model, and carries no user content.
  - A lease across accounts sharing one endpoint is intentional: it's the physical resource. DESIGN must confirm that no account's request data can reach another's.

## 8. Risks

- **A: throughput.** Sequencing different models on one endpoint serialises work that today sometimes runs in parallel, when both models happen to fit. DESIGN decides whether "fits in memory" can be known without controlling LM Studio. If it can't, the lease trades throughput for correctness, and the flag is how an operator opts out.
- **A: starvation.** A long queue for model X could starve Y. It needs FIFO with an aging bound, sized in DESIGN.
- **A: endpoint identity.** `host.docker.internal:1234` and `127.0.0.1:1234` are the same box. Normalisation has to be conservative (the same URL string after normalising); DESIGN covers the aliases.
- **B: preflight false alarms.** A check that cries wolf gets ignored. Every check shows its measured number, not only a verdict.
- **B: disk.** `runs/` with videos and traces grows fast. It needs a retention rule, e.g. keep the last N runs and every run with a red.

## 9. Open questions for CLARIFY

1. **Order:** B then A, as recommended, or A first because it's the user-facing fix?
2. **A's default:** lease on by default for LM Studio, or opt-in per credential?
3. **B's gate:** should a failed preflight **refuse** a full run, or only warn and record the warning in the ledger?
4. **The two unexplained reds (#165):** keep them open until B captures one, or close them after N clean runs recorded in the ledger?
5. **P4 debt:** fix the two old composition unit reds in this work, or open them as separate issues?

## 10. Smallest tests (proposed acceptance hints)

| Option | Test | Drop it if |
|---|---|---|
| B | A one-day spike: preflight + `--output` outside `test-results/` + ledger, used for the next three full runs | The preflight takes more than 2 minutes, or any red in those three runs still lacks a trace and its log window |
| A | Replay run 4's collision on `lw-iso`, first on today's path, then with a per-endpoint sequencer behind a flag | The sequenced run still ends `completed_with_errors`, or its wall time exceeds 2× the two jobs run alone |
