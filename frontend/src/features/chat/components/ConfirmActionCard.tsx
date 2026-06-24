import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ShieldAlert, Check, X } from 'lucide-react';
import { useAuth } from '@/auth';
import { actionsApi, type ActionPreview } from '../actionsApi';
import { useChatStream } from '../providers';
import type { FrontendToolOutcome } from '../hooks/useChatMessages';
import type { ToolCallRecord } from '../types';

// MCP fan-out (C-CONFIRM) — the GENERIC class-C confirm card, keyed on
// `descriptor` + `domain`. The agent called the universal `confirm_action` tool
// (a domain propose tool minted a confirm_token); the run SUSPENDS and this
// renders. On mount it fetches a non-consuming preview
// (GET /v1/<domain>/actions/preview?token=) so the human confirms against what
// is true NOW. Confirm POSTs {confirm_token} to POST /v1/<domain>/actions/confirm
// — the ONLY write path — then resumes with the real outcome (H6). Never
// auto-applies.
//
// H2 — BATCH confirm: when `items[]` is present (e.g. descriptor
// "book.publish_batch"), this renders ONE card listing the N rows with a SINGLE
// Apply — never N cards. The single confirm_token commits all rows server-side,
// so "publish all my drafts" stays one click.
//
// /review-impl FIX 1 — the batch row list is driven by the SERVER preview (the
// token-scoped `preview_rows` the non-batch path already fetches), NOT by the
// LLM's `args.items`. The server preview is what actually commits, so the card
// faithfully previews the commit. `args.items` is only a fallback for when the
// server returns no enumeration, and it is then labelled "requested (advisory)"
// with the Confirm button GATED on the server preview having loaded — so the
// human never one-clicks a batch the server hasn't confirmed it will apply.

interface Props {
  record: ToolCallRecord;
}

interface ConfirmArgs {
  confirm_token?: string;
  descriptor?: string;
  title?: string;
  domain?: string;
  items?: unknown[];
}

type CardState = null | 'done' | 'expired' | 'error' | 'cancelled';

// The generic confirm domains, derivable from a dotted action descriptor
// (`book.publish`, `translation.start_job`, …). Used as a fallback when `domain`
// is absent from the tool args — e.g. when the model confirmed a non-glossary
// action via the legacy `glossary_confirm_action` tool (which carries no domain).
const GENERIC_DOMAINS = ['book', 'composition', 'translation', 'settings'] as const;
export function descriptorDomain(descriptor: string | undefined): string | null {
  if (!descriptor) return null;
  // KG class-C descriptors are non-dotted but kg_-prefixed (kg_schema_edit,
  // kg_adopt, kg_sync_apply, kg_triage_*) and commit at /v1/kg/actions/* — route
  // them to the generic card's `kg` domain. (Glossary's non-dotted descriptors —
  // schema_create_kind, book_delete, adopt, … — are never kg_-prefixed, so this
  // disambiguates cleanly and they keep falling through to the legacy ConfirmCard.)
  if (descriptor.startsWith('kg_')) return 'kg';
  const dot = descriptor.indexOf('.');
  if (dot <= 0) return null; // glossary descriptors are non-dotted (book_delete, …)
  const head = descriptor.slice(0, dot);
  return (GENERIC_DOMAINS as readonly string[]).includes(head) ? head : null;
}

/** Render one batch row from an arbitrary item object — best-effort label. */
function itemLabel(item: unknown): string {
  if (item == null) return '';
  if (typeof item === 'string') return item;
  if (typeof item === 'object') {
    const o = item as Record<string, unknown>;
    const v = o.label ?? o.title ?? o.name ?? o.id;
    if (v != null) return String(v);
    try {
      return JSON.stringify(o);
    } catch {
      return '';
    }
  }
  return String(item);
}

