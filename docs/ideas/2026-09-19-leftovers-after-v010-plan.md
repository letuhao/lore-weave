# IDEA-002 — What the v0.1.0 leftovers plan left behind: one local model, a stepping clock, and reds nobody can replay

| Field | Value |
|---|---|
| Id | IDEA-002 |
| Status | promoted |
| Recorded | 2026-09-19 |
| Last updated | 2026-09-19 |
| Proposed by | chat (PO: "investigate leftovers problem we found in this plan then extend the idea before we continue solve them") |
| Related | [IDEA-001](2026-09-18-close-v010-leftovers.md) · [plan 2026-09-18-close-v010-leftovers](../plans/2026-09-18-close-v010-leftovers.md) Cycles 7–10 · [`DEFERRED.md`](../deferred/DEFERRED.md) #164, #165 · `CHANGELOG.md` `[0.1.0]` Known issues |

## Frame

**How might we** close what the v0.1.0 leftovers plan left behind, so that the next leftover is cheap to find and cheap to fix?

- **For whom:**
  - **The PO**, who has to decide on shipping from a suite that took six full runs to show green.
  - **Self-hosters**, who run LoreWeave on one GPU and one LM Studio.
  - **Whoever runs the suite next.**
- **Pain / opportunity:** each red in the six runs cost 25 minutes and a hand investigation. The causes clustered into a few families, none of them tests the product could have caught on its own:
  - a Docker VM clock that steps back 1.4 s every 30 s;
  - one local model server that aborts when two models are asked for at once;
  - a service worker that reloaded first visits;
  - traces lost to a re-run.

  The same families will produce the next leftovers unless something changes.
- **Already exists?** Parts are recorded, but nothing covers the whole.

**Recorded in `DEFERRED.md`:**
- `DEFERRED.md` #164: revision order depends on the database's wall clock.
- `DEFERRED.md` #165: two single E2E reds with no cause found.

**Known issues in `CHANGELOG.md`:** MCP-created books are provisioned later; a plan can fail after three loops; the critic waits at most 240 s.

**In the plan's text only:**
- the sign-in backfill costs about 130 requests per sign-in for a 105-book account;
- B7.3 moved from E2E to unit coverage;
- two old composition unit reds: `test_create_node_201_and_bad_reference_400` returns 422, and `test_scene_beats` needs `git`, which the image lacks;
- the e2e folder has no tsconfig, and two type errors surfaced;
- `go test ./...` deadlocks unless run with `-p 1`;
- the summary scheduler fires 10 minutes after a restart and collides with the suite's model;
- uncommitted locale edits get baked into test images.

**Not recorded anywhere yet:** the local-model collision as a *product* problem (Cycle 9 filed it as an operating constraint).

### The leftovers, grouped (the investigation)

| # | Leftover | What was measured | Where it lives now |
|---|---|---|---|
| L1 | **One local model, many callers.** Two models requested at once → LM Studio `Engine protocol startup was aborted` → our circuit breaker opens → extraction ends `completed_with_errors` | Run 4: 4 × `LLM_UPSTREAM_ERROR`, then 20 × `LLM_CIRCUIT_OPEN` in 30 s. The second caller was another account's background `kg_summary` | Cycle 9 text only |
| L2 | **Wall clock is not order.** The VM clock steps back 1.39 s every 30 s. Revision "newest two" pairs the wrong revisions | In-container probe; 1 order inversion in 260 saves | DEFERRED #164 |
| L3 | **Reds without a replay.** Traces lost to re-runs; two reds (flywheel, inline-correction) seen once in six runs | 6 runs × ~25 min | DEFERRED #165 |
| L4 | **The sign-in sweep costs O(books) every time.** One `GET /work` per owned book per sign-in, including books provisioned long ago | ~130 requests in 100 ms, 105-book account | plan text |
| L5 | **Test debt.** Two old unit reds; no e2e tsconfig; `go test` needs `-p 1`; B7.3 now covered only in unit tests | observed in Cycles 1, 2, 6 | plan text |
| L6 | **Still-open product gaps.** MCP-created books provisioned later; a 3-loop plan failure; a 240 s critic cap | Known issues | CHANGELOG |
| L7 | **Run hygiene.** The scheduler fires 10 min after a restart; locale edits leak into images; a restart before a run changes the result | Cycle 9 | plan text |

## Diverge

Raw ideas, unjudged. Labelled with the technique.

