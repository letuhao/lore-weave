# MMO-RPG Agent Architecture & Platform Operability — Gap Analysis

- **Date:** 2026-06-20
- **Status:** REVIEW NOTE / backlog seed. Not a build spec.
- **Scope (corrected):** the **LLM-driven super-distributed MMO RPG** — `docs/03_planning/LLM_MMO_RPG/`. 41 services, per-reality sharded DBs, event-sourced, `world-service` (Rust/Go) + `roleplay-service` (the agent runtime) + `game-server` (Colyseus WS). NOT the novel/glossary platform (that's the *immutable canon layer* this game derives from).
- **Trigger:** PO asked to compare two reference images against the repo's **agent** layer — (1) a generic *Event-Driven Multi-Agent AI Architecture for Enterprise Workflows*, (2) the "iceberg" (agents are the visible tip; the foundation is the mass).
- **Companion specs:** the agent design is *already locked* in `05_llm_safety/` (13 decisions, 2026-04-23), `00_foundation/04_kernel_api.md` (`AssemblePrompt`/`ResolveContext`), and the open-problem set `01_problems/A_llm_reasoning.md`. This file does **not** re-decide those — it maps them against the reference diagram and flags what's unbuilt.

> **Correction to my first pass:** I initially scored the repo as a novel-workflow platform and called the agent layer "early / mostly chat tool-loop." Wrong. The agent architecture here is a **deliberately-constrained MMO NPC runtime** with a locked, sophisticated design. The gaps are not "add more agent infra" — they're "the keystone agent service isn't built yet, and the hard *semantic* problems are unmeasured."

---

## 1. The core inversion (read this first — it reframes the whole diagram)

The reference diagram (image 1) is an **autonomous-agent** architecture: agents *decide* and *act* — Action Agent, Code-Execution Agent, A2A delegation, a planner that autonomously orchestrates tools. That is the **wrong shape** for a shared persistent world, and the repo correctly rejects it.

This repo's governing principle (`05_llm_safety/00_principle.md`): **"LLM narrates, world-service decides."** The agent (NPC) is *de-powered on purpose*:

| Reference diagram assumes | This MMO RPG enforces | Why |
|---|---|---|
| Agent decides what happens | `world-service` decides; LLM narrates **post-commit** | Shared world state can't be hallucinated (A5) |
| Agent answers from its weights | **World Oracle** returns deterministic facts; LLM wraps them in voice | Same question → same answer, or it isn't a world (A3) |
| Agent autonomously calls state-changing tools | State mutations come **only** from client `/verb` commands; LLM tool-calls limited to non-mutating flavor (whisper/gesture) | Partial tool-failures can't corrupt world state (A5-D3) |
| Prompt discipline guards leaks | **Retrieval is scoped at the DB layer** (per-pair, reality-scoped, timeline-cutoff) — forbidden facts are structurally absent from context | A perfect jailbreak can't leak what was never retrieved (A6-D3/D5) |
| A2A: agents delegate to agents | **Session is the concurrency boundary** (I6); cross-session/cross-reality is event-driven via `event-handler`/`meta-worker`, never direct agent-to-agent | Multi-aggregate deadlocks + ordering (R7) |

**So the diagram's flashy layers 2 (autonomous runtime) and 8 (code-exec sandbox) are anti-requirements here.** The agent layer's job is *constrained narration over a deterministic, event-sourced, per-reality-sharded substrate.* That inversion **is** the architecture's strength.

The second image (iceberg) is exactly right for this repo: the visible agent tip sits on an enormous foundation that is **already largely built** — 19 enforced invariants, a `contracts/` standard library (`AssemblePrompt`, `MetaWrite`, `AttemptStateTransition`, outbox, resilience), per-reality sharding, an SRE service fleet (canary/incident/postmortem/slo/chaos). The PO's "I need a library + SDK + standard" already exists: `contracts/` *is* the standard, `sdks/python/loreweave_*` *is* the SDK.

---

## 2. Agent-layer scorecard (diagram layer → MMO mechanism → build state)

Build state verified in-repo (2026-06-20): file counts + `contracts/` contents.

| Diagram layer | MMO RPG mechanism | Design | Built? |
|---|---|---|---|
| **Multi-agent runtime** | 3-intent classifier → {command dispatch \| World Oracle \| NPC narration} + output filter. Not autonomous agents — a **routed pipeline**. | ✅ locked (`05_llm_safety/01,02`) | ❌ **`roleplay-service` does not exist** — the runtime keystone is unbuilt |
| **Orchestration / state mgr** | `world-service`: reality lifecycle SM, deterministic command apply, event-sourced projections, single-writer-per-session (I6) | ✅ locked | 🟡 **47 Go files — in progress** |
| **A2A protocol** | *Deliberately none.* Cross-session via `event-handler`, cross-reality via `meta-worker` + `xreality.*` Redis streams (I6/I7) | ✅ locked (as a non-goal) | 🟡 `meta-worker`/`publisher` scaffolded |
| **MCP / tool layer** | `ai-gateway` federates domain tools; roleplay flavor-tools are non-mutating only | ✅ + built | ✅ `ai-gateway` built; roleplay tool-set unbuilt (no roleplay-service) |
| **Memory layer** | NPC core aggregate + **per-(npc,pc) memory** (R8): max 100 facts/pair, rolling summary/50 events, cold-decay 30/90/365d, pgvector embeddings | ✅ infra resolved | 🟡 storage substrate designed; **semantic layer OPEN** (A1) |
| **Semantic cache** | World Oracle cache (deterministic fact cache, invalidated on L3 events) — *domain-specific*, not a generic prompt cache | ✅ designed (A3-D2) | ❌ unbuilt; **no LLM-response/embedding cache anywhere** |
| **Vector DB / RAG** | `knowledge-service` (Postgres SSOT + Neo4j) + timeline-cutoff retrieval + glossary canon; BYOK rerank via provider-registry | ✅ + built | ✅ **491 files** — the strongest agent-foundation piece |
| **Prompt / governance** | `AssemblePrompt` 8-section bundle, user text only in `[INPUT]`, XML-escaped, canary token, `prompt_audit`, versioned templates (I10) | ✅ locked | ✅ **`contracts/prompt/` is real Go** (composer, bundle, canon_cache, canary_token, audit_writer) |
| **Turn engine** | `contracts/turn` — turn_context / lifecycle_hook / outcome_writer / state | ✅ | ✅ **built** (real Go + tests) |
| **Agent gateway controls** | WS ticket handshake (S12), per-message S2/S3 re-authz, SVID service-auth (I11), per-reality isolation | ✅ locked | 🟡 game-server WS scaffold; **D-GAME-WS-EDGE-CONTROLS** open |
| **Injection defense** | 5 layers: L1 sanitize · L2 hard delimiters · **L3 canon-scoped retrieval (primary)** · L4 output filter · L5 per-PC DB isolation (RLS/service-filter) | ✅ locked (A6) | ❌ lives in roleplay-service (unbuilt) + knowledge-service filter (partial) |
| **Observability / cost / eval** | S6 cost ledger (per LLM call), `prompt_audit`, `loreweave_eval`, OTEL/tracing contracts, SRE fleet | ✅ + partial | 🟡 cost+SRE built; **tracing backend unmounted; roleplay eval absent** |

**One-line read:** the *substrate* (world-service, knowledge-service RAG, `contracts/prompt`, `contracts/turn`, cost/SRE) is built or building; the **agent runtime that ties them together (`roleplay-service`) is the single biggest unbuilt piece**, and the **hard semantic problems behind it are explicitly unmeasured (A1/A3/A4/A5/A6 residuals).**

---

## 3. The gaps that actually matter (agent-specific, prioritized)

### KEYSTONE — `roleplay-service` does not exist
Every agent mechanism above (intent classifier, NPC narration prompt, dispatch→narrate wiring, Oracle integration, injection L1/L2/L4) is **designed and locked but has no service**. `world-service` (the decider) is being built; the *narrator* isn't. Until `roleplay-service` lands, the agent layer cannot be exercised or measured — and the residual-OPEN problems below cannot be retired because **they all require V1 prototype data on real sessions**. This is the gating item.

### The hard semantic problems (all `PARTIAL/OPEN`, all need V1 measurement)
These are the genuine research-grade gaps the diagram doesn't even acknowledge:
1. **A4 — Retrieval quality on the knowledge graph.** *Gating.* If retrieval surfaces canonically-wrong facts, the NPC drifts and nothing else matters. Unmeasured on real books. Needs a benchmark dataset + "response + top-5 retrieved facts + human canon-faithfulness grade" loop. (GraphRAG / HippoRAG are the references.)
2. **A1 — NPC memory *semantic* layer.** Storage (R8 per-pair aggregates) is solved; the open parts are **fact-extraction** (what becomes a "fact"?), **summary quality** (compaction prompt), and **retrieval-from-pair** (which facts enter the prompt). No design locked — deferred to real data.
3. **A3/A5 — Classifier & Oracle coverage.** Intent-classifier accuracy and Oracle key-coverage / cache-hit-rate are unknown; misclassification → canon drift or lost commands. Per-model tool-call reliability (Claude vs GPT vs Qwen/Ollama) unbenchmarked.
4. **A6 — Output-filter calibration + novel jailbreaks.** L3/L5 give *structural* safety (strong), but L4 false-positive vs miss rate needs adversarial red-team data; jailbreak classes are an ongoing ops surface, never "solved."

### Cross-cutting agent gaps (cheaper, real)
5. **No roleplay-specific eval harness.** `loreweave_eval` exists (LLM-judge, harness) but there's **no canon-drift / persona-consistency / spoiler-leak eval loop** (G3 is OPEN). An agent you can't grade can't be improved — this should land *with* roleplay-service, as its VERIFY gate.
6. **No generic LLM-response / embedding cache.** The World Oracle caches *facts*, but repeated NPC narrations / embeddings aren't cached. At per-turn latency + cost scale this matters; `infra/docker-compose.redis-cache.yml` exists and is unused.
7. **Tracing backend unmounted.** OTEL + `contracts/tracing` are wired but export to nothing — a multi-hop turn (game-server → roleplay → world-service → knowledge → provider) is currently un-traceable end-to-end.

### The open *product* question (not a defect — a fork in the road)
8. **Autonomous NPC behavior is deliberately absent.** The architecture makes NPCs **reactive narrators**. A "living world" (Stanford Generative Agents / Smallville: NPCs with goals, daily plans, reflection, NPC↔NPC interaction) would require an *autonomous* agent loop that the current "LLM narrates, world decides" principle forbids. This is the one place the reference diagram's "multi-agent runtime" might be a real future requirement — but it must be built as **scheduled, world-service-gated NPC ticks** (proposals the world commits), never as free A2A. Decide explicitly before V3; don't let it leak in.

---

## 4. What the diagram gets *wrong* for this product (do NOT build)

- **Autonomous Action / Code-Execution agents** — violate "world-service decides"; there is no untrusted-code-exec surface. The sandbox layer is N/A.
- **A2A delegation between agents** — violates I6 (session is the concurrency boundary). Cross-context is event-driven by design; an A2A mesh would reintroduce the deadlock/ordering problems R7 solved.
- **A generic agent orchestrator/planner** — the routed 3-intent pipeline + event-sourced world is the orchestrator. A declarative planner adds nondeterminism to a system whose whole point is determinism.
- **Kafka/MSK/EventBridge** — outbox → `publisher` → Redis Streams (I13) is the chosen, sufficient spine.

---

# PART B — Platform operability (running the thing, not just building it)

The agent analysis above is about *building* the world. This part is about *operating* it. The recurring theme across the whole repo holds here too: **the backend capability is world-class; the standards and human-facing surfaces that make it operable are thin or unbuilt.** This is what makes a platform "easy to run" vs. "a CLI and a prayer."

## 5. Observability — the standard exists; adoption is the gap (verified 2026-06-20)

> Correcting the instinct "I haven't defined a logging standard / there's almost no logging": **the standard is already written and it's excellent.** `contracts/logging/` ships typed `Level`/`Field`, **PII-tagged fields** (Normal/Sensitive/PII), a `Redactor` interface (no bare regex), a **compile-time prod-build guard** (`IsProdBuild` const so Debug/PII can't leak in prod), W3C **TraceContext** correlation, and a stable JSON shape. The problem is downstream of definition:

