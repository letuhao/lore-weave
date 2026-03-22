import { useNavigate } from 'react-router-dom';
import type { Chapter } from '@/features/books/api';
import type { ChapterCoverage } from '@/features/translation/versionsApi';
import { TranslationStatusCell } from './TranslationStatusCell';

type Props = {
  bookId: string;
  chapters: Chapter[];
  coverage: ChapterCoverage[];
  knownLanguages: string[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
};

export function TranslationMatrix({
  bookId,
  chapters,
  coverage,
  knownLanguages,
  selectedIds,
  onToggle,
  onSelectAll,
  onDeselectAll,
}: Props) {
  const navigate = useNavigate();

  // Build coverage lookup: chapter_id → { lang → CoverageCell }
  const coverageMap = new Map(coverage.map((c) => [c.chapter_id, c.languages]));

  const allSelected = selectedIds.length === chapters.length && chapters.length > 0;
  const someSelected = selectedIds.length > 0 && !allSelected;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className="w-8 px-2 py-2 text-left">
              <input
                type="checkbox"
                checked={allSelected}
                ref={(el) => { if (el) el.indeterminate = someSelected; }}
                onChange={() => (allSelected ? onDeselectAll() : onSelectAll())}
              />
            </th>
            <th className="px-2 py-2 text-left text-xs font-medium text-muted-foreground">#</th>
            <th className="px-2 py-2 text-left text-xs font-medium text-muted-foreground">Title</th>
            {knownLanguages.map((lang) => (
              <th key={lang} className="px-2 py-2 text-center text-xs font-medium text-muted-foreground">
                {lang}
              </th>
            ))}
            <th className="px-2 py-2 text-right text-xs font-medium text-muted-foreground">Actions</th>
          </tr>
        </thead>
        <tbody>
          {chapters.map((c) => {
            const langCoverage = coverageMap.get(c.chapter_id) ?? {};
            const checked = selectedIds.includes(c.chapter_id);
            return (
              <tr
                key={c.chapter_id}
                className={`border-b transition-colors ${checked ? 'bg-primary/5' : 'hover:bg-muted/50'}`}
              >
                <td className="px-2 py-2">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onToggle(c.chapter_id)}
                  />
                </td>
                <td className="px-2 py-2 text-muted-foreground">{c.sort_order}</td>
                <td className="px-2 py-2 font-medium">
                  {c.title || c.original_filename}
                </td>
                {knownLanguages.map((lang) => (
                  <td key={lang} className="px-2 py-2 text-center">
                    <TranslationStatusCell
                      cell={langCoverage[lang]}
                      onClick={() =>
                        navigate(
                          `/books/${bookId}/chapters/${c.chapter_id}/translations?lang=${lang}`
                        )
                      }
                    />
                  </td>
                ))}
                <td className="px-2 py-2 text-right">
                  <button
                    onClick={() =>
                      navigate(`/books/${bookId}/chapters/${c.chapter_id}/translations`)
                    }
                    className="text-xs text-muted-foreground hover:underline"
                  >
                    versions
                  </button>
                </td>
              </tr>
            );
          })}
          {chapters.length === 0 && (
            <tr>
              <td colSpan={3 + knownLanguages.length + 1} className="px-2 py-4 text-center text-sm text-muted-foreground">
                No chapters found.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {/* Select helpers */}
      <div className="flex gap-3 px-2 py-2 text-xs text-muted-foreground">
        <button className="hover:underline" onClick={onSelectAll}>Select all</button>
        <button className="hover:underline" onClick={onDeselectAll}>Deselect all</button>
        <span>{selectedIds.length} selected</span>
      </div>
    </div>
  );
}
