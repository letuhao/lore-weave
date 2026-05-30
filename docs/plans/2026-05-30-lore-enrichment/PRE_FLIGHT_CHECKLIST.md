# Lore-Enrichment — Pre-Flight Checklist

> Sign-off BEFORE RAID cycle execution. Legend: **[x] verified now** · **[~] at C0/C1 (built in-cycle)** · **[!] NEEDS USER (gating)**.
> Static checks run 2026-05-30.

## Environment & isolation
- [x] On branch `lore-enrichment/foundation`; **0** edits to `world-service`/`game-server`/`tilemap-service` in this branch's commits (isolation holds).
- [x] Dependencies **UP and healthy (verified live, 29h uptime):** postgres (host :5555 → in-net `postgres:5432`), redis (:6399), neo4j (:7688), knowledge-service (:8216), glossary-service (:8211), book-service (:8205), provider-registry-service (:8208), rabbitmq (:5795), minio (:9123). *(api-gateway-bff route wired at C0)*
- [~] New DB `loreweave_lore_enrichment` created — by the C2 migration.
- [x] Service port = **internal 8093 / host 8221** (8093 free; 8221+ per compose convention, 8217-19 reserved, 8220=tilemap). Gateway route `/v1/lore-enrichment/*` registered at C0.

## Secrets / config (service fails to start if missing)
- [~] `LORE_ENRICHMENT_DB_URL`, `INTERNAL_SERVICE_TOKEN`, `JWT_SECRET` set — at C0.
- [~] Read DSNs / tokens for knowledge-service, glossary, book-service — at C0/C1.
- [x] **VERIFIED LIVE (2026-05-30):** `qwen/qwen3.6-35b-a3b` registered + active in provider-registry; lm_studio credential @ `host.docker.internal:1234`; reachable from container (python urllib → **200**). Judges `qwen/qwen3-30b-a3b` + gemma also registered (for C15 ensemble).
- [x] **VERIFIED:** `text-embedding-bge-m3` registered + active + present in LM Studio (technique-b retrieval, C10).
- [x] **JIT auto-load:** LM Studio loads models on demand (judges ≠ enrich model can't co-reside) — call models by id; tolerate first-call load latency. Matches other branches + the eval framework.
- [x] `REDIS_URL` — redis container up (host :6399, in-network `redis:6379`).

## Upstream readiness (endpoints exist in code; live-smoke at C1)
- [~] knowledge-service graph / graph-stats / context / embedding-model + `/internal/embed` for a test project.
- [~] glossary `POST /internal/books/{book_id}/extract-entities` + wiki reachable with internal token.
- [~] book-service chapter/hierarchy read reachable.
- [x] 封神演义 **source downloaded** → `data/lore-enrichment/fengshen-yanyi.txt` (100 回; demo places verified present).
- [x] 山海经 **downloaded** → `data/lore-enrichment/shanhaijing.txt` (19 sections; 崑崙/蓬萊 grounding verified).
- [~] Fengshen book/project **seeded** (import txt via book-service + initial glossary + extracted KG) — C0/C1.
- [ ] Shang–Zhou history corpus (optional, ~C10) — not yet downloaded.

## RAID operational
- [x] `.raid/active-task.yaml` validates → `task_config.py validate` exit 0 (12 keys).
- [x] Quota profile present (`contracts/raid/quota-profile.yaml`); cost posture = conservative/batched (locked).
- [x] Runtime logs initialized: `CYCLE_LOG.md`, `ESCALATIONS.md`, `QUOTA_LOG.jsonl`, `AUDIT_LOG.jsonl`.
- [x] pre-commit hook installed (`.git/hooks/pre-commit` → workflow-gate; warn-and-pass on no state).

## Cost / safety
- [x] (policy, locked) P1 (template+retrieval) only until the eval gate (**C15**); fabrication/re-cook (C16/C17) stay disabled until then.
- [x] Secret-scan + prod-isolation lint scripts present (`scripts/raid/secret-scan-cycle.sh`, `prod-isolation-lint.sh`) — wired per DPS at brief time.

---

## ⛳ Gating summary (2026-05-30 — pre-flight COMPLETE)
- **Verified live ✅:** stack up + healthy; Qwen 3.6 + bge-m3 + judges registered & active; LM Studio reachable from container (200); branch/isolation; ports (8093/8221); RAID config + logs + hook; corpora prefetched; cost policy.
- **Built during cycles (no pre-flight action) ⏳:** `loreweave_lore_enrichment` DB (C2), service env vars + skeleton (C0), Fengshen ingest (C0/C1), runtime live-smokes (C1+).
- **No outstanding USER gate.** Pre-flight passes → ready for `/raid`.
- Dev note: in-network DSN uses `postgres:5432` (service name), not host `:5555`; provider-registry in-net `:8085` (host `:8208`).
