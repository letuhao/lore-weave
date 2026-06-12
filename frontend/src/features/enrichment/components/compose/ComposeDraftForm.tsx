import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import type { ExpandMode } from '../../types';

interface Props {
  draftText: string;
  onDraftChange: (v: string) => void;
  expandMode: ExpandMode;
  onExpandModeChange: (m: ExpandMode) => void;
}

const EXPAND_MODES: ExpandMode[] = ['rewrite', 'add_only'];

/** Mode D form — the author's draft + how to expand it (add_only keeps the prose
 *  verbatim and only adds missing dimensions; rewrite voice-syncs to the book's
 *  profile, preserving meaning). View-only: state lives in ComposePanel. */
export function ComposeDraftForm({ draftText, onDraftChange, expandMode, onExpandModeChange }: Props) {
  const { t } = useTranslation('enrichment');
  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          {t('compose.draft.label')}
        </label>
        <textarea
          value={draftText}
          onChange={(e) => onDraftChange(e.target.value)}
          rows={6}
          placeholder={t('compose.draft.placeholder')}
          data-testid="compose-draft-text"
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        />
      </div>
      <div>
        <span className="mb-1 block text-xs font-medium text-muted-foreground">
          {t('compose.draft.expand_mode')}
        </span>
        <div className="flex gap-2">
          {EXPAND_MODES.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => onExpandModeChange(m)}
              data-testid={`compose-expand-${m}`}
              className={cn(
                'flex-1 rounded-md border px-3 py-2 text-left text-xs transition-colors',
                expandMode === m
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-muted-foreground hover:text-foreground',
              )}
            >
              <span className="block font-semibold">{t(`compose.draft.${m}`)}</span>
              <span className="block text-[11px] opacity-80">{t(`compose.draft.${m}_hint`)}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
