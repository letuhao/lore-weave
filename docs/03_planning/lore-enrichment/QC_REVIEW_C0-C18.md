# Lore-Enrichment — Human-in-loop QC Review of the RAID run (C0–C18)

> Started 2026-05-31 · Branch `lore-enrichment/foundation` · HEAD `8b864487` · Reviewer: human-in-loop (default v2.2)
> Method (per PO): risk-weighted · `/review-impl` adversarial on load-bearing cycles · **live stack-health = full demo re-run**.
> Status: **IN PROGRESS** — Step 1 (live stack-health) done; Steps 2–5 (code review / defer / synthesis) pending.

---

## Step 1 — Live stack-health (DONE)

Stack: the full `infra-*` compose was already up and healthy (postgres/redis/neo4j/glossary/knowledge/book/provider-registry/lore-enrichment all `healthy`). LM Studio reachable on `:1234` with `qwen/qwen3.6-35b-a3b` (chat) + `text-embedding-bge-m3` (embed) loaded; both registered in `provider_registry` for the demo user.

### ✅ Verified live
- **Readiness/liveness (C18):** `lore-enrichment` `/health`=200 and `/ready`=200 from inside the container (port 8093 → host 8221).
- **C4 glossary→KG event pipeline:** consumer group on `loreweave:events:glossary` has **pending 0, lag 0** — not wedged (the prior incident class is clear).
- **P1 generation + H0 quarantine (real Qwen, end-to-end):** ran `tests/live_smoke_c14_job.py` against the live stack for 蓬萊:
  - resolved gen + embed model_refs **by name** via provider-registry BYOK (no hardcoded names) ✓
  - ingested a 山海经 grounding chunk via **real bge-m3 embed** ✓
  - **real Qwen 3.6 generated 5 source-faithful Chinese dimensions**; honest-sparse where the corpus didn't cover (`历史`/`文化` → "检索片段未载…"), `features` quotes the 山海经 anchor「宫室皆以金玉為之，鸟兽尽白」 ✓
  - **H0 held:** persisted proposal `origin=enrichment`, `confidence=0.30 (<1.0)`, `review_status=proposed`, `pending_validation`, 4 grounding refs. Confirmed in DB. ✓
- **P1 promote→canon (real Qwen, end-to-end) — after rebuilding the stale knowledge image (F-LIVE-1):** quarantined proposal → approve → **author promote → enriched-writeback → canon** (glossary entity created, 5 facts promoted) **with permanent origin marker retained** (`origin=enrichment`, `original_technique=retrieval`, `promoted_by`=demo user); 4 lifecycle events, 0 failures. Smoke EXIT 0; DB shows the `promoted` row with markers. ✓ — **H0 invariant live-verified both directions.**

### 🔴 Findings from the live run

> **Process note (review honesty):** the first promote re-run failed on `glossary-service:8087` — that was a **typo in my smoke-harness env** (`GLOSSARY_SERVICE_URL_H=…:8087`), NOT a product bug. The service's real config is correct: live env **and** `infra/docker-compose.yml:577` both have `GLOSSARY_SERVICE_URL=http://glossary-service:8088`. Discarded. Recording it only so the next session doesn't re-chase it.

**F-LIVE-1 (HIGH, stack-health — NOT a code bug) — RESOLVED in-session by rebuild. The running `knowledge-service` image was STALE; the C13 H0 write-back route was missing in-cluster (404).**

> **✅ RESOLVED 2026-05-31:** rebuilt + recreated `knowledge-service`; confirmed `/app/app/routers/internal_enrichment.py` now present + service healthy. Re-ran the C14 promote smoke → **LIVE-SMOKE PASS (EXIT 0)**: real Qwen P1 gen → quarantined H0 proposal → review → author promote → **enriched-writeback → promote→canon** (glossary entity `019e78d4-…`, `facts_promoted=5`) **WITH permanent origin marker intact**; 4 events, 0 failures. **DB ground-truth:** a `promoted` row with `origin=enrichment, conf=0.30 (<1.0), original_technique=retrieval, promoted_by set, promoted_entity_id set`. → **H0 promote→canon path now live-verified end-to-end.** Original-finding detail kept below for the record. **(Net: a deploy/CI gap, not a code defect — see DEFERRED candidate for a stale-image guard.)**

