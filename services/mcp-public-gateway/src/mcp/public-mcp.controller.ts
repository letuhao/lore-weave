import { All, Controller, Logger, Req, Res } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type { Request, Response } from 'express';
import { loadConfig } from '../config/config.js';
import { KeyResolver } from '../auth/key-resolver.js';
import { annotateBatchStepOutcomes, countToolCalls, filterListResponseText, gateRequestBody, isBatchBody, isListRequest, isWriteRequest, singleWriteConfirmToolName } from '../scope/scope-filter.js';
import { detectProposeResult, pendingApprovalResponse, proposeDivertError } from '../scope/propose-detect.js';
import { confirmActionResult, denyConfirmAction, detectConfirmActionCall, injectConfirmActionTool } from '../scope/confirm-action.js';
import { domainScope, type Domain } from '../scope/tool-policy.js';
import { RateLimiter } from '../ratelimit/rate-limiter.js';
import { makeRateLimitStoreFromEnv } from '../ratelimit/redis-store.js';
import { AuditClient } from '../audit/audit-client.js';
import { ApprovalClient } from '../approval/approval-client.js';

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
  // P4 / OD-2: divert a default key's Tier-W propose to the owner's approval queue.
  private readonly approvals = new ApprovalClient();

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
      return this.deny(res, -32001, 'unauthorized');
    }

    if (!this.cfg.internalToken) {
      this.log.error('FATAL: INTERNAL_SERVICE_TOKEN missing — cannot mint envelope');
      return this.deny(res, -32603, 'gateway misconfigured', 500);
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

    // Relay to the USER surface only — never `/mcp/admin` (PUB-9 / H-A).
    const target = `${this.cfg.aiGatewayUrl}/mcp`;
    try {
      const upstream = await fetch(target, {
        method: req.method,
        headers: outboundHeaders,
        body: hasBody ? JSON.stringify(req.body) : undefined,
      });
      let text = await upstream.text();
      // PUB-3 / H-F: filter the `tools/list` RESPONSE so the agent only ever sees the
      // tools its key may call. Only rewrite a successful list; errors pass through.
      const ok = upstream.status >= 200 && upstream.status < 300;
      // H-O: record the relay outcome (per tools/call; non-call relays are not audited).
      this.audit.record(req.body, resolved.keyId, resolved.userId, traceId, ok ? 'relayed' : 'upstream_error');

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

      const rewroteList = ok && hasBody && isListRequest(req.body);
      if (rewroteList) {
        text = filterListResponseText(text, resolved.scopes, this.log);
        // P4 slice B: advertise the synthetic confirm_action tool to a dual-flag key so the
        // agent can discover the headless self-confirm path (it is not in the federated list).
        if (resolved.allowSelfConfirm && resolved.scopes.includes('write_confirm')) {
          text = injectConfirmActionTool(text);
        }
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

      res.status(upstream.status);
      // We emit JSON when we rewrote the list or annotated a batch; otherwise echo upstream type.
      const ct = rewroteList || annotatedBatch ? 'application/json' : upstream.headers.get('content-type');
      if (ct) res.setHeader('content-type', ct);
      res.send(text);
    } catch (e) {
      this.audit.record(req.body, resolved.keyId, resolved.userId, traceId, 'upstream_error'); // H-O
      this.log.warn(`relay to ai-gateway failed: ${e}`);
      return this.deny(res, -32603, 'upstream gateway unavailable', 502);
    }
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
