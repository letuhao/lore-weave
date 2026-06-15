// C24 (dị bản M0) — the 2-layer grounding badge (G2). On a DERIVATIVE Work each
// grounded entity is one of:
//   • INHERITED — base / source project ≤ branch (unchanged canon)
//   • OVERRIDDEN — delta / has an entity_override (the dị bản changed it)
// Distinct visual treatment + a legend (below). The layer is computed from the
// REAL override set (useDerivativeContext.classify) — an OVERRIDDEN entity is
// NEVER rendered INHERITED.
import { useTranslation } from 'react-i18next';
import type { GroundingLayer } from '../hooks/useDerivativeContext';

export function GroundingLayerBadge({ layer }: { layer: GroundingLayer }) {
  const { t } = useTranslation('composition');
  const overridden = layer === 'overridden';
  return (
    <span
      data-testid={`grounding-layer-${layer}`}
      data-layer={layer}
      className={
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ' +
        (overridden
          ? 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200'
          : 'bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-200')
      }
      title={
        overridden
          ? t('derive.layerOverriddenHint', { defaultValue: 'Changed in this what-if (delta)' })
          : t('derive.layerInheritedHint', { defaultValue: 'Inherited unchanged from canon (base)' })
      }
    >
      <span aria-hidden>{overridden ? '✎' : '⛓'}</span>
      {overridden
        ? t('derive.layerOverridden', { defaultValue: 'Overridden' })
        : t('derive.layerInherited', { defaultValue: 'Inherited' })}
    </span>
  );
}

// The legend explaining the two layers — shown once in the grounding panel header
// on a derivative Work so the badges are decodable.
export function GroundingLayerLegend() {
  const { t } = useTranslation('composition');
  return (
    <div data-testid="grounding-layer-legend" className="flex flex-wrap items-center gap-3 text-[10px] text-neutral-500">
      <span className="flex items-center gap-1">
        <span className="h-2 w-2 rounded-full bg-sky-400" />
        {t('derive.layerInherited', { defaultValue: 'Inherited' })} — {t('derive.legendInherited', { defaultValue: 'base canon, unchanged' })}
      </span>
      <span className="flex items-center gap-1">
        <span className="h-2 w-2 rounded-full bg-amber-400" />
        {t('derive.layerOverridden', { defaultValue: 'Overridden' })} — {t('derive.legendOverridden', { defaultValue: 'delta, changed in this what-if' })}
      </span>
    </div>
  );
}
