# Knowledge service — Design draft vs. current implementation (gap analysis)

**Date:** 2026-06-13
**Design source:** `design-drafts/screen-knowledge-service.html` (dated 2026-04-13)
**Current impl:** `frontend/src/features/knowledge/*` (reviewed 2026-06-13)
**Why:** The RAID `creation-unblock` plan scoped the knowledge cycles from *current code + persona gaps*, NOT
from this design. The design contains the knowledge-service's **product centerpiece** (the anchor/curation
flywheel) that the implementation skipped — so the RAID under-scoped knowledge. This catalogs the delta.

> **Caveat:** the draft is ~2 months old (2026-04-13). Some divergence may be intentional (e.g. the current
> `Insights` tab isn't in the draft; the draft's "Evidence browser" == current "Raw"). Treat each row as
> *needs a keep/defer decision*, not an automatic must-build.

---

## 0. Headline

The implemented knowledge UI has the **lifecycle** right (13-state machine, jobs, cost, basic entity/timeline/
raw browse, global bio) — that part is solid. But it is **missing the entire "curation flywheel" half** of the
design, which is the service's actual differentiator (the GraphRAG/HippoRAG anchor-node thesis the draft cites
explicitly). Four whole feature-areas are absent or stubbed:

1. **Build = a 3-step wizard with glossary-pinning** (not a single dialog).
2. **Pending Proposals** inbox (an entire tab) — absent.
3. **Glossary Gap Report** (an entire tab) — absent.
4. **Entities as a canonical/discovered/anchor semantic layer** with **Promote** — the implemented Entities tab
   is a flat list missing this model.

These are not polish. They're the loop: *extraction discovers → you curate the high-value ones → glossary
grows → next extraction is better-anchored.* Without them, the knowledge service is a graph viewer, not a
worldbuilding curation tool.

---

## 1. Surface-by-surface comparison

| Design surface | Current impl | Verdict |
|---|---|---|
| **Projects** — list + **Search** + **type filter** + state cards | state cards only; **no search, no type filter** (just archived toggle) | **Gap** (= BL-19/KN-20, already logged) |
| **Build dialog** — **3-step wizard**: (1) target picker · (2) scope + **glossary pinning dual-list** · (3) budget+models+**concurrency**+live breakdown | **single dialog**: scope radio + range + LLM + embedding + max-spend + estimate | **MAJOR gap** — see §2 |
| **Extraction Jobs** — running/paused/complete + ETA + spend + month/all-time/budget widget | matches well (running/paused/complete/failed + ETA + cost) | ✅ close |
| **Global bio (L0)** — bio + version history + extracted prefs + privacy | matches | ✅ close |
| **Entities (semantic)** — ⭐canonical / 💭discovered / 📦archived · **anchor_score** · semantic search · **Promote→glossary** · legend | flat list (name/kind/project/mentions/confidence) + FTS search + detail panel; **no canonical/discovered/anchor/promote model** | **MAJOR gap** — see §3 |
| **Entity detail** — aliases · description · **known facts list** · relations · **provenance** · edit/merge/**unpin**/cascade-delete | detail panel with relations (+ truncation) | **Partial** — facts/provenance/promote/unpin missing |
| **Timeline** — narrative-order, **major/pivotal** event badges, entity + range filters | flat event list, expandable, filters | **Partial** — event-importance + narrative ordering thin |
| **Evidence browser (Raw)** — semantic search + source filter | matches ("Raw") | ✅ close |
| **Pending Proposals** — unified inbox (glossary drafts + wiki stubs) + deep-links to glossary/wiki | **MISSING — no such tab** | **MAJOR gap** — see §4 |
| **Glossary Gap Report** — high-value gaps, summary cards, **bulk-promote**, curation rationale | **MISSING — no such tab** | **MAJOR gap** — see §4 |
| **Chat memory indicator** (3-mode header popover) | partial via composition grounding; no explicit mode indicator | Gap (= WG-2/UC-34, already logged) |
| **Memory block (XML)** | backend prompt structure (not a screen) | n/a — doc, not UI |
| **Privacy / Mobile / State legend** | privacy ✅; mobile hides entities/timeline; legend implicit | minor (= KN-15) |
| **Insights tab** | exists in impl, **not** in draft | impl-ahead (keep) |

