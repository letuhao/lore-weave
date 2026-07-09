import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Gauge } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ContextBreakdownPanel } from './ContextBreakdownPanel';
import type { CompactControls } from '../hooks/useCompactSession';
import type { ContextBudget } from '../types';

// RAID Wave A3 — the chat header context-budget meter (industry-standard
// "context used %" indicator). Pure render component: the event→state wiring
// lives in useChatMessages / the stream hub; this only renders the snapshot.
//
// Chat Quality Wave W2 — the terse % chip STAYS (market anti-pattern: never
// hide it, no chunky bars). Additions: the hover tooltip now leads with the
// Claude-Code "until auto-compact: X%" phrasing + the Copilot-style baseline
// transparency line, and clicking the chip opens the ContextBreakdownPanel
// drill-down (per-category stacked bar + rows).
//
// Tiered warning bands (pct = used / effective_limit):
//   < 0.70  → normal  (muted)
//   0.70–0.85 → amber (warning)
//   > 0.85  → red     (danger / destructive)
// When pct is null (the model has no registered context_length) → render "—"
// so an unknown budget never crashes or shows a bogus %.

/** Band selector — exported so the unit test asserts the boundary logic directly. */
export type ContextBand = 'normal' | 'warning' | 'danger';

export function contextBand(pct: number): ContextBand {
  if (pct > 0.85) return 'danger';
  if (pct >= 0.7) return 'warning';
  return 'normal';
}

interface Props {
  budget: ContextBudget | null;
  /** Narrow host: render the gauge icon + % without extra chrome. */
  compact?: boolean;
  /** W2: opens the tool/skill manager from the breakdown panel's tool rows.
   *  Omitted on surfaces without the rack (the action is hidden there). */
  onManageTools?: () => void;
  /** W3: the breakdown panel's "Compact now" controls (useCompactSession).
   *  Omitted → the compact section is hidden. */
  compactControls?: CompactControls;
  /** W6: external "open the breakdown panel" signal (the rack's summary chip).
   *  Controlled OR-ed with the meter's own click state — the same pattern as
   *  the rack add modal's externalAddOpen. */
  externalPanelOpen?: boolean;
  onExternalPanelClose?: () => void;
}

export function ContextMeter({
  budget, compact, onManageTools, compactControls, externalPanelOpen, onExternalPanelClose,
}: Props) {
  const { t } = useTranslation('chat');
  const [panelOpen, setPanelOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const effectiveOpen = panelOpen || !!externalPanelOpen;

  function closePanel() {
    setPanelOpen(false);
    onExternalPanelClose?.();
  }

  // Close the drill-down on outside click (same pattern as the message "more"
  // dropdown — no portal, the panel is absolutely positioned in this wrapper).
  useEffect(() => {
    if (!effectiveOpen) return;
    function handleClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setPanelOpen(false);
        onExternalPanelClose?.();
      }
    }
    window.addEventListener('mousedown', handleClick);
    return () => window.removeEventListener('mousedown', handleClick);
  }, [effectiveOpen, onExternalPanelClose]);

  // No snapshot yet (before the first turn finishes) → render nothing rather
  // than a placeholder chip that would just be visual noise.
  if (!budget) return null;

  const known = budget.pct != null && Number.isFinite(budget.pct);
  const pct = known ? (budget.pct as number) : null;
  const band = pct != null ? contextBand(pct) : 'normal';

  // D-CHAT-CONTEXT-METER-OVERCOUNT — a genuine overflow (pct > 1) is real signal
  // and stays visible (e.g. "142%"); compaction triggers at 75% so a turn
  // legitimately reaching a real, uncompacted multiple of the window is not
  // expected. This only guards the DISPLAY against a runaway/misreported value
  // reading as absurd rather than actionable (the backend once showed "469%"
  // from a token-sum bug — fixed at the source, but the badge shouldn't be
  // able to render nonsense again if some future bug reintroduces it).
  const label = known
    ? (pct as number) > 2.99
      ? '>299%'
      : `${Math.round((pct as number) * 100)}%`
    : '—';

  // W2 tooltip — primary phrasing is "until auto-compact: X%" (Claude Code),
  // then used/limit, then the baseline transparency line (Copilot) when the
  // backend measured it. Multi-line via \n in the native title.
  const titleLines: string[] = [];
  if (budget.until_compact_pct != null) {
    titleLines.push(
      t('header.context_meter.until_compact', { pct: Math.round(budget.until_compact_pct * 100) }),
    );
  }
  titleLines.push(
    known
      ? t('header.context_meter.tokens', {
          used: budget.used_tokens,
          limit: budget.effective_limit ?? budget.context_length ?? '?',
        })
      : t('header.context_meter.unknown'),
  );
  if (budget.baseline_tokens != null) {
    titleLines.push(
      t('header.context_meter.baseline', { tokens: budget.baseline_tokens.toLocaleString() }),
    );
  }
  const title = titleLines.join('\n');

  return (
    <div ref={rootRef} className="relative min-w-0">
      <button
        type="button"
        onClick={() => (effectiveOpen ? closePanel() : setPanelOpen(true))}
        title={title}
        aria-label={t('header.context_meter.label')}
        aria-expanded={effectiveOpen}
        data-testid="context-meter"
        data-band={band}
        className={cn(
          'flex min-w-0 items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium tabular-nums transition-colors',
          !known
            ? 'border-border bg-secondary/40 text-muted-foreground'
            : band === 'danger'
              ? 'border-destructive/40 bg-destructive/10 text-destructive'
              : band === 'warning'
                ? 'border-warning/40 bg-warning/10 text-warning'
                : 'border-border bg-secondary/40 text-muted-foreground',
        )}
      >
        <Gauge className="h-3 w-3 shrink-0" />
        {!compact && <span className="tabular-nums">{label}</span>}
      </button>
      {effectiveOpen && <ContextBreakdownPanel budget={budget} onManageTools={onManageTools} compact={compactControls} />}
    </div>
  );
}
