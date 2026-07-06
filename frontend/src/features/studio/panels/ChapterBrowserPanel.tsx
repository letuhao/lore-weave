// 15_chapter_browser.md B1 — the `chapter-browser` dock panel shell: a Title-vs-Content
// search-mode toggle over two independently-buildable sub-components (CB2 — kept as separate
// files for build/test hygiene, NOT because DOCK-8 requires a catalog split here — Title-search
// and Content-search are the SAME "find a chapter in this book" capability with two strategies,
// same accepted in-panel-toggle shape RawSearchPanel already uses; see the spec's DOCK-8 analysis).
//
// Both views stay MOUNTED across a mode switch (CSS `hidden`, never a ternary unmount) per this
// repo's "never conditionally unmount stateful components" FE rule — Title-mode's search/filter/
// selection state and Content-mode's own search state would otherwise reset on every toggle.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { List, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { ChapterBrowserTitleView } from './ChapterBrowserTitleView';
import { ChapterBrowserContentView } from './ChapterBrowserContentView';

type SearchMode = 'title' | 'content';

export function ChapterBrowserPanel(props: IDockviewPanelProps) {
  useStudioPanel('chapter-browser', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const [mode, setMode] = useState<SearchMode>('title');

  return (
    <div data-testid="studio-chapter-browser-panel" className="flex h-full min-h-0 flex-col">
      <div
        className="flex items-center gap-1 border-b p-2"
        role="group"
        aria-label={t('panels.chapter-browser.mode_group', { defaultValue: 'Search mode' })}
      >
        <button
          type="button"
          onClick={() => setMode('title')}
          data-testid="chapter-browser-mode-title"
          aria-pressed={mode === 'title'}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
            mode === 'title' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <List className="h-3.5 w-3.5" />
          {t('panels.chapter-browser.mode_title', { defaultValue: 'Title & filename' })}
        </button>
        <button
          type="button"
          onClick={() => setMode('content')}
          data-testid="chapter-browser-mode-content"
          aria-pressed={mode === 'content'}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
            mode === 'content' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <Search className="h-3.5 w-3.5" />
          {t('panels.chapter-browser.mode_content', { defaultValue: 'Content (full-text)' })}
        </button>
      </div>

      <div
        data-testid="chapter-browser-title-body"
        className={cn('min-h-0 flex-1 overflow-auto', mode !== 'title' && 'hidden')}
      >
        <ChapterBrowserTitleView bookId={host.bookId} />
      </div>
      <div
        data-testid="chapter-browser-content-body"
        className={cn('min-h-0 flex-1 overflow-auto', mode !== 'content' && 'hidden')}
      >
        <ChapterBrowserContentView bookId={host.bookId} />
      </div>
    </div>
  );
}
