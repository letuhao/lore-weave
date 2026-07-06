// TranslationVersionsPanel — params-retargeting singleton ({chapterId, lang}), same precedent as
// OriginalSourcePanel/JsonEditorPanel: empty state with no chapterId, retarget via
// onDidParametersChange, self-titles with a chapter suffix. Resolves book_id from the studio host
// (not params) since the panel only ever opens inside a book's studio. Stubs
// ChapterTranslationsPanel (its own version-sidebar/compare/viewer logic is covered by its own
// tests) so this test stays about THIS panel's own wiring.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider } from '../../host/StudioHostProvider';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

vi.mock('@/features/translation/components/ChapterTranslationsPanel', () => ({
  ChapterTranslationsPanel: ({
    bookId,
    chapterId,
    initialLang,
    showBreadcrumb,
  }: {
    bookId: string;
    chapterId: string;
    initialLang?: string | null;
    showBreadcrumb?: boolean;
  }) => (
    <div
      data-testid="stub-chapter-translations-panel"
      data-book={bookId}
      data-chapter={chapterId}
      data-lang={initialLang ?? ''}
      data-breadcrumb={String(showBreadcrumb)}
    />
  ),
}));

import { TranslationVersionsPanel } from '../TranslationVersionsPanel';

function dockProps(params?: Record<string, unknown>) {
  let handler: ((next: Record<string, unknown> | undefined) => void) | null = null;
  const api = {
    setTitle: vi.fn(),
    onDidParametersChange: (cb: (next: Record<string, unknown> | undefined) => void) => {
      handler = cb;
      return { dispose: () => { handler = null; } };
    },
    updateParameters: (next: Record<string, unknown>) => handler?.(next),
  };
  return { api, params } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(<StudioHostProvider bookId={bookId}>{ui}</StudioHostProvider>);
}

beforeEach(() => {});

describe('TranslationVersionsPanel', () => {
  it('renders the empty state with no chapterId param', () => {
    withHost('b1', <TranslationVersionsPanel {...dockProps()} />);
    expect(screen.getByTestId('studio-translation-versions').textContent).toContain(
      "Open a chapter's translation versions from the Translation matrix.",
    );
    expect(screen.queryByTestId('stub-chapter-translations-panel')).toBeNull();
  });

  it('resolves book_id from the host and renders ChapterTranslationsPanel with showBreadcrumb=false (no internal DOCK-7 fix needed)', () => {
    withHost('b1', <TranslationVersionsPanel {...dockProps({ chapterId: 'ch1', lang: 'vi' })} />);
    const stub = screen.getByTestId('stub-chapter-translations-panel');
    expect(stub.getAttribute('data-book')).toBe('b1');
    expect(stub.getAttribute('data-chapter')).toBe('ch1');
    expect(stub.getAttribute('data-lang')).toBe('vi');
    expect(stub.getAttribute('data-breadcrumb')).toBe('false');
  });

  it('retargets to a new (chapterId, lang) via onDidParametersChange', async () => {
    const props = dockProps({ chapterId: 'ch1', lang: 'vi' });
    withHost('b1', <TranslationVersionsPanel {...props} />);
    expect(screen.getByTestId('stub-chapter-translations-panel').getAttribute('data-chapter')).toBe('ch1');

    (props.api as unknown as { updateParameters: (n: Record<string, unknown>) => void })
      .updateParameters({ chapterId: 'ch2', lang: 'ja' });

    await waitFor(() => {
      const stub = screen.getByTestId('stub-chapter-translations-panel');
      expect(stub.getAttribute('data-chapter')).toBe('ch2');
      expect(stub.getAttribute('data-lang')).toBe('ja');
    });
  });

  it('sets the dock tab title with a chapter suffix', () => {
    const props = dockProps({ chapterId: '0199aabbccdd', lang: 'vi' });
    withHost('b1', <TranslationVersionsPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalledWith('Translation Versions · 0199aabb');
  });
});
