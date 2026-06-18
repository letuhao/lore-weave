# Thanos Sidecar — STUBBED V1

> **STATUS:** STUBBED V1. NOT WIRED INTO docker-compose.observability.yml.
> **Activation:** V1+30d per **Q-L1I-2** (OPEN_QUESTIONS_LOCKED.md line 46).
> **Shipped cycle:** 33 (config only — no live service).

## Why this file exists

Cycle 33 (L7.H Prometheus + Grafana + Thanos) ships the Thanos
**configuration file** (`infra/thanos/thanos.yaml`) without activating the
Thanos sidecar in docker-compose. This is **intentional** per the LOCKED
decision Q-L1I-2:

| Phase | Retention | Backend |
|---|---|---|
| V1 (now) | 30 days | Prometheus native (HA pair scrapes both replicas) |
| V1+30d | 1 year+ | Thanos sidecar uploads 2h blocks → S3 → thanos-query |

Shipping the config now means V1+30d activation is **hours of work, not
weeks** — bucket terraform + docker-compose flip + datasource add.

## How to detect this is still stubbed

The cycle-33 verifier (`scripts/raid/verify-cycle-33.sh`) asserts:

1. This file exists with the `STATUS: STUBBED_V1` banner.
2. `infra/thanos/thanos.yaml` exists and contains `guard.status: STUBBED_V1`.
3. `infra/docker-compose.observability.yml` does **NOT** include a live
   `thanos-sidecar` or `thanos-query` service block.
4. `infra/prometheus/main.yaml` `remote_write` block is **commented out**.

Any future cycle that activates Thanos **MUST**:

1. Remove this file (`rm infra/thanos/STUB_FLAG.md`).
2. Remove the `╔ STATUS: STUBBED V1 ╗` banner from `thanos.yaml`.
3. Uncomment `remote_write` in `prometheus/main.yaml`.
4. Add `thanos-sidecar` service to `docker-compose.observability.yml`.
5. Update the verifier to assert these changes (i.e., flip from "must be
   stubbed" to "must be active").

## Why stub-not-skip

Q-L1I-2 explicitly LOCKS the Thanos decision at the V1 ship boundary. The
alternatives considered:

| Option | Verdict |
|---|---|
| Ship config + active service V1 | REJECTED — adds S3 + IAM cost prematurely; V1 30d native retention is sufficient. |
| Ship nothing, wait V1+30d to design | REJECTED — couples activation to fresh design work; risks drift between Prom main.yaml `remote_write` shape and Thanos receive endpoint. |
| **Ship config-only stubbed V1** | **CHOSEN** — costs nothing operationally, locks the shape, enables fast V1+30d activation. |

## Owner

* **Owner:** platform
* **Activation owner:** SRE (V1+30d sprint)
* **LOCKED reference:** Q-L1I-2 / OPEN_QUESTIONS_LOCKED.md L46
* **Shipped:** 2026-05-29 (RAID cycle 33)
