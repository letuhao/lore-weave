# Lore-Enrichment Track — Session Handoff

> **Last updated:** 2026-05-31 · **Branch:** `lore-enrichment/foundation` (off `origin/main`) · **HEAD:** `8b864487` · **PUSHED to origin** (no PR yet).
> Isolated from `mmo-rpg/foundation-mega-task` (another agent, another folder — do not touch).
> **STATUS: RAID COMPLETE (19/19) + QC REVIEW NEAR-FINAL (Steps 1–5 done; verdict CONDITIONAL GO). Full detail → [QC_REVIEW_C0-C18.md](QC_REVIEW_C0-C18.md).**
> QC covered all 7 load-bearing cycles (`/review-impl`: C2/C11/C12/C13/C15/C16/C17) + C14 + a light low-risk tier + a live DB/Neo4j audit + defer triage. **Findings: 1 HIGH (F-C13-1 retract glossary-recycle is dead code — handler passes no jwt, `Principal` has no token), 3 MED (F-C13-2 promoted enrichment orphaned from canonical entity [live-confirmed]; F-C14-1 cost-pause resume unwired [=defer 051]; F-C12-1 contradiction check inert — `_canon_lookup` stubbed `[]`), + cheap do-nows 044/046.** Cleared live: F-C2-1 (H0 trigger installed), F-C1617-1 (licenses clean). **F-LIVE-2 (circular import) FIXED this session** (`canon_verify.py`+`wiring.py` TYPE_CHECKING guards, live-verified). **F-LIVE-1 RECURS** on a plain stack restart (knowledge image loses C13 enriched-* routes → needs rebuild + a stale-image guard). Core H0/gate/licensing/eval invariants all verified genuinely-wired. **Remaining:** C5 deep review + live retract capstone (after `docker compose build knowledge-service`). Defer list: 048/049 are stale-resolved (close them).
> **PO DECISION RULINGS (2026-05-31) — see QC_REVIEW "PO Decision Rulings".** Canon model: glossary = single SSOT, enrichment = distinguished supplement/`dị bản` of original canon (never merge/overwrite, never a parallel entity) [B1] · writeback must RESOLVE existing glossary entity, not mint from `target_ref`-as-name [B3] · enrichment MAY extend glossary API [B2 ratified] · cost-cap → REAL token units per platform convention [C1, elevates 052→MED] · judge-diversity gate PARKED until `main` merge [C2, 056 blocked-on-merge] · defenses → hybrid flag-for-human + AUTO-REJECT egregious, needs design [C3] · WIRE gap-auto-detect + all built-but-not-wired (retract/resume/corpus-register) [D1/D2] · keep cold-start review gate pre-merge [E1].
> **FIX ORDER:** ~~do-nows 044/046~~ **DONE** (commit `7be1b18d` — 046 numeric-hallucination reject + 044 glossary KNOWLEDGE_SERVICE_URL). Next: **F-C13-2/B1/F-C13-1 cluster** — these are COUPLED (retract can't be fixed before B1 defines how enrichment attaches), spec'd in **[docs/specs/2026-05-31-enrichment-supplement-canon-model.md](../../specs/2026-05-31-enrichment-supplement-canon-model.md)** (L/XL, awaiting PO data-model pick a/b/c — rec **c** = separate `entity_enrichments` table). Then (3) wire D1/D2 + F-LIVE-1 stale-image guard → (4) C1 token metering → (5) C3 auto-reject design. C2 waits for main merge.

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

## 🔵 QC REVIEW IN PROGRESS — Step 1 (live stack-health) DONE 2026-05-31
Full QC tracking doc: **[QC_REVIEW_C0-C18.md](QC_REVIEW_C0-C18.md)**. Method (PO-chosen): risk-weighted · `/review-impl` adversarial on load-bearing cycles · live stack-health = **full demo re-run**.

**Step 1 (live stack-health) — COMPLETE.** P1 demo live-verified end-to-end on 封神演义 with real Qwen; **H0 promote→canon confirmed** (DB ground-truth: `promoted | origin=enrichment | conf=0.30 | original_technique=retrieval | promoted_by✓ | promoted_entity_id✓`). Findings:
- **F-LIVE-1 (HIGH stack-health → RESOLVED in-session):** running `knowledge-service` image was **stale** (predated C13 commit `6daa89fd`) → `enriched-writeback` 404 → promote failed. Rebuilt + recreated `knowledge-service`; re-ran smoke → PASS. *Same stale-image false-green class as last session's glossary incident.* **→ DEFERRED candidate: a stale-image/CI guard so a deployed image behind HEAD is caught automatically.**
- **F-LIVE-2 (MED, real code bug):** circular import on the `app.clients.writeback` entry path (`writeback→verify→generation→retrieval→strategies→fabrication→verify.canon_verify`). Prod startup dodges it via `app.main` import order; verification scripts crash. **Fix: lazy-import `CanonVerifier` in `strategies/fabrication.py`.**
- **F-LIVE-3 (LOW/process):** `tests/` not in the image + smokes hardcode host-port defaults → in-cluster demo not reproducible without copy-in + `app.main` pre-import. Ship a cluster-aware demo entrypoint.

**⏭️ NEXT SESSION — run Steps 2–5 of the QC (fresh context).** See QC_REVIEW_C0-C18.md "Steps 2–5 — PENDING":
1. **Step 2 code review (risk-weighted):** self-review C0,C1,C3,C6,C7,C8,C9 (+MED C4,C5,C10,C14,C18); `/review-impl` adversarial on **C2,C11,C12,C13,C15,C16,C17**. Fold F-LIVE-2 into C16.
2. **Step 3 control audit:** H0 chokepoint · cost-cap on runner path · eval-gate sole-selection · licensing default-deny · isolation/scope-drift.
3. **Step 4 defer triage:** DEFERRED 044–058 + confirm 042/043/048/049/053/054 genuinely resolved.
4. **Step 5 synthesis:** per-cycle verdict table + go/no-go for opening a PR.
A pre-authored multi-agent workflow for Steps 2–4 exists (Coordinator can re-issue) but the PO opted to start it in a fresh session.

---

## Original QC agenda (for reference)
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
