import { useTranslation } from 'react-i18next';
import { AlertTriangle, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { WikiGenerationProvenance } from '../types';

/**
 * wiki-llm M7b-2b — surfaces WHY an AI article needs review or is blocked: the
 * CanonVerifier flags captured at generation time (kind · dimension · evidence),
 * severity-colored. Read-only and self-contained (the data is in the article's
 * generation_provenance — no fetch). Renders nothing when there are no flags.
 */
export function VerifyFlagsPanel({
  provenance,
  blocked,
}: {
  provenance?: WikiGenerationProvenance | null;
  /** generation_status === 'blocked' — the article won't auto-publish. */
  blocked?: boolean;
}) {
  const { t } = useTranslation('wiki');
  const flags = provenance?.verify_flags ?? [];
  if (flags.length === 0 && !blocked) return null;

  const Icon = blocked ? ShieldAlert : AlertTriangle;
  const headTone = blocked ? 'text-destructive' : 'text-amber-500';

  return (
    <div
      className={cn(
        'mb-4 rounded-lg border px-3 py-2.5',
        blocked ? 'border-destructive/30 bg-destructive/5' : 'border-amber-400/30 bg-amber-400/5',
      )}
      role="note"
      data-testid="wiki-verify-flags"
    >
      <div className={cn('mb-1.5 flex items-center gap-1.5 text-xs font-semibold', headTone)}>
        <Icon className="h-3.5 w-3.5" />
        {blocked ? t('gen.flags.blockedTitle') : t('gen.flags.reviewTitle')}
      </div>
      {flags.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">{t('gen.flags.blockedNoDetail')}</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {flags.map((f, i) => (
            <li key={i} className="flex items-start gap-2 text-[11px]" data-testid="wiki-verify-flag">
              <span
                className={cn(
                  'mt-0.5 shrink-0 rounded px-1 py-0.5 text-[9px] font-semibold uppercase',
                  f.severity === 'high'
                    ? 'bg-destructive/15 text-destructive'
                    : 'bg-amber-400/15 text-amber-500',
                )}
              >
                {t(`gen.flags.kind.${f.kind}`, { defaultValue: f.kind })}
              </span>
              <span className="min-w-0">
                <span className="font-medium">{f.dimension}</span>
                {f.evidence && <span className="text-muted-foreground"> — {f.evidence}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
