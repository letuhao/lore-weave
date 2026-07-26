import { All, Controller, Logger, Req, Res } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type { Request, Response } from 'express';
import { loadConfig } from '../config/config.js';
import { KeyResolver } from '../auth/key-resolver.js';
import { annotateBatchStepOutcomes, countToolCalls, filterListResponseText, findToolsCallIdKeys, gateRequestBody, idKey, isBatchBody, isFindToolsCall, isListRequest, isToolListCall, isToolLoadCall, isWriteRequest, scopeFilterFindToolsBatch, scopeFilterFindToolsResult, scopeFilterToolListResult, scopeFilterToolLoadResult, singleToolCallErrored, singleWriteConfirmToolName, writeConfirmCallsById } from '../scope/scope-filter.js';
import { ToolActivation } from '../session/tool-activation.js';
import { makeToolActivationStoreFromEnv } from '../session/tool-activation-store.js';
import { detectProposeInItem, detectProposeResult, pendingApprovalForId, pendingApprovalResponse, proposeDivertError, proposeDivertErrorForId } from '../scope/propose-detect.js';
import type { ResolvedKey } from '../auth/key-resolver.js';
import { confirmActionResult, denyConfirmAction, detectConfirmActionCall, injectConfirmActionTool } from '../scope/confirm-action.js';
import { detectInvokeToolCall, injectInvokeToolTool, notActivatedError, requiresActivation } from '../scope/invoke-tool.js';
import { domainScope, scopeToolCount, DIRECT_LIST_TOOL_THRESHOLD, WILDCARD_SCOPE, type Domain } from '../scope/tool-policy.js';
import { rehydrateContentForLegacyClients } from '../scope/structured-content-rehydration.js';
import { RateLimiter } from '../ratelimit/rate-limiter.js';
import { makeRateLimitStoreFromEnv } from '../ratelimit/redis-store.js';
import { Idempotency } from '../idempotency/idempotency-store.js';
import { makeIdempotencyStoreFromEnv } from '../idempotency/redis-idempotency-store.js';
import { advertiseIdempotencyKeyInList, batchIdempotentItems, idempotencyInProgressError, idempotencyInProgressErrorForId, idempotencyRedisKey, idempotentWriteCallInfo, stripIdempotencyKey, stripIdempotencyKeyFromBatch } from '../idempotency/idempotency.js';
import { AuditClient } from '../audit/audit-client.js';
import { ApprovalClient } from '../approval/approval-client.js';
import { wwwAuthenticateChallenge } from '../oauth/discovery.js';

/**
 * D-PMCP-BATCH-IDEMPOTENCY plan: the result of the pre-relay pass over a JSON-RPC BATCH.
 * `relayArray` is the reduced + key-stripped body to relay; `shortCircuit` are the cached
 * (replay) / in-flight (pending) response items to merge back; `claims` are the proceed-item
 * Redis keys to cache-or-release after the relay settles.
 */
interface BatchIdemState {
  active: boolean;
  relayArray: unknown[];
  shortCircuit: unknown[];
  claims: Array<{ idKey: string; rkey: string }>;
}

/**
 * The PUBLIC MCP edge. An external agent connects here (via api-gateway-bff `/mcp`)
 * with its OWN credential in the Authorization header. The edge:
 *   1. rejects a credential supplied in the query string (H-R — would land in logs)
 *   2. authenticates the credential → a LoreWeave user (PUB-1: identity derived here,
 *      never trusted from the agent)
 *   3. STRIPS the entire inbound `x-*` namespace and mints a FRESH envelope
 *      (PUB-9 — an agent that sends X-Admin-Token / X-Internal-Token / X-User-Id
 *      must have it discarded, never forwarded)
 *   4. relays to `${aiGatewayUrl}/mcp` ONLY — there is NO route to `/mcp/admin`,
 *      and the edge holds no admin token (PUB-9 / H-A)
 *
 * MCP semantics are preserved end-to-end: the relay is transport-transparent, so
 * the external client effectively speaks to ai-gateway's spec-compliant MCP server
 * through it (H-M). ai-gateway runs stateless JSON-RPC, so a request/response relay
 * is faithful for v1.
 *
 * P0 scope: envelope hop + strip + admin isolation, read tools only. Scope filter
 * (P2), rate-limit + spend gate (P3), and write-approval (P4) layer on top.
 */
