# Spec — Stale-Image / Artifact-Behind-HEAD Guard (F-LIVE-1)

> Created 2026-05-31 · Track lore-enrichment (Cluster 2) · Branch `lore-enrichment/foundation`
> Origin: F-LIVE-1 recurred 3× — `docker compose up -d` recreates a service (esp. knowledge-service)
> from a STALE local image, whose `/health` is constant-`ok` so the stale container reports healthy
> while a critical route (`/internal/knowledge/enriched-writeback`) 404s. ContextHub lesson `e16b6f02`.
> Status: **BUILT + VERIFIED 2026-05-31.** PO approved all-22 stamp via compose build.labels + advisory gate. See §7.
> Size: **XL** (cross-service). PO CLARIFY answers (2026-05-31): mechanism = **stamp + probe**;
> scope = **all services**; wiring = **live-smoke/stack-up entrypoint + workflow-gate hook** (no new CI).

## 1. Problem (live-confirmed)
- `/health` is liveness-only (constant `ok`, no DB/route check) → a stale image passes the compose healthcheck.
- A stale image silently lacks current code (e.g. C13 `internal_enrichment.py`) → 404 on the H0 path, discovered only mid-smoke.
- Recurs because compose recreates dependencies from whatever local image exists; nothing compares the deployed artifact to HEAD.

## 2. Goal
Catch "a running container is behind HEAD for its own source" **before** a live run, with a clear message, for **all** compose-built services, plus a fast contract probe of the H0-critical internal routes. Run automatically at stack-up / live-smoke and via the workflow gate.

## 3. Design

### 3a. Drift signal — two tiers (recommended realization)
The drift-check answers, per running service: *was this image built from source older than the latest commit touching that service?*

- **Tier 1 — timestamp proxy (ZERO image changes, covers ALL services immediately).**
  `docker inspect --format '{{.Created}}'` of the running container's image vs
  `git log -1 --format=%cI -- <service source paths> sdks/python sdks/...` (last commit touching the
  service or the shared SDKs it bundles). Image `.Created` **older** than the last relevant commit ⇒ **STALE**.
  Robust, no Dockerfile/compose churn — the pragmatic backbone for "all services."

