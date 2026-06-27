import { Logger } from '@nestjs/common';
import { loadConfig } from '../config/config.js';

/** The wire shape the auth-service approval-create ingest accepts (P4 / OD-2). */
export interface ApprovalCreateInput {
  keyId: string;
  ownerUserId: string;
  toolName: string;
  domain: string;
  confirmToken: string;
  preview: unknown;
  costEstimateUsd: number | null;
}

/**
 * Diverts a default key's Tier-W propose to the owner's human-approval queue
 * (auth-service `POST /internal/mcp-keys/approvals`). UNLIKE the audit client this is
 * AWAITED and load-bearing: the edge needs the returned `approval_id` to hand to the
 * agent, and must fail CLOSED (never leak the confirm token) when the queue is
 * unreachable. Returns the approval id on success, or null on any failure.
 */
export class ApprovalClient {
  private readonly cfg = loadConfig();
  private readonly log = new Logger(ApprovalClient.name);

  async create(input: ApprovalCreateInput): Promise<string | null> {
    if (!this.cfg.internalToken) {
      this.log.error('cannot create approval: INTERNAL_SERVICE_TOKEN unset');
      return null;
    }
    try {
      const res = await fetch(`${this.cfg.authServiceUrl}/internal/mcp-keys/approvals`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-internal-token': this.cfg.internalToken },
        body: JSON.stringify({
          key_id: input.keyId,
          owner_user_id: input.ownerUserId,
          tool_name: input.toolName,
          domain: input.domain,
          confirm_token: input.confirmToken,
          preview: input.preview,
          cost_estimate_usd: input.costEstimateUsd,
        }),
        // Bound the call — a hung auth-service must fail the divert (fail-closed), not
        // hang the agent's request indefinitely.
        signal: AbortSignal.timeout(5000),
      });
      // Check the status range (not res.ok) — consistent with KeyResolver and robust
      // to a 201 Created from the auth-service insert.
      if (res.status < 200 || res.status >= 300) {
        this.log.warn(`approval create non-OK: ${res.status}`);
        return null;
      }
      const body = (await res.json()) as { approval_id?: unknown };
      return typeof body.approval_id === 'string' ? body.approval_id : null;
    } catch (e) {
      this.log.warn(`approval create failed: ${e}`);
      return null;
    }
  }

  /**
   * Self-confirm replay (P4 slice B): forward an `allow_self_confirm` key's confirm_action to
   * auth-service `POST /internal/mcp-keys/confirm`, which replays the token to the owning
   * domain tagged with X-Mcp-Key-Id. Returns the auth {status, body} for the edge to shape
   * into an MCP result, or null on a transport failure. The timeout is generous — a priced
   * confirm effect (e.g. composition.generate) runs the engine in-process for minutes.
   */
  async selfConfirm(input: {
    keyId: string;
    ownerUserId: string;
    domain: string;
    confirmToken: string;
  }): Promise<{ status: number; body: string } | null> {
    if (!this.cfg.internalToken) {
      this.log.error('cannot self-confirm: INTERNAL_SERVICE_TOKEN unset');
      return null;
    }
    try {
      const res = await fetch(`${this.cfg.authServiceUrl}/internal/mcp-keys/confirm`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-internal-token': this.cfg.internalToken },
        body: JSON.stringify({
          key_id: input.keyId,
          owner_user_id: input.ownerUserId,
          domain: input.domain,
          confirm_token: input.confirmToken,
        }),
        signal: AbortSignal.timeout(16 * 60 * 1000),
      });
      return { status: res.status, body: await res.text() };
    } catch (e) {
      this.log.warn(`self-confirm failed: ${e}`);
      return null;
    }
  }
}
