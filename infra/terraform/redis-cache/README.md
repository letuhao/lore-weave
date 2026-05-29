# `infra/terraform/redis-cache/` — STUB (V1+30d)

## Status

**EMPTY by design.** Per Q-L1F-1 (locked):

> Multi-instance Redis topology: shared Sentinel V1; per-AZ V3+
> multi-AZ resilience.

And by Q-L1C-1 transitively (V1 = docker-compose, IaC = V1+30d).

This directory is a **placeholder** for ECS / EKS resources that will
run the production shared Redis Sentinel cluster (V1+30d) and the
per-AZ clusters (V3+).

## V1 substitute

Use `infra/docker-compose.redis-cache.yml` overlay on top of
`infra/docker-compose.meta-ha.yml`:

```bash
docker compose -f infra/docker-compose.meta-ha.yml \
               -f infra/docker-compose.redis-cache.yml up -d
```

App connects via `127.0.0.1:16379` (Redis) and `127.0.0.1:26379`
(Sentinel). See `infra/redis/redis.conf` for the AOF + allkeys-lru
configuration; `infra/redis/sentinel.conf` for the master watcher.

## DEFERRED tracking

Tracked under `D-L1F-PROD-REDIS-IAC` in
`docs/deferred/DEFERRED.md` (Track 2 planning row):

- **Origin:** Cycle 5 (L1.F)
- **Target phase:** V1+30d staging-gate sub-program
- **Inputs needed:** ECS vs EKS placement decision, instance memory
  budget (cache size grows linearly with active reality count), per-AZ
  vs cross-AZ decision (V1 = single AZ; V3+ = per-AZ Sentinel
  clusters).
- **Definition of done:** `terraform apply` provisions a healthy
  Sentinel-fronted Redis cluster reachable from the world-service ECS
  task; `scripts/cache-warmup.sh` populates the top-N realities
  successfully.
