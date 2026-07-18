// The panel-layout preset menu (VS Code "Editor Layout" analogue) — presentational only. It
// receives the current panel count + dock width and reports a picked preset; the trigger
// (StudioLayoutButton) owns open/close + the host seam. Kept view-only so it's unit-testable
// without a dock.
import { useTranslation } from 'react-i18next';
import { LAYOUT_PRESETS, isPresetTooNarrow, type LayoutPreset } from './dockLayout';

interface Props {
  panelCount: number;
  dockWidth: number;
  onPick: (preset: LayoutPreset) => void;
}

const DEFAULT_LABELS: Record<string, string> = {
  single: 'Single',
  cols2: 'Two columns',
  cols3: 'Three columns',
  cols4: 'Four columns',
  grid2x2: 'Grid 2×2',
  grid3x2: 'Grid 3×2',
  grid4x2: 'Grid 4×2',
  cols6: 'Six columns',
  cols8: 'Eight columns',
};

/** A mini glyph of the target arrangement: cols×rows cells drawn in a 24×18 box. */
function PresetGlyph({ cols, rows }: { cols: number; rows: number }) {
  const W = 24, H = 18, pad = 1, gap = 1;
  const cw = (W - pad * 2 - gap * (cols - 1)) / cols;
  const ch = (H - pad * 2 - gap * (rows - 1)) / rows;
  const cells = [];
  for (let c = 0; c < cols; c++) {
    for (let r = 0; r < rows; r++) {
      cells.push(
        <rect
          key={`${c}-${r}`}
          x={pad + c * (cw + gap)}
          y={pad + r * (ch + gap)}
          width={cw}
          height={ch}
          rx={0.75}
          className="fill-current"
        />,
      );
    }
  }
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} aria-hidden className="opacity-80">
      {cells}
    </svg>
  );
}

export function LayoutPicker({ panelCount, dockWidth, onPick }: Props) {
  const { t } = useTranslation('studio');

  const reasonFor = (p: LayoutPreset): 'needPanels' | 'narrow' | null => {
    if ((p.cols > 1 || p.rows > 1) && panelCount < 2) return 'needPanels';
    if (isPresetTooNarrow(p, dockWidth)) return 'narrow';
    return null;
  };

  return (
    <div
      data-testid="studio-layout-picker"
      role="menu"
      className="w-64 rounded-md border bg-popover p-2 text-popover-foreground shadow-lg"
    >
      <div className="px-1 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {t('layout.title', { defaultValue: 'Panel layout' })}
      </div>

      <div className="grid grid-cols-3 gap-1.5">
        {LAYOUT_PRESETS.map((p) => {
          const reason = reasonFor(p);
          const disabled = reason !== null;
          const label = t(`layout.presets.${p.id}`, { defaultValue: DEFAULT_LABELS[p.id] ?? p.id });
          const title = reason === 'needPanels'
            ? t('layout.needPanels', { defaultValue: 'Open at least two panels first' })
            : reason === 'narrow'
              ? t('layout.tooNarrow', { defaultValue: 'Needs a wider window' })
              : label;
          return (
            <button
              key={p.id}
              type="button"
              role="menuitem"
              data-testid={`studio-layout-preset-${p.id}`}
              data-disabled={disabled ? 'true' : 'false'}
              disabled={disabled}
              onClick={() => onPick(p)}
              title={title}
              className={`flex flex-col items-center gap-1 rounded border px-1 py-1.5 text-[10px] leading-tight transition-colors ${
                disabled
                  ? 'cursor-not-allowed border-transparent text-muted-foreground/40'
                  : 'border-transparent text-muted-foreground hover:border-border hover:bg-secondary hover:text-foreground'
              }`}
            >
              <PresetGlyph cols={p.cols} rows={p.rows} />
              <span className="w-full truncate text-center">{label}</span>
            </button>
          );
        })}
      </div>

      <div className="px-1 pt-2 text-[11px] text-muted-foreground" data-testid="studio-layout-hint">
        {panelCount < 1
          ? t('layout.empty', { defaultValue: 'Open panels to arrange them.' })
          : t('layout.hint', { count: panelCount, defaultValue: 'Arranges your {{count}} open panels.' })}
      </div>
    </div>
  );
}