| Gap | Evidence | Fix |
|---|---|---|
| **Adoption ≈ 0** | **0** services import `contracts/logging`; **0** import `contracts/tracing`; **1** imports `contracts/observability`. The 71 Go files that log use raw stdlib `slog`/`log` — untyped, unredacted, no `trace_id`. | Mechanical sweep: replace raw `slog` with the typed logger (free PII redaction + trace correlation per line). |
| **No enforcing invariant** | Prompts (I10), metrics (I19), timeouts (I16) are *enforced*; logging has a library + lint scripts (`logging-discipline-lint.sh`, `log-density-detector.sh`) but **no invariant** wiring services to it. | **Add I20** — "all logs through `contracts/logging`; raw `slog`/`log`/`fmt.Print*` in service paths fails lint." Wire the existing lint as a *blocking* gate. Parallels I10/I16/I19 exactly. |
| **No backend pipeline** | `contracts/logging/doc.go` states Loki/Tempo/Vector is "cycle 33+"; the OTLP exporter is an "interface seam" only. The `trace_id` the standard emits lands nowhere. | Mount Loki/Tempo + an OTLP collector; this is the "tracing backend unmounted" item from §3.7. |

**Net:** observability isn't "undefined" — it's **defined, unadopted, unenforced, and unplumbed.** Closing it is mechanical (sweep + one invariant + a backend), not a redesign.

