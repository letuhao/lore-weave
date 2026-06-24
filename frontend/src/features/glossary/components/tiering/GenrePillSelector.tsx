import { useTranslation } from 'react-i18next';
import { X, Plus } from 'lucide-react';
import type { BookGenre } from '../../tieringTypes';
import { tierFromSourceRef, TIER_CHIP_CLASS } from '../../lib/tiering';

/** Per-entity genre selection (D2). Controlled — `selectedIds` is the entity's genre
 *  set; universal is mandatory (O4) and can't be removed. Used by the entity form;
 *  the host persists via setEntityGenres. */
export function GenrePillSelector({
  genres,
  selectedIds,
  onChange,
}: {
  genres: BookGenre[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}) {
  const { t } = useTranslation('glossaryTiering');
  const selected = genres.filter((g) => selectedIds.includes(g.genre_id));
  const available = genres.filter((g) => !selectedIds.includes(g.genre_id));

  const remove = (id: string) => onChange(selectedIds.filter((x) => x !== id));
  const add = (id: string) => {
    if (id) onChange([...selectedIds, id]);
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {selected.map((g) => {
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
                type="button"
                onClick={() => remove(g.genre_id)}
                data-testid={`entity-drop-genre-${g.code}`}
                className="rounded-full hover:bg-black/10"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </span>
        );
      })}
      {available.length > 0 && (
        <label className="inline-flex items-center gap-1 text-[11px] text-primary">
          <Plus className="h-3 w-3" />
          <select
            value=""
            onChange={(e) => add(e.target.value)}
            data-testid="entity-add-genre"
            className="rounded border bg-background px-1 py-0.5 text-[11px]"
          >
            <option value="">{t('entity.add_genre')}</option>
            {available.map((g) => (
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
