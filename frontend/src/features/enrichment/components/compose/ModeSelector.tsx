import { useTranslation } from 'react-i18next';
import { FileText, PencilLine, ClipboardPaste, Upload, Wand2 } from 'lucide-react';
import { cn } from '@/lib/utils';

/** The compose input modes. Active: D (draft) + C (context) + F (files) + B (intent);
 *  A (gap-fill) routes to the Gaps tab (it already lives there). E (web search) was
 *  dropped (copyright-indefensible). All five input sources now ship. */
export type ComposeMode = 'draft' | 'gap' | 'intent' | 'context' | 'files';

const MODES: { key: ComposeMode; icon: typeof Wand2; status: 'active' | 'gaps' | 'soon' }[] = [
  { key: 'draft', icon: PencilLine, status: 'active' },
  { key: 'gap', icon: Wand2, status: 'gaps' },
  { key: 'context', icon: ClipboardPaste, status: 'active' },
  { key: 'files', icon: Upload, status: 'active' },
  { key: 'intent', icon: FileText, status: 'active' },
];

interface Props {
  mode: ComposeMode;
  onSelect: (m: ComposeMode) => void;
  /** Mode A (gap-fill) lives in the Gaps tab — selecting it routes there. */
  onUseGaps: () => void;
}

/** The mode picker row — one chip per input mode. Only `draft` is selectable in
 *  slice 1; `gap` routes to the Gaps tab; the rest are disabled with a "coming soon"
 *  hint. View-only: state lives in the parent ComposePanel. */
export function ModeSelector({ mode, onSelect, onUseGaps }: Props) {
  const { t } = useTranslation('enrichment');
  return (
    <div className="flex flex-wrap gap-2">
      {MODES.map(({ key, icon: Icon, status }) => {
        const disabled = status === 'soon';
        const active = status === 'active' && mode === key;
        return (
          <button
            key={key}
            type="button"
            disabled={disabled}
            data-testid={`compose-mode-${key}`}
            title={disabled ? t('compose.mode_soon') : undefined}
            onClick={() => (status === 'gaps' ? onUseGaps() : onSelect(key))}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors',
              active
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border text-muted-foreground hover:text-foreground',
              disabled && 'cursor-not-allowed opacity-40 hover:text-muted-foreground',
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            <span>{t(`compose.mode.${key}`)}</span>
            {disabled && <span className="text-[10px]">{t('compose.soon')}</span>}
          </button>
        );
      })}
    </div>
  );
}
