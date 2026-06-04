import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { COMPOSE_KINDS, type ComposeTargetInput } from '../../types';

/** Minimal shape of a glossary entity name option (from useBookEntities). */
export interface ComposeEntityOption {
  display_name: string;
  kind_code?: string;
}

interface Props {
  target: ComposeTargetInput;
  onChange: (t: ComposeTargetInput) => void;
  /** The book's existing entities, for the existing-target autocomplete
   *  (D-COMPOSE-EXISTING-PICKER). Empty → the name field is plain free-text. */
  entities?: ComposeEntityOption[];
}

/** The compose target — enrich an EXISTING glossary entity or create a NEW one.
 *  existing → the backend resolves it by name (target_ref = the name); new → the
 *  glossary anchor is minted only at PROMOTE (H0-clean), so target_ref stays null.
 *  View-only: state lives in ComposePanel. */
export function ComposeTarget({ target, onChange, entities = [] }: Props) {
  const { t } = useTranslation('enrichment');
  const setMode = (mode: 'existing' | 'new') =>
    onChange({ ...target, mode, target_ref: mode === 'new' ? null : target.canonical_name });

  // Existing-target autocomplete: when the typed name matches a known entity, also
  // prefill the kind (only when its glossary kind_code is one we model — never a
  // wrong guess). New-entity mode stays plain free-text (the entity doesn't exist yet).
  const showPicker = target.mode === 'existing' && entities.length > 0;
  const onNameChange = (value: string) => {
    const next: ComposeTargetInput = {
      ...target,
      canonical_name: value,
      target_ref: target.mode === 'new' ? null : value,
    };
    const match = entities.find((e) => e.display_name === value);
    if (match?.kind_code && (COMPOSE_KINDS as readonly string[]).includes(match.kind_code)) {
      next.entity_kind = match.kind_code;
    }
    onChange(next);
  };

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
            onChange={(e) => onNameChange(e.target.value)}
            placeholder={t('compose.target.name_placeholder')}
            data-testid="compose-target-name"
            list={showPicker ? 'compose-entity-list' : undefined}
            autoComplete="off"
            className="min-w-0 flex-1 rounded border bg-background px-2 py-1 font-serif"
          />
          {showPicker && (
            <datalist id="compose-entity-list" data-testid="compose-entity-list">
              {entities.map((e) => (
                <option key={e.display_name} value={e.display_name} />
              ))}
            </datalist>
          )}
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
