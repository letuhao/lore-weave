// W6 §3.4 (mockup 07-A) — one planned │ realized │ conformance row + regenerate-to-
// beat. Reads the chapter reader's NESTED row shape ({planned, realized, conformance}
// — routers/conformance.py). Conformance is co-encoded: glyph (✓/⚠/✗) + WORD + hue
// (§5.3), never hue alone. A null verdict (no completed job / no bound motif) shows a
// neutral "Not checked yet"; a degraded judge (booleans null) shows "Couldn't check".
// `calibrated=false` stamps "advisory / unverified" (R2.1 honesty — never ground
// truth). Reflows to a stacked card on narrow widths (§5.5). Render-only.
import { useTranslation } from 'react-i18next';
import type { SceneConformance } from '../types';
import { conformanceGlyph, conformanceTone } from '../simpleMode';

const TONE_CLASS = {
  ok: 'text-emerald-700 dark:text-emerald-300',
  warn: 'text-amber-700 dark:text-amber-300',
  bad: 'text-red-700 dark:text-red-300',
} as const;

export function ConformanceSceneRow(
  { scene, onRegenerate, onOpenScene }:
  { scene: SceneConformance; onRegenerate: (nodeId: string) => void; onOpenScene?: (sceneId: string) => void },
) {
  const { t } = useTranslation('composition');
  const v = scene.conformance;
  // a verdict is "judged" only when BOTH binary flags are real booleans (the judge
  // can degrade to null on an LLM error — surfaced as "couldn't check", never a tone).
  const judged = !!v && typeof v.beat_realized === 'boolean' && typeof v.tension_band_match === 'boolean';
  const tone = judged ? conformanceTone(v!.beat_realized as boolean, v!.tension_band_match as boolean) : null;
  const glyph = tone ? conformanceGlyph(tone) : '';
  const hasDrift = judged && tone !== 'ok';
  const beatLabel = scene.planned.beat_key ?? scene.beat_role ?? '—';

  return (
    <div data-testid={`conformance-row-${scene.outline_node_id}`} className="grid grid-cols-1 gap-2 border-b border-neutral-200 py-2 text-xs sm:grid-cols-12 dark:border-neutral-700">
      {/* planned */}
      <div className="sm:col-span-4">
        <div className="text-[10px] font-medium uppercase text-neutral-400">{t('motif.conf.planned', { defaultValue: 'Planned' })}</div>
        {/* §2#6 loop-connect — jump to this scene in the inspector to fix a missed/drifted beat. */}
        {onOpenScene ? (
          <button
            type="button"
            data-testid={`conformance-open-scene-${scene.outline_node_id}`}
            onClick={() => onOpenScene(scene.outline_node_id)}
            className="text-left text-neutral-700 underline decoration-dotted hover:text-amber-700 dark:text-neutral-200 dark:hover:text-amber-300"
            title={t('motif.conf.openScene', { defaultValue: 'Open this scene in the inspector' })}
          >
            {beatLabel}
          </button>
        ) : (
          <div className="text-neutral-700 dark:text-neutral-200">{beatLabel}</div>
        )}
        {scene.planned.tension != null && <div className="text-neutral-500">T{scene.planned.tension}</div>}
      </div>
      {/* realized — presence only (the trace never carries prose) */}
      <div className="sm:col-span-4">
        <div className="text-[10px] font-medium uppercase text-neutral-400">{t('motif.conf.realized', { defaultValue: 'Realized' })}</div>
        <div className="text-neutral-600 dark:text-neutral-300">
          {scene.realized.has_prose
            ? t('motif.conf.written', { defaultValue: 'Written' })
            : t('motif.conf.notWritten', { defaultValue: 'Not written yet' })}
        </div>
      </div>
      {/* conformance — glyph + word + hue, or a neutral not-checked/degraded state */}
      <div className="sm:col-span-4">
        <div className="text-[10px] font-medium uppercase text-neutral-400">{t('motif.conf.conformance', { defaultValue: 'Conformance' })}</div>
        {judged ? (
          <div data-testid={`conformance-tone-${scene.outline_node_id}`} className={`font-medium ${TONE_CLASS[tone!]}`}>
            {glyph} {t(`motif.conf.tone.${tone}`, { defaultValue: tone === 'ok' ? 'On beat' : tone === 'warn' ? 'Tension drift' : 'Beat missed' })}
          </div>
        ) : (
          <div data-testid={`conformance-unchecked-${scene.outline_node_id}`} className="text-neutral-400">
            {v?.error
              ? t('motif.conf.couldNotCheck', { defaultValue: "Couldn't check" })
              : t('motif.conf.notChecked', { defaultValue: 'Not checked yet' })}
          </div>
        )}
        {judged && !v!.calibrated && (
          <div data-testid={`conformance-advisory-${scene.outline_node_id}`} className="mt-0.5 text-[10px] italic text-neutral-400">
            {t('motif.conf.advisory', { defaultValue: 'Advisory — unverified self-report' })}
          </div>
        )}
        {hasDrift && (
          <button
            type="button"
            data-testid={`conformance-regen-${scene.outline_node_id}`}
            className="mt-1 rounded border border-amber-400 px-1.5 py-0.5 text-[11px] text-amber-700 hover:bg-amber-50 dark:text-amber-300 dark:hover:bg-amber-950/30"
            onClick={() => onRegenerate(scene.outline_node_id)}
          >
            {t('motif.conf.regenerate', { defaultValue: 'Regenerate to beat' })}
          </button>
        )}
      </div>
    </div>
  );
}
