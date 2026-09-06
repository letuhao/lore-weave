# Changelog

All notable changes to LoreWeave are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versioning
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) — with the pre-1.0 caveat
SemVer itself states in [item 4](https://semver.org/spec/v2.0.0.html#spec-item-4): while the
major version is `0`, anything may change at any time, and a MINOR bump (`0.x.0`) can carry a
breaking change. `0.1.0` is the first tagged release; nothing before it is versioned.

**This file is the source of truth for what shipped in each release, not a summary written
after the fact.** `scripts/changelog-gate.py` enforces the one invariant that makes that true:
a release cannot be cut (`.github/workflows/oss-release.yml` fails closed) unless the version
being tagged has a matching `## [x.y.z]` section here with real content. The `/oss-publish`
skill is what moves entries from `[Unreleased]` into a dated version section when a release is
cut — see `docs/standards/versioning-and-releases.md` for the full policy (bump rules,
pre-release identifiers, what "release" vs "pre-release" means for this repo, artifact scope).

## [Unreleased]

### Added

### Changed

### Fixed

### Removed

### Security

## [0.1.0] - 2026-09-06

First tagged release: the novel-writing platform, published as 33 versioned Docker images
derived directly from `infra/docker-compose.yml`'s service list. `docker compose up` with no
`--profile` flag starts exactly this scope.

### Added

- **Novel Writing Studio** — books, chapters, sharing and a public catalog; composition planning
  with an AI co-writer; glossary/canon entity tracking; a knowledge base with RAG-backed search,
  a wiki view and Q&A; per-book translation coverage tracking; automated lore enrichment and a
  correction-learning loop; an admin CMS.
- **AI Provider & Cost Control** — a bring-your-own-key provider/model registry, a unified
  gateway for LLM/embedding/rerank/image/audio calls, usage metering with tier- and
  credit-based billing, and an MCP tool registry.
- **Chat, Assistant & Roleplay** — agent-runtime chat sessions, a roleplay mode with pre-seeded
  interview-style scripts, a scheduler, and notifications.
- **Content Extras** — video generation, and campaign / Auto-Draft Factory tooling.
- **Public/External** — `mcp-public-gateway`, letting external MCP-speaking agents reach the
  platform's own tools.
- **Platform plumbing** — the `worker-ai` extraction pipeline, the `worker-infra` outbox relay,
  a jobs service and a statistics service.
- **OSS release infrastructure** — this changelog, `scripts/changelog-gate.py` (no tagged
  release without a matching, non-empty section here), `.github/workflows/oss-release.yml`,
  the `/oss-publish` skill, and `docs/standards/versioning-and-releases.md`. Release targets are
  derived from `docker-compose.yml`'s own service list rather than a hand-kept one, so a new
  service is in scope for the next release the moment it's added to compose — not the moment
  someone remembers to also update a release list.

### Changed

- `docker compose up` with no `--profile` flag now starts only the 33 novel-writing-platform
  services. The MMO/game track (`game-server`, `world-service`, `tilemap-service`, `publisher`,
  `orphan-scanner`, `meta-bridge`, the game frontend) moved behind `--profile game` /
  `--profile full` — still in the compose file for anyone who wants it, no longer running, or
  published as a default-scope image, by default.

### Fixed

- `rabbitmq`'s and `knowledge-service`'s Docker healthchecks now tolerate a genuinely cold
  volume — `knowledge-service`'s also accounts for its own 4-service startup chain (postgres,
  redis, glossary-service, neo4j). A first `docker compose up` on a fresh volume no longer
  intermittently reports either as unhealthy before it has actually finished starting.

### Security

- `game-server` (the opt-in `--profile game` / `--profile full` track) refused to start under
  `NODE_ENV=production` whenever `LW_WS_REDIS_URL` was unset, because that condition meant
  WebSocket ticket validation was off and connections would silently fall back to a static
  `dev_token` on a public-facing boundary. `docker-compose.yml` now wires `LW_WS_REDIS_URL` for
  both the ticket issuer (`api-gateway-bff`) and the redeemer (`game-server`) by default, so
  ticket-based auth is on out of the box for anyone who opts into the game track, rather than
  requiring an operator to notice and set it themselves. Note: nothing in v0.1.0's default
  novel-writing-platform scope currently issues or redeems a WS ticket — the endpoint
  (`/v1/ws/ticket`) is live and correctly wired, but dormant there; this fix matters only to
  `--profile game`/`--profile full` deployments today.
- MinIO's own root credentials, and 6 of 9 services' MinIO client credentials, were hardcoded
  literals in `docker-compose.yml` with **no override path at all** — setting an env var would
  have done nothing. All of them now read `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` consistently
  (server and every client together, so one env-var pair rotates the credential everywhere),
  and both are documented in `infra/.env.example` alongside 6 other secrets
  (`INTERNAL_SERVICE_TOKEN`, `ADMIN_TOKEN_ISSUER_SECRET`, `ADMIN_AUDIT_HMAC_KEY`,
  `CONFIRM_TOKEN_SIGNING_SECRET`, `AGENT_REGISTRY_VAULT_KEY`, `LLM_PAYLOAD_ENCRYPTION_KEY`)
  that already had a mechanical override path but weren't listed there, so a deployer had no
  signal they existed.

<!--
  Entries go under the section matching their kind, newest first within a section. A line
  should name the user-visible effect, not the implementation: "chapter drag-and-drop no longer
  loses unsaved edits" reads as a changelog; "fix race in useChapterOrder debounce" reads as a
  commit message these two are not obligated to look the same. Link a PR/issue where one exists.

  Dependency-bump PRs (dependabot) are exempt from adding their own entry per PR — that would be
  pure noise across dozens of routine bumps. They land in the release's own entry (usually under
  Changed, or Security when the bump closes a CVE) written once, at cut time, by whoever runs
  `/oss-publish`, summarizing what actually moved rather than listing every PR number.
-->
