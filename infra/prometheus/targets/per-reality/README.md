# infra/prometheus/targets/per-reality/

Runtime-managed target files for Prometheus `file_sd_configs`.

This directory is read by `infra/prometheus/scrape-config.yaml` job
`per-reality-postgres` via:

```yaml
file_sd_configs:
  - files:
      - /etc/prometheus/targets/per-reality/*.yaml
    refresh_interval: 30s
```

## File-write contract

Each provisioned reality gets ONE file named after its `reality_id`:

```yaml
# /etc/prometheus/targets/per-reality/<reality_id>.yaml
- targets:
    - <db_host>:9187
  labels:
    reality_id: <reality_id>
    shard_host: <db_host_short_name>
    db_class: per-reality
```

## Who writes these files

**`services/world-service`** — the L1.C provisioner's
`register_prometheus_scrape` Effect (cycle 5 trait method;
`services/world-service/src/provisioner.rs` line 199) is the canonical
writer. The deprovisioner's `unregister_prometheus_scrape` Effect
removes the file.

## Current wiring state

- **Trait/Effect:** SHIPPED (cycle 5).
- **FakeEffects (test stub):** SHIPPED (cycle 5 — records calls but
  doesn't actually write files).
- **Production file-write impl:** DEFERRED — tracked as row
  `D-PROVISIONER-PROM-SCRAPE-WIRING` in `docs/deferred/DEFERRED.md`.
  Target cycle = 7 (L1.C ↔ L1.D ↔ L1.I cross-service wiring).

## Why file_sd_configs (not consul/k8s SD)

Q-L1C-1 V1 = docker-compose. No Consul. No K8s in V1. `file_sd_configs`
is the simplest dynamic discovery mechanism Prometheus supports and
needs no extra infra. V3+ may revisit if the deploy moves to K8s.

## Why no `.gitkeep`

This directory ships its own README. Git tracks it.

## Local dev

Don't write into this dir manually — let the provisioner. For ad-hoc
testing, dump a sample target file:

```yaml
# example.yaml
- targets:
    - 127.0.0.1:9187
  labels:
    reality_id: example
    shard_host: local
    db_class: per-reality
```

Then `curl http://prometheus:9090/api/v1/targets?state=active | jq` should
include the target within 30s.
