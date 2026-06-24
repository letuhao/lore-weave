import { useTranslation } from 'react-i18next';
import { X, Plus } from 'lucide-react';
import type { BookGenre } from '../../tieringTypes';
import { tierFromSourceRef } from '../../lib/tiering';
import { TIER_CHIP_CLASS } from '../../lib/tiering';

/** The book's active-genre set = the matrix columns. universal is mandatory (O4) and
 *  cannot be removed. Add/remove call setActiveGenres with the new full set. */
export function ActiveGenrePills({
  genres,
  onSetActive,
}: {
  genres: BookGenre[];
  onSetActive: (genreIds: string[]) => Promise<unknown>;
}) {
  const { t } = useTranslation('glossaryTiering');
  const active = genres.filter((g) => g.active);
  const inactive = genres.filter((g) => !g.active);
  const activeIds = active.map((g) => g.genre_id);

  const remove = (id: string) => void onSetActive(activeIds.filter((x) => x !== id));
  const add = (id: string) => {
    if (id) void onSetActive([...activeIds, id]);
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{t('matrix.active_genres')}:</span>
      {active.map((g) => {
        const tier = tierFromSourceRef(g.source_ref);
        const mandatory = g.code === 'universal';
        return (
          <span
            key={g.genre_id}
            className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] ${TIER_CHIP_CLASS[tier]}`}
          >
            {g.icon ? `${g.icon} ` : ''}
            {g.name}
            {!mandatory && (
              <button
                onClick={() => remove(g.genre_id)}
                title={t('matrix.remove_genre')}
                data-testid={`matrix-remove-genre-${g.code}`}
                className="rounded-full hover:bg-black/10"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </span>
        );
      })}
      {inactive.length > 0 && (
        <label className="inline-flex items-center gap-1 text-[11px] text-primary">
          <Plus className="h-3 w-3" />
          <select
            value=""
            onChange={(e) => add(e.target.value)}
            data-testid="matrix-add-genre"
            className="rounded border bg-background px-1 py-0.5 text-[11px]"
          >
            <option value="">{t('matrix.add_genre')}</option>
            {inactive.map((g) => (
              <option key={g.genre_id} value={g.genre_id}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
