import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { useAuth } from '@/auth';
import type { WikiContribution } from './api';
import { fetchWikiContributions } from './api';

type Props = { userId: string; isSelf: boolean };

export function WikiTab({ userId, isSelf }: Props) {
  const { t } = useTranslation('profile');
  const { accessToken } = useAuth();
  const [items, setItems] = useState<WikiContribution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    // Token only matters for self (to include private/draft); harmless otherwise.
    fetchWikiContributions(userId, accessToken)
      .then((res) => setItems(res.items))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [userId, accessToken]);

  if (loading) {
    return <div className="py-8 text-center text-sm text-[var(--muted-fg)]">{t('loading')}</div>;
  }
  if (error) {
    return <div className="py-8 text-center text-sm text-[var(--muted-fg)]">{t('wikiError')}</div>;
  }
  if (items.length === 0) {
    return <div className="py-8 text-center text-sm text-[var(--muted-fg)]">{t('noWiki')}</div>;
  }

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden bg-[var(--card)]">
      {items.map((c) => (
        <Link
          key={c.article_id}
          // Self → own book wiki manager; others → public book page.
          to={isSelf ? `/books/${c.book_id}/wiki` : `/browse/${c.book_id}`}
          className="flex items-center gap-3 px-3.5 py-3 border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--card-hover)] transition-colors"
        >
          <div
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg text-base"
            style={{ background: 'var(--secondary)' }}
            title={c.kind.name}
          >
            {c.kind.icon || '📄'}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="font-serif text-[14px] font-semibold truncate">
                {c.display_name || t('untitled')}
              </span>
              {c.status !== 'published' && (
                <span className="rounded px-1.5 py-px text-[9px] bg-[var(--secondary)] text-[var(--muted-fg)]">
                  {c.status}
                </span>
              )}
            </div>
            <div className="text-[11px] text-[var(--muted-fg)]">
              {c.kind.name} · {new Date(c.last_contributed_at).toLocaleDateString()}
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
