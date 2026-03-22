import { Link } from 'react-router-dom';
import type { CoverageCell } from '@/features/translation/versionsApi';
import { deriveCellStatus, STATUS_COLOR, STATUS_ICON } from './TranslationStatusCell';

type Props = {
  bookId: string;
  chapterId: string;
  /** Map of language code → coverage cell (from coverage API) */
  coverage: Record<string, CoverageCell> | undefined;
};

export function LanguageStatusDots({ bookId, chapterId, coverage }: Props) {
  if (!coverage || Object.keys(coverage).length === 0) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }

  return (
    <span className="flex flex-wrap gap-1">
      {Object.entries(coverage).map(([lang, cell]) => {
        const key = deriveCellStatus(cell);
        const color = STATUS_COLOR[key];
        const icon = STATUS_ICON[key];
        const tip = cell?.has_active
          ? `${lang}: v${cell.active_version_num} active`
          : cell?.version_count
          ? `${lang}: ${cell.version_count} version(s), not set active`
          : `${lang}: no translation`;

        return (
          <Link
            key={lang}
            to={`/books/${bookId}/chapters/${chapterId}/translations?lang=${lang}`}
            className={`${color} text-xs font-medium hover:underline`}
            title={tip}
          >
            {lang}{icon}
          </Link>
        );
      })}
    </span>
  );
}
