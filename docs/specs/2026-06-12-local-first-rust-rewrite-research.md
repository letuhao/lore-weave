# Local-First Desktop / Hybrid Staging + All-Rust Rewrite — Research & Direction

**Date:** 2026-06-12
**Status:** 🔬 Research / direction notes. **NOT a frozen spec; no build authorized.** Captured from a session discussion to feed a later ADR + decomposition spec.
**Related:** [VCTĐ entity ontology + temporal KG](2026-06-12-van-co-than-de-entity-ontology.md) (temporal-edge model referenced in §8).

Legend: ✅ decided this session · 🔬 verified research finding · 💡 proposal (not locked) · ❓ open question.

---

## 0. Why this document

The thread started from a strategic question: given tightening content-moderation / legal pressure on **public content platforms** in Vietnam, is a **local-first / desktop** model safer than the current cloud-SaaS posture? It broadened into (a) positioning & deployment topology, (b) a 2026 **license-verified** technology survey for a desktop build, and (c) a decision to **rewrite the knowledge-service (KG)**, which has degraded into a *god service*.

This file records findings + decisions so far. It does **not** authorize a rewrite. Next step (deferred — user said *"chưa vội"*) is a decomposition map + ADR (§9).

---

## 1. Decisions locked this session

- ✅ **Direction = hybrid local-first ("staging → HQ").** Default: everything runs on the user's machine (*staging*); cloud *HQ* is an **optional** layer (sync, backup, collaboration, publishing). Philosophy ≈ Obsidian / Git (works 100% without the cloud).
- ✅ **Desktop staging app is mandatory**, not optional — forced by two *independent* constraints:
  1. **Steam delivery** can't ship a ~25-container Docker stack.
  2. A heavy **per-user** "living world" simulation is a **cloud-cost bomb** at scale; user hardware + BYOK is the only sane economics.
- ✅ **All-Rust** for the desktop: game engine **+** shared `world-core` in **one binary** — no FFI/IPC/serialization seam between simulation and knowledge engine.
- ✅ **Rewrite the KG** (`knowledge-service`) — it has become a **god service**; the rewrite is wanted regardless of the desktop move.
- ✅ **Approach = "extract the *meaning*, rewrite the *storage*."** Do **not** from-scratch-reimplement domain logic. Share a transport/persistence-agnostic core; rewrite only the storage/query/infra layer.

---

## 2. Strategic positioning (legal / cost / ownership)

The core lever is the shift from **"publisher" → "infrastructure/tool"** liability posture. Three **independent, stackable** levers, by impact:

1. **Remove public distribution** (feed / ranking / search / community — currently `catalog-service` public catalog + `sharing-service`). **Strongest** lever; ~70% of the benefit, *without* even going local-first. This is what makes you *look* like a publisher.
2. **BYOK for AI** — already in place (`provider-registry-service`, no provider SDKs in services). You are *orchestration*, not an AI provider.
3. **Local storage** — third lever, **most expensive to build**.

Caveats:
- 🔬 **Hybrid does not fully escape.** The moment content syncs to HQ, that subset sits on your servers → hosting posture for *that* subset. Legal benefit is **proportional to how little actually syncs**, not binary.
- ⚖️ **Not legal advice.** Vietnam law / DMCA safe-harbor / ToS / data-protection specifics need a tech lawyer. Direction is plausible; specifics are not self-serviceable.
- 💰 **Cost is the stronger driver than legality.** Running N heavy living-worlds in the cloud is brutal; pushing compute to user hardware + BYOK is the economically forced move.
- 🪪 **World ownership** is a real product/marketing asset, not just a legal hedge: if the startup dies, the user's world survives locally.

---

## 3. Architecture principles (derived)

