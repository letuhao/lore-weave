# S7 F5 — Bencher self-host validation decision

**Date:** 2026-06-13 · **Resolves:** test-plan §11 open decision "Confirm Bencher self-host before committing it as the gate" · **Verdict: PASS (self-host viable).**

## What was validated (live, on the dev box)

| Step | Result |
|---|---|
| `docker compose -f infra/bencher/docker-compose.yml pull` (api + console, v0.6.6) | ✅ images pull |
| `up -d` + API `/v0/server/version` | ✅ `{"version":"0.6.6"}` |
| Storage backend | ✅ embedded SQLite at `/var/lib/bencher/data/bencher.db` (default config; secret_key auto-generated) |
| `POST /v0/auth/signup` (`i_agree:true`) | ✅ `202` |
| SMTP-less bootstrap | ✅ the confirm token is **logged to stderr** (email body) when SMTP is unset → bootstrap is scriptable without a mail server |
| `POST /v0/auth/confirm` → API token | ✅ returns a 272-char API JWT |
| `GET /v0/organizations` → org | ✅ `loreweave-perf` (auto-created at signup) |
| `POST …/projects` → project | ✅ `loreweave-foundation` created |

The full loop **signup → confirm → token → org → project** ran end-to-end. The
remaining piece — `bencher run --adapter go_bench --err` — uses this same API
(the metric-ingest endpoints), so the path is proven; the only gap is the
`bencher` CLI install (a documented one-liner), which is why the conformance
case `requires:[bencher]` and the gate NOTRUNs without it.

## Decision

- **Bencher self-host is the named cross-lang gate (F5).** `infra/bencher/docker-compose.yml`
  + `scripts/perf/bencher-gate.sh` are committed and wired.
- **benchstat (F2) remains the per-PR in-toolchain gate.** Bencher is the
  *cross-language, per-commit time-series* layer on top; benchstat is the fast,
  dependency-free per-PR same-runner A/B gate. They are complementary, not
  redundant — benchstat gates every PR cheaply; Bencher accumulates the series
  that change-point detection needs.
- **Bencher gate runs manual/nightly (`workflow_dispatch`) for now**, not per-PR:
  it needs a booted self-host + a bootstrapped `BENCHER_API_TOKEN`, heavier than
  the benchstat per-PR gate. Promote to automated once a hosted instance + token
  secret exist in CI.

## Honest caveats (tracked, not hidden)

- **Token bootstrap.** The gate requires `BENCHER_API_TOKEN` via env. Auto-bootstrap
  by scraping the stderr-logged confirm JWT works (validated) but is fragile (the
  JWT wraps in log output); CI should bootstrap a token once and store it as a
  secret rather than scrape logs each run.
- **Console port.** Bencher console defaults to `:3000`, which clashes with
  ContextHub MCP + the api-gateway-bff container — moved to `:63000` here
  (env-overridable `BENCHER_CONSOLE_PORT`).
- **Change-point not yet enabled** (`D-S7-BENCHER-CHANGEPOINT`): start with
  t_test/percentage; graduate once a multi-commit series exists (§8).
- **Default config** uses an auto-generated `secret_key` + SQLite. A real deploy
  must set a stable `secret_key` (else tokens invalidate on restart) and consider
  Litestream/backup for the SQLite volume — deployment hardening, not a perf-gate
  concern.