With the harness port fixed, the promote got past the owner check and through `glossary` and then failed at:
```
WritebackError: POST http://knowledge-service:8092/internal/knowledge/enriched-writeback failed (404)
```
The route **exists in source** (`services/knowledge-service/app/routers/internal_enrichment.py` — `enriched-writeback`/`enriched-promote`/`enriched-retract`) and is registered in `app/main.py:27,529`. But the **running container does not have the file** (`ls /app/app/routers/internal_enrichment.py` → No such file). Image built **2026-05-30 15:49Z**; the C13 commit `6daa89fd` landed **2026-05-30 18:22** (+07) — i.e. the deployed image **predates C13**. → The H0 promotion write-back into the KG is unverifiable on the current stack because the container is stale.
**This is exactly the stale-image false-green class from last session** (glossary image was 13d stale, `5e902190`) and the core of ContextHub lesson `e16b6f02`. The *code* looks correct; the *deployed artifact* is behind.
**Fix:** `docker compose build knowledge-service && docker compose up -d knowledge-service`, then re-run the C14 promote smoke → confirm enriched-writeback (quarantined) → promote→canon → origin marker, live. Until then, promote→canon is **NOT** live-verified this session (DB still shows `proposed=1, promoted=0`).

**F-LIVE-2 (MED) — circular import on the `app.clients.writeback` entry path.**
Importing `app.clients.writeback` first raises:
```
ImportError: cannot import name 'CanonVerifier' from partially initialized module 'app.verify.canon_verify' (circular import)
chain: clients.writeback → verify → generation → retrieval → strategies → strategies.fabrication → verify.canon_verify
```
The running service avoids it because `app.main`'s import order initializes the modules in a working sequence — so production startup is fine — but any entry point that imports `writeback` first (incl. the committed verification scripts) crashes. C16 already noted strategies/eval circular-import fragility (worked around with a lazy import). **Fix:** break the cycle structurally (lazy import of `CanonVerifier` in `strategies/fabrication.py`, or restructure the `app.verify`/`app.strategies` package imports) so import order doesn't matter.

**F-LIVE-3 (LOW/process) — verification scripts are not shipped in the image + not runnable as-is.**
`tests/` is not COPYed into the Docker image (only `app/`), and the smokes hardcode **host-port** env defaults (5555/6399/8208/8216/8211/8205). Combined with F-LIVE-2, the "documented" demo is not reproducible in-cluster without (a) copying the script in and (b) pre-importing `app.main`. Consider a committed, in-cluster-aware demo entrypoint (or ship `tests/` + a runner that uses service-name URLs) so the demo is reproducible by the next session.

### ℹ️ Observations (to confirm in Step 2 code review)
- **DB state:** `loreweave_lore_enrichment` has **2 proposals (both `proposed`/`approved`), 0 promoted, 3 corpus chunks** (each smoke run adds a fresh 蓬萊 proposal — itself a NIT: the smoke isn't idempotent on re-run, it creates a new job+proposal each time). The prior demo's "4 locations promoted to canon" is **not** persisted in the current stack — now explained by F-LIVE-1 (stale knowledge image blocks the write-back), corroborating SESSION_HANDOFF concern #3.
- **`LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1` is set directly on lore-enrichment.** Confirm generation/embedding actually route through provider-registry (provider-gateway invariant) and that this var isn't a direct-SDK bypass. (Generation in the smoke did go through provider-registry `/internal/llm` by model_ref; verify nothing else uses the direct LM Studio URL.)

---

## Steps 2–5 — PENDING
- **Step 2 — Code review (risk-weighted):** self-review C0,C1,C3,C6,C7,C8,C9 (+ MED C4,C5,C10,C14,C18); `/review-impl` adversarial on **C2,C11,C12,C13,C15,C16,C17**. Fold F-LIVE-1/2 into the C13/C16 reviews.
- **Step 3 — Cross-cutting control audit:** H0 chokepoint, cost-cap on runner path, eval-gate sole-selection, licensing default-deny, isolation/scope-drift.
- **Step 4 — Defer triage:** DEFERRED 044–058 (do-now/keep/won't-fix) + confirm 042/043/048/049/053/054 genuinely resolved.
- **Step 5 — Synthesis:** per-cycle verdict table + confirmed findings by severity + go/no-go for opening a PR.