## 6. Operational surfaces & enterprise standards — the `admin-cli`-only problem

The repo has an unusually complete ops *backend*: an SRE service fleet (`incident-bot`, `postmortem-bot`, `statuspage-updater`, `slo-budget-calculator`, `canary-controller`, `alert-recorder`, `breach-notifier`, `integrity-checker`, `backup-scheduler`, `retention-worker`, `archive-worker`), a meta-registry full of audit tables, S5 admin-command classification, break-glass. **But the only human interface to all of it is `admin-cli` (a Go CLI).** There are 24 *player/author* FE features + a `frontend-game` client, and **zero operator-facing web surfaces.** For a live LLM MMO (GMs, moderators, support, finance, on-call) a CLI does not scale.

### Missing operator surfaces (the "we don't have a CMS FE yet" class)

| Surface | Operates | Today | Why it's load-bearing for a live MMO |
|---|---|---|---|
| **Admin / CMS web console** | realities, **canon/quest/content authoring**, glossary/wiki, accounts, feature flags | `admin-cli` only | Content is the product; GMs & editors can't drive a CLI. The CMS is the single highest-leverage surface. |
| **Moderation / Trust & Safety queue** | flagged inputs (`npc.suspicious_input`), `npc.output_blocked`, player reports, ban/mute/appeal | backend audit events, **no triage UI** | An LLM MMO is a high-T&S surface (problem doc E). The injection-flag + blocked-output events are *already emitted* — nobody can act on them. |
| **Player support console** | player lookup, session/turn history, state/inventory inspect, refunds, appeals | none (raw DB) | Support can't resolve tickets without psql access — an audit + safety risk in itself. |
| **Live-ops / GM dashboard** | active realities, population, turn latency, cost-per-reality, incident state | metrics emitted, **no dashboard** | Real-time operational visibility is table-stakes for running shards. |
| **Status page** | incidents → user comms | `statuspage-updater` service exists, **no page** | The service publishes to nothing. |
| **Audit-log viewer** | `meta_write_audit`, `admin_action_audit`, `prompt_audit`, `service_to_service_audit` | tables only, SQL-only | Compliance/forensics need a queryable, redaction-aware UI — not ad-hoc SQL. |
| **Feature-flag control plane** | `feature_flags` meta table | table exists, no eval SDK/UI confirmed | Safe rollout + kill-switch needs a UI **and** a typed flag SDK (see below). |
| **FinOps / cost dashboard** | `user_cost_ledger`, budget alerts (S6) | backend ledger, **no dashboard/caps UI** | Per-user/per-reality LLM spend is the platform's #1 variable cost; needs visibility + enforceable caps. |

