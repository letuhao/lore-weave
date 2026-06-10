# Architecture Weaknesses — Review Register

> **Purpose:** Track architectural weaknesses surfaced in review so they get fixed as the system matures. This is a **building** system, not a finished product — items here are work-to-do, not indictments.
> **Created:** 2026-06-10 (from an architecture review of [`DATA_ARCHITECTURE.md`](DATA_ARCHITECTURE.md) + the Living Worlds data-plane kernel)
> **Companion:** [`DATA_ARCHITECTURE.md`](DATA_ARCHITECTURE.md) · [`03_planning/LLM_MMO_RPG/06_data_plane/_index.md`](03_planning/LLM_MMO_RPG/06_data_plane/_index.md) · [`deferred/DEFERRED.md`](deferred/DEFERRED.md) (tracked as umbrella row **071**)
> **Schedule:** post-MVP-0.1 hardening — the project is currently finishing for the 0.1 release. **Exception:** AW-4 (credential encryption) is a gate *before the first real BYOK user*, which may fall before or at 0.1.

---

## How to read this register

**Framing principle (do not re-litigate):** judge the architecture by **fit-for-target** (the Living Worlds multi-reality LLM platform) and **contract correctness**, NOT by current traffic or "perfect-product" completeness. The decomposition (16 DBs, Neo4j, event-sourcing) is a deliberate one-way-door investment for the Living Worlds target; the hard kernel lives in `06_data_plane/` (LOCKED). The methodology is **contract-first on deliberate assumptions → build → measure → refine** — measurement is correctly deferred to V1 prototype data. Most "missing" operational pieces are deferred-by-design, not defects.

**Severity:** 🔴 high · 🟠 medium · 🟡 low / watch
**Status:**
- **ACTION** — fix during current build
- **GATE** — must be resolved before a named milestone (e.g. first real user)
- **DEFER** — correctly deferred by design until runtime/data exists; revisit then
- **WATCH** — monitor; revisit if conditions change
- **DOC** — documentation / presentation fix

---

## Summary table

| ID | Item | Severity | Status | Target / trigger |
|----|------|----------|--------|------------------|
| AW-1 | Sync cross-service call on search hot path (knowledge → book per query) | 🟡 | WATCH/ACTION | When search latency or load matters |
| AW-2 | Neo4j as both graph **and** vector store — is the graph half earning its keep? | 🟠 | ACTION | Audit before deepening KG investment |
| AW-3 | Two message systems + Postgres event_log (RabbitMQ + Redis Streams + outbox) | 🟡 | WATCH | If ops burden grows |
| AW-4 | BYOK credential secret-management / encryption-at-rest | 🟠 | **GATE** | Before first real (non-test) user |
| AW-5 | Cost-of-rebuild economics for derived stores (re-embedding) | 🟡 | DEFER | When corpus + embedding cost are real |
| AW-6 | Structural-assumption risk in locked Living Worlds kernel | 🟠 | WATCH | Get thin V1 in front of assumptions before widening design |
| AW-7 | Entry-doc leads with "16 databases" → invites over-engineering misread | 🟡 | DOC | Next docs pass |

---

## Items

### AW-1 — Synchronous cross-service call on the search hot path
**Severity 🟡 · WATCH/ACTION**

Flow #3 (raw/hybrid search) does **knowledge-service → book-service HTTP** on every query to fetch the lexical leg over `chapter_blocks`. That is a synchronous cross-service hop on a latency-sensitive path = a coupling cost (a mild distributed-monolith smell on the *authoring* plane).

- **Why it's only 🟡:** search is not tick-frequency; and the Living Worlds plane already internalizes the right principle (DP-T tiers: hot-path reads from cache, never event replay). The principle is understood — this is just one place on the novel-workflow side that doesn't apply it.
- **Action when it matters:** consider co-locating the lexical + semantic legs in one store (see AW-2 / pgvector), or caching the lexical leg, so a hybrid query doesn't fan out to two datastores across the network.

### AW-2 — Neo4j doing both graph and vector
**Severity 🟠 · ACTION (audit first)**

Lexical lives in Postgres (`chapter_blocks`); semantic lives in Neo4j (`:Passage` vectors). A single hybrid query therefore spans two datastores. Since Postgres already runs everywhere, **pgvector (HNSW)** could host both legs in one store — fewer hops, one consistency domain, one less datastore to operate.

