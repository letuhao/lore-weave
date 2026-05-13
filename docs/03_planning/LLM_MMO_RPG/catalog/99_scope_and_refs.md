<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: 99_scope_and_refs.md
byte_range: 70021-77227
sha256: e8f7530c146139079584c3fcea8c35a1d593770ed435c1c15bf6660211b022d0
generated_by: scripts/chunk_doc.py
-->

## Status summary

| Category | ✅ Designed | 🟡 Partial | 📦 Deferred | ❓ Open | 🚫 OOS | Total |
|---|---|---|---|---|---|---|
| IF | 319 | 5 | 26 | 0 | 0 | 350 |
| WA | 2 | 2 | 3 | 0 | 0 | 7 |
| PO | 6 | 2 | 1 | 0 | 0 | 9 |
| PL | 4 | 7 | 3 | 0 | 0 | 14 |
| NPC | 6 | 10 | 2 | 0 | 0 | 18 |
| PCS | 2 | 5 | 3 | 0 | 0 | 10 |
| SOC | 0 | 0 | 8 | 0 | 2 | 10 |
| NAR | 2 | 1 | 4 | 1 | 0 | 8 |
| EM | 20 | 0 | 6 | 0 | 0 | 26 |
| PLT | 1 | 2 | 4 | 1 | 0 | 8 |
| CC | 0 | 5 | 3 | 1 | 0 | 9 |
| DL | 0 | 0 | 5 | 1 | 0 | 6 |
| **Total** | **362** | **39** | **68** | **3** | **2** | **474** |

### Interpretation

- **246 Designed** (green): concrete decisions in locked docs — storage, fork, canon model, PC mechanics, R1-R13, M1-M7, WA-4, C1-C5, H1-H6 + M-REV-1..6 + P1-P4, S1-S13, plus **SR1 SLOs + Error Budget Policy (2026-04-24) — 8 decisions, 7 user-journey SLIs (session-availability, turn-completion, event-delivery, realtime-freshness, auth-success, admin-action, cross-reality-propagation), tiered SLO targets (free/paid/premium), error budget policy with 4-tier burn-rate response including feature freeze at ≥90%, multi-tenant isolation SLO (noisy-neighbor + meta 99.99%), reliability review cadence (daily→annual), alert-to-SLO derivation with CI lint, public status page V2+, cardinality + retention cost controls**.

**All 21 SA+DE adversarial + 13 Security (S1-S13) resolved.** Storage + multiverse design fully locked pending external-dependent V1 prototype data. **SRE / Incident Response review COMPLETE 12/12 (2026-04-24)**: SR1 SLOs + SR2 Incident Classification + SR3 Runbook Library + SR4 Postmortem Process + SR5 Deploy Safety + Rollback + SR6 Dependency Failure Handling + SR7 Chaos Drill Cadence + SR8 Capacity Planning + Auto-Scaling (invariant I17) + SR9 Alert Tuning + Pager Discipline + SR10 Supply Chain Security (invariant I18) + SR11 Turn-Based Game Reliability UX + **SR12 Observability Cost + Cardinality (2026-04-24) — 10 decisions + 1 pending (SR12-D11 = proposed invariant I19 awaiting architect approval in POST-REVIEW), observability inventory registry at `contracts/observability/inventory.yaml` with required fields per type (metric + audit_table) + CI enforcement, per-service cardinality + log + audit budgets + `observability_budget_breaches` table (1y retention), 22-table retention audit against S8-D3 matrix with 1 finding (`user_queue_metrics` formalized 1y) + **S8-D3 extended with Operational tier (1y)**, log sampling strategy (error 100%/warn 50%/info 10%/debug 1% with per-service overrides + trace-preservation + non-negotiable PII scrubbing), audit rollup cadences per-table protocol with V1 minimum (alert_outcomes + prompt_audit), meta-observability 6 metrics + DF11 panel + 4 alerts, cardinality admission control tiered (V1 warn-and-drop → V1+30d hard-reject → V2+ pre-commit), per-tenant cost attribution deferred V2+, V1 weekly rebaseline cadence first 4 weeks + monthly/quarterly thereafter per SR2-D8, **12-item V1 launch gate**; 3 new admin commands (`admin/metric-label-audit` Tier 3 + `admin/retention-override` Tier 2 + `admin/log-sampling-update` Tier 2)**. **SRE Review complete.**