@Controller('mcp')
export class PublicMcpController {
  private readonly cfg = loadConfig();
  private readonly log = new Logger(PublicMcpController.name);
  private readonly resolver = new KeyResolver();
  // Built once (one Redis connection); null store (no REDIS_URL) → limiter disabled.
  private readonly limiter = new RateLimiter(makeRateLimitStoreFromEnv());
  // H-O: best-effort per-key call audit (fire-and-forget to auth-service).
  private readonly audit = new AuditClient();
  // H-G: edge dedup of headless write retries (one Redis connection; null → disabled).
  private readonly idempotency = new Idempotency(makeIdempotencyStoreFromEnv());
  // P4 / OD-2: divert a default key's Tier-W propose to the owner's approval queue.
  private readonly approvals = new ApprovalClient();
  // Lazy tool-loading: the per-session activated-tool set (Redis when REDIS_URL, else in-memory
  // so the state machine always works). Keyed by session_id (= key_id).
  private readonly toolActivation = new ToolActivation(makeToolActivationStoreFromEnv());

  @All()
  async handle(@Req() req: Request, @Res() res: Response): Promise<void> {
    // H-R: a key in the query string would be logged by every proxy/CDN. Refuse it.
    if (typeof req.query?.key === 'string' || typeof req.query?.token === 'string') {
      return this.deny(res, -32001, 'credential must be sent in the Authorization header, not the URL');
    }

    const bearer = parseBearer(req.header('authorization'));
    const resolved = await this.resolver.resolve(bearer);
    if (!resolved) {
      // Uniform 401 — no oracle about which check failed (flag off / bad key / no store).
      // P5/RFC 9728: point a spec-compliant MCP client at the Protected Resource Metadata
      // so it can discover the OAuth authorization server and run the auth-code flow.
      if (this.cfg.mcpResourceUrl) {
        res.setHeader('WWW-Authenticate', wwwAuthenticateChallenge(this.cfg.mcpResourceUrl));
      }
      return this.deny(res, -32001, 'unauthorized');
    }

    if (!this.cfg.internalToken) {
      this.log.error('FATAL: INTERNAL_SERVICE_TOKEN missing — cannot mint envelope');
      return this.deny(res, -32603, 'gateway misconfigured', 500);
    }

    // LAZY TOOL-LOADING v2 — `invoke_tool` unwrap. A standard MCP client caches `tools/list`
    // ONCE at connect and never re-polls, so a tool `find_tools` "activated" server-side can
    // never be CALLED directly (the client refuses to send a name it never saw listed) — only
    // `invoke_tool` (always in `tools/list`, like `find_tools`) is callable. Unwrap it into a
    // normal `tools/call` for its REAL target here, before rate-limiting/scope-gate/idempotency
    // read the body, so every downstream gate reads the genuine tool name — zero other changes
    // needed anywhere else in this file. review-impl MED fix: a malformed invoke_tool call is an
    // AUTHENTICATED request (unlike the anonymous checks above) — it must still be rate-limited
    // like any other call from this key, so the response is deferred (`malformedInvokeTool`) and
    // sent AFTER the rate-limit check below, not returned early here.
    let invokeToolTarget: string | null = null;
    let malformedInvokeTool: unknown = null;
    if (req.method !== 'GET' && req.method !== 'HEAD' && req.body !== undefined) {
      const detection = detectInvokeToolCall(req.body);
      if (detection?.kind === 'malformed') {
        malformedInvokeTool = detection.response;
      } else if (detection?.kind === 'rewrite') {
        invokeToolTarget = detection.targetName;
        req.body = detection.rewritten;
      }
    }

    // Mint our own trace id once (never trust an inbound x-trace-id) — reused for
    // the outbound envelope AND every audit row for this request (correlation).
    const traceId = randomUUID();

    // PUB-8: per-key rate limit BEFORE doing any work (shed abusive load early). A
    // write (tools/call to a write-tier tool) fails CLOSED on a store outage; a
    // read fails OPEN. The dev wildcard key still counts (it has a finite rpm).
    const hasBody = req.method !== 'GET' && req.method !== 'HEAD' && req.body !== undefined;
    const isWrite = hasBody ? isWriteRequest(req.body) : false;
    // Weight by tool-call count so a batch can't smuggle N executions past the
    // per-minute limit; a non-call request (list/initialize/single) weighs 1.
    const weight = hasBody ? Math.max(1, countToolCalls(req.body)) : 1;
    const rl = await this.limiter.check(resolved.keyId, resolved.rateLimitRpm, isWrite, weight);
    if (!rl.allowed) {
      this.audit.record(req.body, resolved.keyId, resolved.userId, traceId, 'rate_limited'); // H-O
      res.setHeader('Retry-After', String(rl.retryAfter));
      res.status(429).json({
        jsonrpc: '2.0',
        error: { code: -32029, message: 'rate limit exceeded', data: { retry_after: rl.retryAfter, limit: rl.limit } },
        id: jsonRpcId(req.body),
      });
      return;
    }

    if (malformedInvokeTool !== null) {
      this.audit.record(req.body, resolved.keyId, resolved.userId, traceId, 'tool_error');
      res.status(200).json(malformedInvokeTool);
      return;
    }

    // invoke_tool activation gate — runs AFTER rate-limiting (consistent with the scope gate's
    // own timing below: a denied call still counts against the key's budget). Skipped for the
    // wildcard (dev/smoke) key, whose find_tools calls never populate the activation store
    // (scopeFilterFindToolsResult short-circuits for it) — it already sees the FULL catalogue
    // directly in tools/list, so nothing is ever "unactivated" for it.
    if (invokeToolTarget && requiresActivation(invokeToolTarget) && !resolved.scopes.includes(WILDCARD_SCOPE)) {
      const activated = await this.toolActivation.activated(resolved.keyId);
      if (!activated.has(invokeToolTarget)) {
        // review-impl MED fix: this is NOT a scope violation (the key may well be
        // in-scope for `invokeToolTarget` — it just hasn't find_tools-discovered it
        // yet this session) — `denied_scope` would conflate a normal first-call flow
        // with a genuine scope violation in the owner-facing audit trail. The response
        // shape here is an MCP tool-result `isError` (not a JSON-RPC -32601 anti-oracle
        // deny like the scope gate/confirm_action below), matching how `tool_error` is
        // used elsewhere in this file for "a tool-level error, not a protocol denial".
        this.audit.record(req.body, resolved.keyId, resolved.userId, traceId, 'tool_error');
        res.status(200).json(notActivatedError(jsonRpcId(req.body), invokeToolTarget));
        return;
      }
    }

    // P4 slice B: confirm_action — the headless self-confirm tool. It is a SYNTHETIC edge
    // tool (not federated / not in TOOL_POLICY), so it must be handled BEFORE the scope gate
    // (which would otherwise deny it as unknown). A key with BOTH `write_confirm` AND
    // `allow_self_confirm` may execute a proposed Tier-W action by replaying its token; any
    // other key gets the SAME anti-oracle "not available" as a scope-denied tool.
    if (hasBody) {
      const ca = detectConfirmActionCall(req.body);
      if (ca) {
        // Gate: the key must hold write_confirm + allow_self_confirm AND the domain scope
        // for the action it is confirming (least-privilege — confirm_action takes a domain
        // arg, so a self-confirm key can't reach a domain it lacks; the domain confirm route
        // re-verifies the token as a backstop). Anything else → anti-oracle deny.
        const dualFlag =
          resolved.allowSelfConfirm &&
          resolved.scopes.includes('write_confirm') &&
          resolved.scopes.includes(domainScope(ca.domain as Domain));
        if (!dualFlag) {
          this.audit.record(req.body, resolved.keyId, resolved.userId, traceId, 'denied_scope');
          res.status(200).json(denyConfirmAction(req.body));
          return;
        }
        const sc = await this.approvals.selfConfirm({
          keyId: resolved.keyId,
          ownerUserId: resolved.userId,
          domain: ca.domain,
          confirmToken: ca.confirmToken,
        });
        this.audit.record(req.body, resolved.keyId, resolved.userId, traceId, sc ? 'relayed' : 'upstream_error');
        res.status(200);
        res.setHeader('content-type', 'application/json');
        res.send(JSON.stringify(confirmActionResult(req.body, sc?.status ?? 502, sc?.body ?? '{}')));
        return;
      }
    }

    // PUB-9: build the outbound header set FROM SCRATCH. We copy NOTHING from the
    // inbound x-* namespace (in particular X-Admin-Token / X-Internal-Token /
    // X-User-Id can never be smuggled through). Only transport-relevant non-x-*
    // headers (Accept, Content-Type, MCP-Protocol-Version) are carried.
    const outboundHeaders: Record<string, string> = {
      'x-internal-token': this.cfg.internalToken,
      'x-user-id': resolved.userId,
      'x-mcp-key-id': resolved.keyId,
      // A public agent has no chat conversation, but the envelope still needs a
      // session (some domains, e.g. knowledge, require X-Session-Id for working
      // memory / pending-fact scoping). We mint a STABLE session per credential —
      // session_id = key_id (a UUID) — so one public key behaves as one long-lived
      // agent session (continuity + bounded session rows), never client-supplied.
      'x-session-id': resolved.keyId,
      'x-trace-id': traceId,
      accept: req.header('accept') ?? 'application/json, text/event-stream',
      'content-type': req.header('content-type') ?? 'application/json',
    };
    // P4/Wave-C (H-K) — forward the key's per-key USD spend sub-cap so a priced
    // tool's job carries it (kit → job_meta → provider-registry reserve). Only
    // when the key HAS a cap; a null cap means "owner guardrail only".
    if (resolved.spendCapUsd != null) {
      outboundHeaders['x-mcp-spend-cap-usd'] = String(resolved.spendCapUsd);
    }
    const mcpVersion = req.header('mcp-protocol-version');
    if (mcpVersion) outboundHeaders['mcp-protocol-version'] = mcpVersion;

    // PUB-3 / H-E: scope gate the REQUEST. A `tools/call` to a tool outside the key's
    // tier∩domain scope (or an unknown tool) is denied HERE, before the relay —
    // default-deny / fail-closed. A `*` (dev) key bypasses inside the helper.
    if (hasBody) {
      const denial = gateRequestBody(req.body, resolved.scopes);
      if (denial !== null) {
        this.audit.record(req.body, resolved.keyId, resolved.userId, traceId, 'denied_scope'); // H-O
        res.status(200).json(denial); // JSON-RPC errors travel as a 200 envelope
        return;
      }
    }

    // H-G: idempotency for a SINGLE write_auto `tools/call` carrying `idempotency_key`.
    // The key is an edge-only field → strip it from the relayed body (the tool uses
    // ForbidExtra and would reject it). When the key is usable, dedup on
    // (key_id, tool, key): replay a cached response, reject a concurrent in-flight
    // retry, or claim the slot and cache the result after a successful relay.
    let relayBody: unknown = req.body;
    let idemCacheKey: string | null = null; // set iff we claimed → cache/abort post-relay
    let batchIdem: BatchIdemState | null = null; // set iff a BATCH carries idempotent-write items
    if (hasBody) {
      const idem = idempotentWriteCallInfo(req.body);
      if (idem) {
        relayBody = stripIdempotencyKey(req.body); // never leak the edge field to the tool
        if (idem.idemKey) {
          const rkey = idempotencyRedisKey(resolved.keyId, idem.toolName, idem.idemKey);
          const begin = await this.idempotency.begin(rkey);
          if (begin.kind === 'replay') {
            // The original call already ran — return its response verbatim, no re-execute.
            this.audit.record(req.body, resolved.keyId, resolved.userId, traceId, 'relayed'); // H-O
            res.status(200);
            res.setHeader('content-type', 'application/json');
            res.send(begin.text);
            return;
          }
          if (begin.kind === 'pending') {
            // A concurrent identical request holds the claim — don't double-execute.
            this.audit.record(req.body, resolved.keyId, resolved.userId, traceId, 'relayed'); // H-O
            res.status(200).json(idempotencyInProgressError(req.body));
            return;
          }
          idemCacheKey = rkey; // we won the claim → remember to cache/abort after relay
        }
      } else {
        // D-PMCP-BATCH-IDEMPOTENCY: the single classifier returns null for an array, so a
        // BATCH carrying per-item idempotency keys is handled here. Strip every key, claim
        // each usable one, and EXCLUDE replay/pending items from the relay (we must not
        // re-execute a cached/in-flight item). `active=false` → not a batch with idempotent
        // writes → relay untouched (preserves the divert/annotate batch paths verbatim).
        const plan = await this.beginBatchIdempotency(req.body, resolved.keyId);
        if (plan.active) {
          batchIdem = plan;
          relayBody = plan.relayArray; // the reduced + key-stripped array
        }
      }
    }

    // Relay to the USER surface only — never `/mcp/admin` (PUB-9 / H-A).
    const target = `${this.cfg.aiGatewayUrl}/mcp`;
    try {
      // D-PMCP-BATCH-IDEMPOTENCY: when EVERY idempotent-write item short-circuited (all
      // replay/pending), the reduced relay array is empty → skip the upstream call entirely
      // and synthesize an empty batch response that finalize merges the cached items into.
      const skipRelay = batchIdem !== null && Array.isArray(relayBody) && relayBody.length === 0;
      let upstreamStatus: number;
      let upstreamCt: string | null;
      let text: string;
      if (skipRelay) {
        upstreamStatus = 200;
        upstreamCt = 'application/json';
        text = '[]';
      } else {
        const upstream = await fetch(target, {
          method: req.method,
          headers: outboundHeaders,
          body: hasBody ? JSON.stringify(relayBody) : undefined,
        });
        text = await upstream.text();
        upstreamStatus = upstream.status;
        upstreamCt = upstream.headers.get('content-type');
      }
      // PUB-3 / H-F: filter the `tools/list` RESPONSE so the agent only ever sees the
      // tools its key may call. Only rewrite a successful list; errors pass through.
      const ok = upstreamStatus >= 200 && upstreamStatus < 300;
      // External MCP discoverability audit #9, spec-compliance follow-up — this is the
      // ONLY layer that terminates the MCP handshake with an external client we don't
      // control (ai-gateway's own Server is stateless/per-request and exposes no
      // negotiated-version getter), so it's the only place that can know whether THIS
      // caller can be trusted to read `structuredContent`. Rehydrates the compact
      // placeholder domain services now emit back into the full JSON for a client whose
      // negotiated `mcp-protocol-version` predates structuredContent (or sent none at
      // all) — see structured-content-rehydration.ts for the full spec citation + the
      // conservative-default rationale. A no-op for every request already carrying a
      // 2025-06-18+ version, or a body with no compacted placeholder to begin with.
      if (ok && hasBody) {
        text = rehydrateContentForLegacyClients(text, mcpVersion);
      }
      // H-O: record the relay outcome (per tools/call; non-call relays are not audited).
      // D-PMCP-AUDIT-DOWNSTREAM-OUTCOME: a single tools/call the edge relayed 2xx but
      // whose JSON-RPC body carried an `error` (a downstream denial / tool failure rides
      // a 200) is recorded `tool_error`, not a misleading `relayed`. Batches stay coarse
      // (their per-step truth is the response's `_meta.step_outcome`).
      const relayOutcome = !ok
        ? 'upstream_error'
        : singleToolCallErrored(req.body, text)
          ? 'tool_error'
          : 'relayed';
      this.audit.record(req.body, resolved.keyId, resolved.userId, traceId, relayOutcome);

      // D-PMCP-BATCH-IDEMPOTENCY: settle the per-item claims against the relayed response
      // (cache each successful proceed-item; release errored/missing ones) and MERGE the
      // short-circuited replay/pending items back into the array. We do this BEFORE the
      // divert/list/annotate passes so (a) we cache the RAW relayed item (never a diverted /
      // _meta-annotated one) and (b) those passes see the full, merged batch. Items match by
      // JSON-RPC id, so the merge order is irrelevant. No-op when batchIdem is null.
      if (batchIdem) {
        text = await this.finalizeBatchIdempotency(batchIdem, text, !skipRelay);
      }

      // P4 / OD-2: a DEFAULT key's (allow_self_confirm=false) single Tier-W propose returns
      // a confirm_token WITHOUT spending. Do NOT hand it to the agent — divert the action to
      // the owner's approval queue and return only {status:pending_human_approval}. A
      // self-confirm key keeps the token (slice B's confirm_action path).
      if (ok && hasBody && !resolved.allowSelfConfirm) {
        const wcTool = singleWriteConfirmToolName(req.body);
        if (wcTool) {
          const propose = detectProposeResult(text);
          if (propose) {
            const approvalId = await this.approvals.create({
              keyId: resolved.keyId,
              ownerUserId: resolved.userId,
              toolName: wcTool,
              domain: propose.domain,
              confirmToken: propose.confirmToken,
              preview: propose.preview,
              costEstimateUsd: propose.costEstimateUsd,
            });
            // Fail-closed: if the queue is unreachable we still must NOT return the token.
            const out = approvalId ? pendingApprovalResponse(req.body, approvalId) : proposeDivertError(req.body);
            res.status(200);
            res.setHeader('content-type', 'application/json');
            res.send(JSON.stringify(out));
            return;
          }
        }
      }

      // P4 / OD-2 (D-PMCP-BATCH-WCONFIRM-DIVERT): the single-message divert above only
      // covers a lone tools/call. A default key can also smuggle a write_confirm propose
      // inside a JSON-RPC BATCH — that path returned the confirm_token to the agent verbatim.
      // Divert each propose item in the batch response to the owner's queue (same as the
      // single path), stripping the token; fail-closed per item. We set `text` and FALL
      // THROUGH (not return) so a mixed batch's tools/list item still gets scope-filtered and
      // the step-outcome annotate (slice F) still runs over the rewritten, token-free array.
      // Self-confirm keys keep their tokens (slice-B confirm_action), so this is default-only.
      if (ok && hasBody && !resolved.allowSelfConfirm && isBatchBody(req.body)) {
        const diverted = await this.divertBatchProposes(req.body, text, resolved);
        if (diverted !== null) text = diverted;
      }

      // LAZY TOOL-LOADING — find_tools discovery: the agent searched the catalogue. The result
      // came from ai-gateway's FULL search, so scope-filter it (anti-oracle) + ACTIVATE the
      // in-scope matches into the session, so they appear on the next tools/list (the surface
      // grows). Best-effort: an activation blip just means the agent re-discovers. The BATCH
      // branch closes the anti-oracle hole where a find_tools smuggled inside a JSON-RPC batch
      // would otherwise relay its full-catalogue matches unfiltered (isFindToolsCall is single-only).
      if (ok && hasBody && isFindToolsCall(req.body)) {
        const { text: filtered, activatedNames } = scopeFilterFindToolsResult(text, resolved.scopes);
        text = filtered;
        await this.toolActivation.activate(resolved.keyId, activatedNames);
      } else if (ok && hasBody && isToolLoadCall(req.body)) {
        // WS-1a — tool_load: scope-filter the loaded schemas (anti-oracle) + ACTIVATE the in-scope
        // names, the deterministic analogue of the find_tools→activate path.
        const { text: filtered, activatedNames } = scopeFilterToolLoadResult(text, resolved.scopes);
        text = filtered;
        await this.toolActivation.activate(resolved.keyId, activatedNames);
      } else if (ok && hasBody && isToolListCall(req.body)) {
        // WS-1a — tool_list: scope-filter the enumeration (anti-oracle + entitlement-opacity note).
        // Listing does NOT activate (only tool_load does).
        text = scopeFilterToolListResult(text, resolved.scopes);
      } else if (ok && hasBody && isBatchBody(req.body)) {
        const ftIds = findToolsCallIdKeys(req.body);
        if (ftIds.size > 0) {
          const { text: filtered, activatedNames } = scopeFilterFindToolsBatch(text, resolved.scopes, ftIds);
          text = filtered;
          await this.toolActivation.activate(resolved.keyId, activatedNames);
        }
      }

      const rewroteList = ok && hasBody && isListRequest(req.body);
      if (rewroteList) {
        // Scope-size-adaptive exposure (2026-07-07 spec §3.3/§6/§8b.7): a small, real
        // (non-wildcard) scope skips the lazy-hide collapse entirely and gets the plain
        // scope-filtered list directly — the two-hop find_tools→invoke_tool dance exists to
        // save tokens on a LARGE scope; it's pointless overhead on a 5-tool key. Wildcard is a
        // distinct, EARLIER branch (8b.7) — its "count" would be meaningless, so `&&`
        // short-circuits scopeToolCount away for it entirely, never folding it into the size
        // compare. `activated: undefined` is what makes filterListResponseText skip the
        // collapse (scope-filter.ts's filterOneListMessage only collapses when an `activated`
        // set is supplied) — so this reuses the SAME `filterTools` scope-filter the collapsed
        // path uses, just without the session-surface intersection on top.
        const wildcard = resolved.scopes.includes(WILDCARD_SCOPE);
        const directList = !wildcard && scopeToolCount(resolved.scopes) < DIRECT_LIST_TOOL_THRESHOLD;
        // The SESSION SURFACE: collapse the scope-filtered list to find_tools + the tools the
        // agent has activated this session (lazy tool-loading). session_id = key_id. Skipped
        // (never read from the store) on the direct-list path — nothing to intersect against.
        const activated = directList ? undefined : await this.toolActivation.activated(resolved.keyId);
        text = filterListResponseText(text, resolved.scopes, this.log, activated);
        // H-G: advertise the optional `idempotency_key` arg on write_auto tools so the
        // agent can discover the retry-dedup path (edge-only; stripped before relay).
        text = advertiseIdempotencyKeyInList(text);
        // P4 slice B: advertise the synthetic confirm_action tool to a dual-flag key so the
        // agent can discover the headless self-confirm path (it is not in the federated list).
        if (resolved.allowSelfConfirm && resolved.scopes.includes('write_confirm')) {
          text = injectConfirmActionTool(text);
        }
        // LAZY TOOL-LOADING v2 — every key gets invoke_tool (the execution facade that makes an
        // activated tool actually callable) + the edge-specific find_tools description pointing
        // at it. Unconditional, unlike confirm_action above (which is dual-flag-gated) — every
        // public key needs a way to call whatever find_tools activates, regardless of scopes.
        text = injectInvokeToolTool(text);
      }

      // P4 slice F (H17): multi-step partial-failure honesty. For a successfully-relayed
      // JSON-RPC BATCH, annotate each response item with its `_meta.step_outcome` so the agent
      // sees which steps landed (vs which errored upstream / the edge denied) — WITHOUT
      // reshaping the response: it stays a bare JSON-RPC array (H-M transport-transparency),
      // each item just gains an additive, ignorable `_meta` field. ADDITIVE — a single request
      // and a non-batch/SSE upstream body pass through byte-for-byte (annotateBatchStepOutcomes
      // is a no-op there). A batch-level failure (rate-limit / upstream-down) returned earlier
      // as a single error envelope, so it never reaches here. The confirm_action +
      // propose-divert paths above are single-message-only and have already returned.
      let annotatedBatch = false;
      if (ok && hasBody && !rewroteList && isBatchBody(req.body)) {
        const enriched = annotateBatchStepOutcomes(req.body, resolved.scopes, text);
        if (enriched !== text) {
          text = enriched;
          annotatedBatch = true;
        }
      }

      // H-G: cache a SUCCESSFUL idempotent write's response for replay; release the
      // claim on any failure (upstream error / tool_error) so a retry re-attempts —
      // we never cache an error. `text` is the unmodified upstream body here (the
      // divert/list/annotate paths don't run for a single write_auto call).
      if (idemCacheKey) {
        if (relayOutcome === 'relayed') await this.idempotency.complete(idemCacheKey, text);
        else await this.idempotency.abort(idemCacheKey);
      }

      res.status(upstreamStatus);
      // We emit JSON when we rewrote the list, annotated a batch, or merged a batch-idempotency
      // response (finalize always produces a JSON array); otherwise echo the upstream type.
      const ct = rewroteList || annotatedBatch || batchIdem ? 'application/json' : upstreamCt;
      if (ct) res.setHeader('content-type', ct);
      res.send(text);
    } catch (e) {
      // Release any idempotency claim so the agent's retry isn't stuck "pending" — both the
      // single-message claim and every per-item batch claim we reserved before the relay threw.
      if (idemCacheKey) await this.idempotency.abort(idemCacheKey);
      if (batchIdem) for (const c of batchIdem.claims) await this.idempotency.abort(c.rkey);
      this.audit.record(req.body, resolved.keyId, resolved.userId, traceId, 'upstream_error'); // H-O
      this.log.warn(`relay to ai-gateway failed: ${e}`);
      return this.deny(res, -32603, 'upstream gateway unavailable', 502);
    }
  }

