# services/publisher — L2.D outbox publisher

Cold-path Go service. Drains per-reality `events_outbox` rows into Redis
Streams. Heartbeats meta every 10s. Dead-letters on persistent failure.

## V1 deploy shape

- Single replica per shard host (`Q-L2D-1`: V2 trigger = scale beyond 1000
  active realities).
- Leader-election skeleton ships as **no-op** (`Q-L2-5`: V1 single replica
  is trivially leader; SETNX path stubbed for V2+).
- Lag SLO: outbox row → Redis Stream within **1s P50 / 10s P99** under
  steady load (R06 §12F.3).

## Internal layout

| Package | Purpose |
|---|---|
| `pkg/leader_election` | V1 no-op `IsLeader() => true`; V2+ Redis SETNX |
| `pkg/poll_loop` | `FOR UPDATE SKIP LOCKED` batch poll per reality |
| `pkg/retry` | Exponential backoff + dead-letter at `max_attempts` |
| `pkg/heartbeat` | `publisher_heartbeats` writer (every 10s) |
| `pkg/xreality_fanout` | Cycle 10 DPS 3 — `xreality.*` topic fanout |
| `cmd/publisher` | Entry point + draining shutdown |

## Why `pkg/` not `internal/`?

Go's `internal/` packages can't be imported across modules. The cycle-10
integration test (`tests/integration/publisher_lag_test.go`) needs to
import poll_loop / retry / heartbeat — so they live under `pkg/`. Same
pattern cycle 6 used for `migration-orchestrator`.

## Effects pattern

Like cycle 6 + cycle 5 before it, every IO sink is abstracted as a Go
interface (`StreamEmitter`, `MetaWriter`, `Clock`, `Sleeper`). Test
fakes inject deterministic behavior; production wiring (cycle 11+) binds
the real `redis.Client`, `pgx.Pool`, `time.Now`. This keeps the cycle-10
unit suite fast (no Postgres / no Redis required).

## Runbook

See `runbooks/publisher/lag.md` for the SRE escalation thresholds
(10s warn / 60s page / 300s degraded).
