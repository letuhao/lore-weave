import { useTranslation } from 'react-i18next';
import { STATUS_GLYPH, STATUS_LEGEND_ORDER } from '../lib/entityStatus';

// C8 — explains the three derived entity states (⭐ canonical /
// 💭 discovered / 📦 archived) so the row glyphs aren't opaque. Pure
// presentational; the glyph map + order come from the shared lib so the
// legend can never drift from the row rendering.

export function EntityStatusLegend() {
  const { t } = useTranslation('knowledge');
  return (
    <div
      className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border bg-muted/30 px-3 py-2 text-[11px] text-muted-foreground"
      data-testid="entities-status-legend"
    >
      <span className="font-medium uppercase tracking-wide">
        {t('entities.legend.title')}
      </span>
      {STATUS_LEGEND_ORDER.map((s) => (
        <span key={s} className="flex items-center gap-1" data-status={s}>
          <span aria-hidden="true">{STATUS_GLYPH[s]}</span>
          <span>{t(`entities.status.${s}`)}</span>
          <span className="text-muted-foreground/70">
            — {t(`entities.legend.${s}`)}
          </span>
        </span>
      ))}
    </div>
  );
}
