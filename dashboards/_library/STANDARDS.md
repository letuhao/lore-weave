# Dashboard Standards (cycle 33 L7.H.7)

> **Owner:** platform · **Shipped:** RAID cycle 33 · **Status:** V1 LOCKED.

This document is the canonical reference for **all** Grafana dashboards
shipped in the foundation. Every new dashboard JSON file MUST conform.
The CI lint `scripts/dashboard-validator.sh` enforces a subset of these
rules automatically.

## Why standards?

Foundation V1 will ship 30+ dashboards (10 platform + ~20 per-service).
Without conventions, every dashboard is a snowflake — operators waste
seconds parsing layouts during incidents, and inconsistent label/colour
semantics cause misreads at 3 AM.

## Naming conventions

| Element | Convention | Example |
|---|---|---|
| Dashboard `title` | `<Subject> (cycle <N> <layer>)` | `Logs Explorer (cycle 33 L7.F)` |
| Dashboard `uid`   | `kebab-case-stable` (never changes) | `logs-explorer` |
| Dashboard `tags`  | `[<topic>, cycle-<N>, <layer-id>]` | `["logs", "cycle-33", "L7.F"]` |
| Folder            | `LoreWeave Foundation` (root) | — |
| Panel `id`        | Sequential integers, dashboard-local, 1-indexed | 1, 2, 3, … |
| Panel `title`     | Title Case Plain English | `Live log stream` |

## Color palette

Use the standard Grafana "Classic" palette UNLESS overridden below.

| Semantic | Color | Use for |
|---|---|---|
| OK / Healthy | `green` (`#73BF69`) | Up state, success rate |
| WARN | `yellow` (`#F2CC0C`) | Backpressure, elevated latency |
| ERROR / DEGRADED | `orange` (`#FF780A`) | Service degraded (L1.J Limited) |
| CRITICAL / DOWN | `red` (`#F2495C`) | Service down, SLO burn ≥ 4x |
| Cohort A (deploy) | `blue` (`#5794F2`) | Cycle-30 deploy cohort A |
| Cohort B (deploy) | `purple` (`#B877D9`) | Cycle-30 deploy cohort B |
| External (provider) | `grey` (`#909090`) | Provider-registry LLM calls |

## Panel layout

* **Grid:** 24-wide; row heights multiples of 4.
* **Header row (y=0):** single "current state" stat panel spanning full
  width — quick eye check at top.
* **Trend rows (y=4..N):** time-series panels in pairs (12-wide each).
* **Detail rows (y=N..M):** logs/tables/bar gauges.
* **Drill-down:** link from rolled-up dashboard to per-service via panel
  `links` → URL with `var-service=$service`.

## Variables

Every dashboard MUST have the variables it filters on declared in
`templating.list`. Standard variables foundation-wide:

| Name | Type | Source | Default |
|---|---|---|---|
| `lw_env` | custom | `dev,staging,prod` | `dev` |
| `service` | query | `label_values(service)` | `All` |
| `shard_host` | query | `label_values(shard_host)` | `All` (where relevant) |
| `cohort_id` | query | `label_values(cohort_id)` (cycle-30) | `All` |

## Refresh + time range

* `refresh: "30s"` (matches Prom scrape interval).
* `time.from: "now-1h"` default; longer for capacity-planner-style boards.
* `timezone: "utc"` — always.

## Datasource UIDs (cycle 33 LOCKED)

* `prom-primary` — Prometheus HA pair primary (V1 default)
* `prom-secondary` — Prometheus HA pair secondary
* `loki-primary` — Loki self-hosted (Q-L7F-1)
* `thanos-query` — STUBBED V1, activates V1+30d (Q-L1I-2)

Dashboards MUST reference the appropriate UID. The validator checks
that no dashboard references an unknown datasource UID.

## Cardinality discipline (cycle-6 carry-forward)

* Per-reality dashboards: ONLY `reality_id` + `shard_host` labels may
  vary per reality. Adding new per-reality labels breaks the L1.I.5
  cardinality invariant.
* Per-service dashboards: ONLY `service` + `instance` may vary.

## Drill-down pattern

Platform-level dashboard → per-service dashboard via panel link:

```json
{
  "title": "Drill into <service>",
  "url": "/d/per-service-<service>/per-service-overview?var-service=$service&var-lw_env=$lw_env",
  "targetBlank": false
}
```

## What the validator checks (cycle 33 v1)

`scripts/dashboard-validator.sh` enforces (exit 1 on violation):

1. `title` is non-empty and ends with `(cycle <N> <layer>)`.
2. `uid` is kebab-case, non-empty.
3. `tags` array includes `cycle-<N>`.
4. Every panel has a non-empty `title`.
5. Every panel `datasource.uid` is one of the LOCKED UIDs above.
6. Time range and refresh interval present.

## Change procedure

| Change | Procedure |
|---|---|
| Add new dashboard | Use `_library/TEMPLATE.json` as starting point, run validator, commit. |
| Modify standard | Update this doc + bump cycle-N tag everywhere via PR. |
| Add color | Append to palette table; update validator allow-list. |
| Add datasource UID | Update LOCKED list above; update `infra/grafana/provisioning/datasources/datasources.yaml`. |

## Linked items

* `L7.H.6/7/8/9/10` — dashboard library + STANDARDS + TEMPLATE
* `scripts/dashboard-validator.sh` — CI lint
* `Q-L7F-1` — Loki self-hosted
* `Q-L1I-1` — Prom HA federation
* `Q-L1I-2` — Thanos V1+30d activation