### Enterprise *standards* still missing (not just UIs)

These are the contract-library gaps that, like the logging case, make the above surfaces buildable consistently:
- **Admin RBAC capability map** — S5 classifies admin *commands* and dual-actor tiers exist, but there's no declared **role → capability** map for a console (who sees moderation vs. finance vs. canon vs. support). A CMS needs this before line one.
- **Unified audit-query contract** — many audit tables, **no common read/query/redaction standard** to surface them safely. Today each would be hand-rolled SQL.
- **Typed feature-flag SDK** — a flag-eval + audit library parallel to `contracts/logging`/`contracts/prompt`, so flags are consistent and killable, not scattered env checks.
- **Content-localization pipeline** — regions speaking different languages is an *in-world mechanic*; that needs a real content + UI localization standard beyond `frontend/src/i18n` (player UI) — e.g. canon/quest text variants per region.

**One-line read:** you've built the engine room and the audit trail; what's missing is the **bridge** — the operator console, the moderation queue, the cost dashboard — plus the two standards (admin RBAC, audit-query) that make those surfaces uniform instead of bespoke. The CMS FE is the right first instinct: it's the surface every other operator role eventually needs.

## 7. Security audit — heavy *design*, no audit *practice*

The repo takes security seriously at the **design** level — but there is no **security-audit standard** and no holistic audit has ever been run. These are different things, and conflating them is the risk.

| What exists | What's missing |
|---|---|
| **Design controls (deep):** S08 PII/retention, S11 SVID + ACL matrix, S12 WS security, A6 5-layer injection defense, tenancy tiers (System/User/Book), invariants I11 (SVID), I12 (secrets), I13 (outbox), I18 (supply-chain hashes). | **A threat-model methodology** — no STRIDE / attack-surface map per trust boundary. The S-docs are per-feature security *designs*, not an *audit* of the system as built. |
| **Per-task adversarial review:** `docs/audit/findings-*.md` (AMAW adversary + `/review-impl`), `AUDIT_LOG.jsonl`, the built-in `/security-review` skill, `/code-review ultra`. | **A security-audit checklist + cadence** — nothing defines *what* to audit, *when* (per-service / per-release / periodic), or *who signs off*. Reviews are diff-scoped, never whole-system. |
| **Some CI gates:** `dep-pinning-lint.sh`, `pii-classify-lint.sh`, `ai-provider-gate.py`, `read-audit-query-type-drift-lint.sh`. | **Promised-but-unwired tooling:** I12 says secrets are "enforced by gitleaks / semgrep" — **neither is in `scripts/`.** No SAST, no dependency-CVE scan (`govulncheck`/`pip-audit`/`npm audit`/`trivy`), no `SECURITY.md` / disclosure policy. |

**The tell that this matters:** the repo's *known* security bugs were all caught **reactively** — the 5 IDOR fixes, the `entity_kinds` global-mutable **tenancy** bug, and the E0 grant-mapping deny-gaps (see memories `user-boundary-multitenant`, `e0-grant-mapping-test-pattern`). Every one is the class a standing audit catches *systematically* instead of by accident. Tenant isolation across 41 services is exactly where ad-hoc review leaks.

### The standard to add (proposed shape)
1. **Threat model** — STRIDE per trust boundary: public edge (`api-gateway-bff`), the **WS edge** (`game-server`, the sanctioned 2nd entry — D-GAME-WS-EDGE-CONTROLS is still open), service-to-service (SVID/ACL), **LLM I/O** (injection), meta-registry, per-reality DB. Existing S-docs become the "control" column — so the model shows coverage *and gaps*.
2. **Audit checklist** — anchored to **OWASP ASVS + API Security Top 10** *and* the repo's own invariants. Lead category: **authZ / tenant-isolation / IDOR** (the repeat offender), then secret handling, prompt+SQL injection, service-auth, PII/retention, dependency CVEs, supply chain.
3. **Cadence + ownership** — add a security-audit step to the "when you add a service" checklist (`07_feature_workflow.md`), a per-release pass, and a periodic full sweep. Define the sign-off role.
4. **Wire the promised tooling** — actually add gitleaks + semgrep (close the I12 gap), a dependency-CVE scanner per language, and a `SECURITY.md`. Keep `/security-review` for diffs; the standard is the *whole-system* complement.
5. **Findings tracking** — reuse `docs/audit/` + `DEFERRED.md`, but add **severity (CVSS-ish)** + a linked invariant, so a finding is either fixed or consciously risk-accepted, never lost.

**First action worth doing now:** a **tenant-isolation / IDOR sweep across all 41 services** — it's the highest-signal first audit given the bug history, and it can run before the full standard is written.

# PART C — Enterprise & distributed-systems go-live readiness audit (architecture-level)