  /**
   * D-PMCP-BATCH-IDEMPOTENCY — pre-relay planning for a JSON-RPC BATCH. For each `write_auto`
   * item carrying an `idempotency_key`:
   *   - strip the edge-only key from EVERY item (so `ForbidExtra` never sees it),
   *   - `begin()` each usable key: a `replay` (cached) or `pending` (in-flight) item is recorded
   *     as a short-circuit response AND EXCLUDED from the relay (we must not re-execute it); a
   *     `proceed` item stays in the relay array and is remembered as a claim to settle after.
   * `active=false` (no idempotent-write item / not a batch) tells the caller to relay untouched —
   * which keeps the existing divert/annotate batch behaviour byte-for-byte for non-idempotent batches.
   */
  private async beginBatchIdempotency(body: unknown, keyId: string): Promise<BatchIdemState> {
    const items = batchIdempotentItems(body);
    if (items.length === 0) return { active: false, relayArray: [], shortCircuit: [], claims: [] };
    const stripped = stripIdempotencyKeyFromBatch(body) as unknown[];
    const excluded = new Set<string>(); // idKey of items removed from the relay (replay/pending)
    const shortCircuit: unknown[] = [];
    const claims: Array<{ idKey: string; rkey: string }> = [];
    for (const it of items) {
      if (it.idemKey == null) continue; // unusable key → stripped only, relays normally (no dedup)
      const rkey = idempotencyRedisKey(keyId, it.toolName, it.idemKey);
      const begin = await this.idempotency.begin(rkey);
      if (begin.kind === 'replay') {
        excluded.add(idKey(it.id));
        shortCircuit.push(this.parseReplayItem(begin.text, it.id));
      } else if (begin.kind === 'pending') {
        excluded.add(idKey(it.id));
        shortCircuit.push(idempotencyInProgressErrorForId(it.id));
      } else {
        claims.push({ idKey: idKey(it.id), rkey });
      }
    }
    const relayArray = stripped.filter((m) => !excluded.has(idKey((m as { id?: unknown })?.id ?? null)));
    return { active: true, relayArray, shortCircuit, claims };
  }

