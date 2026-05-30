# Lore-Enrichment Track — Session Handoff

> **Last updated:** 2026-05-31 · **Branch:** `lore-enrichment/foundation` (off `origin/main`) · **HEAD:** `b6283a21` · **PUSHED to origin** (no PR yet).
> Isolated from `mmo-rpg/foundation-mega-task` (another agent, another folder — do not touch).
> **STATUS: RAID COMPLETE — 19/19 cycles (C0–C18) DONE, 0 escalations, ~49 commits. P1 demo validated live.**

## What this track is
A `lore-enrichment-service` (Python/FastAPI) that GENERATES the missing "off-page" canon a novel leaves implicit, so a book can become a game world. Demo corpus: **封神演义**. Four techniques: template scaffolding (P1), cultural retrieval (P1), canon-grounded fabrication (P2), real history/news re-cook (P3) — phased behind a cost-cap + eval gate. **H0 core invariant: enriched ≠ canon** (quarantine + author-promote-only + permanent origin marker).

## RAID run summary (C0–C18, all DONE on `lore-enrichment/foundation`)
| Cycle | Deliverable | Independent-adversary finding (Coordinator-run) → status |
|---|---|---|
| C0 | service skeleton (full default+AMAW) | — |
| C1 | KG-read clients + port + H1/H2/M4 verifies | — |
| C2 | data model + H0 (DB CHECKs + promote trigger) | — |
| C3 | OpenAPI contract + stubs + author-promote | — |
| C4 | **K14 glossary→KG event pipeline** | WARN manual-name propagation → DEFERRED-043 |
| C5 | **D4-03 wiki-from-KG** | (053 surfaced later, fixed) |
| C6 | gap-MODEL + LOCATION dims + Fengshen fixtures | — |
| C7 | gap-detection engine | — |
| C8 | strategy-core (flag-gated registry + cost guardrail + state machine) | — |
| C9 | template strategy | — |
| C10 | retrieval strategy (real bge-m3) | — |
| C11 | schema-gov gen + H0 tagging | 2 WARN confidence/cjk fidelity → 045/046/047 |
| C12 | canon-verify + injection-defense | 2 false-greens (contradiction fail-open, anachronism bypass) → **FIXED** |
| C13 | review-gate + H0 write-back/promote/retract | self-fixed A1; adversary 2 H0 leaks (makeup-as-name, minted-anchor) → **FIXED** |
| C14 | job orchestration (**DEMO**) | **cost-cap inert** (false-green) + unsafe resume → **FIXED**; persistence quirk (see agenda) |
| C15 | eval-gate (judge-ensemble) | 3 forward WARN (enforcement/freshness/diversity) → 054(closed e2e)/055/056/057 |
| C16 | fabrication (P2, gate-enforced) | gate not on runner path (false-green) → **FIXED e2e (054)** |
| C17 | re-cook (P3, gate + licensing) | licensing ingest default-allow + un-neutralized excerpt → **FIXED** + 058 |
| C18 | productionize (observability + /ready) | clears DEFERRED-042 |

**Demo validated live (real Qwen 3.6):** 4 locations (玉虛宮/碧遊宮/蓬萊/陳塘關) → enriched Chinese → review → promote→canon, **origin marker retained for life**. Eval composite 96.88 → P2/P3 gate cleared. Honest no-fabrication behaviour (ungrounded dims say "检索语料未及…").

## Key docs (read for the review)
1. [CLARIFY_GROUND_TRUTH.md](CLARIFY_GROUND_TRUTH.md) + [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md) — locked decisions (review basis).
2. [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md) — what each cycle was supposed to ship (compare vs actual diff).
3. [docs/raid/CYCLE_LOG.md](../../raid/CYCLE_LOG.md) — per-cycle commit + verify evidence. [docs/audit/AUDIT_LOG.jsonl](../../audit/AUDIT_LOG.jsonl) — every phase + adversary verdict. `docs/audit/findings-*.md` — independent-adversary findings.
4. [DEFERRED.md](../../deferred/DEFERRED.md) — forward backlog (042–058) to triage.

## Locked decisions (the review baseline — relitigate only with cause)
Separate Python/FastAPI service; consumes knowledge-service KG (not re-extract). Write-back via glossary SSOT (extract-entities + wiki/canon-content) → `glossary_sync` → Neo4j (Q2). Per-user/project scoping (Q3). 4 techniques phased P1→P2→P3 behind cost-cap + eval gate (Q-R2). Mirror `pending_facts`. Schema isolated from mmo-rpg. Output Chinese; models via provider-registry (no hardcoded names). **H0** (enriched≠canon).

---

## ⏭️ NEXT SESSION — HUMAN-IN-LOOP QC REVIEW of this run (default v2.2, NOT autonomous /raid)
The run was executed autonomously (Coordinator + single-agent cycle-runners + Coordinator-run independent adversaries). Next session = **human controls the pace**; review for quality, decisions, missing, defer, drift. Agenda:

1. **Quality** — per cycle, diff vs the CYCLE_DECOMPOSITION brief: did it ship the scope? any stub/placeholder-only deliverable? Spot-check riskiest: C13 (H0 write-back), C16/C17 (gated techniques), C15 (gate).
2. **Decisions** — sound? Notably: (a) Coordinator-runs-independent-adversary model (sub-agents can't nest); (b) C13 A1 + WARN fixes (makeup-as-name, minted-anchor); (c) **053 Q2 glossary-SSOT split** (glossary `short_description` summary + KG per-dimension facts — right canonical model?); (d) C14 opaque cost units (embed=1/gen=4/fab=8); (e) **κ informational, not a hard gate** (056).
3. **Missing** — known gaps: **044** (glossary `KNOWLEDGE_SERVICE_URL` NOT wired in compose → wiki KG-sections only with override); **C14 demo** persisted only a template scaffold in a stray project until a Coordinator re-run (in-cycle promote not durably reflected — verify the API/runner persists e2e); is fabrication/recook reachable from the API now the runner is factory-routed (C16-fix)? Shang–Zhou history corpus not downloaded.
4. **Defer** — triage open DEFERRED 044/045/046/047/050/051/052/055/056/057/058 (do-now vs keep vs won't-fix). Confirm 042/043/048/049/053/054 genuinely resolved.
5. **Drift** — scope drift (anything outside the locked plan / H0 / isolation?), quality drift (did the bar slip late vs early?), policy drift (confirm NO human-gate crept back into the RAID flow; `raid.md` generic untouched + still untracked), and the **"built-but-not-wired false-green" pattern** (ContextHub lesson `e16b6f02`): audit ALL load-bearing controls (cost-cap, eval gate, licensing, H0 chokepoint) are actually on the PRODUCTION path, not just unit-tested.
6. **Stack-health** — live stack had a stale glossary image + wedged KG consumer (both fixed in-run, `5e902190`); re-confirm a clean `docker compose up --build` boots healthy + the C4 event pipeline propagates end-to-end.

**Tools:** `/review-impl` (deep adversarial) on C13/C15/C16/C17; or open a PR then `/code-review ultra <PR#>`. Do NOT auto-`/raid` — the run is done.

## Reusable infra (adopt, don't reinvent)
confidence/quarantine/pending_validation · pending_facts confirm-reject + injection-defense · job state machine · per-project embedding-model · Neo4j graph-stats · CJK-aware splitting · Redis Streams (outbox→relay→consumer; consumer redis read-timeout bug fixed `5e902190`) · chat/knowledge skeleton + `loreweave_obs` (OTEL) · judge-ensemble (`tests/quality/`).
