// Render-only steering editor form. Holds its own controlled draft state (view-local form
// state — permitted); all persistence logic lives in useSteering. match_pattern shows only for
// scene_match; the 8000-char body counter turns warning past the cap; the `auto` mode carries a
// v1-honesty note (auto currently behaves like manual).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { INCLUSION_MODES, STEERING_LIMITS, type InclusionMode, type SteeringEntry, type SteeringInput } from '../types';
import type { SteeringErrorKind } from '../hooks/useSteering';

interface Props {
  initial: SteeringEntry | null;
  saving: boolean;
  errorKind: SteeringErrorKind;
  onSubmit: (payload: SteeringInput) => void;
  onCancel: () => void;
}

export function SteeringEditor({ initial, saving, errorKind, onSubmit, onCancel }: Props) {
  const { t } = useTranslation('studio');
  const [name, setName] = useState(initial?.name ?? '');
  const [body, setBody] = useState(initial?.body ?? '');
  const [mode, setMode] = useState<InclusionMode>(initial?.inclusion_mode ?? 'always');
  const [matchPattern, setMatchPattern] = useState(initial?.match_pattern ?? '');
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);

  const bodyOver = body.length > STEERING_LIMITS.bodyMax;
  const nameOver = name.length > STEERING_LIMITS.nameMax;
  const invalid = !name.trim() || !body.trim() || bodyOver || nameOver;

  const submit = () => {
    if (invalid || saving) return;
    onSubmit({
      name: name.trim(),
      body,
      inclusion_mode: mode,
      match_pattern: mode === 'scene_match' ? matchPattern.trim() || null : null,
      enabled,
    });
  };

  const field = 'w-full rounded border bg-background px-2 py-1 text-[13px]';

  return (
    <div data-testid="steering-editor" className="flex flex-col gap-3 p-3 text-[13px]">
      <label className="flex flex-col gap-1">
        <span className="text-[11px] font-medium text-muted-foreground">{t('steering.form.name')}</span>
        <input
          data-testid="steering-form-name" className={cn(field, nameOver && 'border-destructive')}
          value={name} maxLength={STEERING_LIMITS.nameMax + 20}
          placeholder={t('steering.form.namePlaceholder')} onChange={(e) => setName(e.target.value)}
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="flex items-center justify-between text-[11px] font-medium text-muted-foreground">
          {t('steering.form.body')}
          <span data-testid="steering-form-body-count" className={cn('font-mono', bodyOver && 'text-destructive')}>
            {t('steering.charCount', { n: body.length, max: STEERING_LIMITS.bodyMax })}
          </span>
        </span>
        <textarea
          data-testid="steering-form-body" rows={6} className={cn(field, 'resize-y font-mono', bodyOver && 'border-destructive')}
          value={body} placeholder={t('steering.form.bodyPlaceholder')} onChange={(e) => setBody(e.target.value)}
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-[11px] font-medium text-muted-foreground">{t('steering.form.mode')}</span>
        <select
          data-testid="steering-form-mode" className={field} value={mode}
          onChange={(e) => setMode(e.target.value as InclusionMode)}
        >
          {INCLUSION_MODES.map((m) => (
            <option key={m} value={m}>{t(`steering.mode.${m}`)}</option>
          ))}
        </select>
        {mode === 'auto' && (
          <span data-testid="steering-form-auto-note" className="text-[11px] text-warning">
            {t('steering.autoNote')}
          </span>
        )}
      </label>

      {mode === 'scene_match' && (
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">{t('steering.form.matchPattern')}</span>
          <input
            data-testid="steering-form-match-pattern" className={field} value={matchPattern}
            placeholder={t('steering.form.matchPatternPlaceholder')} onChange={(e) => setMatchPattern(e.target.value)}
          />
        </label>
      )}

      <label className="flex items-center gap-2">
        <input
          type="checkbox" data-testid="steering-form-enabled" checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />
        <span className="text-[12px]">{t('steering.form.enabled')}</span>
      </label>

      {errorKind && (
        <p data-testid="steering-form-error" className="text-[12px] text-destructive">
          {t(`steering.error.${errorKind}`)}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="button" data-testid="steering-form-save" disabled={invalid || saving}
          onClick={submit}
          className="rounded bg-primary px-3 py-1 text-[12px] text-primary-foreground hover:opacity-90 disabled:opacity-40"
        >
          {t('steering.form.save')}
        </button>
        <button
          type="button" data-testid="steering-form-cancel" onClick={onCancel}
          className="rounded border px-3 py-1 text-[12px] hover:bg-secondary"
        >
          {t('steering.form.cancel')}
        </button>
      </div>
    </div>
  );
}
