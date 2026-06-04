import { useTranslation } from 'react-i18next';
import { Check, AlertTriangle, ShieldAlert, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { CanonVerify, VerifyFlag } from '../types';

const FLAG_ICON: Record<string, typeof Check> = {
  injection: ShieldAlert,
  regurgitation: Copy,
  contradiction: AlertTriangle,
  anachronism: AlertTriangle,
};

/** Surfaces the C12 canon-verify + ③ regurgitation results — the trust signal the
 *  author reviews before promoting. Clean = the three checks found nothing AND ran
 *  against real canon; flags carry typed evidence (never an opaque boolean). */
export function VerifyPanel({ verify }: { verify?: CanonVerify }) {
  const { t } = useTranslation('enrichment');

  if (!verify) {
    return <p className="text-xs text-muted-foreground">{t('verify.none')}</p>;
  }

  const flags = verify.flags ?? [];
  const clean = flags.length === 0 && !verify.verify_degraded;

  return (
    <div className="space-y-2" data-testid="enrichment-verify">
      {clean && (
        <div className="flex items-center gap-2 text-xs text-success" data-testid="verify-clean">
          <Check className="h-3.5 w-3.5" />
          {t('verify.clean')}
        </div>
      )}
      {!clean && verify.verify_degraded && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <AlertTriangle className="h-3.5 w-3.5" />
          {t('verify.degraded')}
        </div>
      )}
      {flags.map((f, i) => (
        <FlagRow key={i} flag={f} />
      ))}
    </div>
  );
}

function FlagRow({ flag }: { flag: VerifyFlag }) {
  const { t } = useTranslation('enrichment');
  const Icon = FLAG_ICON[flag.kind] ?? AlertTriangle;
  const high = flag.severity === 'high';
  return (
    <div
      className={cn(
        'rounded-md border px-3 py-2 text-xs',
        high ? 'border-destructive/30 bg-destructive/5' : 'border-warning/30 bg-warning/5',
      )}
    >
      <div className="flex items-center gap-1.5 font-medium">
        <Icon className={cn('h-3.5 w-3.5', high ? 'text-destructive' : 'text-warning')} />
        <span>{t(`verify.flag.${flag.kind}`, { defaultValue: flag.kind })}</span>
        {flag.dimension && <span className="text-muted-foreground">· {flag.dimension}</span>}
        <span
          className={cn(
            'ml-auto rounded px-1.5 py-0.5 text-[10px]',
            high ? 'bg-destructive/10 text-destructive' : 'bg-warning/12 text-warning',
          )}
        >
          {t(`verify.severity.${flag.severity}`, { defaultValue: String(flag.severity) })}
        </span>
      </div>
      {flag.evidence && (
        <p className="mt-1 break-words font-mono text-[11px] text-muted-foreground">{flag.evidence}</p>
      )}
    </div>
  );
}