**All 13 storage risks (R1–R13) resolved + C1 from SA+DE adversarial review resolved via orphan-worlds reframe. Storage + multiverse design design-complete** (residual items external-data-dependent: A4 benchmark, D1 cost, E3 legal).
- **38 Partial** (yellow): broad strokes designed, concrete detail pending (prompt assembly, retrieval quality, realtime).
- **44 Deferred** (blue): explicitly pushed to DF1–DF14 (DF12 withdrawn) future design docs or platform mode. Known but not gating V1.
- **3 Open** (red): identified but no approach — NPC-4 (retrieval quality), NAR-8 (L1/L2 propagation), CC-6 (a11y). A1 moved to PARTIAL with R8 infrastructure resolution.
- **2 Out of scope**: no parties (SOC-6), no global chat (SOC-7) — deliberate anti-MMO choices.

## V1 scope (solo RP, single reality)

Features marked `V1` (33 items) + required `INFRA` (17 items) = 50 total features to build for a working solo RP prototype.

Critical-path `❓ Open` blocking V1:
- **NPC-3** (per-PC memory) — needs [01 A1](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--open) solution
- **NPC-4** (retrieval quality) — needs [01 A4](01_OPEN_PROBLEMS.md#a4-retrieval-quality-from-knowledge-service--partial) measurement

Non-blocking but must address:
- **PL-4** (prompt assembly) — concrete recipe needed
- **CC-6** (accessibility) — must not be afterthought

## V2 scope (coop, 2–4 players per reality)

Add `V2` items (18 items): session features (DF5), PvP, PC-as-NPC conversion (DF1 core), reality freeze/archive, swipe/regenerate, session replay, cross-language, freeze warnings.

## V3 scope (persistent multiverse)

Add `V3` items (14 items): DB subtree split, reality resurrect, author dashboard, canonization (DF3), L1/L2 propagation, NPC daily routines (DF1 full), world simulation tick, cross-reality browser.

## V4+ scope (vision, far-future)

Add `V4` items (4 items): world travel (DF6), echo visit, dimensional rifts, rich media (book import/export).

---

## Relationships visualized

```
                     FEATURE DEPENDENCY CLUSTERS

    ┌─────────────── INFRA (IF-*) ───────────────┐
    │ Storage → Registry → Realtime → LLM gateway │
    └───────────────────────┬─────────────────────┘
                            │
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
    ┌─────────────┐  ┌────────────┐  ┌──────────┐
    │ WORLD AUTH  │  │ PLAY LOOP  │  │ PLATFORM │
    │ (WA)        │  │ (PL)       │  │ (PLT)    │
    └──────┬──────┘  └──────┬─────┘  └────┬─────┘
           │                │             │
           ▼                ▼             ▼
    ┌──────────┐     ┌──────────┐    ┌──────────┐
    │ PO + PCS │     │ NPC      │    │ SOC      │
    │ (players)│     │ (AI chars)│   │ (groups) │
    └─────┬────┘     └────┬─────┘    └────┬─────┘
          │               │               │
          └───────┬───────┴───────────────┘
                  ▼
          ┌───────────────┐
          │ NAR (canon)   │
          │ EM (advanced) │
          │ DL (daily life│
          │ CC (UI/i18n)  │
          └───────────────┘
```

## References

- [00_VISION.md](00_VISION.md) — why this exists
- [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) — risks indexed by category
- [02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) — IF-* detail
- [03_MULTIVERSE_MODEL.md](03_MULTIVERSE_MODEL.md) — WA-3, EM-1 to EM-6 detail
- [04_PLAYER_CHARACTER_DESIGN.md](04_PLAYER_CHARACTER_DESIGN.md) — PO, PCS, SOC detail; DF1–DF8 registry
- [OPEN_DECISIONS.md](OPEN_DECISIONS.md) — all locked + pending decisions
- [../References/SillyTavern_Feature_Comparison.md](../References/SillyTavern_Feature_Comparison.md) — inspirations for PL-*, NPC-*, CC-8
