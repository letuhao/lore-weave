# Node (Local Binary) — Boundary Map Draft (v0)

**Date:** 2026-06-13
**Status:** 📐 **DRAFT** — Track 2 design. **Build NOT authorized.** Purpose: enumerate the node binary's boundaries, mark what is already decided vs what needs **deep design**, and produce a ranked deep-design queue.
**Relations:** child of the [phased topology draft](2026-06-12-node-hq-phased-architecture-draft.md) (T2 tier); consumes [research §10](2026-06-12-local-first-rust-rewrite-research.md) verdicts and the game-foundation multiverse model (L1–L4 canon).

---

## 0. What the binary is

One self-contained executable on the player/author machine. Two shell archetypes over the same core (Q2 decides ship order):

- **Tool archetype** — authoring: editor-adjacent worldbuilding, glossary/KG curation, consistency checking.
- **Game archetype** — local Solo RP client: V1 experience running fully on-node against a book's world.

```
┌─────────────────────────── node binary ───────────────────────────┐
│  Shells (tool UI / game client)                                    │
│      │ B2                                                          │
│  world-core  (pure: decide/evolve · canon L1–L3 · graph · rules)   │
│   │ B1          │ B3            │ B4             │ B5              │
│  storage      AI runtime      sim plane        ingest             │
│  (SQLite +    (BYOK/local     (ECS, L4)        (book packs /      │
│   in-mem       LLM+embed)                       local extraction) │
│   graph)                                                           │
└────│────────────│──────────────────────────────────│──────────────┘
     B6 OS/files  B3′ network(AI)        B7 HQ (dormant P1)
            B8 license/build · B9 trust/authority · B10 safety
```

---

## 1. Boundary inventory

Legend: ✅ decided (cite) · 🔧 known pattern, needs adaptation · 🔴 **needs deep design** (no in-house precedent or load-bearing novelty).

### B1 — world-core ↔ storage
- ✅ Seam exists by design: `dp-kernel`'s `EventStore` trait reserved for backend swap → **SQLite impl**.
- ✅ Mechanics locked by research §10: anchor+delta, WAL single-writer, arc-swap snapshot rotation, backup-API-only exports.
- 🔧 Needs: SQLite schema for event log + snapshots + projections; single-writer thread design; in-mem graph build-on-load (Spike S2).
- Risk: medium — spike-covered, prior art strong.

### B2 — world-core ↔ shells
- ✅ Pattern: shells call commands (`decide`) and read immutable snapshots (clone-per-frame, never hold Guards).
- 🔧 Needs: the command/query API surface; error surfacing UX; long-op progress (extraction/LLM calls) without async leaking into core.
- Risk: low-medium — standard ports-and-adapters work.

### B3 — world-core ↔ AI runtime
- ✅ Invariant carries over: core never imports a provider SDK — `LlmProvider`/`EmbeddingProvider` ports; adapters = BYOK remote, LM Studio/Ollama local server, (optional) embedded llama.cpp + fastembed.
- 🔧 Needs: adapter matrix + model-capability detection on-node (no provider-registry service locally — its *resolution logic* becomes a core-adjacent module); cost/latency budgets per consumer (narrator vs extraction vs embeddings).
- Risk: medium — patterns exist in both repos; the new part is *registry-less* model resolution.

