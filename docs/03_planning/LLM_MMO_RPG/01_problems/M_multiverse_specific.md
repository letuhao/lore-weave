<!-- CHUNK-META
source: 01_OPEN_PROBLEMS.ARCHIVED.md
chunk: M_multiverse_specific.md
byte_range: 31700-38205
sha256: bf099eb866f50ad80f44767188840ba7621495508f9bb754e2576c1b31e08542
generated_by: scripts/chunk_doc.py
-->

## M. Multiverse-model-specific risks

New category introduced by the multiverse model in [03_MULTIVERSE_MODEL.md §11](03_MULTIVERSE_MODEL.md). These are trade-offs created by adopting peer realities + snapshot fork; they are the price of the benefits elsewhere.

### M1. Reality discovery problem — **PARTIAL**

**Problem:** Many realities per book → which does a new player join? Poor discovery = every reality is lonely. Related to C3 cold-start.

**Resolved by:** 7-layer design in [03 §9.1](03_MULTIVERSE_MODEL.md#91-reality-discovery) — smart-funnel entry flow, composite ranking (friend presence / density / locale / canonicality / recency / near-cap penalty), friend-follow via auth-service, creator-declared canonicality hint, flat browse UI with filters, create-new gated behind "Advanced" tab, metrics feedback loop for weight tuning. Decisions M1-D1..D7 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN` (blocks SOLVED):**
- Actual weight values — V1 defaults are starting guesses; tune from real data
- Notable-event preview format (raw L3 headline vs AI 1-line summary) — needs engagement measurement
- First-week cold-start interaction with C3 (seeded AI populations?)
- Preview-content caching freshness policy

### M2. Storage cost of inactive realities — **PARTIAL**

**Problem:** Users fork freely, abandon 30 minutes later → DB rows accumulate across thousands of inactive realities.

**Resolved by:** All mitigation layers locked — MV10 (30d auto-freeze), MV11 (90d auto-archive), R9-L6 (soft-delete via rename with 90d hold), MV4-b (V1 no fork quota; platform-mode tier quota deferred), M1-D5 (hibernated/frozen hidden from discovery). Status **MITIGATED in [03 §11.M2](03_MULTIVERSE_MODEL.md#m2-storage-cost-of-many-inactive-realities--mitigated)**; kept `PARTIAL` in 01 for residual platform-mode tier detail.

**Residual `OPEN`:**
- Platform-mode fork-quota tier specifics — deferred to `103_PLATFORM_MODE_PLAN.md`
- Compression thresholds for long-term archived events — V3+ tuning

### M3. Canonization contamination — **PARTIAL**

**Problem:** Canonization (L3 → L2, author-gated per MV2) opens a path for emergent player narrative to influence canon. Risks: pollution, social pressure on author, accidental breaks, IP uncertainty, low-quality promotions, player consent, system gaming. Related to E3 IP ownership and gated by DF3 for full implementation.

**Resolved by:** 8-layer safeguard framework in [03 §9.7](03_MULTIVERSE_MODEL.md#97-canonization-safeguards--m3-resolution) — author-only trigger, mandatory diff view with cascade impact, event eligibility + per-PC consent gates, harder L2 → L1 promotion gate (R9 pattern), 90-day undo window, attribution metadata, distinguishability in book content, explicit scope fence with DF3 and E3. Decisions M3-D1..D8 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN` (blocks SOLVED):**
- "Significant event" category definitions per World Rule (DF4 + V1 data)
- >90-day compensating-write mechanism (DF3 implementation detail)
- Export attribution UI format (strip / footnote / appendix) — DF3 detail
- Edge cases: deleted PC / banned user / retroactive opt-out — DF3 policy
- **E3 (IP ownership)** — independent legal blocker for platform-mode launch; self-hosted mode exempt

### M4. Inconsistent L1/L2 updates across reality lifetimes — **PARTIAL**

**Problem:** Author edits L2 after realities exist. Cascade rule says overriding realities' L3 events win → author's change doesn't apply there. Confuses authors expecting "my change applies everywhere."

**Resolved by:** 6-layer author-safety UX in [03 §9.8](03_MULTIVERSE_MODEL.md#98-canon-update-propagation--m4-resolution) — cascade-impact preview before edit, default passive read-through, optional force-propagate with 3-gate consent (opt-in + owner consent + R13 audit), louder L1 warnings with conflict listing, reuse of locked R5-L2 xreality channels, glossary entity change timeline. Decisions M4-D1..D6 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN` (blocks SOLVED):**
- Compensating L3 event schema specifics — DF3-adjacent
- Notification copy per M7 `UI_COPY_STYLEGUIDE.md`
- Consent mechanism for ownerless / abandoned realities — governance policy
- Runtime canon-guardrail prompt discipline for L1 enforcement — A6-adjacent

### M5. Fork depth explosion — **PARTIAL**

**Problem:** Snapshot fork allows forks of forks of forks → deep ancestry chains → cascading read across N reality_ids at load time.

**Resolved by:** MV9 auto-rebase at depth N=5 (flatten ancestor chain into fresh-seeded reality with inherited snapshot), projection-table cascade flattening at read ([03 §7](03_MULTIVERSE_MODEL.md)), ops metrics per shard including ancestry depth (R4-L5). Status **MITIGATED in [03 §11.M5](03_MULTIVERSE_MODEL.md#m5-fork-explosion-depth--mitigated)**; kept `PARTIAL` in 01 for threshold tuning.

**Residual `OPEN`:**
- N=5 depth threshold — V1 starting value, tune from ops data on real chain behavior

### M6. Cross-reality analytics — **KNOWN PATTERN**
"Alice is alive in how many realities?" requires scan across reality_registry + projection rows. ETL to ClickHouse for analytics. Pattern is standard; cost is real but predictable.

### M7. Concept complexity for users — **PARTIAL**

**Problem:** Multiverse is sophisticated. New users may not understand "realities" on first contact → churn.

**Resolved by:** 5-layer progressive disclosure in [03 §9.6](03_MULTIVERSE_MODEL.md#96-progressive-disclosure--m7-resolution) — user-facing terminology map (reality → timeline, NPC → character, L1 → "world law", etc.), 3-tier user model (Reader / Player / Author) with soft upgrade triggers, 4-step onboarding tutorial, copy style guide at [`docs/02_governance/UI_COPY_STYLEGUIDE.md`](../../02_governance/UI_COPY_STYLEGUIDE.md), contextual tooltips on canonicality/fork/hibernated/friend/forked-from. Decisions M7-D1..D5 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN` (blocks SOLVED):**
- Tutorial copy A/B testing — which phrasing reduces bounce rate on real users
- Tier-upgrade trigger thresholds (3 sessions default, may tune per intent signal)
- Word choice at Reader tier: "world" vs "book" vs "story" for source material
- Tooltip wording refinement per locale

---

