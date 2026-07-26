// LOOM Composition (WS-B1) — the advisory critic verdict display, extracted from
// ComposeView so the standing `critic` SubTab panel can render the SAME verdict
// (coherence/voice/pacing/canon dims + the C26 derivative override-gate + per-rule
// violations). Display-only: the accept-BLOCK lives in ComposeView's accept path
// (this just surfaces the verdict). `onRegenerate`/`onDismiss` are optional so a
// read-only surface (the popped-out CriticPanel) can omit the cowrite actions.
import { useTranslation } from 'react-i18next';
import type { Critic } from '../types';

export function CriticFlags({
  critic,
  onRegenerate,
  onDismiss,
}: {
  critic: NonNullable<Critic>;
  jobId?: string | null;
  onRegenerate?: () => void;
  onDismiss?: (ruleId: string) => void;
}) {
  const { t } = useTranslation('composition');
  const dims: [string, number | null][] = [
    ['coherence', critic.coherence], ['voice_match', critic.voice_match],
    ['pacing', critic.pacing], ['canon_consistency', critic.canon_consistency],
  ];
  // C26 GATE — a derivative override slipped. `needs_regeneration` BLOCKS accept
  // (the user must regenerate); `regen_exhausted` means the cap was hit so the gate
  // fails OPEN (we surface the finding but no longer block). The findings explain WHY.
  const findings = critic.derivative_findings ?? [];
  const blocked = critic.needs_regeneration === true;
  return (
    <div data-testid="compose-critic" className="rounded border border-neutral-200 p-2 text-xs dark:border-neutral-700">
      {(blocked || critic.regen_exhausted) && (
        <div
          data-testid="compose-override-gate"
          className={`mb-2 rounded p-2 ${blocked ? 'bg-red-50 dark:bg-red-950' : 'bg-amber-50 dark:bg-amber-950'}`}
        >
          <div className={`font-medium ${blocked ? 'text-red-700 dark:text-red-300' : 'text-amber-800 dark:text-amber-300'}`}>
            {blocked
              ? t('overrideSlipBlocked', { defaultValue: 'Accept blocked: a what-if-version override slipped back to the canon value. Regenerate before accepting.' })
              : t('overrideSlipExhausted', { defaultValue: 'Override still slipping after the regeneration cap — surfaced for your review (accept is no longer blocked).' })}
          </div>
          <ul className="mt-1 list-disc pl-4">
            {findings.map((f, i) => (
              <li key={i} className="text-neutral-700 dark:text-neutral-300">
                {f.kind === 'override_slip'
                  ? t('overrideSlipDetail', {
                      defaultValue: '{{name}} ({{field}}): expected “{{expected}}”, found “{{found}}”',
                      name: f.name || f.entity_id, field: f.field, expected: f.expected, found: f.found,
                    })
                  : t('deltaInconsistencyDetail', {
                      defaultValue: '{{name}}: contradicts the delta rule “{{rule}}”',
                      name: f.name || f.entity_id, rule: f.rule,
                    })}
              </li>
            ))}
          </ul>
          {blocked && onRegenerate && (
            <button
              data-testid="compose-override-regenerate"
              className="mt-1.5 rounded bg-red-600 px-2.5 py-1 text-xs text-white"
              onClick={onRegenerate}
            >
              {t('regenerate', { defaultValue: 'Regenerate' })}
            </button>
          )}
        </div>
      )}
      <div className="mb-1 font-medium">{t('critic', { defaultValue: 'Critic (advisory)' })}</div>
      {critic.error ? (
        <div className="text-neutral-500">{t('criticUnavailable', { defaultValue: 'Critic unavailable.' })}</div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {dims.map(([k, v]) => (
            <span key={k} className="rounded bg-neutral-100 px-1.5 py-0.5 dark:bg-neutral-800">
              {t(k, { defaultValue: k })}: {v ?? '—'}
            </span>
          ))}
        </div>
      )}
      {(critic.violations ?? []).map((vio) => (
        <div key={vio.rule_id} className={`mt-1 rounded bg-amber-50 p-1.5 dark:bg-amber-950 ${vio.dismissed ? 'opacity-50 line-through' : ''}`}>
          <span className="text-amber-800 dark:text-amber-300">{vio.why || vio.span}</span>
          {!vio.dismissed && onDismiss && (
            <button className="ml-2 text-[11px] text-neutral-500 underline" onClick={() => onDismiss(vio.rule_id)}>
              {t('dismiss', { defaultValue: 'dismiss' })}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
