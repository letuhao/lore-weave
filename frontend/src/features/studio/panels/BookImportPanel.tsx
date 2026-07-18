// docs/specs/2026-07-06-pdf-book-import.md + the classic ChaptersTab's import toolbar —
// ported into the Writing Studio dock so import is reachable without leaving the studio
// (D-STUDIO-IMPORT-PANEL). Reuses the SAME dialogs ChaptersTab renders (ImportDialog,
// PdfImportWizard) rather than forking their logic (DOCK-2 precedent — BooksBrowserPanel does
// the same with useBooksList).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { FileText, Upload } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { ImportDialog } from '@/components/import/ImportDialog';
import { PdfImportWizard } from '@/features/pdf-import/PdfImportWizard';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function BookImportPanel(props: IDockviewPanelProps) {
  useStudioPanel('book-import', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const queryClient = useQueryClient();
  const [importOpen, setImportOpen] = useState(false);
  const [pdfImportOpen, setPdfImportOpen] = useState(false);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['chapters', host.bookId] });

  return (
    <div data-testid="studio-book-import-panel" className="flex h-full min-h-0 flex-col gap-4 overflow-auto p-4">
      <p className="text-sm text-muted-foreground">{t('panels.book-import.intro')}</p>

      <div className="grid gap-3 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => setImportOpen(true)}
          data-testid="book-import-open-text"
          className="flex items-start gap-3 rounded-lg border p-4 text-left transition-colors hover:border-[hsl(var(--border-hover,25_6%_24%))] hover:bg-card"
        >
          <Upload className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground" />
          <div>
            <div className="text-sm font-medium">{t('panels.book-import.text.title')}</div>
            <div className="mt-0.5 text-xs text-muted-foreground">{t('panels.book-import.text.desc')}</div>
          </div>
        </button>

        <button
          type="button"
          onClick={() => setPdfImportOpen(true)}
          data-testid="book-import-open-pdf"
          className="flex items-start gap-3 rounded-lg border p-4 text-left transition-colors hover:border-[hsl(var(--border-hover,25_6%_24%))] hover:bg-card"
        >
          <FileText className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground" />
          <div>
            <div className="text-sm font-medium">{t('panels.book-import.pdf.title')}</div>
            <div className="mt-0.5 text-xs text-muted-foreground">{t('panels.book-import.pdf.desc')}</div>
          </div>
        </button>
      </div>

      <ImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        bookId={host.bookId}
        onImported={invalidate}
      />

      <PdfImportWizard
        open={pdfImportOpen}
        onOpenChange={setPdfImportOpen}
        bookId={host.bookId}
        onComplete={invalidate}
      />
    </div>
  );
}
