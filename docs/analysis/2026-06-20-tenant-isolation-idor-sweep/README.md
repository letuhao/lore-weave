# Tenant-Isolation / IDOR Sweep

- **Date:** 2026-06-20
- **Status:** ✅ COMPLETE — see [`FINDINGS.md`](FINDINGS.md). **Result: 2 Critical + ~10 live High** (book-service media/audio cluster, auth `/internal/users/*` ungated, statistics `/v1/stats/*` ungated, translation settings). Architecture sound; defects are "guard not applied" + missing deny-tests.
- **Source:** [gap-analysis](../../specs/2026-06-20-platform-ai-architecture-gap-analysis.md) §11 Task 1 (P0, size XL)
- **Type:** Read-only security audit. **No code is modified.**

## Why this audit
LoreWeave is **multi-tenant** (self-hosted ≠ single-user). The tenancy invariant (System → Per-user → Per-book scope) is LOCKED in design but has **never been audited across the service fleet** — and the entire known security-bug history lives exactly here:
- 5× IDOR fixes (P0–P6 era)
- the `entity_kinds` bug — globally-unique + user-mutable shared rows
- E0 grant-mapping deny-gaps (view/edit grantees wrongly denied, or owner-only handlers never swept for grants)

This sweep checks the **system as built** against the tenancy rules.

## Method
~20 user-data-bearing services grouped into 6 batches, each audited by an independent agent hunting four known bug classes:
1. **IDOR** — handler acts on a resource id without authorizing the caller for *that specific* resource.
2. **SHARED-MUTABLE** — any authenticated user can write a System/shared row (the `entity_kinds` class).
3. **MISSING-GRANT-MAP** — owner-only checks where E0 grants should apply; missing non-owner-grantee deny-tests.
4. **MISSING-SCOPE-FILTER** — list/search/read that omits the `owner_user_id`/`book_id` filter → cross-tenant rows.

Pure infra/ops services (publisher, meta-worker, canary-controller, etc.) are confirmed NOT-APPLICABLE (system-only, no user-resource handlers).

Severity: **Critical** (cross-tenant write / data leak) · **High** (cross-tenant read) · **Medium** (weak/missing test, defense-in-depth) · **Low**.

## Output
Synthesized findings → [`FINDINGS.md`](FINDINGS.md) (written on sweep completion).
