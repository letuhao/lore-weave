// docs/specs/2026-07-06-pdf-book-import.md — PDF import wizard types.

export type PdfImportStep = 'upload' | 'configure' | 'confirm' | 'progress' | 'results';

export const PDF_IMPORT_STEPS: PdfImportStep[] = ['upload', 'configure', 'confirm', 'progress', 'results'];

export type PdfImportState = {
  step: PdfImportStep;
  stepIndex: number;
  file: File | null;
  pageCount: number | null;
  /** True once pdf-peek has returned successfully for the current file. */
  peeked: boolean;
  peekError: string | null;
  pagesPerChunk: number;
  captionImages: boolean;
  modelSource: string | null;
  modelRef: string | null;
  jobId: string | null;
};
