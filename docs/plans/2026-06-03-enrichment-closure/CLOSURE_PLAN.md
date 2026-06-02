# Enrichment Feature — Closure Plan (2026-06-03)

> Branch `lore-enrichment/foundation`. Goal: bring the enrichment feature to **closure** —
> finish the GUI so users can *run* enrichment (not just view it), then test the feature
> end-to-end. Driven autonomously; the human is away and will review decisions async.
>
> **Operating mode (human-delegated, recorded):** the user asked me to complete this
> "without instruction", said they will not answer questions or give confirmations, and
> put me in bypass-permissions mode. So: I make every call myself with a sensible default,
> record it in [DECISIONS.md](DECISIONS.md), and **skip + document** anything blocked in
> [SKIPS_AND_BLOCKERS.md](SKIPS_AND_BLOCKERS.md) for later review. The mandatory POST-REVIEW
> human checkpoint is converted to a written decision record per slice (flagged each time).

## The three gaps (user-stated, confirmed against code)

1. **GUI tests** — `features/enrichment/` has **zero** automated vitest tests (the prior
   "smoke test" was a one-off live Playwright e2e). Need a full suite measured against the
   draft mockups (`design-drafts/enrichment-review.html`, `enrichment-gaps-sources.html`,
   `enrichment-ui-architecture.md`).
2. **GUI can't *initiate* enrichment.** The API layer (`api.ts`) already has every write
   method (`detectGaps`, `autoEnrich`, `registerSource`, `ingestSource`, `resumeJob`,
   `approve/reject/edit/promote/retract`). The gap is the **UI controls/forms** that drive
   them. Phase 0 audit pins down functional vs partial vs read-only vs missing per action.
3. **Other enrichment features untested** — backend features (`gaps/jobs/sources/proposals/eval/templates`)
   are largely live-smoked via curl, not covered by automated tests nor exercised via the GUI.

## Phases

| Phase | What | Output | Status |
|---|---|---|---|
| 0 | Audit: write-wiring · draft-parity · FE test cov · BE test cov (parallel workflow) | [AUDIT.md](AUDIT.md) | ✅ done |
| 1a | Functional GUI: ingest-source · retract · auto-enrich cost-cap+top_k · reject-reason + i18n×4 | FE diff (tsc clean) | ✅ done |
| 1b | Parity GUI: ProposalCard enrich · technique filter · live H0 banner · author-only · error-state · dim count + i18n×4 | FE diff (tsc clean) | ✅ done |
| 2 | Full FE vitest suite vs the drafts | **20 files / 149 tests GREEN** (was 0) | ✅ done |
| 3 | Backend HTTP-handler tests (jobs lifecycle, eval-gate fail-closed, single-read IDOR, auto-enrich cost-cap) | **+35 tests, 614 pass / 30 skip** | ✅ done |
| 4 | Live e2e (read-smoke + retract↔promote write-cycle); browser layer deferred | [E2E_RESULTS.md](E2E_RESULTS.md) | ✅ done (browser deferred S7) |
| 5 | Closure: docs, deferreds, SESSION_HANDOFF, commit+push | commits `2ba5050a` + this | ✅ done |

**Commits:** `2ba5050a` (phases 1–3: GUI + FE/BE tests, pushed) · closure-docs commit (phase 4–5).
**Net result:** the 2 functional gaps (ingest, retract) + 2 partials (cost-cap, reject-reason) closed; high-value parity gaps closed; FE 0→149 tests, BE +35; retract↔promote proven live. Backlog → LOW residuals (S1–S7) all documented.

## Done bar (closure definition)

- (a) every backend-supported enrichment action reachable + functional in the GUI;
- (b) full FE vitest suite matching the drafts, green;
- (c) every backend enrichment feature has ≥1 automated test OR a documented live-smoke/skip;
- (d) one full browser e2e of the create→promote loop (or documented skip);
- (e) backlog drained or deferred-with-doc;
- (f) closure summary + decisions docs written;
- (g) committed + pushed to `lore-enrichment/foundation`.

## Guardrails

- No PR to `main`, no merges, no destructive ops — stop + document instead.
- Don't touch the shared `mmo-rpg` branch or daemon state beyond rebuilding our own images.
- No hardcoded model names (resolve from provider-registry). Server is source of truth (no localStorage for user data).
- Not legal advice — the ④ promote gate is a reputational/IP-safety layer; release needs IP counsel.

## Known environmental risks (may force documented skips)

- **provider-registry image clobber** — shared Docker daemon; the other agent's branch rebuilds
  `infra-provider-registry-service:latest` from a pre-`0bf049cd` state → embed double-`/v1` → 502.
  Mitigation: `docker compose build --no-cache provider-registry-service` + freshness pre-flight.
- **LM Studio JIT eviction** — loading the 35B gen model evicts bge-m3 → multi-gap jobs hit
  "No models loaded" on the post-gen embed; single-gap completes.
