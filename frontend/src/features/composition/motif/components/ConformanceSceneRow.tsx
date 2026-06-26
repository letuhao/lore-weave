// W6 §3.4 (mockup 07-A) — one planned │ realized │ conformance row + regenerate-to-
// beat. Conformance is co-encoded: glyph (✓/⚠/✗) + WORD + hue (§5.3), never hue
// alone. `calibrated=false` stamps "advisory / unverified" (R2.1 honesty — never
// presented as ground truth). Reflows to a stacked card on narrow widths (§5.5).
// Render-only.
import { useTranslation } from 'react-i18next';
import type { SceneConformance } from '../types';
import { conformanceGlyph, conformanceTone } from '../simpleMode';

const TONE_CLASS = {
  ok: 'text-emerald-700 dark:text-emerald-300',
  warn: 'text-amber-700 dark:text-amber-300',
  bad: 'text-red-700 dark:text-red-300',
} as const;

export function ConformanceSceneRow({ scene, onRegenerate }: { scene: SceneConformance; onRegenerate: (nodeId: string) => void }) {
  const { t } = useTranslation('composition');
  const tone = conformanceTone(scene.beat_realized, scene.tension_band_match);
  const glyph = conformanceGlyph(tone);
  const hasDrift = scene.flags.length > 0 || tone !== 'ok';

  return (
    <div data-testid={`conformance-row-${scene.outline_node_id}`} className="grid grid-cols-1 gap-2 border-b border-neutral-200 py-2 text-xs sm:grid-cols-12 dark:border-neutral-700">
      {/* planned */}
      <div className="sm:col-span-4">
        <div className="text-[10px] font-medium uppercase text-neutral-400">{t('motif.conf.planned', { defaultValue: 'Planned' })}</div>
        <div className="text-neutral-700 dark:text-neutral-200">{scene.beat_label}</div>
        {scene.planned_tension != null && <div className="text-neutral-500">T{scene.planned_tension}</div>}
      </div>
      {/* realized */}
      <div className="sm:col-span-4">
        <div className="text-[10px] font-medium uppercase text-neutral-400">{t('motif.conf.realized', { defaultValue: 'Realized' })}</div>
        <div className="line-clamp-2 text-neutral-600 dark:text-neutral-300">{scene.realized_excerpt || '—'}</div>
        {scene.realized_tension != null && <div className="text-neutral-500">T{scene.realized_tension}</div>}
      </div>
      {/* conformance — glyph + word + hue */}
      <div className="sm:col-span-4">
        <div className="text-[10px] font-medium uppercase text-neutral-400">{t('motif.conf.conformance', { defaultValue: 'Conformance' })}</div>
        <div data-testid={`conformance-tone-${scene.outline_node_id}`} className={`font-medium ${TONE_CLASS[tone]}`}>
          {glyph} {t(`motif.conf.tone.${tone}`, { defaultValue: tone === 'ok' ? 'On beat' : tone === 'warn' ? 'Tension drift' : 'Beat missed' })}
        </div>
        {!scene.calibrated && (
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
