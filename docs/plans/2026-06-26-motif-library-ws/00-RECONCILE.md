# Motif Library — Cross-Workstream Reconciliation (post detailed-design)

> **Date:** 2026-06-26 · After 8 parallel detailed-design passes (F0 + W1-W7). This captures the **integration seams** + the **F0 contract deltas** the parallel design surfaced. **F0 must incorporate §1 BEFORE it freezes** — these change the frozen contract. The seams in §2 are kept disjoint (one file = one owner).
> Read with: [`master-plan`](../2026-06-26-motif-library-master-plan.md) + the 8 `W*.md` / `F0-foundation.md` in this folder + spec [`§R1/§R2`](../../specs/2026-06-26-narrative-motif-library.md).

---

## §1 — F0 CONTRACT DELTAS (incorporate before F0 freezes)

Small additive schema/config changes the WSs proved they need. F0 owns `migrate.py`/`models.py`/`config.py`, so they land there.

| # | Delta | Why | Source |
|---|---|---|---|
| **D1** | **Add `motif.annotations JSONB NOT NULL DEFAULT '{}'`** | `scheme` `info_asymmetry` is a property of the **template**, not only the application. §R1.4 put `annotations` only on `motif_application`. W7's scheme seeds + W5's conformance read it on the motif. | W7-D3, W5 |
| **D2** | **Config `motif_embed_model` + `motif_embed_owner_id`** (a reserved platform-owner row) | the platform embed (R1.1.2) needs a stable owner identity — the BYOK-as-platform pattern (CLAUDE.md local-rerank precedent). | W3-MD1 |
| **D3** | **`consumed_tokens(jti TEXT PK, descriptor, user_id, consumed_at)` table + `billing_internal_url` config** | W4's Tier-W ops need a replay-prevention ledger + a real usage-billing precheck. composition-service has **no billing client** → net-new. **`jti = sha256(token)`** (the C-KIT confirm token has no `jti` claim). | W4-MD3/MD7 |
| **D4** | **Seeds embed `NULL`; lazy platform back-fill owned by W3** | platform `/internal/embed` is per-user + may be **down at boot** (the C16 "never wall boot on an optional dependency" lesson) → W7 seeds `embedding=NULL`, W3 lazily back-fills on first retrieve using the same `embedded_summary_hash` machinery. F0's `MotifRetriever` contract must tolerate a NULL-embedding row (skip + queue backfill, never 0.0-rank it as a real miss). | W7-D4 ↔ W3 |
| **D5** | **Opaque-lineage trigger: default to the no-extension fallback** `source_ref := 'lineage:'||id` unless the deploy role can `CREATE EXTENSION pgcrypto` | the motif's own id leaks nothing about the source, so HMAC is optional. | F0-§6C, W1 |
| **D6** | **System seeds use `visibility='unlisted'`** (not `private`) to satisfy the `motif_user_owned` CHECK (`owner IS NOT NULL OR visibility<>'private'`) | a both-NULL system row must be non-private; F0's CHECK + W7's seeds agree. | F0, W7 |

---

## §2 — CROSS-WS SEAMS (one engine, two entries — disjoint ownership preserved)

| Seam | Owner (file) | Callers / readers | Contract |
|---|---|---|---|
| **Bind/swap/undo engine** | **W2** `engine/motif_select.py` | W4 MCP `composition_motif_bind`; W2 HTTP `PATCH …/motif` | one engine, two entries; W4 imports, never re-implements |
| **`motif_application` writes** | **W2** (the binder writes `motif_id`+`beat_key`+`role_bindings`) | W4 (MCP read), W5 (trace join **requires** `motif_id`/`beat_key`) | W2 is the sole writer; W5's trace depends on the binder populating `beat_key` |
| **`generation_job.critic`** | shared column, **COALESCE-clobbered** | W5 (writes `motif_conformance`), W2 (must not clobber) | **every producer read-modify-writes** (`merge_conformance`, the `dismiss_violation` pattern) — a bare `{motif_conformance:…}` UPDATE **destroys** `coherence`/`violations`. **Load-bearing.** |
| **Gold seed (R2.1)** | **W5** (owns labeling + calibration) | W2 (eval-gate consumes) | one artifact, two consumers |
| **Platform-embed fn** | **W3** `engine/motif_embed.py` | W1 clone | **RESOLVED:** clone **COPIES** the source vector (valid — one platform model = one space, cheap); re-embed only if the clone **edits the summary**. W3-MD3's "re-embed-on-clone" was the old-model caution; under one-platform-model, copy is correct. |
| **FE studio-shell additive touches** | **W6** (single owner of these additive edits) | — | `CompositionPanel.tsx` (dock register), `workspace/types.ts`+`dock.ts` (slot types), `composition.json` ×4 — W6 coordinates the 1-line W2 FE wiring |
| **`test_mcp_server.py`** scope hardcode | **W4** | — | the `scope=='book'` assertion breaks when user-scope tools register → W4 updates it |

---

## §3 — Catalog / scope expansions surfaced

- **W4-MD2 — add `composition_motif_unbind`** (+ optionally `composition_motif_archive`): R2.8 lists only `_create`/`_bind` for Tier-A, but a **first** bind has no other verified reverse op, so the MCP-R2 honest-undo contract **requires** an explicit unbind. Expands the §13 catalog by 1-2 tools.
- **W1 correction:** publish/adopt need only the **count-ceiling** quota, NOT a usage-billing `$` precheck (that rides Tier-W mine/import in W4/W11). The master-plan §4-W1 B-4 phrasing is corrected to this.
- **W4 confirmation:** `_adopt` = **Tier-W confirm** (verified: glossary `book_tools.go:21` "adopt … = class C confirm-token"); the §13.1 "adopt = Tier-A" was the bug R1.6/H-6 already flagged.

---

## §4 — Disjointness verdict

Every WS owns a disjoint file set. The only shared-file touches are: F0's `migrate.py`/`models.py`/`config.py` (lands first, frozen — incorporates §1), W6's additive studio-shell edits (single-owner protocol), and W4's `test_mcp_server.py` + `actions.py` (W4 sole owner). **No two Wave-1 workstreams edit the same file** → git/worktree-parallel-safe, as designed.

**Net:** the parallel detailed-design converged — every doc consumed the F0-frozen signatures correctly, found the real integration seams, and kept ownership disjoint. The 6 F0 deltas (§1) are small + additive; fold them into F0, freeze, and Wave 1 fans out clean. **The plan is build-ready.**
