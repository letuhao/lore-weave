# Chaos scripts (T2-close-3)

Live failure-injection scripts for chaos scenarios **C05 / C06 / C08** from KSA §9.10.
Each script is a bash program a human runs against the running `infra` compose stack.
They complement the unit-level coverage already automated in the knowledge-service
test suite (see `docs/sessions/GATE_13_READINESS.md` §2 for the mapping).

## When to run

- Before a production deploy of the knowledge-service stack.
- After a change to the events consumer (`services/knowledge-service/app/events/`)
  or the K11.9 reconciler (`services/knowledge-service/app/jobs/`).
- Ad-hoc, whenever you want a "does the system actually recover from X" answer.

These are **not** part of the automated test suite because they:

- Require the full compose stack running (Postgres, Redis, Neo4j, knowledge-service).
- Mutate real infrastructure state (restart containers, write to Neo4j, emit Redis
  events) — running them in parallel with real work would interfere.
- Take 30 s – 3 min each.

## Prerequisites

| Requirement | Check |
|---|---|
| Docker running | `docker ps` shows the infra containers |
| `infra-*` containers healthy | `docker ps --format '{{.Names}}'` shows `infra-postgres-1`, `infra-redis-1`, `infra-neo4j-1`, `infra-knowledge-service-1` |
| bash 4+ (for `wait_until` polling loop) | `bash --version` |

If your compose project name isn't the default `infra`, set
`LOREWEAVE_INFRA_PREFIX=<your-prefix>` before running.

## Running

```bash
# Individual scenarios:
./scripts/chaos/c05_redis_restart.sh
./scripts/chaos/c06_neo4j_drift.sh
./scripts/chaos/c08_bulk_cascade.sh

# Capture output for the SESSION_PATCH evidence log:
./scripts/chaos/c05_redis_restart.sh 2>&1 | tee /tmp/c05-$(date +%Y%m%d).log
```

Each script exits `0` on PASS and `1` on any assertion failure. The last line of
stdout is always `C0X:PASS` or the script dies with `FAIL <reason>` on stderr.

## Scenario details

### C05 — Redis restart resilience

**Hypothesis**: knowledge-service consumer reattaches to its XREADGROUP consumer
group after a Redis restart and continues processing new events without growing
the DLQ.

**Injection**: `docker restart infra-redis-1`.

**Observable**: DLQ (`dead_letter_events`) unchanged; post-restart probe event
gets acked within 15 s (pending count returns to baseline).

**Runtime**: ~20 s.

### C06 — Neo4j evidence-count drift + reconciliation

**Hypothesis**: when a node's cached `evidence_count` diverges from its actual
`EVIDENCED_BY` edge count, the K11.9 `reconcile_evidence_count` job detects and
corrects it.

**Injection**: seed an `:Entity` with `evidence_count=3` and 3 edges; delete 2 of
the edges via raw Cypher (bypasses the `add_evidence` write path that keeps
them in sync).

**Observable**: reconciler reports `entities_fixed >= 1`; post-run
`evidence_count == actual edge count`.

**Runtime**: ~10 s.

### C08 — Bulk chapter cascade (1000 events)

**Hypothesis**: a 1000-event `chapter.deleted` burst drains cleanly — all
`:ExtractionSource` nodes removed, all orphan edges cleaned up, no DLQ growth,
and the consumer is still responsive after the burst.

**Injection**: seed 1000 `:ExtractionSource` + `:Entity` pairs in Neo4j, then
XADD 1000 `chapter.deleted` events to the Redis stream as fast as the loop can
issue them.

**Observable**: `:ExtractionSource` count for the test user returns to 0 within
120 s; orphan entities = 0; DLQ unchanged; a post-burst probe event is acked
within 15 s.

**Runtime**: ~60–120 s depending on Neo4j + consumer speed.

## Cleanup

Every script has a `trap cleanup EXIT` so even a failed run removes its test
nodes (`user_id = '00000000-0000-0000-c0XX-...'`). If a script is killed
mid-run with SIGKILL, you can sweep residual test data with:

```bash
docker exec infra-neo4j-1 cypher-shell -u neo4j -p loreweave_dev \
  "MATCH (n) WHERE n.user_id STARTS WITH '00000000-0000-0000-c0' DETACH DELETE n"

docker exec infra-postgres-1 psql -U loreweave -d loreweave_knowledge \
  -c "DELETE FROM extraction_pending WHERE user_id::text LIKE '00000000-0000-0000-c0%'"
```

## Recording results

Per the Track 2 close-out plan, each successful run should update
`docs/sessions/SESSION_PATCH.md` Chaos Evidence Log with:

- Script name + timestamp + HEAD SHA
- Runtime
- Short note if any warnings fired (e.g., drain took longer than last run)

Failed runs should update `GATE_13_READINESS.md` §2 with the specific failure so
the next operator knows what to look at first.
