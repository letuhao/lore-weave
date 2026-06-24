import { useTranslation } from 'react-i18next';
import type { BookAttribute, BookGenre } from '../../tieringTypes';
import { tierFromSourceRef } from '../../lib/tiering';
import { TierChip } from './TierChip';
import { FieldTypeBadge } from './FieldTypeBadge';

/** Read-only detail for the selected matrix cell. Editing happens in the Manage tab
 *  (single edit surface — the matrix is for cross-genre comparison). */
export function MatrixCellInspector({
  attribute,
  genre,
}: {
  attribute: BookAttribute | null;
  genre: BookGenre | null;
}) {
  const { t } = useTranslation('glossaryTiering');

  if (!attribute || !genre) {
    return (
      <div className="rounded-lg border bg-card p-4 text-xs text-muted-foreground">{t('matrix.no_cell')}</div>
    );
  }

  return (
    <div className="space-y-3 rounded-lg border bg-card p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {t('matrix.cell_inspector')}
      </div>
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm font-semibold">{attribute.code}</span>
        <span className="text-xs" style={{ color: genre.color }}>
          · {genre.name}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <FieldTypeBadge fieldType={attribute.field_type} />
        <TierChip tier={tierFromSourceRef(attribute.source_ref)} />
      </div>
      {attribute.description && <p className="text-[13px] text-foreground/80">{attribute.description}</p>}
      {attribute.field_type === 'select' && attribute.options.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {attribute.options.map((o) => (
            <span key={o} className="rounded border bg-secondary px-1.5 py-0.5 text-[11px]">
              {o}
            </span>
          ))}
        </div>
      )}
      <div className="text-[11px] text-muted-foreground">
        {t('matrix.required', { defaultValue: 'required' })}: {attribute.is_required ? 'yes' : 'no'} ·{' '}
        {t('matrix.sort')}: {attribute.sort_order}
      </div>
    </div>
  );
}
