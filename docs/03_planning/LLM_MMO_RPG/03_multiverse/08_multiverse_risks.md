<!-- CHUNK-META
source: 03_MULTIVERSE_MODEL.ARCHIVED.md
chunk: 08_multiverse_risks.md
byte_range: 46497-50972
sha256: cf325be6677ec89081f07275772bd7b46911b534ffb4cb60d3d6643f40bd6e26
generated_by: scripts/chunk_doc.py
-->

## 11. Risks specific to the multiverse model

### M1. Reality discovery problem (C3 variant) — **MITIGATED**

Resolved by 7-layer design in [§9.1](#91-reality-discovery): smart-funnel entry flow, composite ranking (friend presence / density / locale / canonicality / recency / near-cap penalty), friend-follow via auth-service, creator-declared canonicality hint, flat browse UI with filters, create-new gated behind "Advanced" tab, metrics feedback loop for weight tuning. Decisions M1-D1..D7 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md). Residual sub-items (weight values, preview format, cold-start interaction with C3, preview caching) need V1 prototype data before SOLVED.

### M2. Storage cost of many inactive realities — **MITIGATED**

All mitigation layers locked: auto-freeze at 30 days no activity (MV10), auto-archive at 90 days frozen (MV11), soft-delete via `ALTER DATABASE RENAME` with 90-day hold (R9-L6), V1 no fork quota (MV4-b; platform-mode tier quota deferred to `103_PLATFORM_MODE_PLAN.md`), hibernated / frozen realities hidden from discovery by default (M1-D5). Storage cost per active reality is bounded by R8 (NPC memory budget) + R1 (event retention layers); inactive realities compound toward archive under automatic policies. Residual platform-mode tier-quota detail remains a `103_PLATFORM_MODE_PLAN.md` concern.

### M3. Canonization contamination — **MITIGATED**

Resolved by 8-layer safeguard framework in [§9.7](#97-canonization-safeguards--m3-resolution): author-only trigger (no player request queue, no voting, no public metrics), mandatory diff view with cascade impact analysis, event eligibility + per-PC consent gates, harder L2 → L1 promotion gate (R9-style with 7-day cooldown + typed confirm + double approval), 90-day undo window with compensating-write for later reverts, attribution + IP metadata schema, distinguishability in book content (label + icon + export options), explicit scope fence with DF3 (implementation) and E3 (legal launch-gate). Decisions M3-D1..D8 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md). Residual sub-items are DF3 implementation details + E3 legal review (independent launch gate for platform mode; self-hosted exempt).

### M4. Inconsistent L1/L2 updates across reality lifetimes — **MITIGATED**

Resolved by 6-layer author-safety UX in [§9.8](#98-canon-update-propagation--m4-resolution): cascade-impact preview before edit, default passive read-through (safe default — cascade rule handles it), optional force-propagate with 3-gate consent (opt-in + owner consent + R13 admin audit), louder L1 warnings with conflict listing, reuse of locked R5-L2 `xreality.canon.updated` channels, glossary entity change timeline with per-reality drill-down. Decisions M4-D1..D6 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md). Residual sub-items are DF3 implementation details + governance policy for ownerless / abandoned realities.

### M5. Fork explosion (depth) — **MITIGATED**

All mitigation layers locked: auto-rebase at depth N=5 (MV9 — flatten ancestor chain into fresh-seeded reality with inherited snapshot, breaking the lineage cleanly), projection-table cascade flattening at read (§7 — depth invisible at read time, only matters at rebuild), ops metrics per shard including ancestry depth (R4-L5). Residual: the N=5 threshold is a V1 starting value; tune up or down from ops data if real-world chains behave differently.

### M6. Cross-reality queries (analytics)

"How many realities is Alice alive in?" requires scanning all realities of a book. Mitigations:
- Analytics ETL pipeline (ClickHouse) denormalizes across realities for aggregate queries
- Runtime answer via aggregation over reality_registry + projection rows (bounded by book, manageable)

### M7. Concept complexity for users — **MITIGATED**

Resolved by 5-layer progressive disclosure in [§9.6](#96-progressive-disclosure--m7-resolution): user-facing terminology map (reality → timeline, NPC → character, L1 → "world law", etc.), 3-tier user model (Reader / Player / Author) with soft upgrade triggers, 4-step onboarding tutorial, copy style guide governance doc, and contextual tooltips on must-appear concepts. Decisions M7-D1..D5 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md). Residual sub-items (tutorial A/B copy, tier-upgrade thresholds, tooltip wording per locale) need V1 prototype data before SOLVED.

