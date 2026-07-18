// S5-B4 — the branch prose-diff view (a Diff tab inside the divergence panel). Lists
// the dị bản's changed/added scenes and shows a two-column canon↔branch line diff for
// the selected one. Renders only; data + correspondence live in useBranchDiff.
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useBranchDiff, type BranchDiffScene } from '../hooks/useBranchDiff';
import { lineDiff } from '../lib/lineDiff';

// H-5b — below this width the side-by-side canon↔branch diff STACKS vertically (each side gets
// full width) rather than squeezing into two unreadable columns in a narrow dock.
const DIFF_STACK_BELOW_PX = 360;

export function BranchDiffView({
  derivativeProjectId,
  sourceProjectId,
  token,
}: {
  derivativeProjectId: string;
  sourceProjectId: string | null;
  token: string | null;
}) {
  const { t } = useTranslation('composition');
  const q = useBranchDiff(derivativeProjectId, sourceProjectId, token, !!sourceProjectId);
  const scenes = useMemo(() => (q.data ?? []).filter((s) => s.status !== 'unchanged'), [q.data]);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const selected = scenes.find((s) => s.nodeId === selectedNode) ?? scenes[0] ?? null;

  if (!sourceProjectId) {
    return <div data-testid="branchdiff-nosource" className="p-3 text-xs text-muted-foreground">{t('branchdiff.noSource', { defaultValue: 'This branch has no resolvable source to diff against.' })}</div>;
  }
  if (q.isLoading) {
    return <div data-testid="branchdiff-loading" className="p-3 text-xs text-muted-foreground">{t('branchdiff.loading', { defaultValue: 'Reading prose…' })}</div>;
  }
  if (q.isError) {
    return <div data-testid="branchdiff-error" className="p-3 text-xs text-red-600">{t('branchdiff.error', { defaultValue: 'Could not read the branch prose.' })}</div>;
  }
  if (scenes.length === 0) {
    return (
      <div data-testid="branchdiff-empty" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('branchdiff.empty', { defaultValue: 'No diverged prose yet — every scene inherits canon. Promote a take on the what-if canvas to see a diff here.' })}
      </div>
    );
  }

  // H-5b — narrow-dock responsive: the scene list shrinks (minmax) and the right column gets
  // minmax(0,1fr) so it can shrink below content width (no clip); prose columns carry min-w-0 +
  // break-words to wrap rather than overflow.
  return (
    <div data-testid="branchdiff" className="grid h-full min-h-0 grid-cols-[minmax(96px,164px)_minmax(0,1fr)]">
      <div className="overflow-y-auto border-r border-border p-2 text-[11.5px]">
        <div className="px-1 pb-1.5 text-[9.5px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('branchdiff.scenes', { defaultValue: '{{n}} diverged', n: scenes.length })}
        </div>
        {scenes.map((s) => (
          <button
            key={s.nodeId}
            type="button"
            data-testid={`branchdiff-scene-${s.nodeId}`}
            onClick={() => setSelectedNode(s.nodeId)}
            className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left ${selected?.nodeId === s.nodeId ? 'bg-secondary' : 'hover:bg-muted'}`}
          >
            <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${s.status === 'added' ? 'bg-emerald-500' : s.status === 'no-prose' ? 'bg-muted-foreground/40' : 'bg-amber-500'}`} />
            <span className={`flex-1 truncate ${s.status === 'no-prose' ? 'text-muted-foreground' : ''}`}>{s.title || t('branchdiff.untitledScene', { defaultValue: 'scene' })}</span>
            <span className={`rounded px-1 text-[8.5px] font-medium uppercase ${s.status === 'added' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200' : s.status === 'no-prose' ? 'bg-muted text-muted-foreground' : 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-200'}`}>
              {s.status === 'added' ? t('branchdiff.new', { defaultValue: 'new' }) : s.status === 'no-prose' ? t('branchdiff.todo', { defaultValue: 'todo' }) : t('branchdiff.chg', { defaultValue: 'chg' })}
            </span>
          </button>
        ))}
      </div>
      <div className="min-h-0 overflow-hidden">
        {selected && <SceneDiff scene={selected} />}
      </div>
    </div>
  );
}

function SceneDiff({ scene }: { scene: BranchDiffScene }) {
  const { t } = useTranslation('composition');
  const rows = useMemo(() => lineDiff(scene.canonText, scene.branchText), [scene]);
  // H-5b — measure the container (a dock column of unknown width, no @container plugin in the app)
  // and stack the two prose panes vertically when too narrow for a legible side-by-side.
  const ref = useRef<HTMLDivElement>(null);
  const [stacked, setStacked] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const update = () => setStacked(el.clientWidth < DIFF_STACK_BELOW_PX);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  if (scene.status === 'no-prose') {
    return (
      <div data-testid="branchdiff-noprose" className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{t('branchdiff.noProseTitle', { defaultValue: 'Not written yet' })}</span>
        <span>{t('branchdiff.noProseBody', { defaultValue: 'This diverged scene has no prose in the what-if version yet — promote a take on the what-if canvas, then its diff appears here.' })}</span>
      </div>
    );
  }
  if (scene.status === 'added') {
    return (
      <div data-testid="branchdiff-added" className="h-full overflow-y-auto p-3 text-[12.5px] leading-relaxed">
        <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-600">{t('branchdiff.allNew', { defaultValue: 'All-new (no canon counterpart)' })}</div>
        {scene.branchText.split('\n').map((ln, i) => (
          <p key={i} className="rounded bg-emerald-50/60 px-1 dark:bg-emerald-950/20">{ln}</p>
        ))}
      </div>
    );
  }
  return (
    <div
      ref={ref}
      data-testid="branchdiff-changed"
      data-stacked={stacked || undefined}
      className={`grid h-full min-h-0 ${stacked ? 'grid-rows-2 grid-cols-1' : 'grid-cols-2'}`}
    >
      {/* H-5b — min-w-0 + break-words so each side wraps rather than clipping; the divider is on the
          right when side-by-side, on the bottom when stacked. */}
      <div className={`min-h-0 min-w-0 overflow-y-auto border-border p-3 text-[12.5px] leading-relaxed ${stacked ? 'border-b' : 'border-r'}`}>
        <div className="sticky top-0 mb-1.5 bg-background pb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t('branchdiff.canon', { defaultValue: 'Canon' })}</div>
        {rows.filter((r) => r.type !== 'add').map((r, i) => (
          <p key={i} className={`break-words ${r.type === 'del' ? 'rounded bg-red-50/70 px-1 dark:bg-red-950/20' : 'px-1'}`}>{r.text}</p>
        ))}
      </div>
      <div className="min-h-0 min-w-0 overflow-y-auto p-3 text-[12.5px] leading-relaxed">
        <div className="sticky top-0 mb-1.5 bg-background pb-1 text-[10px] font-semibold uppercase tracking-wide text-purple-500">{t('branchdiff.branch', { defaultValue: 'Dị bản' })}</div>
        {rows.filter((r) => r.type !== 'del').map((r, i) => (
          <p key={i} className={`break-words ${r.type === 'add' ? 'rounded bg-emerald-50/70 px-1 dark:bg-emerald-950/20' : 'px-1'}`}>{r.text}</p>
        ))}
      </div>
    </div>
  );
}
