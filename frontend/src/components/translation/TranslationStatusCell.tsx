import type { CoverageCell } from '@/features/translation/versionsApi';

// Shared status vocabulary — used across TranslationStatusCell, LanguageStatusDots, VersionSidebar
export type StatusKey = 'none' | 'running' | 'translated' | 'active' | 'failed' | 'partial';

export function deriveCellStatus(cell: CoverageCell | null | undefined): StatusKey {
  if (!cell) return 'none';
  if (cell.latest_status === 'running') return 'running';
  if (cell.latest_status === 'failed' && cell.version_count === 1) return 'failed';
  if (cell.has_active) return 'active';
  if (cell.version_count > 0 && cell.latest_status === 'completed') return 'translated';
  if (cell.version_count > 0) return 'partial';
  return 'none';
}

export const STATUS_COLOR: Record<StatusKey, string> = {
  none:       'text-muted-foreground',
  running:    'text-amber-600',
  translated: 'text-blue-600',
  active:     'text-green-600',
  failed:     'text-red-600',
  partial:    'text-amber-600',
};

export const STATUS_ICON: Record<StatusKey, string> = {
  none:       '—',
  running:    '◌',
  translated: '○',
  active:     '●',
  failed:     '✗',
  partial:    '⚠',
};

type Props = {
  cell: CoverageCell | null | undefined;
  onClick?: () => void;
};

export function TranslationStatusCell({ cell, onClick }: Props) {
  const key = deriveCellStatus(cell);
  const color = STATUS_COLOR[key];
  const icon = STATUS_ICON[key];
  const label = cell?.has_active
    ? `v${cell.active_version_num} ✓`
    : cell?.latest_version_num
    ? `v${cell.latest_version_num}`
    : '';

  if (key === 'none') {
    return <span className="text-muted-foreground select-none">—</span>;
  }

  return (
    <button
      onClick={onClick}
      className={`${color} text-xs font-medium hover:underline focus:outline-none`}
      title={`${key} · ${cell?.version_count ?? 0} version(s)`}
    >
      {icon}{label ? ` ${label}` : ''}
    </button>
  );
}