Parts A/B cover *building* and *operating*. This part audits **go-live readiness** for a commercial, multi-tenant, distributed platform — the things that must be true before a paying public touches it. **Scope: architecture audit only, no design.**

The repo's `01_problems/` set (A–G, M) and the S/R/SR storage docs already *name* most of these — which is more than most projects do. But **naming a problem in a locked design note is not the same as auditing it for launch.** A large share are explicitly `OPEN` / `PARTIAL` / "defer to platform-mode," several legal/safety items are absent entirely, and **almost nothing has been audited against the system as built.**

**Legend:** 🟢 designed + (partly) built · 🟡 designed but incomplete / deferred · 🔴 absent · ⬛ never audited (regardless of design state).

### 8.1 Trust, Safety & Content (the "content audit & censor" gap)
| Domain | State | Go-live audit gap |
|---|---|---|
| Input/output content moderation | 🟡 | E2 PARTIAL; A6 output-filter design; flag events *emitted* but no pipeline/triage/classifier built or calibrated |
| **CSAM detection / hash-matching + NCMEC reporting** | 🔴 | **Hard legal blocker** for any UGC+LLM platform. Not mentioned anywhere. |
| Content rating / age-appropriateness taxonomy | 🔴 | 0 docs; LLM generates across the full spectrum with no tier |
| NSFW handling + opt-in + age gate | 🟡 | E2 PARTIAL; no age-verification mechanism exists |
| Player reporting / shadow-ban / escalation | 🟡 | noted only; T&S queue absent (§6) |
| LLM harmful-generation safety | 🟢/⬛ | A6 5-layer is structural & strong, but output-safety **never red-teamed** |

### 8.2 Legal & Compliance
| Domain | State | Go-live audit gap |
|---|---|---|
| **Terms of Service / EULA** | 🔴 | No artifact ("terms of service" = 0 docs). Cannot launch commercially. |
| **Privacy Policy** | 🔴 | Mentioned 3×, no artifact. Must reflect S08 data handling. |
| IP ownership / licensing of player stories in authored books | 🟡 | E3 OPEN — genuine legal uncertainty; blocks platform-mode |
| **DPA / sub-processor disclosure (BYOK LLM = a data processor)** | 🔴 | User prompts flow to 3rd-party LLMs; no consent surface, no DPA, no sub-processor list. Critical given BYOK. |
| GDPR/CCPA data-subject rights (access / erasure / portability) | 🟡 | S08 crypto-shred designed; DSAR *process* + portability never audited |
| Age verification / COPPA (minors) | 🔴 | Game + LLM RP + minors = high-risk; no age gate (0 COPPA docs) |
| DSA / platform obligations (EU) | 🟡 | 11 mentions, not consolidated or audited |
| AI Act / AI-generated-content disclosure | 🔴 | LLM-content labeling + model transparency not addressed |
| DMCA / takedown workflow | 🟡 | E4 "known pattern", deferred; no workflow |
| Data residency / cross-border transfer | 🟡 | 3 mentions; not audited |

### 8.3 User-data boundary & privacy (your explicit concern)
| Domain | State | Go-live audit gap |
|---|---|---|
| Multi-tenant isolation (System / User / Book) | 🟢 / ⬛ | Invariant LOCKED, but **never audited across the 41 services** — and the entire bug history (5× IDOR, `entity_kinds`, E0 grant gaps) lives exactly here |
| Cross-reality / cross-session isolation | 🟢 / ⬛ | I6/I7 designed; never penetration-audited |
| PII classification + retention + crypto-shred | 🟢 | S08 + `pii-classify-lint`; runtime retention reconciliation unaudited |
| BYOK prompt → 3rd-party exposure | 🟡 | S9 retention / trains-on-inputs flags exist; no user consent surface (ties to DPA gap) |
| PII in logs | 🔴 | Redactor exists but **unadopted** (§5) → raw `slog` can leak PII today |

### 8.4 Distributed-systems readiness (you flagged "especially distributed")
| Domain | State | Go-live audit gap |
|---|---|---|
| Concurrency / first-write-wins | 🟢 | B1 known pattern |
| Event-sourcing replay + schema evolution during replay | 🟡 | B5 / R3 residual OPEN — replay-correctness across schema versions unaudited |
| Projection rebuild time at scale | 🟡 | R2 OPEN — rebuild SLA unmeasured |
| Exactly-once / idempotency / outbox | 🟢 / ⬛ | I13 + at-least-once+dedup; idempotency of *every* consumer never swept |
| **DR: RPO/RTO + backup-restore drill** | 🟡 / ⬛ | `backup-scheduler` exists; a restore drill has **never been run**; per-reality PITR unverified |
| SLO / error budget | 🟢 / 🔴 | SR1 designed, but no live SLO possible without the observability backend (§5) |
| Capacity / load test at scale | 🟢 / ⬛ | I17 + SR8 gate exist; load test never executed |
| Cascading failure / breaker / timeout | 🟢 / ⬛ | SR6 + I16; chaos fault-injection (SR7) never executed |
| Per-reality migration safety | 🟢 / ⬛ | `migration-orchestrator` + R4; migration drill unaudited |
| Multi-region / failover | 🔴 | Single-region assumption; not addressed |