- **Tier 2 — precise git-SHA stamp (optional enhancement; the PO's "build-stamp").**
  Inject `GIT_SHA` at build time and compare the running image's SHA to the latest commit touching the
  service path (`git merge-base --is-ancestor <imgSHA> HEAD` + `git diff --quiet <imgSHA> HEAD -- <paths>`).
  Precise (immune to clock skew / no-op rebuilds), but costs one stanza per build target. **Two realizations:**
  - **compose `build.labels`** (no Dockerfile edits): add `build: { labels: { "org.loreweave.git_sha": "${GIT_SHA:-unknown}" } }`
    to each service + a `scripts/build-stack.sh` that exports `GIT_SHA=$(git rev-parse HEAD)` before `docker compose build`.
  - **Dockerfile `ARG GIT_SHA` + `LABEL`** (touches each Dockerfile). More portable to non-compose builds.
  - Drift-check reads the label via `docker image inspect --format '{{ index .Config.Labels "org.loreweave.git_sha" }}'`;
    a missing label ⇒ treat as UNKNOWN→STALE (an image built before this guard).

> **Architect recommendation:** ship **Tier 1 for all services now** (zero churn, immediate full coverage) +
> **Tier 2 git-SHA via compose `build.labels`** for the enrichment-track 3 services (knowledge/glossary/
> lore-enrichment — the proven silent-404 surface), with the `build.labels` pattern documented so the
> remaining services adopt it incrementally. This honors "all services" (Tier 1) + "build-stamp" (Tier 2)
> without 22 Dockerfile edits up front. **PO: confirm, or require Tier 2 on all 22 targets now.**

### 3b. Route-contract probe (H0-critical surface)
A probe that asserts the H0/contract-critical internal routes EXIST on the running stack (a 404 = missing route = stale/broken deploy; any non-404, incl. 401/400/422, = route present):
- knowledge-service: `POST /internal/knowledge/enriched-writeback`, `enriched-promote`, `enriched-retract`
- glossary-service: `POST /internal/books/{b}/entities/{e}/enrichments`, `…/canon-content`
Probe with a deliberately-minimal body + the internal token; assert status ≠ 404 (and ≠ 5xx route-missing). Targeted, not all-routes (a generic all-route probe isn't well-defined).

### 3c. Single tool + wiring
- New `scripts/check_stack_freshness.py` (stdlib + `docker`/`git` subprocess; no service deps):
  `--probe-only` / `--drift-only` / default both; `--services a,b` filter; exit 0 = fresh+routes-present, 1 = stale/missing, 3 = docker/git unavailable (skip, non-fatal). Prints a per-service table.
- **Wiring:**
  - Live-smoke/stack-up: call it at the TOP of `live_smoke_c14_job.py` + `live_verify_t8.py` (fail fast with a clear "rebuild knowledge-service" message instead of a mid-run 404). Optionally a `scripts/` convenience wrapper.
  - **workflow-gate hook:** add a `workflow-gate.py check-stack` subcommand (advisory by default — warn, never block a commit, mirroring the live-smoke soft-warning), so the dev workflow surfaces drift.

## 4. Acceptance
- A knowledge-service container running a pre-C13 image is reported **STALE** by `check_stack_freshness.py` (Tier 1 timestamp) AND the route-probe reports `enriched-writeback` **404/missing** — both BEFORE any smoke runs.
- After `docker compose build knowledge-service && up -d`, the check reports **FRESH** + all probed routes present.
- The check covers all compose-built services (Tier 1); the enrichment-track 3 also carry a git-SHA label (Tier 2) if approved.
- Wired into both live-smoke entrypoints + a `workflow-gate.py check-stack` subcommand. No new CI.
- Non-fatal when docker/git is unavailable (exit 3) — never breaks an offline unit run.

## 6b. Known limitation (honest) — drift is an advisory heuristic
The DRIFT check answers "was the image built from a commit behind HEAD for this service?" It can **over-warn** in two benign cases, because it compares against COMMITTED state / shipped-path granularity it can't fully know:
- **build-then-commit inner loop:** you build from a dirty working tree (image HAS the code), then commit — now the image's build-SHA/timestamp predates the commit → flagged STALE though the code is in the image.
- **test/doc-only change:** a commit touches `services/<svc>/tests` or docs (not COPYed into the image) → the `services/<svc>` diff is non-empty → flagged STALE though the shipped artifact is unchanged.

Both are SAFE-direction over-warns (a rebuild is always harmless) and DRIFT is **advisory-only** (gate warns, never blocks). The **route-probe is the authoritative signal** that gates the live-smoke entrypoints — it has NO false positive (a 404 means the route genuinely isn't served). This split is deliberate: probe = hard gate (reliable), drift = soft advisory (heuristic).

## 7. Implementation (BUILT 2026-05-31)
- `scripts/check_stack_freshness.py` — drift (tier-2 git-SHA label diff → tier-1 image-`.Created` proxy) + H0 route-probe; skips non-source/pulled images; exit 0/1/3. Pure decision logic unit-tested (`scripts/test_check_stack_freshness.py`, 7 tests).
- `infra/docker-compose.yml` — `x-build-labels` anchor + `labels: *build-labels` on all 23 build blocks (git_sha + build_time from env).
- `scripts/build-stack.sh` — exports `GIT_SHA`/`BUILD_TIME` then `docker compose build`.
- Wired: `live_smoke_c14_job.py` + `live_verify_t8.py` call the probe at entry (abort→exit 3 on a missing route); `workflow-gate.py check-stack` (advisory warn, never blocks).

## 5. Out of scope / deferred
- A GitHub Actions CI workflow (no general service CI exists; net-new infra — explicitly deferred per PO).
- Behavioral-drift beyond version (a route present with old LOGIC at the same SHA) — the SHA/timestamp check covers version drift; deep behavioral contract-testing is separate.
- Auto-rebuild on detected drift (the guard REPORTS; the human/`compose build` fixes) — keeps it safe + predictable.

## 6. Open confirmations for PO (before BUILD)
1. **Tier-2 scope:** git-SHA label on the **enrichment-track 3** now (+ documented pattern to roll out), or on **all ~22 build targets** now?
2. **Tier-2 realization:** compose `build.labels` (no Dockerfile edits, compose-only) vs Dockerfile `ARG`+`LABEL` (portable, 22 edits)?
3. **workflow-gate severity:** advisory **warn** (recommended — mirrors the live-smoke soft-warning, never blocks a commit) vs **block** the commit on detected drift?
