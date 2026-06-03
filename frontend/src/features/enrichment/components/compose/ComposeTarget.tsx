import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { COMPOSE_KINDS, type ComposeTargetInput } from '../../types';

interface Props {
  target: ComposeTargetInput;
  onChange: (t: ComposeTargetInput) => void;
}

/** The compose target — enrich an EXISTING glossary entity or create a NEW one.
 *  existing → the backend resolves it by name (target_ref = the name); new → the
 *  glossary anchor is minted only at PROMOTE (H0-clean), so target_ref stays null.
 *  View-only: state lives in ComposePanel. */
export function ComposeTarget({ target, onChange }: Props) {
  const { t } = useTranslation('enrichment');
  const setMode = (mode: 'existing' | 'new') =>
    onChange({ ...target, mode, target_ref: mode === 'new' ? null : target.canonical_name });

  return (
    <div className="space-y-3 rounded-lg border bg-card px-4 py-3">
      <div className="flex gap-2">
        {(['existing', 'new'] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            data-testid={`compose-target-mode-${m}`}
            className={cn(
              'rounded-md border px-3 py-1.5 text-xs font-medium transition-colors',
              target.mode === m
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border text-muted-foreground hover:text-foreground',
            )}
          >
            {t(`compose.target.${m}`)}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-4 text-xs">
        <label className="flex flex-1 items-center gap-2">
          <span className="text-muted-foreground">{t('compose.target.name')}</span>
          <input
            value={target.canonical_name}
            onChange={(e) =>
              onChange({
                ...target,
                canonical_name: e.target.value,
                // keep target_ref in sync with the name for the existing path.
                target_ref: target.mode === 'new' ? null : e.target.value,
              })
            }
            placeholder={t('compose.target.name_placeholder')}
            data-testid="compose-target-name"
            className="min-w-0 flex-1 rounded border bg-background px-2 py-1 font-serif"
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-muted-foreground">{t('compose.target.kind')}</span>
          <select
            value={target.entity_kind}
            onChange={(e) => onChange({ ...target, entity_kind: e.target.value })}
            data-testid="compose-target-kind"
            className="rounded border bg-background px-2 py-1"
          >
            {COMPOSE_KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`compose.kind.${k}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="text-[11px] text-muted-foreground">
        {target.mode === 'new' ? t('compose.target.new_hint') : t('compose.target.existing_hint')}
      </p>
    </div>
  );
}
