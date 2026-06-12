import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';
import type { ContextLicense } from '../../types';

interface Props {
  contextText: string;
  onContextTextChange: (v: string) => void;
  license: ContextLicense;
  onLicenseChange: (l: ContextLicense) => void;
}

const LICENSES: ContextLicense[] = ['public_domain', 'licensed', 'owned', 'copyrighted'];

/** Mode C form — paste reference text + assert its license. The pasted text is
 *  ingested as a grounding corpus on run; a retrieval/recook job then grounds on it.
 *  `copyrighted` is default-denied by the backend (and disables Run upstream), so the
 *  author must own / license / use public-domain material. View-only: state lives in
 *  ComposePanel. */
export function ComposeContextForm({ contextText, onContextTextChange, license, onLicenseChange }: Props) {
  const { t } = useTranslation('enrichment');
  const blocked = license === 'copyrighted';
  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          {t('compose.context.label')}
        </label>
        <textarea
          value={contextText}
          onChange={(e) => onContextTextChange(e.target.value)}
          rows={6}
          placeholder={t('compose.context.placeholder')}
          data-testid="compose-context-text"
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        />
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          {t('compose.context.license_label')}
        </label>
        <select
          value={license}
          onChange={(e) => onLicenseChange(e.target.value as ContextLicense)}
          data-testid="compose-context-license"
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        >
          {LICENSES.map((l) => (
            <option key={l} value={l}>
              {t(`compose.context.license.${l}`)}
            </option>
          ))}
        </select>
        {blocked && (
          <p
            data-testid="compose-context-copyright-warning"
            className="mt-1 flex items-start gap-1 text-[11px] text-destructive"
          >
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
            {t('compose.context.copyrighted_warning')}
          </p>
        )}
        <p className="mt-1 text-[11px] text-muted-foreground">{t('compose.context.responsibility')}</p>
      </div>
    </div>
  );
}