1. **Model lease per local endpoint**: provider-registry grants one "loaded model" at a time per LM Studio endpoint and queues callers for other models. *(analogy: a database connection pool)*
2. **Load-abort is contention, not failure**: classify `Engine protocol startup was aborted` as retryable-with-backoff so it never trips the circuit breaker. *(inversion: the error is the queue's job, not the breaker's)*
3. **Model affinity scheduling**: batch pending jobs by model, and drain all 12B work before swapping to 26B. *(analogy: a disk elevator)*
4. **Background jobs yield to interactive ones**: summary regen and distill run only when no foreground job is in flight. *(persona lens: the author at the keyboard)*
5. **Scheduler jitter, not "10 min after start"**: every restart re-arms the same collision; spread first runs over a window, or persist the last-run time. *(remove a constraint)*
6. **The one-model constraint as a product setting**: "this provider serves one model at a time"; the platform plans around it instead of discovering it by failure. *(make the implicit explicit)*
7. **The platform owns loading**: provider-registry pre-loads the needed model before dispatching. *(inversion — but the PO rule is: never control LM Studio by hand; a product call is not by hand, still worth writing down)*
8. **A suite preflight**: before a full run, measure clock steps for 60 s, list schedulers due in the next 30 min, show which models are loaded, and refuse or warn. *(analogy: an aircraft checklist)*
9. **Artifacts always outside `test-results/`**: the run wrapper sets `--output=runs/<ts>` and `--trace=retain-on-failure`, so a solo re-run can never erase evidence. *(worst idea inverted: "delete the evidence")*
10. **A run ledger**: every full run appends pass/fail per test to one file; a test that failed once in N runs is visible without memory. *(analogy: flight data recorder)*
11. **Rerun-on-fail with trace, reported separately**: never counted as a pass, always recorded as "failed once, passed on rerun" with its trace. *(from research — Microsoft's `on-first-retry`)*
12. **Quarantine with an owner and a deadline**: a test that goes red twice without a cause moves to a quarantine job that still runs. *(from research — Slack/GitHub/Atlassian pattern)*
13. **Fix the dev VM clock**: document the WSL2 fix (`hwclock -s` / chrony with slewing) and have the preflight detect the steps. *(from research)*
14. **A per-chapter revision sequence** (DEFERRED #164): order by a monotonic `seq`, not `created_at`. *(analogy: git commit parents)*
15. **Hybrid logical clocks for every ordered table**: wall time nudged forward so it never goes back. *(from research — HLC; wild for this codebase)*
16. **Refuse to start when the clock steps**: a service health check fails if wall-clock minus monotonic jumps. *(worst possible idea — surfaces how widespread time-dependence is)*
17. **Sign-in sweep with a watermark**: book-service remembers "all books provisioned as of revision X" per user, and a sign-in only checks books created or changed since. *(SCAMPER: eliminate)*
18. **One batch call instead of N**: composition answers "which of these book ids lack a ready Work" in one query. *(SCAMPER: combine)*
19. **Retire the sweep once the backfill is done**: after every legacy book is provisioned, creation-time provisioning covers new books; drop the sign-in trigger behind a flag. *(remove a constraint)*
20. **An MCP provisioning queue**: `book_create` records "provision on the owner's next authenticated request", consumed by the sign-in or Studio path. *(from Known issues)*
21. **Critique becomes 202 + poll**: removes the 240 s cap entirely. *(from IDEA-001's rejected list, revisited)*
22. **A debt sweep**: fix the two old unit reds, add an e2e tsconfig to CI, make `go test` serialise DB packages by itself. *(persona lens: the next contributor)*
23. **Images built from a clean tree**: the iso build refuses a dirty working tree, or builds from `git stash`/a worktree, so uncommitted locale edits never reach a test image. *(inversion)*
24. **A "known stack state" snapshot**: take a DB snapshot before a suite and restore after, so leftover data (the 26 foreign scenes, the other account's jobs) cannot leak between runs. *(analogy: VM snapshots)*
25. **Chaos mode**: deliberately step the clock and collide models in a nightly run, so these failure families are tested on purpose, not by accident. *(wild — analogy: Netflix Chaos Monkey)*
26. **A single "why did this go red" command**: given a failed test, it pulls its trace, the matching service logs by trace id, `llm_jobs` rows, and clock steps in that window. *(analogy: incident runbook automation; builds on `collect_run_evidence.py`)*

## Research

| Source | What it shows | Read |
|---|---|---|
| [Fixing Time Drift in Docker on WSL2 — Heath Stewart](https://heaths.dev/troubleshooting/2020/05/23/fixing-time-drift-in-docker-on-wsl2.html) | WSL2's VM clock desynchronises from the host (sleep/resume, load); containers inherit it | 2026-09-19 |
| [docker/for-win #10347](https://github.com/docker/for-win/issues/10347) | Long-running report of wrong container time under the WSL2 backend | 2026-09-19 |
| [Fix WSL time drift — Ishan Das Sharma](https://ishan.page/blog/2023-03-08-wsl-time-drift/) | Workarounds: `hwclock -s`, `ntpdate`, `wsl --shutdown`; chrony with slewing after the first step | 2026-09-19 |
| [LM Studio bug #1796 — JIT auto-evict](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1796) | Concurrent requests for different models evict a model before it finishes, or load both despite insufficient RAM; no setting mitigates it | 2026-09-19 |
| [hermes-agent #78011 — MoA with LM Studio JIT](https://github.com/NousResearch/hermes-agent/issues/78011) (via search summary) | Concurrent requests to several models abort each load; the suggested fix is sequential calls | 2026-09-19 |
| [zeroclaw #9177](https://github.com/zeroclaw-labs/zeroclaw/issues/9177) (via search summary) | The same `Engine protocol startup was aborted` on JIT loading, while manual load works | 2026-09-19 |
| [HLC in depth — Kousik Nath](https://medium.com/geekculture/all-things-clock-time-and-order-in-distributed-systems-hybrid-logical-clock-in-depth-7c645eb03682) | Hybrid logical clocks stay close to wall time but never violate happens-before | 2026-09-19 |
| [Flaky tests: detection, quarantine, prevention (2026)](https://scrolltest.com/flaky-tests-detection-quarantine-prevention-guide-2026/) (via search summary) | Detect by repeated runs; quarantine with owner + deadline; keep running quarantined tests separately | 2026-09-19 |
| [BrowserStack — Playwright flaky tests](https://www.browserstack.com/guide/playwright-flaky-tests) (via search summary) | `trace: 'on-first-retry'` captures evidence exactly when it is needed | 2026-09-19 |

- **What users say:** LM Studio users hit the same abort whenever two models are requested concurrently, and the requests have to be sequenced *upstream* (in the caller). LM Studio has no setting for it. WSL2 users treat the clock as a known, recurring nuisance with manual resets.
- **What failed:** relying on LM Studio's JIT auto-evict to arbitrate concurrent callers (#1796). Ad-hoc `wsl --shutdown` resets, which drift back.
- **Ideas added from research:** 11, 12 and 13 above. Research also *confirms* 1–3: the fix for concurrent local models belongs in the caller, which here is provider-registry.
- The page `cr0x.net/en/wsl2-time-drift-fix` could not be fetched (connection refused), so it is not used.

## Converge

**Clusters:**
- **(A) One local model, many callers:** 1–7, 20.
- **(B) Trustworthy runs:** 8–13, 23, 24, 26, and 25 (wild).
- **(C) Time is not order:** 14–16.
- **(D) Sign-in sweep cost:** 17–19.
- **(E) Debt and open gaps:** 21, 22.

| # | Candidate | Value | Fit | Effort | Risk | Evidence | Novelty | Score |
|---|---|---|---|---|---|---|---|---|
| A | **Local-model lease in provider-registry + load-abort as retryable** (ideas 1, 2, 3) | 5 — a self-hoster on one GPU silently gets `completed_with_errors` whenever two of their jobs overlap; run 4 proved it | 5 — local-first and "one strong model at a time" are stated platform rules; this makes the platform respect them | 3 — one Go service (provider-registry) plus the SDK's error classification; about a week | 3 — changes throughput and fairness for every LLM call; reversible behind a flag | 5 — measured (run 4) + three independent upstream reports | 3 — sequencing is the known fix; doing it at the platform's provider layer is less common | **4.1** |
| B | **Evidence-first suite runner** (ideas 8, 9, 10, 11, 13, 26): preflight (clock, due schedulers, loaded models), artifacts outside `test-results/`, a run ledger, a `why-red` command | 4 — every red in six runs cost a manual investigation; two are still unexplained because evidence was lost | 5 — the repo already treats evidence as the product of a run (bite rule, `collect_run_evidence.py`) | 4 — scripts and a wrapper, no product code; days | 5 — tooling only, fully reversible | 5 — six runs measured; research agrees on trace-on-retry + ledger | 3 — known pieces, combined around this repo's rules | **4.4** |
| C | **Per-chapter revision sequence** (idea 14, DEFERRED #164) | 2 — production DB clocks do not step back; the dev VM does | 3 — correctness hardening | 2 — migration + ~15 writers | 2 — migration on a core table | 4 — measured inversion | 2 — standard | **2.4** |
| D | **Sign-in sweep watermark or batch call** (ideas 17, 18) | 2 — ~130 cheap requests per sign-in; no user-visible cost measured yet | 4 — keeps the backfill honest at scale | 4 — book-service and composition, days | 4 — additive | 3 — one measurement | 2 — standard | **3.2** |
| E | **Debt sweep** (idea 22 + a clean-tree image build, idea 23) | 3 — removes known reds and a leak into test images | 5 — gates stay green and meaningful | 4 — small, local fixes | 5 — test/tooling | 5 — each item observed | 1 — housekeeping | **3.9** |

**Invariant notes:**
- **A**: stays inside provider-registry, which already owns every LLM call (the single gateway; no new direct LLM imports). The Go service keeps its language. It must **not** load or unload models in LM Studio itself: the PO's rule is that LM Studio manages its own models. The lease only *sequences* requests, which the research says is the caller's job anyway. Idea 7 (platform pre-loads models) conflicts with that rule and is dropped.
- **B**: no product code; nothing to check against the invariants.
- **C**: a migration on `chapter_revisions`, so DESIGN must cover its ~15 writers.
- **D**: user-data scope is unchanged (owner-only, OQ-1).

**Recommendation:** do **B first, then A.**
- **B** scores highest, costs days, and pays back on every future leftover. The two unexplained reds (#165) can only be solved with evidence that B keeps by default.
- **A** is the most valuable *product* change. It turns a class of silent `completed_with_errors` into a queue, for every self-hoster on one GPU.
- They don't compete: B tells us whether A worked.

**Why the others lost:**
- **C** protects against a clock problem that production doesn't have. It stays deferred (#164), with its recipe, until a multi-host database appears.
- **D** costs roughly 130 cheap requests per sign-in, and no user has felt it yet. Measure it under B's ledger first.
- **E** is worth doing but is housekeeping. Fold it into B's plan as its first rows rather than make it a phase of its own.
- **21 (async critique)** stays rejected for now, for the reason IDEA-001 gave: it's a contract change, and the 240 s cap is honest and documented.

## Shortlist

- **B — Evidence-first suite runner** — shortlisted 2026-09-19. Preflight, kept artifacts, run ledger, `why-red`. It also closes E's clean-tree build.
- **A — Local-model lease + load-abort as retryable** — shortlisted 2026-09-19. Sequence requests per local endpoint in provider-registry, and stop tripping the circuit breaker on contention.

## Smallest test

- **B:**
  - **Test:** a one-day spike. A wrapper runs one full suite with a 60 s clock-step probe, a list of the schedulers due in the next 30 min, and the loaded models, with `--output` outside `test-results/`, and appends to a ledger.
  - **Drop it if:** the preflight takes more than 2 minutes, or across the next three full runs any red still lacks a trace and the matching log window.
- **A:**
  - **Test:** replay run 4's collision on `lw-iso`. Fire one 26B `kg_summary` and one 12B glossary extraction at the same moment. First run them through today's path (expected: `completed_with_errors`); then run them through a provider-registry build with a per-endpoint sequencer behind a flag.
  - **Drop it if:** the sequenced run still ends `completed_with_errors`, or its wall time is more than 2× the sum of the two jobs run alone.

## Log

- 2026-09-19 — seed — PO asked to investigate the leftovers found by the v0.1.0 leftovers plan and extend the idea before solving them.
- 2026-09-19 — explored — 26 ideas across 7 techniques; research on WSL2 clock drift, LM Studio concurrent JIT loading, hybrid logical clocks, and flaky-test practice (9 sources).
- 2026-09-19 — shortlisted — B (evidence-first suite runner, 4.4) and A (local-model lease, 4.1); C stays deferred (#164); D and E fold into B's plan.
- 2026-09-19 — promoted — PO promoted it. Spec draft for CLARIFY: [`docs/specs/2026-09-19-evidence-runner-and-local-model-lease.md`](../specs/2026-09-19-evidence-runner-and-local-model-lease.md). Premise corrected while drafting: provider-registry already has a per-kind governor, a breaker and a per-credential cap. A's gap is counting requests rather than distinct models, keying by credential rather than endpoint, and counting load-aborts against the breaker.
