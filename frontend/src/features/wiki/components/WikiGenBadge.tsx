import { useTranslation } from 'react-i18next';
import { Sparkles, AlertTriangle, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { WikiGenerationStatus } from '../types';

/**
 * wiki-llm M7b-2b — the AI-generation status badge. `needs_review` (amber) and
 * `blocked` (red) draw attention to articles the CanonVerifier flagged; the clean
 * `generated` state shows a subtle "AI" marker (omitted on the compact sidebar
 * rows via `subtle`). Renders nothing for a human-authored article (null status).
 */
export function WikiGenBadge({
  status,
  subtle = false,
}: {
  status?: WikiGenerationStatus | null;
  /** Compact mode: hide the clean `generated` marker (sidebar rows). */
  subtle?: boolean;
}) {
  const { t } = useTranslation('wiki');
  if (!status) return null;
  if (status === 'generated' && subtle) return null;

  const cfg = {
    generated: { Icon: Sparkles, cls: 'bg-primary/12 text-primary' },
    needs_review: { Icon: AlertTriangle, cls: 'bg-amber-400/15 text-amber-500' },
    blocked: { Icon: ShieldAlert, cls: 'bg-destructive/12 text-destructive' },
  }[status];

  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[9px] font-medium',
        cfg.cls,
      )}
      title={t(`gen.badge.${status}Hint`)}
      data-testid={`wiki-gen-badge-${status}`}
    >
      <cfg.Icon className="h-2.5 w-2.5" />
      {t(`gen.badge.${status}`)}
    </span>
  );
}
