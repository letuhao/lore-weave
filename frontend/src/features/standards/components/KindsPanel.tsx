import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Copy } from 'lucide-react';
import { StandardRow } from './StandardRow';
import { useUserStandards, type KindRow } from '../hooks/useUserStandards';

/** Kinds tab — merged System+User kinds; clone a System kind into your tier. */
export function KindsPanel() {
  const { t } = useTranslation('standards');
  const { kinds, isLoading, error, cloneKind } = useUserStandards();

  const onClone = (k: KindRow) => {
    cloneKind.mutate(k, {
      onSuccess: () => toast.success(t('toast.cloned', { name: k.name })),
      onError: () => toast.error(t('toast.cloneError', { name: k.name })),
    });
  };

  if (isLoading) return <p className="py-6 text-sm text-muted-foreground">{t('loading')}</p>;
  if (error) return <p className="py-6 text-sm text-destructive">{t('error')}</p>;
  if (kinds.length === 0)
    return <p className="py-6 text-sm text-muted-foreground">{t('empty.kinds')}</p>;

  return (
    <ul className="space-y-1.5" data-testid="standards-kinds">
      {kinds.map((k) => (
        <li key={`${k.tier}:${k.id}`}>
          <StandardRow icon={k.icon} name={k.name} code={k.code} tier={k.tier}>
            {k.tier === 'system' ? (
              <button
                type="button"
                onClick={() => onClone(k)}
                disabled={cloneKind.isPending}
                className="inline-flex items-center gap-1 rounded border px-2 py-1 text-[12px] font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
                data-testid={`clone-kind-${k.code}`}
              >
                <Copy className="h-3 w-3" />
                {t('action.clone')}
              </button>
            ) : (
              <span className="text-[11px] text-muted-foreground">{t('action.yours')}</span>
            )}
          </StandardRow>
        </li>
      ))}
    </ul>
  );
}