- **Three seams the shared core must cut cleanly:**
  1. **Transport seam** — domain logic must not know HTTP/AMQP. Cloud wraps it in services; desktop calls it in-process. *(Already proven: `worker-ai` runs Pass-2 via the `loreweave_extraction` library in-process.)*
  2. **Persistence seam** (hard) — cloud = Postgres-per-service + eventual consistency *across* service boundaries; desktop = one embedded ACID store, synchronous, FKs across former boundaries. Core must target an **abstract repository**, not SQL.
  3. **Consistency seam** (subtle) — cloud bakes in async/eventual (outbox, replay, Redis-Streams sync). Desktop is synchronous/transactional. **Rule: the core expresses operations as *intents/transactions*; the *shell* decides** in-process commit (desktop) vs outbox-event (cloud).
- **On desktop, most infra is *deleted*, not *replaced*.** Redis Streams / RabbitMQ / MinIO / Postgres-per-service exist only to solve *distribution* (async, multi-tenant, cross-service). On one machine they vanish → direct calls, one ACID store, filesystem.
- **A library-first core cannot become a god service** — it has no place to accumulate orchestration responsibility. (See §6.3.)
- **Split by scaling-profile + transactional boundary, not "one service per noun."** The antidote to a god service is *correct bounded contexts*, not maximum microservices (that's a distributed monolith — equally bad).

---

## 4. The persistence reality (why "rewrite" is correct for the storage layer)

Correction to an earlier over-glib "just swap the adapter Postgres↔SQLite":

- For **Neo4j/Cypher** that is **wrong** — Cypher graph traversal is a different *paradigm*, not a driver swap. The storage/query layer, **especially the graph**, is a genuine **rewrite**.
- What is **shared** is the **meaning** (model + rules + invariants: what an Entity/Relation/TemporalEdge *is*, what valid canon is, what a contradiction is). What is **rewritten** is the **storage** (queries + persistence).
- **Why pin the meaning:** staging↔HQ **sync** makes *semantic divergence* between two engines (cloud says consistent, desktop says contradiction, same data) a **catastrophic** bug class. Share the *definition* of semantics, not the queries.
- The **one genuinely hard problem** left on desktop: an **embeddable graph + vector + temporal store** (today Neo4j holds entities / timeline / passage-vector index / K21 memory). Everything else is *delete + SQLite*.

---

## 5. Technology research — 2026, license-verified

### 5.1 License filter (the lens — reuse for every dependency)

The desktop repo is **copyright / closed-source**, so dependency licenses are a hard constraint.

| Tier | License | Use in a closed bundle? | Examples |
|---|---|---|---|
| 🟢 Safe | **Public Domain, MIT, Apache-2.0, BSD** | Yes, unconditionally | SQLite, llama.cpp, DuckDB, Tauri, Godot, Bevy, fastembed-rs |
| 🟢 Safe (lib use) | **MPL-2.0** | Yes — must open-source only *modified MPL files*; embedding as a lib in a closed app is fine | CozoDB |
| 🟡 Care | **LGPL** | Only with **dynamic linking** + relink ability → awkward for a static single binary | Qt |
| 🟡 Care | **BSL-1.1** | Embedding in your app *is* allowed; but non-OSI, 4-yr delay to Apache, legal-review overhead | SurrealDB |
| 🔴 Avoid | **GPL/GPLv3, AGPL, SSPL** | No — forces opening the whole app | **Neo4j Community = GPLv3** |

> ⚠️ **The landmine that motivated all this:** Neo4j Community is **GPLv3**; Enterprise is commercial-$$$. No path to embed in a closed desktop app → must replace.

### 5.2 Cautionary tale — Kùzu is dead

🔬 **Kùzu (recommended in an earlier turn) was archived Oct 2025** — Apple acqui-hired the team. MIT forks exist (LadybugDB, RyuGraph, Vela) but carry **fork-risk**. **Lesson: don't bet a copyright product's core on a non-trivial embedded dependency without a fallback.**

### 5.3 Candidate matrix — the shared "world core"

| Layer | Cloud (now) | Desktop candidates | License | Note |
|---|---|---|---|---|
| Relational | Postgres ×N | **SQLite** / libSQL / DuckDB | PD / MIT | Collapse per-service DBs → 1 ACID file |
| **Graph** (hardest) | Neo4j | **(1) in-memory graph + SQLite** · (2) **CozoDB** (graph+vector in one) · (3) **DuckDB + DuckPGQ** · (4) Kùzu-fork (LadybugDB) | PD/MIT · **MPL** · MIT · MIT (fork-risk) | One author's KG is *small* (≤ tens of thousands of nodes) → Neo4j's multi-tenant rationale evaporates |
| Vector | pgvector | **sqlite-vec** / **LanceDB** | Apache | Or let CozoDB cover vectors too |
| LLM runtime | provider-registry | **llama.cpp** (FFI from any lang) / `candle` + BYOK / LM Studio | MIT / Apache | LM Studio already integrated |
| Embeddings | (cloud) | **fastembed-rs** (ONNX via `ort`, **no PyTorch**) | Apache | Small, clean bundle, no Python |
| Events/queue/objects | Redis / RabbitMQ / MinIO | **deleted** → in-process + 1 SQLite log table + filesystem | — | SQLite log table = sync contract to HQ |

> ⚠️ **License the *model weights* too, not just the runtime.** llama.cpp is MIT but GGUF weights vary (Qwen/Mistral = Apache ✅; Llama = Meta community, restrictions). Embeddings: pick MIT/Apache weights (e.g. BGE). If you **ship** weights in a commercial bundle, choose commercially-OK models; if the user supplies/downloads them (BYOK), lighter burden.

💡 **Graph recommendation:** start with an **in-memory graph built from SQLite on load** (hand-write the traversals you actually need — e.g. *temporal-at-chapter-X*). Rationale: (a) **zero abandonment risk** (cf. Kùzu); (b) single-user scale fits in RAM easily; (c) tiny bundle, all PD/MIT; (d) matches "share meaning, rewrite storage" — an in-memory graph built from the domain model *is* the storage rewrite, fully under your control. Upgrade to **CozoDB (MPL)** later if you need rich persistent graph+vector queries in one engine.

### 5.4 Shell by archetype

| Archetype | Shell candidates | License | When |
|---|---|---|---|
| **Tool-app** (editor / worldbuilder / graph UI) | **Tauri** (Rust) · Wails (Go) · Avalonia (C#) · Electron | MIT/Apache | Desktop = authoring tool |
| **Game / living-world client** (real-time, explorable) | **Godot 4** (MIT, 0 royalty, native Steam export) · **Bevy** (Rust, MIT) · Unity (proprietary, $/trust issues) | Godot/Bevy 🟢 · Unity 🟡 | Desktop = "living world" experience |

### 5.5 Language / packaging reality

Prefer **single-binary-friendly** (Steam likes self-contained):

| Lang | Bundle | Productivity | Ecosystem license |
|---|---|---|---|
| **Rust** (Tauri/Bevy) | 1 binary ~3–10 MB, **no runtime install** | Lower (curve) | MIT/Apache |
| **C#** (.NET 9 NativeAOT + Avalonia) | self-contained exe, **no .NET install** | High | Avalonia MIT |
| **Go** (Wails) | 1 binary ~15 MB, system WebView | High | MIT |
| **Python** | Nuitka/PyInstaller → **heavy, large, slow startup** | Fast to write, **poor to ship** | — |

- **Drop Python from the desktop *runtime*.** Bundling a full interpreter (Nuitka better than PyInstaller for real products) is a Steam liability (size, startup, AV false-positives). The clean move: make the desktop core **not need Python** (llama.cpp + fastembed-rs + SQLite cover the heavy AI/data) and reimplement the Python *rules* in the core language.
- 🔬 **"VS-installer is impossible on Steam" — not a hard wall.** Steam **Common Redistributables** (VC++, .NET, DirectX) auto-install when needed, and there is a doc for distributing non-game / open-source apps. Self-contained is still cleaner (no install script, no admin), so the preference stands — but it's not a blocker.

### 5.6 Recommended Rust-native stack (all 🟢)

**Bevy** *or* **Fyrox** (engine — see §8) · `rusqlite` (SQLite) · `sqlite-vec` · `candle` / llama.cpp · `fastembed-rs` · `tokenizers` (HF — already Rust). **Zero Python in the runtime.** Game + `world-core` link directly in one binary.

---

## 6. The god-service problem (`knowledge-service`)

### 6.1 Diagnosis — why it won't scale (from its own config)

- **Opposing SLAs in one process:** `build_context` grounding is a **500 ms** hot path (`KNOWLEDGE_CLIENT_TIMEOUT_S=0.5`) **but** extraction is a **30–90 s/chapter** batch — same service. Can't tune/scale one without dragging the other.
- **Cross-service DB coupling:** reads `GLOSSARY_DB_URL` directly — touching another service's DB is a smell that locks independent evolution.
- **Neo4j carries 4 differently-shaped concerns:** graph + timeline + passage-vector index + K21 memory.
- **Cycle accretion** (72, 73b/d/e/h…): MCP surface + wiki-gen + glossary-sync consumer + precision filter + entity recovery + writer autocreate — all in one place.

### 6.2 Target decomposition (bounded contexts)

| Context | Role | Profile |
|---|---|---|
| `world-core` (Rust lib, no I/O) | meaning + rules + algorithms; **conformance-tested** | — |
| extraction | producer (keep Python `loreweave_extraction` *temporarily*) → emits deltas | batch, LLM-heavy |
| graph/canon store | transactional writes (cloud: Postgres · desktop: SQLite + in-mem) | OLTP |
| retrieval/grounding | hot-path reads; scaled for latency | low-latency |
| memory (K21) | per-user agentic state | per-user |
| MCP surface | thin tool API | — |
| wiki-gen | 💡 consider moving entirely into **glossary** (already hosts wiki) | batch |

### 6.3 Synthesis — the library-first core *is* the cure

A library-first `world-core` (functional core: domain types + canon rules + graph algorithms; storage/transport as ports) **structurally cannot become a god service**. On cloud, it lets you **split the god service into thin services by scaling profile, all sharing `world-core`**. → **Extract once (`world-core`), ship N ways** (N cloud services + 1 desktop app). The *act of extracting* forces the SRP decomposition the god service is missing.

### 6.4 Anti-pattern guard

⚠️ Don't trade god service for **distributed monolith**. Split by **scaling-profile + transactional boundary**: cloud ≈ **3–4 services**; desktop = **all modules in one process**. Chatty nano-services are as bad as a god service.

---

## 7. Rewrite discipline (where rewrites die)

Rewriting a running system is a classic project-killer (Netscape). The current extraction quality is **eval-validated** (cycle 72/73, F1 ≈ 0.916) — a Rust rewrite must *re-earn* that. Safe path:

1. **Use the existing eval suite as a conformance gate.** Rust `world-core` only replaces Python when it **passes the same golden vectors + matches F1**. The measuring stick already exists — use it to de-risk.
2. **Sequence by risk, NOT big-bang.** Rewrite the part that is *both rotten and must-change-for-desktop* **first**: graph/canon/storage (Neo4j → embedded). Keep Python extraction as the **proven producer** feeding the new core via a clean contract. **Port extraction last** (most eval-critical, currently working).
3. **Event spine = integration contract** between the split contexts (cloud) **and** the sync contract to HQ (desktop). Reuse it; don't reinvent.

---

## 8. Open questions

- ❓ **KG ↔ ECS mapping.** Candidate model: **KG (persistent, temporal canon) is source-of-truth; hydrate the Bevy ECS on load; runtime changes write back as temporal edges** (ties directly to the temporal-edge model in [VCTĐ ontology](2026-06-12-van-co-than-de-entity-ontology.md): each chapter/time-step = a world-state layer). KG = persistent layer; ECS = in-memory projection.
- ❓ **Game engine sub-choice (Rust).** **Bevy** (elegant, ECS-native, but — as of 2026 — code-first, **no official editor**, pre-1.0 API churn) vs **Fyrox** (scene-based, has an editor, more stable). **Spike + verify current 2026 status** before locking.
- ❓ **Desktop graph store.** in-memory + SQLite (recommended start, zero dep risk) vs CozoDB (MPL) vs DuckPGQ. **Spike:** build one book's KG, measure a *temporal-at-chapter-X* query on each.
- ❓ **Cloud-side split count.** Target 3–4 services from the god service; exact boundaries TBD by the seam inventory.
- ❓ **Sync surface.** Which pieces sync to HQ — legal exposure ∝ how much syncs.

---

## 9. Next steps (deferred — *"chưa vội"*)

1. **Seam-inventory / decomposition map** of `knowledge-service`: read handlers + dependencies, map each responsibility → target bounded context, mark `world-core` (shared) vs shell. *(First concrete "de-god" step.)*
2. **ADR** locking: all-Rust core · `world-core` library-first · incremental rewrite **gated-by-eval**.
3. **Spikes:** (a) Bevy-vs-Fyrox + KG→ECS; (b) desktop graph store (in-memory vs CozoDB); (c) Rust port of *one* extraction stage, conformance-checked against the Python eval.

---

## 10. Deep-research findings (adversarially verified) — detailed architecture synthesis

**Provenance:** deep-research workflow `wf_4af7adb1-36b` (2026-06-12): 23 sources fetched → 113 claims extracted → top 25 adversarially verified (3-vote refute panels) → **24 confirmed, 1 refuted**. The harness's final merge step died on a session limit; this synthesis was done in-session from the raw verified claims. ⚠️ Cost note: 105 agents / ~5.5M tokens — any future research at this depth requires explicit cost sign-off first.

**Evidence tiers:** ✅ backed by verified claims (3-0 or 2-1) · ◐ source fetched, claim NOT verified (lower confidence) · ✗ not researched (quota cut).

### 10.1 Verdicts locked by verified evidence

1. ✅ **No ES framework — hand-roll decide/evolve.** cqrs-es targets serverless; esrs is Postgres-only + tokio-coupled (adapter-layer at best, cannot be the desktop store) and pre-1.0 with an 18-month-stale crates.io release. The decide/evolve *shape* itself (handle_command/apply_event) is production-validated (Prima.it insurtech). The pure core depends on none of them; the pattern is small to hand-roll. *(Refuted-claim note: "cqrs-es documents no SQLite backend" was killed 0-3 — it may have one; doesn't change the verdict, which rests on purity + targeting.)*
2. ✅ **Anchor+delta (snapshots + delta log), NOT full event-sourcing purism.** Peer-reviewed (AeonG, VLDB): periodic snapshot + delta log beats both full-graph snapshots (Clock-G) and tuple-versioning (T-GQL) — **5.73× lower storage, 2.57× lower temporal-query latency, 9.74%** overhead on non-temporal ops. Practitioner study (19 systems, 25 engineers, arXiv:2104.01146): full ES's chronic pains = schema evolution, projection rebuilds (slow enough that teams schedule them for weekends), steep learning curve. → The Delta contract keeps its 4 roles, but **snapshots are first-class** — state is not required to be derivable only by replay.
3. ✅ ⚠️ **TIMING GATE — most consequential finding.** *"A high level of maturity of the domain knowledge is a prerequisite. When the domain knowledge is still evolving, applying event sourcing introduces more risk."* Schema churn against an immutable log is the #1 reported pain. The VCTĐ ontology was designed THIS WEEK. → **Do not freeze the Delta schema until the ontology has survived extraction of ≥1 full real book (cloud-side).** Hardens §7's sequencing into a hard gate.
4. ✅ **Schema evolution: load-time upcasting, not versioned-enums-everywhere.** Industry tactic usage: copy-and-transform 14/25, upcasting 12/25, explicit versioned events only **2**/25; the cqrs-es book explicitly recommends upcasters over version-suffixed types (duplicated logic/tests). BUT: upcaster chains accumulated over years degrade load performance → pair upcasting with periodic **snapshot-rewrite migrations** (on app update: load via upcasters → rewrite snapshot → archive old deltas).
5. ✅ **Delta serialization: self-describing only — postcard banned for the contract.** Postcard's wire format *explicitly* excludes schema evolution and is not self-describing — version skew between devices/cloud is undetectable at the wire level. → serde-JSON envelope `{schema_version, kind, payload}` for the Delta contract; postcard acceptable for internal ephemeral caches only.
6. ✅ **Bitemporal mechanics: XTDB pattern — append-only writes, query-time resolution.** XTDB v2 handles retroactive corrections by appending a single event; the write path never reads or mutates prior rows; bitemporal complexity lives at query time with an **as-of-now fast path** that terminates early. → A retroactive chapter edit appends correction deltas; **no write-time invalidation cascade**. Academic SOTA (AeonG) is transaction-time-only — the two-axis model must live at the domain level: **valid time = `chapter_id` carried as domain data on deltas/edges (exactly the VCTĐ design); transaction time = log order.**
7. ✅ **Derived-fact invalidation ("edit ch.3 breaks ch.4–50"): salsa's MODEL, not salsa itself (yet).** Salsa = memoized pure queries + fine-grained input-driven invalidation — exactly the right mechanism category. But salsa self-declares WIP/pre-1.0 (June 2026) — risky under a years-long contract. → v1: hand-rolled dirty-set + recompute (≤100k nodes is cheap); adopt salsa only if profiling demands.
8. ✅ **Runtime concurrency: arc-swap snapshot rotation validated.** ArcSwap outperforms `RwLock<Arc<T>>` in contended and uncontended read-mostly use. Failure mode: ~8 fast borrow slots/thread; Guards must not be stored or held across yields → **Bevy systems clone the Arc once per frame; never store Guards.**
9. ✅ **SQLite safety rails (desktop).** WAL = concurrent readers + exactly one writer → single-writer-thread design validated. Corruption vectors (sqlite.org): file-copying a live DB mid-transaction yields mixed-page corrupt copies; the `.db` and `-wal` are an inseparable unit; separating them silently loses committed transactions. → **Steam Cloud / any backup must never touch the live DB** — sync a checkpointed export (SQLite backup API / `VACUUM INTO`); treat `.db`+`-wal` as atomic.

### 10.2 Directional (fetched, unverified — revalidate at build time)

- ◐ **Sync engine: hand-rolled delta-log shipping + HLC ordering + LWW-per-entity.** Corroborating sources fetched: Cinapse's move away from CRDTs (PowerSync blog), ElectricSQL's own pivot to a simpler model ("electric-next"), jlongster's hand-rolled single-user sync (Actual Budget). All point the same way for single-author multi-device: CRDT platforms are overkill + abandonment-prone; simple log-shipping survives. Use **hybrid logical clocks**, not wall clock (skew edge case).
- ◐ **Shared-core counter-evidence — Dropbox post-mortem** (abandoned shared C++ core for iOS/Android): the strongest documented argument against shared cores. Mitigating differences here: one language (Rust) end-to-end, both shells owned by us, no foreign-platform glue. Lesson retained: keep platform glue thin; the core must earn its place with genuinely shared logic.
- ◐ **Mentat/Tofino post-mortem:** Mozilla's general-purpose datom store on SQLite died with its host product. Lesson: build a **domain-specific** store for the queries the product needs — do NOT build a generic temporal-EAVT engine.

### 10.3 Not researched (quota cut — low-risk, defer)

- ✗ PyO3/maturin adoption details (pydantic-core pattern is mainstream; verify call-overhead + wheel-CI burden at adoption time).
- ✗ Rust modulith enforcement specifics (cargo-deny bans / clippy disallowed-lists are standard practice; design the gate when the workspace exists).
- ✗ Bevy hydration/change-detection benchmarks (bevy#18697 fetched, unverified).

### 10.4 Resulting detailed architecture (one paragraph)

world-core = hand-rolled pure decide/evolve; state = **anchor snapshots + append-only delta log** (SQLite desktop / Postgres cloud); Delta = **serde-JSON enveloped, `schema_version` + load-time upcasters + periodic snapshot-rewrite migrations**; temporality = **two-axis at domain level** (valid = `chapter_id`, tx = log order) with **query-time resolution + as-of-now fast path**, retroactive edits append-only; derived facts = **memoized queries + dirty-set invalidation** (salsa-model, hand-rolled v1); runtime = **single writer thread + arc-swap snapshot rotation** (clone-per-frame discipline); persistence = **WAL + single writer + backup-API-only exports** (Steam Cloud never touches the live DB); sync = **delta-log shipping + HLC + LWW-per-entity** (hand-rolled, revalidate at build); **the Delta schema freezes only after the ontology survives one real book.**

### 10.5 Key verified sources (§10 additions)

- ES practitioner study (19 systems): https://arxiv.org/abs/2104.01146 · cqrs-es book (upcasters): https://doc.rust-cqrs.org/ · esrs: https://github.com/primait/event_sourcing.rs
- AeonG anchor+delta (VLDB): https://www.vldb.org/pvldb/vol17/p1515-lu.pdf · XTDB bitemporal resolution: https://xtdb.com/blog/building-a-bitemp-index-2-resolution
- Salsa: https://github.com/salsa-rs/salsa · arc-swap: https://docs.rs/arc-swap · postcard wire format: https://postcard.jamesmunns.com/wire-format
- SQLite corruption/WAL: https://sqlite.org/howtocorrupt.html · https://sqlite.org/wal.html
- Post-mortems (◐): Dropbox shared-core https://dropbox.tech/mobile/the-not-so-hidden-cost-of-sharing-code-between-ios-and-android · Mentat/Tofino https://www.ncalexander.net/blog/2017/05/31/tofino-data-storage-and-how-we-got-to-mentat/ · ElectricSQL pivot https://electric-sql.com/blog/2024/07/17/electric-next · jlongster CRDTs-in-the-wild https://archive.jlongster.com/using-crdts-in-the-wild · Cinapse off CRDTs https://powersync.com/blog/why-cinapse-moved-away-from-crdts-for-sync

---

## Sources (verified 2026-06-12)

- Kùzu archived / Apple acqui-hire — https://www.theregister.com/2025/10/14/kuzudb_abandoned/ · MIT fork — https://github.com/Vela-Engineering/kuzu
- SurrealDB License FAQ (BSL 1.1) — https://surrealdb.com/license
- CozoDB (MPL-2.0, relational-graph-vector) — https://github.com/cozodb/cozo
- DuckPGQ (property graph in DuckDB) — https://duckdb.org/community_extensions/extensions/duckpgq · https://duckdb.org/2025/10/22/duckdb-graph-queries-duckpgq
- Tauri vs Electron 2026 — https://tech-insider.org/tauri-vs-electron-2026/
- Avalonia NativeAOT (MIT) — https://docs.avaloniaui.net/docs/deployment/native-aot · Wails (Go, MIT) — https://github.com/wailsapp/wails
- llama.cpp (MIT) — https://github.com/ggml-org/llama.cpp · fastembed-rs (Apache, ONNX, no PyTorch) — https://github.com/Anush008/fastembed-rs
- Godot vs Unity 2026 (MIT, no royalty) — https://dev.to/linou518/godot-vs-unity-in-2026-which-engine-should-indie-developers-choose-50g4
- Steam: distributing open-source/non-game apps — https://partner.steamgames.com/doc/sdk/uploading/distributing_opensource · Common Redistributables — https://partner.steamgames.com/doc/features/common_redist
- Nuitka vs PyInstaller — https://sparxeng.com/blog/software/python-standalone-executable-generators-pyinstaller-nuitka-cx-freeze