### 8.5 Operational & release readiness
| Domain | State | Go-live audit gap |
|---|---|---|
| Observability (log / trace / metric) | 🔴 | §5: standard unadopted, backend unmounted — would launch blind |
| Runbooks / on-call / incident | 🟢 / ⬛ | SR2/SR3 (27-runbook gate); never validated by a drill |
| Status page / user comms | 🟡 | `statuspage-updater` backend, no page |
| Deploy safety / rollback / canary | 🟢 / ⬛ | SR5 + `canary-controller`; never exercised end-to-end |
| Cost / FinOps controls | 🟢 | S6 ledger; no dashboard or enforceable caps UI (§6) |
| Accessibility (WCAG) | 🟡 / ⬛ | a11y mentioned 34×; game-client a11y never audited |
| Anti-cheat / economy-exploit / LLM-cost abuse | 🟡 / ⬛ | D_economics + S07 designed; exploit audit never run |

### 8.6 Highest-severity go-live blockers (the 🔴 that cannot ship as-is)
1. **CSAM detection + reporting** — legally mandatory for UGC+LLM; absent.
2. **ToS + Privacy Policy + DPA/sub-processor disclosure** — no commercial launch without these; BYOK makes the DPA non-optional.
3. **Age verification / COPPA** — minors + LLM roleplay is a top-tier risk; no gate.
4. **Tenant-isolation audit never run** — the architecture is sound *on paper*; the bug history says the implementation isn't, and it's never been swept.
5. **Observability blind** — launching without logs/traces/SLOs landing anywhere (§5) makes every other incident un-diagnosable.

### 8.7 Audit verdict
The architecture **anticipates** an unusually complete set of enterprise + distributed concerns — the problem-set discipline is real and rare. But **go-live readiness ≠ design coverage.** Three structural truths fall out of this audit:
- **A large fraction of named domains are `OPEN` / `PARTIAL` / deferred-to-platform-mode** — designed, not done.
- **Almost nothing has been audited against the system as built** (⬛ everywhere) — no drills, no sweeps, no red-team, no load test.
- **Several hard legal/safety blockers are simply absent** (CSAM, ToS/DPA, age-gate) — these are not "harden later," they are launch gates.

The repo is in excellent shape as a *design*; it is **not** audited-ready for an enterprise distributed go-live, and the gap is concentrated in **legal/safety artifacts that don't exist** and **implementation audits that have never been run** — not in missing architecture.

## 9. Analyses this audit does NOT cover (declared scope boundary)

This document audited **build (A) · operate (B) · launch-readiness (C)**. It did **not** audit whether the platform is **viable, fast, coherent, and tested**. Those are distinct analyses, listed here so the audit's own boundary is explicit and on record:

| # | Uncovered analysis | Why it matters | Auditable now? |
|---|---|---|---|
| 1 | **Unit economics / cost-per-player-hour** | *Existential* for an LLM MMO — if a player-hour costs more than the tier price, no architecture saves it. VISION + `D_economics` flag it as a gating unknown. | ✅ yes — **done in §10 below** |
| 2 | **Turn-latency budget (real-time path)** | The turn loop *is* the UX; p95 > ~2–3s kills it. I16 requires a chain budget; none is audited. | ✅ from the timeout matrix |
| 3 | **Data-architecture / SSOT consistency** | Dual SSOT (glossary authored + knowledge extracted) + per-reality DBs + canon-immutability — dual-write / divergence risk unaudited. | ✅ from `DATA_ARCHITECTURE.md` |
| 4 | **Test / QA coverage** | 41 services; "tests pass" ≠ "surface covered." Actual unit/contract/integration/E2E coverage unknown. | 🟡 needs metrics run |
| 5 | **Frontend / game-client architecture** | Zero FE audited. Real-time sync, reconnection, the open `D-GAME-WS-EDGE-CONTROLS`. | ✅ |
| 6 | **Identity / auth lifecycle** | Token/refresh lifecycle, device registry, recovery, MFA, revocation propagation — audited as threat-surface, not as architecture. | ✅ |
| — | Product/UX coherence; multi-region/failover; FMEA; provider lock-in | Real but lower priority for a pre-launch single-region V1. | partial |

#10 below closes item 1 (the existential one) within this session's "audit-only, no design" rule.

## 10. Unit-economics audit — cost-per-turn & cost-per-player-hour

*(Architecture-level estimate. Illustrative provider tiers — order-of-magnitude to test viability, not a pricing sheet. Grounded in `D_economics` D1/D2 + `S06` cost-control configs.)*

### 10.1 Per-turn LLM fan-out (from the agent design)
One free-narrative turn fires, per `05_llm_safety` + S09:
| Call | Model class | Token shape | Cost driver? |
|---|---|---|---|
| Intent classifier (A5-D1) | local/rules | — | ~$0 |
| Retrieval embedding (A6-D3) | embedding | ~50 tok | negligible |
| **NPC narration (S09 8-section prompt)** | **the turn model** | **~3–5K input / ~300 output** | **★ dominant** |
| Output filter (A6-D4) | cheap/rules | small | minor |
| Memory summary (R8, every ~50 events) | turn model | amortized ÷50 | minor |
| World Oracle (A3) | none (deterministic, cached) | — | $0 on hit |

The **8-section prompt is the cost** (`[SYSTEM]`+`[WORLD_CANON]`+`[SESSION_STATE]`+`[ACTOR_CONTEXT]`+`[MEMORY]`+`[HISTORY]`+`[INSTRUCTION]`+`[INPUT]`). With ~20 canon facts + ~20 memory facts (the SQL `LIMIT 20`) + ~10 history turns + persona sheet, input lands at **~4K tokens** — "input-heavy," exactly as D1 says.

