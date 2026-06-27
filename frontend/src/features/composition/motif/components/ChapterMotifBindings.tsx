// D-MOTIF-FE-PLANNERVIEW-WIRING (Shape A) — the POST-commit per-scene motif-binding
// surface: for a committed chapter, render MotifBindingCard per scene wired to
// useMotifBinding(nodeId). Render-only; logic lives in useMotifBindings (fetch the
// map) + useMotifBinding (per-node swap/rebind/clear/chain). Each scene's binding hook
// lives in its own child (SceneMotifBindingRow) so hooks aren't called in a loop.
import { useTranslation } from 'react-i18next';
import type { CommitAndGenerateRoute, SceneBoundMotif } from '../types';
import type { RosterOption } from '../../hooks/useGlossaryRoster';
import { useMotifBindings } from '../hooks/useMotifBindings';
import { useMotifBinding } from '../hooks/useMotifBinding';
import { useMotifCandidates } from '../hooks/useMotifCandidates';
import { MotifBindingCard, type MotifCandidateOption } from './MotifBindingCard';

export type CommittedScene = { id: string; title: string };

type Props = {
  projectId: string;
  bookId: string;
  chapterId: string | null;
  scenes: CommittedScene[];
  roster?: RosterOption[];
  /** Swap candidates per scene node (node_id → options); empty when none supplied. */
  candidatesByNode?: Record<string, MotifCandidateOption[]>;
  token: string | null;
  onGenerate?: (route: CommitAndGenerateRoute) => void;
};

export function ChapterMotifBindings({
  projectId, bookId, chapterId, scenes, roster = [], candidatesByNode = {}, token, onGenerate,
}: Props) {
  const { t } = useTranslation('composition');
  const q = useMotifBindings(projectId, chapterId, token);
  const bindings = q.data?.bindings ?? {};
  // the user's visible motifs — the bind/swap picker options (same for every scene).
  const candidates = useMotifCandidates(token);
  const candidateOpts = candidates.data ?? [];

  if (!chapterId || scenes.length === 0) return null;

  return (
    <div className="space-y-1.5" data-testid="chapter-motif-bindings">
      <div className="text-xs font-medium text-muted-foreground">
        {t('motif.binding.sectionTitle', { defaultValue: 'Scene motifs' })}
      </div>
      {q.isError && (
        <div className="text-xs text-destructive" role="alert">
          {t('motif.binding.loadError', { defaultValue: 'Could not load scene motifs.' })}
        </div>
      )}
      {scenes.map((s) => (
        <SceneMotifBindingRow
          key={s.id}
          projectId={projectId}
          bookId={bookId}
          nodeId={s.id}
          title={s.title}
          bound={bindings[s.id] ?? null}
          roster={roster}
          candidates={candidatesByNode[s.id] ?? candidateOpts}
          token={token}
          onGenerate={onGenerate}
        />
      ))}
    </div>
  );
}

type RowProps = {
  projectId: string;
  bookId: string;
  nodeId: string;
  title: string;
  bound: SceneBoundMotif | null;
  roster: RosterOption[];
  candidates: MotifCandidateOption[];
  token: string | null;
  onGenerate?: (route: CommitAndGenerateRoute) => void;
};

function SceneMotifBindingRow({
  projectId, bookId, nodeId, title, bound, roster, candidates, token, onGenerate,
}: RowProps) {
  const b = useMotifBinding({ projectId, bookId, nodeId, token });
  return (
    <div className="flex flex-col gap-1" data-testid={`scene-binding-${nodeId}`}>
      <span className="truncate text-[11px] text-muted-foreground">{title}</span>
      <MotifBindingCard
        sceneId={nodeId}
        bound={bound}
        candidates={candidates}
        roster={roster}
        swapping={b.swap.isPending}
        onSwap={(motifId) => b.swap.mutate(motifId)}
        onClear={() => b.clearMotif.mutate()}
        onRebindRole={(roleKey, entityId) => b.rebindRole.mutate({ roleKey, entityId })}
        onChain={(hint) => b.chainIt.mutate(hint)}
        onCommitAndGenerate={(sceneId) => onGenerate?.(b.commitAndGenerate(sceneId))}
      />
    </div>
  );
}
