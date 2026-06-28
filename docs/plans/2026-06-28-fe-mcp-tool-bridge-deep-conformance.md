# Plan — FE→MCP-tool bridge + deep arc-conformance model-picker (`D-W10-ARC-CONFORMANCE-DEEP-FE`)

**Date:** 2026-06-28 · **Branch:** `feat/narrative-pattern-library` · **Size:** XL (4 services, new cross-service contract + auth surface)

## Problem

The deep arc-conformance vertical is backend-complete (deep job + entailment judge); the only missing
piece is the FE that triggers it. That FE needs a **Tier-W propose** mechanism (mint a cost-gated
confirm token) which does not exist for the FE. Verified against code:

- Composition's propose tools (`composition_conformance_run`, `composition_motif_adopt`,
  `composition_motif_mine`, `composition_arc_import_analyze`) are **MCP tools** that MINT the confirm
  token. There is **no HTTP `/actions/{op}/estimate`** route.
- The FE's `motif/api.ts` POSTs to `/actions/{op}/estimate` + `/actions/{op}/confirm` (token in body) —
  **matches no backend route** (real confirm is `POST /actions/confirm?token=`). The whole FE motif
  Tier-W layer is non-functional scaffolding.
- Composition's `/actions/confirm` is **internal-token gated** (`X-Internal-Token` + `X-User-Id`), so it
  is **not FE-reachable** through the BFF (a pure prefix proxy that forwards only the JWT). Contrast
  glossary, whose `/actions/confirm` is **JWT-authed** (`requireUserID`) — the established FE-reachable
  confirm pattern.
- The ai-gateway `/mcp` face is SO-1 (internal-token) gated; the FE (user JWT) cannot reach it directly,
  and no FE→single-MCP-tool path exists.

**Decision (user-chosen):** build a **generic FE→MCP-tool bridge** — reusable for all FE Tier-W ops and
maximally MCP-first-compliant — rather than a per-op REST `/estimate` endpoint.

## Architecture (propose → confirm → poll)

```
PROPOSE  FE ──POST /v1/ai/tools/execute {tool, args}──► api-gateway-bff (validate JWT → userId,
                                                          FE-tool allowlist)
            bff ──POST /internal/tools/execute (X-Internal-Token + X-User-Id)──► ai-gateway
              ai-gateway ──federation.executeTool(tool, args, envelope)──► composition /mcp
            ◄── {confirm_token, descriptor, estimate{estimated_usd,…}} ───────────────────────
CONFIRM  FE ──POST /v1/composition/actions/confirm?token=X  (Authorization: Bearer)──► composition
            ◄── {outcome:"action_accepted", job_id, poll} ── (composition confirm now JWT-authed)
POLL     FE ──GET /v1/composition/jobs/{job_id} (Bearer)──► composition  ◄── job.result (deep report)
```

The bridge handles **propose** (and **poll** for MCP-only poll tools); **confirm** stays the existing
HTTP write route, made JWT-authed to mirror glossary. Poll reuses the existing JWT `GET /jobs/{id}`.

## Milestones

- **M1 — ai-gateway `POST /internal/tools/execute`** — new `ToolsController` (SO-1 gate, mirrors
  `GroundingController`; injects `FederationService`). Body `{tool, args, meta?}`; envelope from
  `X-User-Id`/`X-Project-Id`/`X-Trace-Id`. `federation.executeTool` → unwrap `CallToolResult`
  (`structuredContent ?? JSON.parse(content[0].text)`); `isError` → 400 `{error}`; unknown tool → 404.
  Register in `AppModule`. Vitest.

- **M2 — BFF `POST /v1/ai/tools/execute`** — new `ToolsController` + `ToolsModule`. Validate Bearer JWT
  (`JWT_SECRET`) → `userId` (mirror `notifications.controller`); enforce an **FE-tool allowlist**
  (propose/poll only — never destructive/confirm tools); forward `{tool, args}` to
  `${AI_GATEWAY_URL}/internal/tools/execute` with `X-Internal-Token` + `X-User-Id` + `X-Project-Id`
  (from `args.project_id`) + `X-Trace-Id`. New env `AI_GATEWAY_URL` + `INTERNAL_SERVICE_TOKEN`
  (main.ts `requireEnv` + docker-compose). Jest.

- **M3 — composition `/actions/confirm` + `/preview` accept a Bearer JWT** — when a valid JWT is present,
  `envelope_user = jwt.sub` (skip the internal-token requirement); else keep the existing
  `X-Internal-Token` + `X-User-Id` service path. Token's `u` re-checked against `envelope_user`
  regardless (INV-9). pytest (JWT path, internal path, identity mismatch, missing-both).

- **M4 — FE generic `mcpExecute` client + rewire propose** — `mcpExecute(tool, args, token)` → POST
  `/v1/ai/tools/execute`. Rewire `motif/api.ts` `conformanceRun*` + `adopt*`: propose via `mcpExecute`
  (map `estimate{estimated_usd}` → `CostEstimate{confirm_token, est_usd, est_tokens, quota_remaining}`);
  confirm via `POST /actions/confirm?token=` (Bearer); poll via existing `getJob`. Vitest.

- **M5 — FE deep arc-conformance model-picker** — `ArcConformancePanel` gains a `ModelRolePicker`
  (`capability='chat'`, reuse `features/campaigns`) + a "Run deep conformance" action: propose
  `composition_conformance_run` (`scope='arc'`, `arc_template_id`, `model_ref`) → confirm → poll
  `composition_get_mine_job` (via bridge) / `getJob` → render the deep report (`.deep` incl.
  `entailment_verified`/`entailed`). Thread `effectiveModelRef` CompositionPanel → MotifLibraryView →
  ArcTemplateLibraryView → ArcConformancePanel. Vitest + tsc.

- **M6 — VERIFY** — unit suites all four services; provider-gate; live smoke the
  bridge→propose→confirm→poll on the deployed stack (or track `D-…-LIVE-SMOKE` with reason).

## Security notes

- The FE never supplies its own identity: `X-User-Id` is derived server-side from the validated JWT in
  the BFF (SEC-1). The ai-gateway endpoint trusts `X-User-Id` only behind the SO-1 internal-token gate
  (same trust level as `/mcp`).
- The BFF **allowlist** prevents the FE from invoking destructive/confirm/admin tools via the bridge —
  only the safe propose/poll tools are reachable. Confirm remains a separate, signed-token-gated write.
- Propose-time gates (EDIT grant, arc visibility) run inside the MCP tool; confirm re-checks ownership +
  EDIT + the signed payload (the LLM/clients cannot alter the target between propose and confirm).
