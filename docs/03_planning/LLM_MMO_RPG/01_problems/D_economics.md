<!-- CHUNK-META
source: 01_OPEN_PROBLEMS.ARCHIVED.md
chunk: D_economics.md
byte_range: 20077-22759
sha256: da3a0682f2eb5865f389713d8329dab80ef718546b6d9c5aae7ce5e56c59a33c
generated_by: scripts/chunk_doc.py
-->

## D. Economics

### D1. LLM cost per user-hour — **OPEN**

**Problem:** Back-of-envelope: 100 concurrent users × 3 turns/min × $0.003/turn (Claude Sonnet input-heavy) = ~$54/hour. 24/7 = ~$1,300/day for 100 concurrent. Not sustainable for a hobby or low-tier product.

**Why hard:** Real economics, not solvable by engineering alone.

**Known mitigations:**
- Tier the quality: cheap/local model for small-talk, premium for quest moments
- Aggressive caching (identical NPC greeting, cached)
- BYOK tier (users pay their own LLM costs)
- Prompt-caching on providers that support it (Anthropic, OpenAI)

**Notes:** Bring this into alignment with `103_PLATFORM_MODE_PLAN.md` tier model before any implementation decision.

### D2. Tier viability — **PARTIAL**

**Problem:** At what tier price do the numbers work? Free tier cost per user must be near zero; paid tiers must cover their LLM spend plus margin.

**Resolved by:** Tier SHAPE + feature gating + measurement protocol locked now; exact prices and budget caps pending D1 measurement data.

- **D2-D1** 3-tier shape: **Free / Paid / Premium** aligned with `103_PLATFORM_MODE_PLAN`. Self-hosted is exempt (user controls infra + keys).
- **D2-D2** Free tier = **BYOK-only** (user supplies LLM keys). Zero platform marginal LLM cost for free users.
- **D2-D3** Unit economics target: `tier_price/month ≥ 1.5 × (cost_per_user_hour × avg_hours_played/month)`. Below 1.0x → insolvent; 1.0-1.5x → review.
- **D2-D4** Feature gating per tier (Free: frozen tick B3-D1 / manual fork MV4-b / Reader UX M7-D2; Paid: platform-LLM budget + lazy-when-visited B3-D2 + multi-device sync + Player UX + drift SLO <2%; Premium: scheduled tick B3-D3 + premium models + 5+ PC slots PC-C1 + Author UX + drift SLO <0.5%).
- **D2-D5** V1 measurement protocol: solo-RP prototype instruments cost per session / hour by G2-D4 script mix; output feeds D1 → break-even math.
- **D2-D6** Exact pricing + monthly budget caps **deferred to post-V1 data**. D2 locks framework; numbers require D1 + market research.

Decisions D2-D1..D6 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN`:**
- Exact monthly prices per tier (depends D1)
- Monthly budget cap values per tier (depends D1 + session-volume projection)
- Tier renaming / positioning per market research

### D3. Self-hosted vs platform — **ACCEPTED**

**Decision:** LoreWeave supports both. Self-hosted = user's own LLM keys, no cost to platform. Platform = tier-bounded usage.

**Notes:** MMO only makes sense in platform mode (requires shared server). Self-hosted MMO is a contradiction — one user.

---

