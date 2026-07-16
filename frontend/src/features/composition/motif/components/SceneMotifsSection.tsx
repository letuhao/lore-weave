// 3b §3.2a — the Motifs section for ONE scene, mounted in scene-inspector (between Craft
// and Links). Reuses MotifBindingCard + useMotifBinding verbatim (the legacy chapter surface
// is per-node too). Adds the ONE suggest button this wave owns: "Suggest a motif" → the
// ranked BE-M4 candidates with a match_reason, replacing the flat unranked list (GG-1). No
// silent fail: the suggest error + empty both render; binding failures keep the prior binding.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MotifBindingCard } from './MotifBindingCard';
import { useMotifBindings } from '../hooks/useMotifBindings';
import { useMotifBinding } from '../hooks/useMotifBinding';
import { useMotifCandidates } from '../hooks/useMotifCandidates';
import { useMotifSuggestions } from '../hooks/useMotifSuggestions';
import type { RosterOption } from '../../hooks/useGlossaryRoster';

type Props = {
  projectId: string | null;
  bookId: string | null;
  chapterId: string | null;
  sceneId: string;
  roster?: RosterOption[];
  token: string | null;
};

export function SceneMotifsSection({ projectId, bookId, chapterId, sceneId, roster = [], token }: Props) {
  const { t } = useTranslation('composition');
  // No composition Work yet (imported book, no plan) → binding isn't available; say so
  // instead of rendering a dead card. Split so the hooks below never run conditionally
  // (rules of hooks) and always have a real projectId.
  if (!projectId) {
    return <p data-testid="motif-no-work" className="px-1 text-[11px] text-neutral-500">{t('motif.binding.noWork', { defaultValue: 'Create a plan for this book to bind motifs to its scenes.' })}</p>;
  }
  return <SceneMotifsInner projectId={projectId} bookId={bookId} chapterId={chapterId} sceneId={sceneId} roster={roster} token={token} />;
}

function SceneMotifsInner({ projectId, bookId, chapterId, sceneId, roster = [], token }: Props & { projectId: string }) {
  const { t } = useTranslation('composition');
  const [suggestOpen, setSuggestOpen] = useState(false);

  const bindingsQ = useMotifBindings(projectId, chapterId, token);
  const binding = useMotifBinding({ projectId, bookId: bookId ?? '', nodeId: sceneId, token });
  const candidates = useMotifCandidates(token);
  const suggestions = useMotifSuggestions(projectId, sceneId, token, suggestOpen);

  const bound = bindingsQ.data?.bindings?.[sceneId] ?? null;
  const succession = bindingsQ.data?.succession?.[sceneId] ?? null;

  return (
    <div className="flex flex-col gap-1.5">
      <MotifBindingCard
        sceneId={sceneId}
        bound={bound}
        candidates={candidates.data ?? []}
        overuse={null}
        succession={succession}
        roster={roster}
        swapping={binding.swap.isPending || binding.clearMotif.isPending}
        onSwap={(motifId) => binding.swap.mutate(motifId)}
        onClear={() => binding.clearMotif.mutate()}
        onRebindRole={(roleKey, entityId) => binding.rebindRole.mutate({ roleKey, entityId })}
        onChain={(hint) => binding.chainIt.mutate(hint)}
        onCommitAndGenerate={(sid) => binding.commitAndGenerate(sid)}
      />

      {/* The ONE suggest button this wave owns — ranked candidates + a "why this motif". */}
      <div>
        <button
          type="button"
          data-testid="motif-suggest-toggle"
          aria-expanded={suggestOpen}
          onClick={() => setSuggestOpen((v) => !v)}
          className="rounded border border-amber-400 px-2 py-0.5 text-[11px] text-amber-700 hover:bg-amber-50 dark:text-amber-300 dark:hover:bg-amber-950/30"
        >
          ✨ {t('motif.suggest.button', { defaultValue: 'Suggest a motif' })}
        </button>

        {suggestOpen && (
          <div data-testid="motif-suggest-panel" className="mt-1 rounded border border-neutral-200 p-1.5 dark:border-neutral-700">
            {suggestions.isLoading && <p className="p-1 text-[11px] text-neutral-500">{t('motif.suggest.loading', { defaultValue: 'Ranking motifs for this scene…' })}</p>}
            {suggestions.isError && (
              <p data-testid="motif-suggest-error" className="rounded bg-red-50 px-2 py-1 text-[11px] text-red-700 dark:bg-red-950/30 dark:text-red-300">
                {t('motif.suggest.error', { defaultValue: 'Could not suggest motifs.' })}
                <button type="button" className="ml-2 underline" onClick={() => suggestions.refetch()}>{t('motif.suggest.retry', { defaultValue: 'Retry' })}</button>
              </p>
            )}
            {!suggestions.isLoading && !suggestions.isError && (suggestions.data?.length ?? 0) === 0 && (
              <p data-testid="motif-suggest-empty" className="p-1 text-[11px] text-neutral-500">{t('motif.suggest.empty', { defaultValue: 'No motif fits this scene yet — add more to your library.' })}</p>
            )}
            <ul className="space-y-1">
              {(suggestions.data ?? []).map((s) => (
                <li key={s.motif.id} data-testid="motif-suggest-row" className="flex items-center gap-1.5 rounded bg-neutral-50 px-1.5 py-1 text-[11px] dark:bg-neutral-800/50">
                  <span className="min-w-0 flex-1 truncate">
                    <span className="font-medium">{s.motif.name}</span>
                    <span className="ml-1 text-neutral-400">{Math.round(s.score * 100)}%</span>
                    <span className="ml-1 text-neutral-400">{Object.keys(s.match_reason ?? {}).filter((k) => k !== 'degraded').join(' · ')}</span>
                  </span>
                  <button
                    type="button"
                    data-testid="motif-suggest-bind"
                    disabled={binding.swap.isPending}
                    onClick={() => binding.swap.mutate(s.motif.id, { onSuccess: () => setSuggestOpen(false) })}
                    className="shrink-0 rounded bg-amber-600 px-1.5 py-0.5 text-white hover:bg-amber-700 disabled:opacity-40"
                  >
                    {t('motif.suggest.bind', { defaultValue: 'Bind' })}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
