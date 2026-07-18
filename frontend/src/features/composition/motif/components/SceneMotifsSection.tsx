// 3b §3.2a — the Motifs section for ONE scene, mounted in scene-inspector (between Craft
// and Links). Reuses MotifBindingCard + useMotifBinding verbatim (the legacy chapter surface
// is per-node too). Adds the ONE suggest button this wave owns: "Suggest a motif" → the
// ranked BE-M4 candidates with a match_reason, replacing the flat unranked list (GG-1). No
// silent fail: the suggest error + empty both render; binding failures keep the prior binding.
import { useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { MotifSuggestion } from '../api';
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

/** One ranked suggestion row. Shows the % + reasons ONLY when the match is real (not a
 * degraded fallback) — a flat degraded score presented as a % is the silent-lie this guards. */
function SuggestRow(
  { s, t, swapping, onBind }: {
    s: MotifSuggestion; t: TFunction; swapping: boolean; onBind: (id: string) => void;
  },
): ReactNode {
  const degraded = (s.match_reason as { degraded?: boolean } | null)?.degraded;
  return (
    <li data-testid="motif-suggest-row" className="flex items-center gap-1.5 rounded bg-neutral-50 px-1.5 py-1 text-[11px] dark:bg-neutral-800/50">
      <span className="min-w-0 flex-1 truncate">
        <span className="font-medium">{s.motif.name}</span>
        {degraded ? (
          <span className="ml-1 text-neutral-400">·</span>
        ) : (
          <>
            <span className="ml-1 text-neutral-400">{Math.round(s.score * 100)}%</span>
            <span className="ml-1 text-neutral-400">{Object.keys(s.match_reason ?? {}).filter((k) => k !== 'degraded' && k !== 'section').join(' · ')}</span>
          </>
        )}
      </span>
      <button
        type="button"
        data-testid="motif-suggest-bind"
        disabled={swapping}
        onClick={() => onBind(s.motif.id)}
        className="shrink-0 rounded bg-amber-600 px-1.5 py-0.5 text-white hover:bg-amber-700 disabled:opacity-40"
      >
        {t('motif.suggest.bind', { defaultValue: 'Bind' })}
      </button>
    </li>
  );
}

/** Group the ranked candidates into their two embedding SPACES — "your motifs" (U-space,
 * embedded with YOUR own model) and "the library" (P-space, platform) — and render each as
 * its own labelled list. The two spaces' scores aren't comparable, so they are NEVER merged
 * into one order (the honest two-section presentation). A candidate with no `section` (older
 * BE, or a shared row) falls into the library group.
 *
 * A degrade note lives INSIDE each section with the RIGHT cause — the two degrade for
 * DIFFERENT reasons: "your motifs" degrade when YOU have no embedding model set up (fixable
 * by you), "the library" degrades when the PLATFORM embedding model isn't configured (an
 * admin concern). A single global "library fallbacks" banner mislabelled the first case. */
function renderMotifSuggestions(
  rows: MotifSuggestion[],
  { t, swapping, onBind }: { t: TFunction; swapping: boolean; onBind: (id: string) => void },
): ReactNode {
  const mine = rows.filter((s) => (s.match_reason as { section?: string } | null)?.section === 'mine');
  const library = rows.filter((s) => (s.match_reason as { section?: string } | null)?.section !== 'mine');
  const group = (
    items: MotifSuggestion[], testid: string, label: string,
    degradeTestid: string, degradeText: string,
  ) => {
    if (items.length === 0) return null;
    const degraded = items.some((s) => (s.match_reason as { degraded?: boolean } | null)?.degraded);
    return (
      <div data-testid={testid}>
        <p className="px-0.5 pt-0.5 text-[10px] font-semibold uppercase tracking-wide text-neutral-400">{label}</p>
        {degraded && (
          <p data-testid={degradeTestid} className="my-0.5 rounded bg-amber-50 px-2 py-0.5 text-[10px] text-amber-700 dark:bg-amber-950/30 dark:text-amber-300">
            {degradeText}
          </p>
        )}
        <ul className="space-y-1">
          {items.map((s) => (
            <SuggestRow key={s.motif.id} s={s} t={t} swapping={swapping} onBind={onBind} />
          ))}
        </ul>
      </div>
    );
  };
  return (
    <div className="space-y-1.5">
      {group(
        mine, 'motif-suggest-section-mine', t('motif.suggest.sectionMine', { defaultValue: 'Your motifs' }),
        'motif-suggest-degraded-mine',
        t('motif.suggest.degradedMine', { defaultValue: "Your motifs aren't ranked by fit — set up an embedding model in your settings to rank them semantically." }),
      )}
      {group(
        library, 'motif-suggest-section-library', t('motif.suggest.sectionLibrary', { defaultValue: 'From the library' }),
        'motif-suggest-degraded',
        t('motif.suggest.degradedLibrary', { defaultValue: "Not ranked by fit — the shared library's embedding model isn't configured, so these are genre fallbacks, not scored matches." }),
      )}
    </div>
  );
}

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
            {/* NO SILENT DEGRADE — when the retriever falls back (the platform embedding model isn't
                configured, so vectors are missing), the scores are NOT semantic. Say so, don't show a
                flat % as if it were a real match (the challenge that surfaced this). */}
            {/* Two SECTIONS (tenancy re-design 2026-07-17): "your" motifs (embedded in YOUR
                own model space) rank separately from the shared library (platform space) — the
                scores aren't comparable across spaces, so we never merge them into one order.
                A candidate with no `section` (older BE) falls into the library group. Each
                section carries its OWN degrade note (different causes — see the helper). */}
            {renderMotifSuggestions(suggestions.data ?? [], {
              t, swapping: binding.swap.isPending,
              onBind: (id) => binding.swap.mutate(id, { onSuccess: () => setSuggestOpen(false) }),
            })}
          </div>
        )}
      </div>
    </div>
  );
}
