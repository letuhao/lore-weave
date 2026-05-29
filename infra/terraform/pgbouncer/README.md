# `infra/terraform/pgbouncer/` — STUB (V1+30d)

## Status

**EMPTY by design.** Per Q-L1G-1 (locked):

> Stick with pgbouncer (vs pgcat/Odyssey)? YES; re-evaluate trigger =
> transaction-pool limits hit V3.

And by Q-L1C-1 transitively (V1 = docker-compose, IaC = V1+30d).

This directory is a **placeholder** for the future ECS/EKS task
definition + ALB target group resources that will run a per-shard
pgbouncer instance in production.

## V1 substitute

Use `infra/docker-compose.pgbouncer.yml` overlay on top of
`infra/docker-compose.meta-ha.yml`:

```bash
docker compose -f infra/docker-compose.meta-ha.yml \
               -f infra/docker-compose.pgbouncer.yml up -d
```

App connects via `127.0.0.1:16432`. See `infra/pgbouncer/pgbouncer.ini`
for the transaction-mode + capacity configuration.

## DEFERRED tracking

Tracked under `D-L1G-PROD-PGBOUNCER-IAC` in
`docs/deferred/DEFERRED.md` (Track 2 planning row):

- **Origin:** Cycle 5 (L1.G)
- **Target phase:** V1+30d staging-gate sub-program
- **Inputs needed:** ECS vs EKS placement decision (Q-L6G-1 says K8s for
  capacity admission; align here), per-shard task definition memory
  budget, ALB vs NLB.
- **Definition of done:** `terraform apply` provisions a healthy
  pgbouncer fleet behind a load balancer that the world-service can
  reach with the same `db_pool` registry config (no app-side changes).