### B4 — canon plane ↔ sim plane 🔴
- ✅ Frame locked: canon = L1+L2+L3; sim = L4/ECS; KG hydrates ECS; sim never source of truth; two time axes meeting only at reality seeding.
- 🔴 **Deep design needed — the narrator loop on-node:** game action → narrator (LLM, guardrail-checked) → proposed L3 events → `decide` validation against canon → commit → projections update → ECS applies. What exactly crosses this boundary per tick vs per scene? What is *allowed* to write L3 (narrator output only? player choices? sim emergent events)? How do guardrails (YAML, shared with T1) bind into the loop? How does a retroactive canon edit (author changes L2) invalidate a running reality?
- Risk: **high** — novel, load-bearing, defines the game feel AND the data model. No in-house node-side precedent (T1's loop is server-side and still in build).

### B5 — ingest: how a book's world gets INTO the node 🔴
- The hidden boundary. Cloud extraction is Python `loreweave_extraction` (eval-validated, F1-tracked). The node is Rust-only — **the node cannot run the proven pipeline.**
- **Proposal — the `book pack`:** a sealed, versioned export artifact produced by the platform (T0): canon L1/L2 + KG + glossary + embeddings + guardrail rules + seed manifest. Node *consumes* packs; needs **zero local extraction** for the game archetype. One-way artifact — radically simpler than sync, and it IS the P1 cloud↔node bridge.
- Consequence for **Q2 (archetype order):** Solo RP first ⇒ B5 = book-pack reader only (small). Tool-first ⇒ local extraction needed ⇒ either Rust port (research says port LAST) or degraded local pipeline. **This boundary is the strongest argument to ship the game archetype first.**
- 🔴 Deep design needed: pack format (versioned, signed?), embedding portability (model/dim metadata — reuse the 2b dual-identity lesson), partial updates (book grew 50 chapters), license/DRM posture of packs for *other people's* books.
- Risk: **high** — new artifact class, and it gates P1 scope.

### B6 — node ↔ OS/filesystem
- ✅ Rails locked: G4 (schema_version + upcasting from first public build), WAL+sidecar atomicity, Steam Cloud must never touch the live DB (checkpointed exports only).
- 🔧 Needs: save layout (per-world dirs? one DB per reality?), crash-recovery UX, export/import.
- Risk: low — rules known, implementation discipline.

### B7 — node ↔ HQ (dormant in P1) 🔴-lite
- Nothing ships in P1 — but **retrofitting sync into an unprepared P1 save format is the catastrophic path**. Design the *dormant shape* now:
  - stable, deterministic IDs everywhere (UUIDv5 seeding pattern already exists in `reality_seeder`);
  - HLC-ready timestamp fields reserved on L3 events;
  - `schema_version` on every persisted record (G4 doubles as sync-readiness);
  - event log append-only with no in-place rewrites (already the dp-kernel way).
- 🔴 Deep design needed (small but unskippable): the **sync-readiness checklist** P1 must satisfy — one page, enforced in review.
- Risk: medium probability, **catastrophic** cost if skipped → design now, build later.

### B8 — license/build boundary
- ✅ Layering locked (G2′ + E-K): foundation-kernel (MIT/Apache) ← world-core (non-AGPL) ← shells (closed). No AGPL/GPL in the binary (G2).
- 🔧 Needs: build-time license gate (cargo-deny config) — mechanical.
- Risk: low.

### B9 — trust & authority (per-reality flip) 🔴-lite
- For a **private/local reality**: the node IS authoritative — canon guardrails run locally, full stop.
- For a **shared reality** (P3+): the node becomes an **untrusted client** — everything it proposes must re-validate at T1 (server-authoritative, already the T1 stance).
- The flip must be a **first-class property of a reality**, not an afterthought — it decides *where* guardrail/validation code runs and what the node is allowed to fabricate. Cheap to model in P1 (a single `authority` field + a rule), expensive to retrofit.
- Risk: low effort, high leverage — fold into B4's design doc.

### B10 — content safety
- ✅ Guardrail rules are data (YAML, shared artifact with T1); `05_llm_safety` corpus exists in game-foundation.
- 🔧 Needs: which safety checks are node-local vs pack-embedded vs HQ-only (P3 canonization review is the natural human gate).
- Risk: low-medium — policy more than architecture.

---

## 2. Ranked deep-design queue

| # | Boundary | Why this order | Output artifact |
|---|---|---|---|
| 1 | **B5 ingest / book pack** | Gates P1 scope AND answers Q2 (Solo-RP-first ⇒ no local extraction). Smallest assumption set; pure data design — can start before any engine/storage choice | book-pack format spec |
| 2 | **B4 canon↔sim narrator loop** (+B9 authority flip) | The product-defining loop; everything else serves it. Needs B5's pack as input fixture | narrator-loop design doc + authority model |
| 3 | **B7 sync-readiness checklist** | One page now prevents the un-retrofittable disaster; constrains B1's schema before it's built | P1 sync-readiness checklist |
| 4 | **B1 storage schema** | After B7's constraints + Spike S2 result | node storage spec |
| 5 | **B3 registry-less model resolution** | Medium novelty; can lag until P1 build starts | adapter-matrix note |
| B2/B6/B8/B10 | — | known patterns; design inline during build | — |

**Recommended next concrete step (still design-only, Track-2-safe):** draft #1 — the **book-pack format**. It is pure data design, zero code, zero Track-1 impact, and its existence makes Q2's answer nearly automatic.

---

## 3. Open questions raised here

- **Q2 (updated recommendation):** B5 analysis favors **game archetype (Solo RP) first** — book packs make its ingest trivial, while tool-first forces the extraction problem years early. PO to confirm.
- **Q8 — pack trust model:** are book packs signed by HQ? Can a node author a pack offline (tool archetype later) and what marks it "unofficial"?
- **Q9 — reality persistence granularity:** one SQLite DB per reality vs one per book (realities as row-partitions)? Feeds B1/B6.
- **Q10 — embedded-LLM floor:** is there a minimum local model the game archetype *requires* (offline narrator), or is BYOK/local-server the only supported path at P1?

## 4. What this draft does NOT do

No pack format details (queue #1's job) · no narrator-loop mechanics (queue #2) · no storage schema (queue #4) · no engine choice (S1 unchanged) · still **zero build authorization**.