  /**
   * D-PMCP-BATCH-IDEMPOTENCY — post-relay settlement + merge. Cache each proceed-item claim from
   * the relayed response (release errored/missing ones so a retry re-executes), then append the
   * short-circuited replay/pending items. Returns the merged response array as JSON text. If the
   * upstream body isn't a parseable JSON array (SSE / a single error envelope) we can't match
   * per-id, so we release all claims (retry-safe) and pass the upstream text through unchanged.
   */
  private async finalizeBatchIdempotency(state: BatchIdemState, upstreamText: string, relayed: boolean): Promise<string> {
    let relayedItems: unknown[] = [];
    if (relayed) {
      let parsed: unknown;
      try {
        parsed = JSON.parse(upstreamText);
      } catch {
        for (const c of state.claims) await this.idempotency.abort(c.rkey);
        return upstreamText; // can't safely merge a non-JSON body
      }
      if (!Array.isArray(parsed)) {
        for (const c of state.claims) await this.idempotency.abort(c.rkey);
        return upstreamText; // a single error envelope (e.g. batch-level reject) — don't reshape
      }
      relayedItems = parsed;
      const byId = new Map<string, unknown>();
      for (const item of relayedItems) {
        if (item && typeof item === 'object') byId.set(idKey((item as { id?: unknown }).id), item);
      }
      for (const c of state.claims) {
        const item = byId.get(c.idKey);
        // Cache only a clean success — an errored or missing item must stay retryable (never cached).
        if (item && typeof item === 'object' && (item as { error?: unknown }).error == null) {
          await this.idempotency.complete(c.rkey, JSON.stringify(item));
        } else {
          await this.idempotency.abort(c.rkey);
        }
      }
    }
    return JSON.stringify([...relayedItems, ...state.shortCircuit]);
  }

