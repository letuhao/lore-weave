// S-10 O6b — "Suggest an arc for this premise". composition_arc_suggest had a REST twin
// (POST /arc-templates/suggest) with zero FE callers; this is the button. A premise (+ optional
// genre) ranks the caller-visible arc templates that fit, newest match first. Read-only discovery —
// the ranked rows say WHY each matched so the writer can pick one from their library to apply.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useArcSuggest } from '../hooks/useArcSuggest';

type Props = {
  projectId: string | null;
  token: string | null;
};

export function ArcSuggestView({ projectId, token }: Props) {
  const { t } = useTranslation('composition');
  const sg = useArcSuggest(projectId, token);
  const [premise, setPremise] = useState('');
  const [genre, setGenre] = useState('');

  const disabled = !projectId || sg.isPending;

  if (!projectId) {
    return (
      <p data-testid="arc-suggest-noproject" className="p-4 text-center text-xs text-muted-foreground">
        {t('motif.arc.suggest.noProject', {
          defaultValue: 'Open a book with a Work to get arc suggestions for its premise.',
        })}
      </p>
    );
  }

  return (
    <div data-testid="arc-suggest-view" className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-col gap-1.5 border-b p-2">
        <textarea
          data-testid="arc-suggest-premise"
          value={premise}
          onChange={(e) => setPremise(e.target.value)}
          placeholder={t('motif.arc.suggest.premisePlaceholder', {
            defaultValue: 'Describe the premise — e.g. "a reluctant heir must reclaim a fallen house"',
          })}
          className="min-h-[54px] resize-y rounded border bg-background px-2 py-1 text-[12px] outline-none focus:border-ring"
        />
        <div className="flex items-center gap-2">
          <input
            data-testid="arc-suggest-genre"
            value={genre}
            onChange={(e) => setGenre(e.target.value)}
            placeholder={t('motif.arc.suggest.genrePlaceholder', { defaultValue: 'Genre (optional)' })}
            className="w-40 rounded border bg-background px-2 py-1 text-[11px] outline-none focus:border-ring"
          />
          <button
            type="button"
            data-testid="arc-suggest-run"
            disabled={disabled}
            className="rounded bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            onClick={() => sg.run(premise.trim(), genre.trim())}
          >
            {sg.isPending
              ? t('motif.arc.suggest.running', { defaultValue: 'Ranking…' })
              : t('motif.arc.suggest.run', { defaultValue: 'Suggest arcs' })}
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {sg.isError && (
          <p role="alert" data-testid="arc-suggest-error" className="p-4 text-center text-xs text-destructive">
            {t('motif.arc.suggest.error', { defaultValue: 'Could not rank arc suggestions.' })}
          </p>
        )}
        {sg.ran && !sg.isError && sg.candidates.length === 0 && (
          <p data-testid="arc-suggest-empty" className="p-4 text-center text-xs text-muted-foreground">
            {t('motif.arc.suggest.empty', {
              defaultValue: 'No arc templates fit yet — create one, or import a story to deconstruct.',
            })}
          </p>
        )}
        {sg.candidates.length > 0 && (
          <ul data-testid="arc-suggest-results" className="flex flex-col">
            {sg.candidates.map((c) => (
              <li key={c.arc_template.id} data-testid={`arc-suggest-row-${c.arc_template.id}`} className="border-b px-2 py-1.5">
                <div className="flex items-center gap-2">
                  <span className="flex-1 truncate text-[12px] font-medium">{c.arc_template.name}</span>
                  {c.arc_template.mine && (
                    <span className="rounded bg-muted px-1 py-0.5 text-[9px] text-muted-foreground">
                      {t('motif.arc.suggest.mine', { defaultValue: 'yours' })}
                    </span>
                  )}
                  <span className="text-[10px] tabular-nums text-muted-foreground">{Math.round(c.score * 100)}%</span>
                </div>
                <div className="mt-0.5 flex items-center gap-2 text-[10px] text-muted-foreground">
                  {c.arc_template.chapter_span != null && (
                    <span>{t('motif.arc.suggest.span', { count: c.arc_template.chapter_span, defaultValue: '{{count}} ch' })}</span>
                  )}
                  {c.arc_template.genre_tags.length > 0 && <span className="truncate">{c.arc_template.genre_tags.join(' · ')}</span>}
                </div>
                {c.match_reason && (
                  <p data-testid="arc-suggest-reason" className="mt-0.5 text-[10px] italic text-muted-foreground/80">{c.match_reason}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
