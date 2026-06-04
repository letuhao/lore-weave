import { useTranslation } from 'react-i18next';
import { Upload, X, FileText, AlertTriangle, Loader2, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ContextLicense } from '../../types';
import type { UploadItem } from '../../hooks/useUploads';

interface Props {
  items: UploadItem[];
  onAddFiles: (files: File[]) => void;
  onRemove: (id: string) => void;
  license: ContextLicense;
  onLicenseChange: (l: ContextLicense) => void;
  responsibilityChecked: boolean;
  onResponsibilityChange: (v: boolean) => void;
}

const LICENSES: ContextLicense[] = ['public_domain', 'licensed', 'owned', 'copyrighted'];
const ACCEPT = '.txt,.md,.pdf,.docx,.epub';

/** Mode F form — attach files (.txt/.md/.pdf/.docx/.epub). Each file uploads + is
 *  extracted (+OCR) in the background; the row shows its status. License is asserted
 *  for the batch (copyrighted is default-denied + disables Run upstream). View-only:
 *  state lives in ComposePanel (+ useUploads for the item list). */
export function ComposeFilesForm({
  items, onAddFiles, onRemove, license, onLicenseChange, responsibilityChecked, onResponsibilityChange,
}: Props) {
  const { t } = useTranslation('enrichment');
  const blocked = license === 'copyrighted';

  const pick = (fileList: FileList | null) => {
    if (fileList && fileList.length) onAddFiles(Array.from(fileList));
  };

  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          {t('compose.files.license_label')}
        </label>
        <select
          value={license}
          onChange={(e) => onLicenseChange(e.target.value as ContextLicense)}
          data-testid="compose-files-license"
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        >
          {LICENSES.map((l) => (
            <option key={l} value={l}>{t(`compose.context.license.${l}`)}</option>
          ))}
        </select>
        {blocked && (
          <p data-testid="compose-files-copyright-warning" className="mt-1 flex items-start gap-1 text-[11px] text-destructive">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
            {t('compose.context.copyrighted_warning')}
          </p>
        )}
      </div>

      <label
        className="flex cursor-pointer flex-col items-center gap-1 rounded-md border border-dashed px-3 py-6 text-center text-xs text-muted-foreground hover:bg-muted/40"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files); }}
      >
        <Upload className="h-5 w-5" />
        <span>{t('compose.files.dropzone')}</span>
        <span className="text-[10px] opacity-70">{t('compose.files.accept')}</span>
        <input
          type="file"
          multiple
          accept={ACCEPT}
          data-testid="compose-files-input"
          className="hidden"
          onChange={(e) => pick(e.target.files)}
        />
      </label>

      {items.length > 0 && (
        <ul className="space-y-1">
          {items.map((it) => (
            <li
              key={it.id}
              data-testid={`compose-files-item-${it.id}`}
              className="flex items-center gap-2 rounded-md border px-2 py-1.5 text-xs"
            >
              {it.status === 'processing' && <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />}
              {it.status === 'ready' && <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-green-600" />}
              {it.status === 'failed' && <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-destructive" />}
              {it.status === 'ready' && it.result && (it.result.extracted_chars ?? 0) === 0 && (
                <FileText className="h-3.5 w-3.5 shrink-0 text-amber-500" />
              )}
              <span className="flex-1 truncate">{it.filename}</span>
              <span className="text-[10px] text-muted-foreground">
                {it.status === 'ready' && it.result
                  ? t('compose.files.ready', {
                      chars: it.result.extracted_chars ?? 0,
                      ocr: it.result.ocr_used ? ` · ${t('compose.files.ocr')}` : '',
                    })
                  : it.status === 'failed'
                    ? (it.error || t('compose.files.failed'))
                    : t('compose.files.processing')}
              </span>
              <button
                type="button"
                onClick={() => onRemove(it.id)}
                data-testid={`compose-files-remove-${it.id}`}
                className="rounded p-0.5 text-muted-foreground hover:text-destructive"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <label className="flex items-start gap-2 text-[11px] text-muted-foreground">
        <input
          type="checkbox"
          checked={responsibilityChecked}
          onChange={(e) => onResponsibilityChange(e.target.checked)}
          data-testid="compose-files-responsibility"
          className="mt-0.5"
        />
        <span>{t('compose.files.responsibility')}</span>
      </label>
    </div>
  );
}