### 10.2 Cost per turn by model tier (~4K in / ~300 out)
| Tier (illustrative) | ~Input $/M | ~Output $/M | **$/turn** | vs mini |
|---|---|---|---|---|
| **mini-class** (Paid floor) | 0.15 | 0.60 | **~$0.0008** | 1× |
| **mid/Sonnet-class** (Paid ceiling) | 3 | 15 | **~$0.017** | ~20× |
| **mid + prompt-cache hit** (stable prefix cached) | 0.30 | 15 | **~$0.006** | ~7× |
| **frontier/Opus-class** (Premium) | 15 | 75 | **~$0.083** | ~100× |

> **Finding 1 — the design's $0.003/turn is ~2–5× optimistic** for the real 8-section prompt at Sonnet-class pricing (actual ~$0.017, or ~$0.006 *if* prompt-caching is built). The D1 number only holds on mini-class or with caching.

### 10.3 Cost per player-hour & the margin test
At the S06 **paid rate cap of 120 turns/hr** (1 turn/30s):
| Tier | $/turn | **$/player-hour** |
|---|---|---|
| mini | 0.0008 | **~$0.10** |
| Sonnet (cached) | 0.006 | **~$0.72** |
| Sonnet (uncached) | 0.017 | **~$2.04** |
| Opus | 0.083 | **~$9.96** |

Apply the locked margin rule **D2-D3** (`tier_price ≥ 1.5 × cost/hr × hours/month`), assuming a **$15 Paid tier @ 10 h/month**:
| Tier model | Monthly LLM cost | Margin ratio | Verdict |
|---|---|---|---|
| mini | $1.00 | **10×** | ✅ healthy |
| Sonnet (cached) | $7.20 | **1.4×** | 🟡 review zone |
| Sonnet (uncached) | $20.40 | **0.5×** | ❌ insolvent |
| Opus on flat tier | $99.60 | **0.1×** | ❌ impossible (hence Premium shows per-turn $ in UI) |

> **Finding 2 — viability is entirely a function of model tier + caching.** mini = 10× margin; Sonnet swings from insolvent→viable purely on whether prompt-caching exists; Opus can never sit on a flat tier.

> **Finding 3 — the cost caps protect the *platform*, not the *margin*.** S06's paid **daily cap is $1.50** → up to **$45/user/month**, which is **3× a $15 tier**. The caps stop budget *drain* (the economic-DOS vector they were designed for) but are set **above** per-user break-even — a sustained heavy paid user is a structural loss the caps permit. Cap-to-margin alignment is unaudited.

### 10.4 Cost drivers, ranked
1. **Model tier** — 20–100× spread; dominates everything.
2. **Prompt-caching of the stable prefix** — `[SYSTEM]`+`[WORLD_CANON]`+`[ACTOR_CONTEXT]` are ~identical across a session's turns → ideal cache targets → ~80% input reduction. **Highest-leverage lever, and it's unbuilt** (the semantic-cache gap from Part A §2). This single item converts Sonnet from insolvent to viable.
3. **Turns/hour (engagement)** — bounded by the S06 rate cap; good.
4. **World-simulation tick (V3 scheduled, B3-D3)** — a *second* cost axis beyond turns (per-region LLM calls); correctly Premium-gated + daily-budget-capped, but unmodeled here.