- The only justification to keep Neo4j is the **graph relations** (GraphRAG-style). But per the raw-search eval spec, retrieval currently measures lexical + semantic + RRF — **graph-traversal-augmented retrieval is not yet in the measured path**. So the graph half may be carrying ops weight on promise, not present value. (GraphRAG's cost/benefit is itself still corpus-dependent and contested as of 2026.)
- **Action:** audit the repo — does any Cypher traversal feed retrieval ranking, or is Neo4j only `:Passage` vector + `glossary_entity_id` anchor? If the latter, evaluate collapsing the vector leg into pgvector and scoping Neo4j to where graph relations earn their keep. *(Offered: I can run this audit.)*
- **Cost / footprint angle (added 2026-06-10):** this is also the **highest-leverage footprint reducer**. IaC + k8s bin-pack the *stateless* service count cheaply; the real driver is the *stateful* tier. On a **single shared VM** (the current model — the whole stack idles <~4GB on a 16–32GB box), Neo4j's JVM (heap + pagecache) is typically the largest RAM tenant; at **HA/scale**, a Neo4j causal cluster is the priciest tier (licensed). Either way, dropping Neo4j's vector role into the Postgres you already run cuts the footprint and removes JVM tuning from the ops surface — so AW-2 is a cost/simplicity lever, not only a retrieval-architecture question.

### AW-3 — Two message systems + a Postgres event log
**Severity 🟡 · WATCH**

RabbitMQ (batch jobs) + Redis Streams (outbox relay / fan-out + `xreality.*`) + per-service `outbox_events` + `loreweave_events.event_log` = four messaging-ish mechanisms.

- **Why only 🟡:** the durability gap is engineered deliberately — DP-Ch16..Ch20 use hybrid Redis Streams + Postgres catchup with resume tokens and gap-free delivery; the cross-instance policy explicitly leaves a "(or successor bus)" seam. They know Redis Streams may not be the endgame.
- **Watch:** consolidation is still a fair question (Redis Streams as a *durable, replayable* event backbone is non-standard vs Kafka/SNS-SQS). Revisit if operational burden or replay/ordering needs grow.

### AW-4 — BYOK credential secret-management / encryption-at-rest
**Severity 🟠 · GATE (before first real user)**

`provider_registry.provider_credentials` stores user BYOK provider keys. I have not found a documented story for secret storage / encryption-at-rest / key management. Channel privacy redaction (DP-Ch43-45) is in-game visibility, **not** user-credential protection.

- **Why it's a GATE, not just DEFER:** unlike perf/scale items, its failure mode is **irreversible** — a leaked credential cannot be un-leaked. So even though most ops hardening is correctly deferred until runtime, this one needs an explicit gate **before the first real (non-test) user**.
- **Action:** confirm/define envelope encryption (KMS-backed) for credentials at rest; add a tracked row so it can't be implicitly skipped. *(May already exist — if so, link it here and downgrade.)*

### AW-5 — Cost-of-rebuild economics for derived stores
**Severity 🟡 · DEFER**

"Derived is rebuildable" is architecturally correct, but rebuilding Neo4j `:Passage` vectors = **re-embedding the whole corpus = real money** in an LLM-heavy system. Today there's no rebuild runbook / cost model.

- **Correctly deferred:** meaningless to quantify before a realistic corpus size and actual embedding cost exist.
- **Revisit when:** corpus reaches non-trivial scale or a model/embedding migration is on the table. At that point: rebuild runbook + cost estimate + (if costly) incremental re-embed strategy.

### AW-6 — Structural-assumption risk in the locked Living Worlds kernel
**Severity 🟠 · WATCH**

The kernel (`06_data_plane/`, 24 LOCKED docs, DP-Ch1..Ch53) is contract-first on **assumptions** — correct methodology (you can't measure a kernel before building on it; locking the expensive-to-change contract early minimizes refactor cost; quantitative SLOs are explicitly V1-deferred).

- The **irreducible** residual is *not* "missing measurements" (impossible to have yet) but a **structural** assumption proving wrong — e.g. the hierarchical channel model (cell→…→continent + bubble-up). A wrong *structural* assumption is contract-level rework, not a number tweak, and its blast radius grows with how much is built on it.
- **Mitigant (already your direction):** get a **thin V1 prototype** in front of the load-bearing structural assumptions *before* the design surface widens further. Lock contracts early — yes; just keep the V1 reality-check close behind the structural bets.

### AW-7 — Entry-doc framing undersells the real depth
**Severity 🟡 · DOC**

[`DATA_ARCHITECTURE.md`](DATA_ARCHITECTURE.md) opens with "**16 Postgres databases**". A store count reads as complexity-as-achievement and invites the exact over-engineering misread (the reviewer fell into it). It also **hides** the genuinely impressive part — the locked `06_data_plane` kernel and the Living Worlds target.

- **Action (next docs pass):** lead with the **platform target + the depth of the locked kernel design**, not the store count. Frame the system honestly as "validated novel-workflow core + rigorously-designed, not-yet-load-tested game data-plane." This also directly serves the goal of presenting/​"showing off" the architecture without inviting the wrong critique.

---

## Recalibrated / withdrawn during review (do not resurrect)

These were raised early then **withdrawn or downgraded** once the Living Worlds target and the `06_data_plane` kernel were read. Recorded so they don't get re-litigated as "weaknesses":

| Early claim | Why withdrawn |
|-------------|---------------|
| "Over-decomposition / premature distribution (20 svc / 16 DB for a small project)" | **Withdrawn.** Justified by the Living Worlds target; clean service boundaries are one-way-door investments, cheaper to establish early than to retrofit. |
| "High operational cost / DevOps burden from 20 svc + 5 datastores" | **Withdrawn (refined 2026-06-10).** IaC + k8s/GitOps + the existing observability automation (health/ready probes, worker heartbeat, stack-freshness guards) collapse the naive "20 services = 20× manual toil"; routine/steady-state ops is genuinely low, and local (compose/k3s) ↔ AWS parity is a packaging concern, not a per-service tax. **Current-stage reality (measured 2026-06-10):** the whole stack — all services + Postgres + Neo4j + Redis + RabbitMQ + MinIO — idles under **~4GB RAM** and runs on a **single 16–32GB VM** (single-instance, no HA), fitting the ~$50–200/mo Y1 target. At current scale the ops/$ concern is essentially gone. Genuinely deferred (not defects — stage-appropriate tradeoffs): (a) **HA / availability** — single-VM is a deliberate SPOF + blast-radius choice, correct for low user count, revisited when uptime SLAs or load demand it; (b) **sizing under load** (LLM extraction, embedding, hybrid search) is the real driver vs idle — headroom on the 16–32GB box absorbs it at low concurrency. **AW-2 still applies**, reframed: on a shared single VM, Neo4j's JVM is typically the largest RAM tenant of the stateful tier — collapsing its vector role into the existing Postgres cuts footprint and removes JVM tuning. Living-Worlds DB-per-reality scale stays empirically deferred (AW-6). |
| "Missing governance / DR / consistency entirely" | **Largely withdrawn.** The kernel has failure/recovery (DP-F: degraded mode, split-brain, migration rollback, chaos drills), cache coherency (DP-X), a cross-instance policy, and user-deletion propagation. Only narrow residuals survive → AW-4, AW-5. |
| "Thousands of DBs is operationally unvalidated → defect" | **Reframed.** Design is rigorous (rejects `postgres_fdw`/fan-out at N=1000; meta-registry + event propagation + import/export). Empirical validation is **deferred to V1 by design** (DP-S Q20 Phần A) — a tracked open measurement, not a defect. |
| "BDUF — design runs ahead of evidence, contradicts your eval discipline" | **Withdrawn.** Contract-first on assumptions is the correct methodology; eval applies to *implemented* things and can't apply to a not-yet-built kernel. Quantitative parts were correctly deferred. Only the structural-assumption residual survives → AW-6. |
| "Hobby project" implying low quality | **Withdrawn — category error.** "Hobby/OSS/solo" is a *funding/resourcing* fact, not a quality statement. QC here is high (12-phase workflow, eval harness with measured recall 0.63→0.95, locked specs). |

---

*Maintained as a living register. Close an item by linking the fixing PR/spec and moving it to a "Resolved" list (or deleting after a few sessions). Add new items with the same ID scheme (AW-N).*
