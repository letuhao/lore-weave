// W6 §15.1 — the scheme intrigue card (kind='scheme'): who knows, who is deceived,
// and the information gap. Renders in the detail drawer + the binding card. Simple
// mode renders a plain-language "who's in the dark" sentence; expert mode shows the
// structured knows / deceived / gap. Render-only.
import { useTranslation } from 'react-i18next';
import type { InfoAsymmetry } from '../types';
import { useMotifSimpleMode } from '../context/MotifSimpleModeContext';

export function InfoAsymmetryCard({ info }: { info: InfoAsymmetry }) {
  const { t } = useTranslation('composition');
  const { simple } = useMotifSimpleMode();

  if (simple) {
    // "who's in the dark" — lead with the deceived party + the gap.
    const deceived = info.deceived.join(', ');
    const knows = info.knows.join(', ');
    return (
      <div data-testid="motif-info-asymmetry" className="rounded border border-violet-200 bg-violet-50 p-2 text-xs dark:border-violet-900 dark:bg-violet-950/30">
        <div className="font-medium text-violet-800 dark:text-violet-200">
          {t('motif.simple.infoAsymmetry', { defaultValue: "Who's in the dark" })}
        </div>
        <p className="mt-1 text-violet-700 dark:text-violet-300">
          {knows && t('motif.simple.infoKnows', { who: knows, defaultValue: '{{who}} knows the truth' })}
          {deceived && `; ${t('motif.simple.infoDeceived', { who: deceived, defaultValue: '{{who}} is fooled' })}`}
          {info.gap && `. ${info.gap}`}
        </p>
      </div>
    );
  }

  return (
    <div data-testid="motif-info-asymmetry" className="rounded border border-violet-200 bg-violet-50 p-2 text-xs dark:border-violet-900 dark:bg-violet-950/30">
      <div className="font-medium text-violet-800 dark:text-violet-200">
        {t('motif.expert.infoAsymmetry', { defaultValue: 'Information asymmetry' })}
      </div>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-violet-700 dark:text-violet-300">
        <dt className="font-medium">{t('motif.expert.knows', { defaultValue: 'Knows' })}</dt>
        <dd>{info.knows.join(', ') || '—'}</dd>
        <dt className="font-medium">{t('motif.expert.deceived', { defaultValue: 'Deceived' })}</dt>
        <dd>{info.deceived.join(', ') || '—'}</dd>
        <dt className="font-medium">{t('motif.expert.gap', { defaultValue: 'Gap' })}</dt>
        <dd>{info.gap || '—'}</dd>
      </dl>
    </div>
  );
}