### 10.5 Audit verdict
The economic **architecture** is genuinely strong and near-complete — tiering (D2), 7-layer cost controls (S06: rate limit, session cap, daily cap, observability, circuit breaker, ledger, model gating), and **Free = BYOK (zero marginal cost)** is the correct structural move. **What's unvalidated is the unit economics underneath it:**
- The platform is viable **only** on **mini-class models** (healthy 10× margin) **or Sonnet-class *with prompt-caching built*** (which it isn't). On Sonnet without caching it is **break-even-to-insolvent**.
- The design's **$0.003/turn assumption is optimistic** and must be replaced with a measured number from the real 8-section prompt before any price is set (D2-D5 measurement protocol — not yet run).
- **Prompt-caching should be reclassified from "optimization" to "viability requirement."**
- **The daily cost cap ($1.50) sits above the $15-tier break-even** — caps prevent catastrophe, not loss; cap-to-margin alignment needs an explicit pass.

**Bottom line:** the architecture *can* be economically viable, but only inside a narrow corridor — **mini-class default, caching built, caps aligned to margin, premium isolated behind per-turn pricing.** Outside that corridor (Sonnet default, no cache) the numbers do not close. This is the one analysis that can invalidate the product premise, and it now has a grounded answer: *viable, but conditionally — and the conditions aren't built yet.*

## 11. Priority check-tasks (sized to the repo's own rubric)

Derived from this audit. Sized by **Logic (primary) + Risk floor** per CLAUDE.md (audits are read-only → low risk floor, size driven by breadth of distinct checks; refactors carry side-effect floors). **Tracked here, deliberately NOT in `SESSION_HANDOFF.md`.** Detailed audit outputs live under [`docs/analysis/`](../analysis/).

**P0 — existential / known weak spot**
| # | Task | Type | Size | Closes |
|---|---|---|---|---|
| 1 | **Tenant-isolation / IDOR sweep across all services** | audit | **XL** | §8.3 + IDOR/`entity_kinds`/E0 history · **✅ DONE → 2 Critical + ~10 High; findings in [`docs/analysis/2026-06-20-tenant-isolation-idor-sweep/FINDINGS.md`](../analysis/2026-06-20-tenant-isolation-idor-sweep/FINDINGS.md)** |
| 2 | Cost-model: validate $0.003/turn vs the real 8-section prompt | audit | **M** | §10 F1–F3 |

**P1 — high-leverage, mostly cheap**
| # | Task | Type | Size | Closes |
|---|---|---|---|---|
| 3 | Turn-latency budget audit (sum the I16 timeout chain vs SLO) | audit | **S** | §9 #2 · **✅ DONE → [findings](../analysis/2026-06-20-contracts-adoption-and-latency/FINDINGS.md)** (turn path unbuilt; 4 internal hops have no declared timeout) |
| 4 | `contracts/` adoption-gap audit (which standards ~0 services import) | audit | **S** | §5 · **✅ DONE → [findings](../analysis/2026-06-20-contracts-adoption-and-latency/FINDINGS.md)** (13/23 service SDKs at 0 adoption) |
| 5 | Logging: add **I20** + lint-gate, then sweep services off raw `slog` | refactor | **L** | §5 |
| 6 | Wire gitleaks + semgrep + CVE scan + `SECURITY.md` | refactor | **M** | §7 |

**P2 — completeness**
| # | Task | Type | Size | Closes |
|---|---|---|---|---|
| 7 | Data-arch / SSOT consistency audit | audit | **M** | §9 #3 · **✅ DONE → [findings](../analysis/2026-06-20-data-architecture-ssot/FINDINGS.md)** (glossary↔knowledge delete/rename desync, 2 High) |
| 8 | Test-coverage audit | audit | **M** | §9 #4 · **✅ DONE → [findings](../analysis/2026-06-20-test-coverage/FINDINGS.md)** (auth-flow untested; 3 services miss tenant deny-tests) |
| 9 | DR restore drill (per-reality RPO/RTO) | audit+ops | **L** | §8.4 |
| 10 | FE/game-client + identity-lifecycle audits | audit | **M** ea. | §9 #5/#6 · **✅ DONE → [FE](../analysis/2026-06-20-frontend-architecture/FINDINGS.md) · [identity](../analysis/2026-06-20-identity-auth-lifecycle/FINDINGS.md)** (auth token in localStorage; 4 identity Highs) |

**Not engineering tasks (launch gates, different track):** ToS · Privacy Policy · DPA/sub-processor disclosure · CSAM detection · age/COPPA gate (§8.6).

**Recommended sequence:** cheap read-only #3+#4 first → commit #1 as a dedicated fan-out → #5/#6 in parallel.

## 12. Suggested next steps (backlog seed — no commitment)

1. **Build `roleplay-service` as the keystone** (it's the only path to retiring A1/A3/A4/A5/A6 residuals). Sequence: intent classifier → dispatch↔narrate wiring (reuse `contracts/turn` + `AssemblePrompt`) → Oracle integration → injection L1/L2/L4 → memory read path. Ship the **A4 retrieval-quality benchmark first** — it's gating.
2. **Stand up the roleplay eval loop with the service** (canon-drift / persona / spoiler grading) as its VERIFY gate — close G3.
3. **Mount a tracing backend** so the multi-hop turn is observable before it's tuned.
4. **Decide the autonomous-NPC question (#8) explicitly** before V3 — gated NPC ticks vs. reactive-only.
**Operability (Part B) — independent of the agent track, ship-anytime:**

5. **Close observability the mechanical way:** add **I20** (logging-through-`contracts/logging`, lint as blocking gate) → sweep services off raw `slog` → mount Loki/Tempo + OTLP. Order matters: invariant first (stops new drift), then sweep, then backend.
6. **Build the admin/CMS web console as the first operator surface** — it's the base every other role (moderation, support, finance, GM) extends. Gate it behind the **admin RBAC capability map** (write that standard first) and the **unified audit-query contract**. Then layer the moderation queue (already-emitted T&S events) and the FinOps cost dashboard onto the same shell.
7. **Stand up a security-audit standard, then run the first audit.** Write the threat-model + checklist + cadence (§7), wire the promised gitleaks/semgrep + a CVE scanner + `SECURITY.md`. **Highest-signal first pass: a tenant-isolation/IDOR sweep across all 41 services** — do this even before the full standard, given the bug history.
8. **Treat the §8.6 blockers as a launch gate, not a backlog** — the legal/safety artifacts (CSAM, ToS/Privacy/DPA, age-gate) and the never-run implementation audits (tenant-isolation sweep, DR drill, load test, chaos) are go-live gates; the rest of Part C is the readiness checklist to burn down before any public/commercial launch.
9. Add all the above as **Deferred rows** in `docs/sessions/SESSION_HANDOFF.md`, categorized (keystone / research-needs-data / perf / **operability** / **security** / **legal-compliance** / **go-live-readiness**).

> **Scope note:** this is a *map*, not a plan. Each item needs its own CLARIFY/DESIGN per the workflow, and must honor the locked kernel invariants (`00_foundation/02_invariants.md`) — especially I6, I10, and the A3/A5/A6 safety decisions — none of which the gaps above justify relaxing.
