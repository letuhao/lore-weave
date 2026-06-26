// W6 §3.4 / §5.5 — tier / kind / genre / tension facets. A left column on desktop;
// on narrow widths the parent collapses it into a filter sheet (§5.5). role=group
// + aria-pressed per facet button (§5.1). Render-only.
import { useTranslation } from 'react-i18next';
import type { MotifFacets } from '../hooks/useMotifLibrary';
import type { MotifKind } from '../types';
import { kindLabelKey, tierLabelKey } from '../simpleMode';
import { useMotifSimpleMode } from '../context/MotifSimpleModeContext';

type Props = {
  facets: MotifFacets;
  available: { genres: string[]; kinds: MotifKind[] };
  onSetFacet: <K extends keyof MotifFacets>(k: K, v: MotifFacets[K]) => void;
  onClear: () => void;
};

const TIERS: Array<'system' | 'user' | 'public'> = ['system', 'user', 'public'];
const TENSIONS = [1, 2, 3, 4, 5];

function FacetGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="group" aria-label={label} className="flex flex-col gap-1">
      <div className="text-[10px] font-medium uppercase tracking-wide text-neutral-400">{label}</div>
      <div className="flex flex-wrap gap-1">{children}</div>
    </div>
  );
}

function Chip({ active, testid, onClick, children }: { active: boolean; testid: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      data-testid={testid}
      aria-pressed={active}
      className={`rounded px-1.5 py-0.5 text-[11px] ${active ? 'bg-amber-600 text-white' : 'border border-neutral-300 text-neutral-600 hover:bg-neutral-100 dark:border-neutral-600 dark:text-neutral-300 dark:hover:bg-neutral-800'}`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

export function MotifFacetRail({ facets, available, onSetFacet, onClear }: Props) {
  const { t } = useTranslation('composition');
  const { simple } = useMotifSimpleMode();
  const hasAny = !!(facets.kind || facets.genre || facets.tension != null || facets.tier);

  return (
    <div data-testid="motif-facet-rail" className="flex flex-col gap-3 p-2">
      <FacetGroup label={t('motif.facet.tier', { defaultValue: 'Tier' })}>
        {TIERS.map((tier) => (
          <Chip key={tier} active={facets.tier === tier} testid={`motif-facet-tier-${tier}`} onClick={() => onSetFacet('tier', tier)}>
            {t(tierLabelKey(tier), { defaultValue: tier })}
          </Chip>
        ))}
      </FacetGroup>

      {available.kinds.length > 0 && (
        <FacetGroup label={t('motif.facet.kind', { defaultValue: 'Kind' })}>
          {available.kinds.map((kind) => (
            <Chip key={kind} active={facets.kind === kind} testid={`motif-facet-kind-${kind}`} onClick={() => onSetFacet('kind', kind)}>
              {t(kindLabelKey(kind, simple), { defaultValue: kind })}
            </Chip>
          ))}
        </FacetGroup>
      )}

      {available.genres.length > 0 && (
        <FacetGroup label={t('motif.facet.genre', { defaultValue: 'Genre' })}>
          {available.genres.map((g) => (
            <Chip key={g} active={facets.genre === g} testid={`motif-facet-genre-${g}`} onClick={() => onSetFacet('genre', g)}>
              {g}
            </Chip>
          ))}
        </FacetGroup>
      )}

      <FacetGroup label={t('motif.facet.tension', { defaultValue: 'Intensity' })}>
        {TENSIONS.map((n) => (
          <Chip key={n} active={facets.tension === n} testid={`motif-facet-tension-${n}`} onClick={() => onSetFacet('tension', n)}>
            T{n}
          </Chip>
        ))}
      </FacetGroup>

      {hasAny && (
        <button
          type="button"
          data-testid="motif-facet-clear"
          className="self-start text-[11px] text-amber-600 hover:underline"
          onClick={onClear}
        >
          {t('motif.facet.clear', { defaultValue: 'Clear filters' })}
        </button>
      )}
    </div>
  );
}
