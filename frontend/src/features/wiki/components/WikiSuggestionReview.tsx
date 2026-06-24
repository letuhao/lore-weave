// W1 — one wiki suggestion, reviewed. Renders the AI-regen proposal as a read-only
// preview + a collapsible computed del/add diff vs the current article body
// (CLARIFY: preview + diff-thu-gọn). A non-envelope diff_json (hypothetical
// community suggestion — no FE creates one today) degrades to a raw JSON fallback
// without crashing. Shared by the editor sidebar panel and the reader inline panel.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { JSONContent } from '@tiptap/react';
import { CheckCircle2, XCircle, Sparkles, Users, ChevronDown, ChevronRight } from 'lucide-react';
import { ContentRenderer } from '@/components/reader/ContentRenderer';
import { CitationProvider } from '@/components/reader/CitationContext';
import type { WikiSuggestionResp } from '../types';
import { asAiRegenEnvelope, tiptapToLines, diffLines } from '../lib/wikiDiff';

export function WikiSuggestionReview({
  suggestion,
  currentBodyJson,
  bookId,
  onAccept,
  onReject,
}: {
  suggestion: WikiSuggestionResp;
  currentBodyJson?: unknown;
  bookId: string;
  onAccept: () => void;
  onReject: () => void;
}) {
  const { t } = useTranslation('wiki');
  const [showDiff, setShowDiff] = useState(false);
  const envelope = asAiRegenEnvelope(suggestion.diff_json);

  return (
    <div className="border-b px-3 py-3 last:border-b-0">
      <div className="mb-2 flex items-center gap-2">
        {envelope ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-medium text-primary">
            <Sparkles className="h-3 w-3" /> {t('suggestions.aiRegen')}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/15 px-2 py-0.5 text-[10px] font-medium text-blue-400">
            <Users className="h-3 w-3" /> {t('suggestions.community')}
          </span>
        )}
        <span className="text-xs font-medium">{suggestion.article_display_name || t('edit')}</span>
      </div>

      {envelope && (
        <p className="mb-2 text-[11px] text-muted-foreground">{t('suggestions.humanEditedNote')}</p>
      )}
      {suggestion.reason && (
        <p className="mb-2 text-[11px] italic text-muted-foreground">{suggestion.reason}</p>
      )}

      {envelope ? (
        <>
          <div className="mb-2 rounded border bg-card/50 p-2">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              {t('suggestions.preview')}
            </div>
            <div className="wiki-article-body max-h-64 overflow-y-auto text-sm">
              <CitationProvider bookId={bookId}>
                <ContentRenderer
                  blocks={(envelope.body_json as { content?: JSONContent[] }).content ?? []}
                  mode="compact"
                />
              </CitationProvider>
            </div>
          </div>

          {currentBodyJson != null && (
            <div className="mb-2">
              <button
                type="button"
                onClick={() => setShowDiff((v) => !v)}
                className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline"
              >
                {showDiff ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                {showDiff ? t('suggestions.hideDiff') : t('suggestions.showDiff')}
              </button>
              {showDiff && (
                <div className="mt-1 max-h-72 overflow-auto rounded border font-mono text-[11px]">
                  {diffLines(tiptapToLines(currentBodyJson), tiptapToLines(envelope.body_json)).map(
                    (row, idx) => (
                      <div
                        key={idx}
                        className={
                          row.type === 'del'
                            ? 'bg-red-500/10 px-2 py-0.5 text-red-300'
                            : row.type === 'add'
                              ? 'bg-green-500/10 px-2 py-0.5 text-green-300'
                              : 'px-2 py-0.5 text-muted-foreground'
                        }
                      >
                        <span className="select-none opacity-60">
                          {row.type === 'del' ? '- ' : row.type === 'add' ? '+ ' : '  '}
                        </span>
                        {row.text}
                      </div>
                    ),
                  )}
                </div>
              )}
            </div>
          )}
        </>
      ) : (
        <pre className="mb-2 max-h-40 overflow-auto rounded border bg-card/50 p-2 text-[10px] text-muted-foreground">
          {JSON.stringify(suggestion.diff_json, null, 2)}
        </pre>
      )}

      <div className="flex gap-1">
        <button
          type="button"
          onClick={onAccept}
          className="inline-flex items-center gap-1 rounded border border-green-500/20 bg-green-500/10 px-2 py-0.5 text-[10px] font-medium text-green-400 hover:bg-green-500/20"
        >
          <CheckCircle2 className="h-3 w-3" /> {t('suggestions.accept')}
        </button>
        <button
          type="button"
          onClick={onReject}
          className="inline-flex items-center gap-1 rounded border border-red-500/15 bg-red-500/[0.06] px-2 py-0.5 text-[10px] font-medium text-red-400 hover:bg-red-500/15"
        >
          <XCircle className="h-3 w-3" /> {t('suggestions.reject')}
        </button>
      </div>
    </div>
  );
}