  /** Parse a cached replay item back to an object; defensively wrap a non-object cache value in a
   *  minimal JSON-RPC result under the request id (a stored value is always a response object, so
   *  this only guards corruption). */
  private parseReplayItem(text: string, id: unknown): unknown {
    try {
      const obj = JSON.parse(text);
      if (obj && typeof obj === 'object') return obj;
    } catch {
      /* fall through to the defensive wrapper */
    }
    return { jsonrpc: '2.0', id: id ?? null, result: { isError: false } };
  }

  /**
   * D-PMCP-BATCH-WCONFIRM-DIVERT: rewrite a default key's relayed BATCH response, diverting
   * every write_confirm propose item to the owner's approval queue and stripping its
   * confirm_token. Returns the rewritten JSON text iff at least one item was diverted; null
   * when there is nothing to divert (no write_confirm step, not a parseable batch array, or
   * no propose found) so the caller falls through to the normal slice-F annotate path.
   *
   * Mirrors the single-message divert: an item is diverted iff its id matches a write_confirm
   * `tools/call` request step AND its result carries a routable propose. Fail-closed per item
   * — a queue failure yields a token-free `isError` result, never the token. The caller falls
   * through to the existing list-filter + slice-F annotate over this returned, token-free text.
   */
  private async divertBatchProposes(reqBody: unknown, upstreamText: string, resolved: ResolvedKey): Promise<string | null> {
    const wcById = writeConfirmCallsById(reqBody);
    if (wcById.size === 0) return null; // no write_confirm step in the batch → nothing to divert
    let parsed: unknown;
    try {
      parsed = JSON.parse(upstreamText);
    } catch {
      return null; // not JSON (SSE / unexpected) — can't safely rewrite; let it pass through
    }
    if (!Array.isArray(parsed)) return null; // a batch request should yield an array; if not, pass through

    let diverted = false;
    for (let i = 0; i < parsed.length; i++) {
      const item = parsed[i];
      if (!item || typeof item !== 'object') continue;
      const toolName = wcById.get(idKey((item as { id?: unknown }).id));
      if (!toolName) continue; // this item is not a write_confirm step
      const propose = detectProposeInItem(item);
      if (!propose) continue; // relayed result with no routable token — nothing to strip
      const id = (item as { id?: unknown }).id;
      const approvalId = await this.approvals.create({
        keyId: resolved.keyId,
        ownerUserId: resolved.userId,
        toolName,
        domain: propose.domain,
        confirmToken: propose.confirmToken,
        preview: propose.preview,
        costEstimateUsd: propose.costEstimateUsd,
      });
      // Fail-closed: even if the queue is unreachable we must NOT return the token.
      parsed[i] = approvalId ? pendingApprovalForId(id, approvalId) : proposeDivertErrorForId(id);
      diverted = true;
    }
    if (!diverted) return null; // tokens present but none routable/matched → leave to normal path

    // Return the token-free array; the caller falls through to list-filter (mixed batch) +
    // the slice-F step-outcome annotate. Diverted items carry no `error`, so they read as
    // `relayed` there (the propose DID run; only the token was withheld) — honest reporting.
    return JSON.stringify(parsed);
  }

  private deny(res: Response, code: number, message: string, status = 401): void {
    res.status(status).json({ jsonrpc: '2.0', error: { code, message }, id: null });
  }
}

/** Best-effort JSON-RPC id for an error envelope (null for a batch / no id). */
function jsonRpcId(body: unknown): unknown {
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    return (body as { id?: unknown }).id ?? null;
  }
  return null;
}

/** Extract the bearer token from an `Authorization: Bearer <token>` header. */
export function parseBearer(header: string | undefined): string | undefined {
  if (!header) return undefined;
  const m = /^Bearer\s+(.+)$/i.exec(header.trim());
  return m ? m[1].trim() : undefined;
}
