import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ShieldQuestion, Check, CheckCheck, X } from 'lucide-react';
import { useChatStream } from '../providers';
import type { FrontendToolOutcome } from '../hooks/useChatMessages';
import type { ToolCallRecord } from '../types';

// RAID C2 (DR-C2 §4) — the Write-mode Tier-A approval card. The agent wants to
// run an undoable server write (e.g. book_create) that is NOT on the user's
// per-tool allowlist; the run SUSPENDS with a `tool_approval` pending payload
// {kind, tool, args, tier} riding the existing pending-tool-call surface (no
// new frontend tool). Approve once runs it this time; Always allow also
// persists the per-user allowlist row (never prompts for this tool again);
// Deny feeds "denied by user" so the agent self-corrects. The server executes
// on resume — this card performs NO API call of its own.

interface Props {
  record: ToolCallRecord;
}

interface ApprovalArgs {
  kind?: string;
  tool?: string;
  args?: Record<string, unknown>;
  tier?: string;
}

/** True when a pending tool record is the RAID C2 tool_approval suspension. */
export function isToolApprovalRecord(tc: ToolCallRecord): boolean {
  return (
    tc.pending === true &&
    !!tc.args &&
    typeof tc.args === 'object' &&
    (tc.args as ApprovalArgs).kind === 'tool_approval'
  );
}

type CardState = null | 'approved' | 'always' | 'denied' | 'never';

export function ToolApprovalCard({ record }: Props) {
  const { t } = useTranslation('chat');
  const { submitToolResult } = useChatStream();
  const [state, setState] = useState<CardState>(null);
  const [busy, setBusy] = useState(false);

  const args = (record.args ?? {}) as ApprovalArgs;
  const tool = args.tool ?? record.tool;
  const tier = args.tier ?? 'A';
  const toolArgs = args.args ?? {};

  let prettyArgs = '';
  try {
    prettyArgs = JSON.stringify(toolArgs, null, 2);
  } catch {
    prettyArgs = String(toolArgs);
  }

  async function decide(outcome: FrontendToolOutcome, next: Exclude<CardState, null>) {
    if (busy || state) return;
    setBusy(true);
    setState(next);
    try {
      if (record.runId && record.toolCallId) {
        await submitToolResult(record.runId, record.toolCallId, outcome);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      data-testid="tool-approval-card"
      data-tool={tool}
      className="mt-1.5 rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs"
    >
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-amber-500">
        <ShieldQuestion className="h-3 w-3" />
        {t('toolApproval.label', { defaultValue: 'Allow the agent to run this tool?' })}
        <span
          data-testid="tool-approval-tier"
          className="ml-auto rounded-sm border border-amber-500/40 px-1 text-[9px] font-semibold uppercase tracking-wide"
          title={t('toolApproval.tier_hint', { defaultValue: 'Tier {{tier}} — an undoable write', tier })}
        >
          {t('toolApproval.tier', { defaultValue: 'Tier {{tier}}', tier })}
        </span>
      </div>
      <p className="mb-1 font-mono text-[11px] text-foreground/90">{tool}</p>
      {prettyArgs && prettyArgs !== '{}' && (
        <pre className="mb-1 max-h-40 overflow-auto rounded bg-background/60 p-1.5 font-mono text-[10px] leading-snug text-foreground/80">
          {prettyArgs}
        </pre>
      )}
      <p className="mb-1 text-[10px] text-muted-foreground">
        {t('toolApproval.hint', {
          defaultValue: 'This write is undoable. "Always allow" stops asking for this tool.',
        })}
      </p>
      {state === null ? (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => void decide('approved_once', 'approved')}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm bg-amber-500 px-2 py-0.5 text-[11px] font-medium text-white hover:brightness-110 disabled:opacity-50"
          >
            <Check className="h-3 w-3" />
            {t('toolApproval.approve_once', { defaultValue: 'Approve once' })}
          </button>
          <button
            type="button"
            onClick={() => void decide('approved_always', 'always')}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm border border-amber-500/50 px-2 py-0.5 text-[11px] font-medium text-amber-500 hover:bg-amber-500/10 disabled:opacity-50"
          >
            <CheckCheck className="h-3 w-3" />
            {t('toolApproval.always_allow', { defaultValue: 'Always allow' })}
          </button>
          <button
            type="button"
            onClick={() => void decide('denied', 'denied')}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <X className="h-3 w-3" />
            {t('toolApproval.deny', { defaultValue: 'Deny' })}
          </button>
          {/* D3 (PO sign-off) — "Never allow": persist a standing deny for this tool
              right here, the moment it is asking. Revocable later in the permissions panel. */}
          <button
            type="button"
            onClick={() => void decide('denied_always', 'never')}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm border border-red-500/40 px-2 py-0.5 text-[11px] text-red-500 hover:bg-red-500/10 disabled:opacity-50"
          >
            <X className="h-3 w-3" />
            {t('toolApproval.never_allow', { defaultValue: 'Never allow' })}
          </button>
        </div>
      ) : (
        <div className="mt-1.5 text-[10px] text-muted-foreground">
          {state === 'approved' && t('toolApproval.approved', { defaultValue: 'Approved — running ✓' })}
          {state === 'always' && t('toolApproval.always_allowed', { defaultValue: 'Always allowed — running ✓' })}
          {state === 'denied' && t('toolApproval.denied', { defaultValue: 'Denied' })}
          {state === 'never' && t('toolApproval.never_allowed', { defaultValue: 'Never allowed — you can undo this in Settings → Permissions' })}
        </div>
      )}
    </div>
  );
}