---

## 2. Build wizard + glossary pinning (the biggest miss)

Design (`#build-dialog`): a **3-step wizard**, premised on *"a generic build-everything button doesn't work at
5,000-chapter scale."*
- **Step 1 — target picker:** Event Timeline · Entities(→glossary) · Relationships · Lore & Worldbuilding
  (→wiki stubs) · Chapter Summaries. Each target has its **own shape/inputs**.
- **Step 2 — scope + glossary pinning dual-list:** chapter range **plus** a left/right dual-list to **pin
  sparse-but-critical entities** (e.g. "The Creator: appears ch1 & ch5000 only, spans 100%") so they're injected
  in **every** extraction window regardless of range. Includes search, type/frequency/sort filters, **auto-pin
  suggestions** for sparse-long-reaching entries, per-window token budgeting, pagination.
- **Step 3 — budget & models:** embedding (locked-after-build note) + LLM + max-spend + **concurrency** + a
  **live cost breakdown** (extraction / pinned-injection / dedup / embeddings) + duration + cap-vs-estimate.

Current (`BuildGraphDialog`): one dialog — scope **radio** (all/chapters/chat/glossary_sync), chapter range,
LLM, embedding, max-spend, single estimate. **No target picker, no glossary pinning, no concurrency, no
per-line cost breakdown.**

**Impact:** the pinning feature is the design's headline scale-solution and is **completely absent**. The
target-picker is a different extraction mental model (build a *specific target* vs "everything in a scope") —
reconciling it needs a backend check on whether per-target extraction is supported.

---

## 3. Entities as a canonical/discovered/anchor layer (the two-layer pattern, made visible)

Design (`#entities`): the semantic layer the CLAUDE.md two-layer pattern describes, **surfaced**:
- ⭐ **canonical** (anchored to a glossary entry, `anchor_score=1.0`, glossary overrides name/type),
- 💭 **discovered** (extraction-only, `anchor_score = mentions/max`, **Promote→glossary** button),
- 📦 **archived** (glossary entry deleted; kept for graph/RAG consistency, hidden from default search).
- Semantic search ("the god who made the world"), status filter (canonical/discovered/archived), anchor sort,
  and an explainer legend (GraphRAG ~34% dup reduction, HippoRAG +18–25% multi-hop).

Current (`EntitiesTab`): flat list, FTS search, kind/project filters, detail panel — **no canonical/discovered/
archived distinction, no anchor_score, no Promote action.** The two-layer anchoring exists in the data model
(glossary_entity_id FK) but is **invisible and non-actionable** in the UI.

---

## 4. Pending Proposals + Glossary Gap Report (the curation flywheel — both absent)

- **Pending Proposals** (`#proposals`): a unified inbox of what extraction has submitted to glossary (drafts via
  `extract-entities status=draft`) and wiki (stubs via `wiki/generate author_type=ai`), with confidence,
  conflict flags, and deep-links to the glossary/wiki review queues. **No such tab exists.**
- **Glossary Gap Report** (`#gap-report`): high-mention discovered entities with **no glossary entry** —
  summary cards (canonical % / discovered % / high-value gaps), a threshold filter, and **bulk-promote**. The
  explicit "curate these first → glossary grows → extraction improves" loop. **No such tab exists.**

Together these are the **human-in-the-loop curation half** of the service. Without them the anchor flywheel
can't be driven from the UI at all — extraction discovers entities but the user has no surfaced path to curate
them into the glossary.

---

## 5. RAID impact — the plan under-scoped knowledge

The current `creation-unblock` cycles touch knowledge via: C1–C3 (rerank), C4 (book picker), C5 (build-gate
*recovery*, not the wizard), C6 (project detail + explore), C7 (list browse + polish), C11–C12 (visual graph).
**None of them build:** the 3-step wizard, glossary pinning, the proposals inbox, the gap report, or the
canonical/discovered/anchor/promote entities model.

So the RAID, as written, would "unblock" knowledge to the level of *the current design-incomplete UI* — it
would **not** deliver the curation flywheel the design intends. **The knowledge phase needs re-planning.**

