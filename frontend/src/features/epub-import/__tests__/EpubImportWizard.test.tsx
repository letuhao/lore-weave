import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'token' }) }));

const apiMocks = vi.hoisted(() => ({
  inspectEpub: vi.fn(),
  startEpubImport: vi.fn(),
  getEpubImportJob: vi.fn(),
  getEpubImportReport: vi.fn(),
  cancelEpubImport: vi.fn(),
  resumeEpubImport: vi.fn(),
  rollbackEpubImport: vi.fn(),
}));
vi.mock('@/features/books/api', () => ({
  booksApi: apiMocks,
}));

import { EpubImportWizard } from '../EpubImportWizard';

const inspection = {
  source_id: 'source-1',
  sha256: 'sha',
  duplicate_source: false,
  navigation_source: 'epub3-nav',
  metadata: { title: 'Fixture EPUB', language: 'en', subjects: ['Fantasy'] },
  warnings: [],
  structure: [{
    source_key: 'part', source_href: 'part.xhtml', title: 'Part I', depth: 0, ordinal: 0, role: 'part', linear: true, selected: false,
    children: [{ source_key: 'chapter-1', source_href: 'chapter-1.xhtml', title: 'Chapter one', depth: 1, ordinal: 1, role: 'chapter', linear: true, selected: true, children: [] }],
  }],
};

function renderWizard() {
  return render(<MemoryRouter><EpubImportWizard open onOpenChange={vi.fn()} bookId="book-1" onImported={vi.fn()} /></MemoryRouter>);
}

beforeEach(() => {
  window.localStorage.clear();
  apiMocks.inspectEpub.mockReset().mockResolvedValue(inspection);
  apiMocks.startEpubImport.mockReset().mockResolvedValue({ job_id: 'job-1', book_id: 'book-1', status: 'queued' });
  apiMocks.getEpubImportJob.mockReset().mockResolvedValue({ job_id: 'job-1', book_id: 'book-1', source_id: 'source-1', status: 'queued', progress_total: 1, progress_completed: 0, progress_failed: 0, chapters_created: 0, warnings: [], errors: [], resumable: false, cancellable: true, rollback_available: false });
  apiMocks.getEpubImportReport.mockReset();
  apiMocks.cancelEpubImport.mockReset().mockResolvedValue(undefined);
  apiMocks.resumeEpubImport.mockReset().mockResolvedValue(undefined);
  apiMocks.rollbackEpubImport.mockReset().mockResolvedValue(undefined);
});

describe('EpubImportWizard', () => {
  it('requires an explicit replace-all confirmation and submits the selected metadata policy', async () => {
    renderWizard();
    const file = new File(['epub'], 'fixture.epub', { type: 'application/epub+zip' });
    fireEvent.change(screen.getByTestId('epub-import-file-input'), { target: { files: [file] } });

    await screen.findByText('Fixture EPUB');
    fireEvent.change(screen.getByTestId('epub-import-metadata-title'), { target: { value: 'use_source' } });
    fireEvent.click(screen.getByTestId('epub-import-next'));
    fireEvent.click(screen.getByTestId('epub-import-next'));
    fireEvent.click(screen.getByRole('radio', { name: 'epubImport.strategy.replace_all' }));
    fireEvent.click(screen.getByTestId('epub-import-option-import_images'));

    expect(screen.getByTestId('epub-import-next')).toBeDisabled();
    fireEvent.click(screen.getByTestId('epub-import-replace-confirmation'));
    fireEvent.click(screen.getByTestId('epub-import-next'));

    await waitFor(() => expect(apiMocks.startEpubImport).toHaveBeenCalledWith('token', expect.objectContaining({
      source_id: 'source-1',
      strategy: 'replace_all',
      destructive_confirmation: true,
      metadata_policy: expect.objectContaining({ title: 'use_source', subjects: 'merge', cover: 'use_source' }),
      selected_source_keys: ['chapter-1'],
      options: expect.objectContaining({ import_images: false, preserve_hierarchy: true }),
    })));
  });

  it('does not submit a chapter that was deselected in the table of contents', async () => {
    apiMocks.inspectEpub.mockResolvedValue({
      ...inspection,
      structure: [{
        ...inspection.structure[0],
        children: [
          ...inspection.structure[0].children,
          { source_key: 'chapter-2', source_href: 'chapter-2.xhtml', title: 'Chapter two', depth: 1, ordinal: 2, role: 'chapter', linear: true, selected: true, children: [] },
        ],
      }],
    });
    renderWizard();
    const file = new File(['epub'], 'fixture.epub', { type: 'application/epub+zip' });
    fireEvent.change(screen.getByTestId('epub-import-file-input'), { target: { files: [file] } });

    await screen.findByText('Fixture EPUB');
    fireEvent.click(screen.getByTestId('epub-import-next'));
    const [firstChapter] = screen.getAllByRole('checkbox', { name: 'epubImport.selectChapter' });
    fireEvent.click(firstChapter);
    fireEvent.click(screen.getByTestId('epub-import-next'));
    fireEvent.click(screen.getByTestId('epub-import-next'));

    await waitFor(() => expect(apiMocks.startEpubImport).toHaveBeenCalledWith('token', expect.objectContaining({
      selected_source_keys: ['chapter-2'],
    })));
  });

  it('restores the durable terminal report when the wizard is reopened', async () => {
    window.localStorage.setItem('loreweave:epub-import-job:book-1', 'job-1');
    apiMocks.getEpubImportJob.mockResolvedValue({ job_id: 'job-1', book_id: 'book-1', source_id: 'source-1', status: 'completed_with_warnings', progress_total: 1, progress_completed: 1, progress_failed: 0, chapters_created: 1, warnings: ['source_warning'], errors: [], resumable: false, cancellable: false, rollback_available: true });
    apiMocks.getEpubImportReport.mockResolvedValue({ job_id: 'job-1', status: 'completed_with_warnings', chapters_created: 1, warnings: ['source_warning'], errors: [] });

    renderWizard();

    await screen.findByTestId('epub-import-report-summary');
    expect(apiMocks.getEpubImportJob).toHaveBeenCalledWith('token', 'job-1');
    expect(apiMocks.getEpubImportReport).toHaveBeenCalledWith('token', 'job-1');
    expect(screen.getByTestId('epub-import-report-warnings')).toHaveTextContent('source_warning');
  });

  it('sends resume and rollback controls to the restored durable job', async () => {
    window.localStorage.setItem('loreweave:epub-import-job:book-1', 'job-1');
    apiMocks.getEpubImportJob.mockResolvedValue({ job_id: 'job-1', book_id: 'book-1', source_id: 'source-1', status: 'cancelled', progress_total: 1, progress_completed: 0, progress_failed: 0, chapters_created: 0, warnings: [], errors: [], resumable: true, cancellable: false, rollback_available: true });
    apiMocks.getEpubImportReport.mockResolvedValue({ job_id: 'job-1', status: 'cancelled', chapters_created: 0, warnings: [], errors: [] });

    renderWizard();

    await screen.findByTestId('epub-import-resume');
    fireEvent.click(screen.getByTestId('epub-import-resume'));
    await waitFor(() => expect(apiMocks.resumeEpubImport).toHaveBeenCalledWith('token', 'job-1'));
    fireEvent.click(screen.getByTestId('epub-import-rollback'));
    await waitFor(() => expect(apiMocks.rollbackEpubImport).toHaveBeenCalledWith('token', 'job-1'));
  });
});
