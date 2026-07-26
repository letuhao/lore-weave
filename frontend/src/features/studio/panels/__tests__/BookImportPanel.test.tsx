// BookImportPanel — the classic ChaptersTab's import toolbar (ImportDialog + PdfImportWizard)
// ported into the studio dock (D-STUDIO-IMPORT-PANEL). Both dialogs are stubbed (their own
// upload/parse/WS-polling logic is covered by their own tests); this test is about THIS panel's
// own wiring: registration/self-titling, bookId resolution from the studio host, opening each
// dialog from its launcher card, and the invalidate-on-complete wiring (DOCK-2 precedent —
// mirrors BookSettingsPanel.test.tsx's thin-wrapper shape).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/components/import/ImportDialog', () => ({
  ImportDialog: ({ open, onOpenChange, bookId, onImported }: {
    open: boolean; onOpenChange: (o: boolean) => void; bookId: string; onImported: () => void;
  }) => (
    open ? (
      <div data-testid="stub-import-dialog" data-book={bookId}>
        <button onClick={() => { onImported(); onOpenChange(false); }}>complete-text-import</button>
      </div>
    ) : null
  ),
}));

vi.mock('@/features/pdf-import/PdfImportWizard', () => ({
  PdfImportWizard: ({ open, onOpenChange, bookId, onComplete }: {
    open: boolean; onOpenChange: (o: boolean) => void; bookId: string; onComplete?: () => void;
  }) => (
    open ? (
      <div data-testid="stub-pdf-import-wizard" data-book={bookId}>
        <button onClick={() => { onComplete?.(); onOpenChange(false); }}>complete-pdf-import</button>
      </div>
    ) : null
  ),
}));

import { BookImportPanel } from '../BookImportPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { qc, ...render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>
    </QueryClientProvider>,
  ) };
}

beforeEach(() => { hostRef = null; });

describe('BookImportPanel', () => {
  it('registers with the host and titles its dock tab', () => {
    const props = dockProps();
    withHost('book-1', <BookImportPanel {...props} />);
    expect(hostRef!.getRegisteredTool('book-import')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('book-import')!.commandId).toBe('studio.openPanel.book-import');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('opens ImportDialog scoped to the host bookId, resolved from the studio host not a route param', () => {
    withHost('book-42', <BookImportPanel {...dockProps()} />);
    fireEvent.click(screen.getByTestId('book-import-open-text'));
    expect(screen.getByTestId('stub-import-dialog')).toHaveAttribute('data-book', 'book-42');
  });

  it('opens PdfImportWizard scoped to the host bookId', () => {
    withHost('book-42', <BookImportPanel {...dockProps()} />);
    fireEvent.click(screen.getByTestId('book-import-open-pdf'));
    expect(screen.getByTestId('stub-pdf-import-wizard')).toHaveAttribute('data-book', 'book-42');
  });

  it('invalidates the chapters query when the text import completes', () => {
    const { qc } = withHost('book-42', <BookImportPanel {...dockProps()} />);
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    fireEvent.click(screen.getByTestId('book-import-open-text'));
    fireEvent.click(screen.getByText('complete-text-import'));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['chapters', 'book-42'] });
  });

  it('invalidates the chapters query when the PDF import completes', () => {
    const { qc } = withHost('book-42', <BookImportPanel {...dockProps()} />);
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
    fireEvent.click(screen.getByTestId('book-import-open-pdf'));
    fireEvent.click(screen.getByText('complete-pdf-import'));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['chapters', 'book-42'] });
  });
});