export function ConfirmActionCard({ record }: Props) {
  const { t } = useTranslation('chat');
  const { accessToken } = useAuth();
  const { submitToolResult } = useChatStream();
  const [state, setState] = useState<CardState>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<ActionPreview | null>(null);
  // /review-impl FIX 1: track whether the server preview resolved (vs failed/
  // pending) so a batch can gate its Confirm button on a loaded preview.
  const [previewLoaded, setPreviewLoaded] = useState(false);
  // The BE's actionable reason for a 422, surfaced instead of a blanket "Expired".
  const [detail, setDetail] = useState('');

  const args = (record.args ?? {}) as ConfirmArgs;
  const token = args.confirm_token ?? '';
  // Prefer the explicit `domain` (the generic confirm_action tool sets it); fall
  // back to deriving it from a dotted descriptor so a non-glossary action the model
  // confirmed via the legacy `glossary_confirm_action` (no domain arg) still routes
  // to the correct /v1/<domain>/actions/* endpoints instead of failing.
  const domain = args.domain ?? descriptorDomain(args.descriptor) ?? '';
  const argTitle = args.title ?? '';
  const items = Array.isArray(args.items) ? args.items : [];

  // Fetch the current-state preview once on mount (synchronization, not event
  // handling). A failed/expired preview is non-fatal — Confirm re-validates.
  useEffect(() => {
    let alive = true;
    if (!accessToken || !token || !domain) return;
    actionsApi
      .previewAction(domain, token, accessToken)
      .then((p) => {
        if (alive) {
          setPreview(p);
          setPreviewLoaded(true);
        }
      })
      .catch(() => {
        /* preview is best-effort; confirm is the source of truth */
      });
    return () => {
      alive = false;
    };
  }, [accessToken, token, domain]);

  const title = preview?.title || argTitle;
  const rows = preview?.preview_rows ?? [];
  const destructive = preview?.destructive ?? false;

  async function resume(outcome: FrontendToolOutcome) {
    if (record.runId && record.toolCallId) {
      await submitToolResult(record.runId, record.toolCallId, outcome);
    }
  }

  async function confirm() {
    if (busy || state || !accessToken || !token || !domain) return;
    // FIX 1: when previewing a batch only from advisory items[], don't commit
    // until the server preview loaded (button is also disabled, this is defence).
    if (confirmGatedOnPreview) return;
    setBusy(true);
    let outcome: FrontendToolOutcome;
    try {
      await actionsApi.confirmAction(domain, token, accessToken);
      outcome = 'action_done';
      setState('done');
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 422) {
        // expired, already-confirmed (single-use), or a precondition drift — all
        // re-proposable. Surface the BE's actionable reason instead of a blanket
        // "expired" (which used to hide WHY the 422 happened).
        outcome = 'token_expired';
        setState('expired');
        const msg = (err as Error).message;
        const meaningful = !!msg && msg !== 'Unprocessable Entity';
        setDetail(meaningful ? msg : '');
        toast.error(meaningful ? msg : t('actionConfirm.expired', { defaultValue: 'This confirmation is no longer valid — ask again to propose it afresh.' }));
      } else {
        outcome = 'action_error';
        setState('error');
        toast.error(t('actionConfirm.error', { defaultValue: 'Could not apply the change.' }));
      }
    } finally {
      setBusy(false);
    }
    await resume(outcome);
  }

  async function cancel() {
    if (busy || state) return;
    setBusy(true);
    setState('cancelled');
    try {
      await resume('cancelled');
    } finally {
      setBusy(false);
    }
  }

  const accent = destructive ? 'red' : 'amber';
  const isBatch = items.length > 0;
  // /review-impl FIX 1: prefer the SERVER preview's token-scoped rows for the
  // batch list — that is what actually commits. Only when the server returns no
  // enumeration do we fall back to the LLM's `args.items`, labelled advisory.
  const serverEnumeratesBatch = isBatch && rows.length > 0;
  const usingAdvisoryItems = isBatch && !serverEnumeratesBatch;
  // When falling back to advisory items, the Confirm button is GATED on the
  // server preview having actually loaded (so the human never one-clicks a batch
  // the server hasn't confirmed). A server-enumerated batch is inherently loaded.
  const confirmGatedOnPreview = usingAdvisoryItems && !previewLoaded;

  return (
    <div
      data-testid="confirm-action-card"
      data-descriptor={args.descriptor ?? ''}
      data-domain={domain}
      data-batch={isBatch ? 'true' : 'false'}
      className={`mt-1.5 rounded-md border p-2 text-xs ${
        accent === 'red' ? 'border-red-500/40 bg-red-500/5' : 'border-amber-500/40 bg-amber-500/5'
      }`}
    >
      <div className={`mb-1 flex items-center gap-1.5 text-[11px] font-medium ${accent === 'red' ? 'text-red-500' : 'text-amber-500'}`}>
        <ShieldAlert className="h-3 w-3" />
        {title || t('actionConfirm.label', { defaultValue: 'Confirm action' })}
        {isBatch && ` · ${t('actionConfirm.batch_count', { defaultValue: '{{count}} items', count: items.length })}`}
      </div>

      {/* H2 batch, FIX 1 — render the N rows in ONE card, sourced from the SERVER
          preview when it enumerates the token's items (what actually commits). */}
      {serverEnumeratesBatch && (
        <ul data-testid="confirm-batch-rows" data-source="server" className="mb-1 max-h-40 space-y-0.5 overflow-y-auto text-[10px] text-foreground/90">
          {rows.map((r, i) => (
            <li key={i} className="flex items-center gap-1.5 rounded bg-background/60 px-1.5 py-0.5">
              <span className="text-muted-foreground">{i + 1}.</span>
              <span className="truncate">{r.label}{r.value ? `: ${r.value}` : ''}{r.note ? ` — ${r.note}` : ''}</span>
            </li>
          ))}
        </ul>
      )}

      {/* Fallback: the server preview didn't enumerate the batch, so we show the
          LLM's requested items[] EXPLICITLY labelled advisory; Confirm is gated
          on the server preview having loaded (see confirmGatedOnPreview). */}
      {usingAdvisoryItems && (
        <>
          <p data-testid="confirm-batch-advisory" className="mb-0.5 text-[10px] italic text-muted-foreground">
            {t('actionConfirm.advisory_items', { defaultValue: 'Requested (advisory) — the server confirms the exact set on apply' })}
          </p>
          <ul data-testid="confirm-batch-rows" data-source="advisory" className="mb-1 max-h-40 space-y-0.5 overflow-y-auto text-[10px] text-foreground/90">
            {items.map((it, i) => (
              <li key={i} className="flex items-center gap-1.5 rounded bg-background/60 px-1.5 py-0.5">
                <span className="text-muted-foreground">{i + 1}.</span>
                <span className="truncate">{itemLabel(it)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {/* Non-batch single-action preview rows (token-scoped). */}
      {!isBatch && rows.length > 0 && (
        <ul className="mb-1 space-y-0.5 text-[10px] text-foreground/90">
          {rows.map((r, i) => (
            <li key={i} className="flex justify-between gap-2">
              <span className="text-muted-foreground">{r.label}</span>
              <span>{r.value}{r.note ? ` — ${r.note}` : ''}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mb-1 text-[10px] text-muted-foreground">
        {destructive
          ? t('actionConfirm.warning_destructive', { defaultValue: 'This is destructive and cascades — please confirm.' })
          : t('actionConfirm.warning', { defaultValue: 'This change is high-impact — please confirm.' })}
      </p>
      {state === null ? (
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            onClick={confirm}
            disabled={busy || confirmGatedOnPreview}
            title={confirmGatedOnPreview ? t('actionConfirm.awaiting_preview', { defaultValue: 'Loading the server preview…' }) : undefined}
            className={`inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[11px] font-medium text-white hover:brightness-110 disabled:opacity-50 ${
              accent === 'red' ? 'bg-red-500' : 'bg-amber-500'
            }`}
          >
            <Check className="h-3 w-3" />
            {isBatch
              ? t('actionConfirm.confirm_all', { defaultValue: 'Confirm all' })
              : t('actionConfirm.confirm', { defaultValue: 'Confirm' })}
          </button>
          <button
            type="button"
            onClick={cancel}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <X className="h-3 w-3" />{t('actionConfirm.cancel', { defaultValue: 'Cancel' })}
          </button>
        </div>
      ) : (
        <div className="mt-1.5 text-[10px] text-muted-foreground">
          {state === 'done' && t('actionConfirm.done', { defaultValue: 'Done ✓' })}
          {state === 'expired' && (detail || t('actionConfirm.expired_short', { defaultValue: 'Expired — re-ask' }))}
          {state === 'error' && t('actionConfirm.error_short', { defaultValue: 'Failed' })}
          {state === 'cancelled' && t('actionConfirm.cancelled', { defaultValue: 'Cancelled' })}
        </div>
      )}
    </div>
  );
}
