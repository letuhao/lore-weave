# Lore-Enrichment — Pre-Flight Checklist

> Sign-off BEFORE RAID cycle execution. Legend: **[x] verified now** · **[~] at C0/C1 (built in-cycle)** · **[!] NEEDS USER (gating)**.
> Static checks run 2026-05-30.

## Environment & isolation
- [x] On branch `lore-enrichment/foundation`; **0** edits to `world-service`/`game-server`/`tilemap-service` in this branch's commits (isolation holds).
- [x] `infra/docker-compose.yml` has all dependencies: postgres, redis, neo4j, knowledge-service, glossary-service, book-service, **provider-registry-service**, api-gateway-bff. *(presence verified; runtime stack-up is C1 live-smoke)*
- [~] New DB `loreweave_lore_enrichment` created — by the C2 migration.
- [x] Service port = **internal 8093 / host 8221** (8093 free; 8221+ per compose convention, 8217-19 reserved, 8220=tilemap). Gateway route `/v1/lore-enrichment/*` registered at C0.

## Secrets / config (service fails to start if missing)
- [~] `LORE_ENRICHMENT_DB_URL`, `INTERNAL_SERVICE_TOKEN`, `JWT_SECRET` set — at C0.
- [~] Read DSNs / tokens for knowledge-service, glossary, book-service — at C0/C1.
- [!] **Qwen 3.6 (LM Studio) registered in provider-registry** + endpoint (`http://host.docker.internal:1234/v1`) **reachable from the service container**. — **only you can set this up.**
- [!] **Embedding model in LM Studio** (bge-m3 / nomic-embed) + registered, for technique-(b) retrieval (C10).
- [~] `REDIS_URL` reachable — infra/C0.

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

## ⛳ Gating summary
- **Ready now:** branch/isolation, ports, compose deps, RAID config + logs + hook, prefetched corpora, cost policy. ✅
- **Built during cycles (no action):** DB, env vars, ingest, runtime live-smokes. ⏳
- **NEEDS YOU before C7/C10 can live-smoke:** LM Studio up with **Qwen 3.6 + an embedding model**, registered in provider-registry, reachable from containers. 🔴
