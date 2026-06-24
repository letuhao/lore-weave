import { useTranslation } from 'react-i18next';
import type { BookKind } from '../../tieringTypes';

/** Kind dropdown for the attribute matrix — picks which kind's matrix is shown. */
export function KindSelect({
  kinds,
  value,
  onChange,
}: {
  kinds: BookKind[];
  value: string | null;
  onChange: (kindId: string) => void;
}) {
  const { t } = useTranslation('glossaryTiering');
  return (
    <label className="flex items-center gap-2 text-xs">
      <span className="font-medium text-muted-foreground">{t('matrix.kind_label')}</span>
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        data-testid="matrix-kind-select"
        className="rounded-md border bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring/40"
      >
        <option value="" disabled>
          {t('matrix.select_kind')}
        </option>
        {kinds.map((k) => (
          <option key={k.book_kind_id} value={k.book_kind_id}>
            {k.icon ? `${k.icon} ` : ''}
            {k.name}
          </option>
        ))}
      </select>
    </label>
  );
}
