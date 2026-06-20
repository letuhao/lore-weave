import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Copy } from 'lucide-react';
import type { Genre } from '@/features/glossary/tieringTypes';
import { StandardRow } from './StandardRow';
import { useUserStandards } from '../hooks/useUserStandards';

/** Genres tab — merged System+User genres; clone a System genre into your tier. */
export function GenresPanel() {
  const { t } = useTranslation('standards');
  const { genres, isLoading, error, cloneGenre } = useUserStandards();

  const onClone = (g: Genre) => {
    cloneGenre.mutate(g, {
      onSuccess: () => toast.success(t('toast.cloned', { name: g.name })),
      onError: () => toast.error(t('toast.cloneError', { name: g.name })),
    });
  };

  if (isLoading) return <p className="py-6 text-sm text-muted-foreground">{t('loading')}</p>;
  if (error) return <p className="py-6 text-sm text-destructive">{t('error')}</p>;
  if (genres.length === 0)
    return <p className="py-6 text-sm text-muted-foreground">{t('empty.genres')}</p>;

  return (
    <ul className="space-y-1.5" data-testid="standards-genres">
      {genres.map((g) => (
        <li key={g.genre_id}>
          <StandardRow icon={g.icon} name={g.name} code={g.code} tier={g.tier}>
            {g.tier === 'system' ? (
              <button
                type="button"
                onClick={() => onClone(g)}
                disabled={cloneGenre.isPending}
                className="inline-flex items-center gap-1 rounded border px-2 py-1 text-[12px] font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
                data-testid={`clone-genre-${g.code}`}
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
