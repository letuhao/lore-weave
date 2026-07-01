// Writing Studio (v2) — a VS Code-style docking workspace for a whole BOOK.
//
// This is a NEW, from-scratch surface (it does NOT touch the current ChapterEditorPage).
// dockview owns the layout: draggable / splittable / tabbable regions, floating groups,
// and pop-out windows, with the layout serialized per-book. Panels are added later, one at
// a time — for now the studio is intentionally blank (a single Welcome panel) so the shell,
// theme, and persistence are proven before any real tool goes in.
//
// Architecture note (carried over from the old in-house dock layer): live/in-flight state
// (co-writer streams, editor docs) must live ABOVE dockview and panels stay thin views over
// it, so closing/moving a panel never drops work. We wire that when the first stateful panel
// lands; the blank shell needs none of it yet.
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, LayoutDashboard } from 'lucide-react';
import {
  DockviewReact,
  themeAbyss,
  type DockviewReadyEvent,
  type DockviewApi,
  type IDockviewPanelProps,
} from 'dockview-react';
import 'dockview-core/dist/styles/dockview.css';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';

/** Per-book persisted layout (dockview api.toJSON()). Per-device UI state → localStorage. */
const layoutKey = (bookId: string) => `lw_studio_layout_${bookId}`;

/**
 * The panel component registry. dockview looks up a panel's `component` string here.
 * Blank for now except a Welcome placeholder — real tools (compose, planner, cast, …) are
 * added to this map one at a time as we build them.
 */
const PANEL_COMPONENTS: Record<string, React.FunctionComponent<IDockviewPanelProps>> = {
  welcome: WelcomePanel,
};

function WelcomePanel(_props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
      <LayoutDashboard className="h-8 w-8 text-muted-foreground/50" />
      <p className="text-sm font-medium text-foreground/80">
        {t('welcome.title', { defaultValue: 'Writing Studio' })}
      </p>
      <p className="max-w-sm text-xs text-muted-foreground">
        {t('welcome.body', {
          defaultValue:
            'A dockable workspace for this book. Panels (compose, planner, cast, quality…) will be added here one at a time. Drag tabs to split, stack, float, or pop out into their own window.',
        })}
      </p>
    </div>
  );
}

export function WritingStudioPage() {
  const { t } = useTranslation('studio');
  const { bookId = '' } = useParams();
  const { accessToken } = useAuth();
  const apiRef = useRef<DockviewApi | null>(null);
  const [bookTitle, setBookTitle] = useState('');

  useEffect(() => {
    if (!accessToken || !bookId) return;
    let mounted = true;
    booksApi.getBook(accessToken, bookId)
      .then((b) => { if (mounted) setBookTitle(b.title || ''); })
      .catch(() => { /* title is cosmetic */ });
    return () => { mounted = false; };
  }, [accessToken, bookId]);

  const onReady = useCallback((event: DockviewReadyEvent) => {
    const api = event.api;
    apiRef.current = api;

    // Persist on every layout change (add/move/split/resize/close). Registered BEFORE the
    // initial restore/seed so even the default layout is captured on first load.
    const disposable = api.onDidLayoutChange(() => {
      try { localStorage.setItem(layoutKey(bookId), JSON.stringify(api.toJSON())); } catch { /* quota */ }
    });

    // Restore the saved layout; fall back to a single Welcome panel. A saved layout that
    // references a panel no longer in the registry would throw on fromJSON — guarded so a
    // stale layout degrades to the blank default instead of a crash.
    let restored = false;
    try {
      const saved = localStorage.getItem(layoutKey(bookId));
      if (saved) { api.fromJSON(JSON.parse(saved)); restored = true; }
    } catch { restored = false; }

    if (!restored) {
      api.addPanel({ id: 'welcome', component: 'welcome', title: t('welcome.tab', { defaultValue: 'Welcome' }) });
    }

    return () => disposable.dispose();
  }, [bookId, t]);

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-background">
      {/* Thin chrome — back to book + title. The studio itself is dockview below. */}
      <div className="flex h-10 flex-shrink-0 items-center gap-2 border-b bg-card px-3 text-xs">
        <Link
          to={`/books/${bookId}`}
          className="flex items-center gap-1 rounded px-1.5 py-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
          title={t('back', { defaultValue: 'Back to book' })}
        >
          <ArrowLeft className="h-3.5 w-3.5" />
        </Link>
        <LayoutDashboard className="h-3.5 w-3.5 text-primary" />
        <span className="font-medium text-foreground">{t('title', { defaultValue: 'Writing Studio' })}</span>
        {bookTitle && (
          <>
            <span className="text-border">/</span>
            <span className="truncate text-muted-foreground">{bookTitle}</span>
          </>
        )}
      </div>

      <div className="relative min-h-0 flex-1">
        <DockviewReact
          onReady={onReady}
          components={PANEL_COMPONENTS}
          theme={themeAbyss}
          className="absolute inset-0"
        />
      </div>
    </div>
  );
}