### Proposed added cycles (pending keep/defer decision per surface)
| New | Scope | Notes |
|---|---|---|
| **K-A** | Entities semantic layer: canonical/discovered/archived + anchor_score + **Promote→glossary** + semantic search/status filter | needs BE: anchor_score + promote endpoint (verify what exists) |
| **K-B** | **Glossary Gap Report** tab: gap query + summary cards + threshold + **bulk-promote** | BE: high-value-gap query; reuses promote from K-A |
| **K-C** | **Pending Proposals** inbox: unified glossary-draft + wiki-stub list + deep-links | BE: list submitted-but-pending; deep-link targets exist |
| **K-D** | **Build wizard** rework: 3-step + target picker + **glossary pinning dual-list** + concurrency + cost breakdown | BIGGEST; needs BE check on per-target extraction + pinned-injection |
| **K-E** | Entity detail enrichment: facts list + provenance + unpin + promote | extends current detail panel |
| **K-F** | Timeline: narrative-order + event-importance (major/pivotal) | extends current timeline |

K-A/K-B/K-C are the flywheel (highest product value, likely the user's real want). K-D is the biggest lift and
may be partly deferrable (pinning is a 5,000-chapter-scale power feature). K-E/K-F are enrichment.

---

## 5b. Backend audit results (2026-06-13) — accurate sizing

Audited knowledge-service + lore-enrichment-service + glossary-service. **Most of the flywheel exists
server-side; the build wizard is the only heavy full-stack lift.** Mapped onto the RAID cycles:

| Cycle | Design surface | Backend reality | Size | RAID |
|---|---|---|---|---|
| K-A → **C8** | Entities semantic layer | `anchor_score`/`glossary_entity_id`/`archived_at` EXIST on Entity; list has FTS only (no semantic/status-filter/anchor-sort) | thin BE (params + vector) + FE = **M** | C8 |
| K-A/K-E → **C9** | Promote + entity detail | `link_to_glossary()` EXISTS (no router); facts endpoint EXISTS; provenance partial | wire endpoint + FE = **M** | C9 |
| K-B → **C10** | Gap Report | `find_gap_candidates()` EXISTS (no router) — entity gaps, high-mention, no glossary entry | wire endpoint + FE bulk-promote = **S-M** | C10 |
| K-C → **C11** | Pending Proposals | list endpoints EXIST in lore-enrichment (`/proposals`) + glossary (`?status=draft&tags=ai-suggested`) + wiki drafts | FE aggregation + deep-links = **M (FE-only)** | C11 |
| K-D → **C12** | Build wizard + pinning | extraction is **monolithic** — NO target-typed builds, NO pinned injection, NO concurrency | **full-stack L/XL** (worker-ai + packer + contract) | C12 |
| K-F → **C13** | Timeline narrative-order | events exist; importance/narrative-order thin | thin BE + FE = **S-M** | C13 |

**Overlap flag (locked):** lore-enrichment-service already owns a curation flywheel. The knowledge UI must
**aggregate/deep-link** over it + glossary, not build a parallel review system. lore-enrichment's `detect-gaps`
(attribute-dimension gaps) is a DIFFERENT concept from the design's entity Gap Report (`find_gap_candidates`) —
keep both.

## 6. Decisions needed before re-planning — RESOLVED 2026-06-13
- **Draft is source of truth** (PO) → all missing surfaces in-scope.
- **Investigate backend first** (PO) → done (§5b); cycles re-sized.
- Knowledge phase re-planned in `docs/plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md` → **C8–C13**
  added; task now **28 cycles (C0–C27)**.
1. **Is the 2026-04-13 draft still the source of truth**, or has the product intentionally moved on (e.g. the
   `Insights` tab, dropped pinning)? Confirm per major surface.
2. **Which of K-A..K-F enter the RAID**, and at what priority vs the existing unblock + net-new (graph viz,
   world container, dị bản)?
3. **Backend reality check** (gates K-A/K-D): does the BE already expose anchor_score, a promote endpoint,
   per-target extraction, and pinned-entity injection — or do those need building too? (A `lore-enrichment`
   service already does enrichment/promotion — likely overlaps; reconcile.)
