import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Layers } from 'lucide-react';
import { Skeleton } from '@/components/shared';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import type { GroundResult } from '../types';

interface ModelOpt {
  user_model_id: string;
  alias?: string | null;
  provider_model_name: string;
}

/** C2 chapter-SELECTION grounding: the author picks specific chapters (a list, never
 *  auto-bulk) to embed as a grounding corpus — raw prose beyond what knowledge RAG +
 *  glossary canon surface. Self-contained: owns the chapter list + selection state.
 *  Embeds via a chosen model (BYOK); idempotent server-side (re-ingest = no-op). */
export function ChapterSelectionPicker({
  bookId,
  embeds,
  onGround,
  busy,
}: {
  bookId: string;
  embeds: ModelOpt[];
  onGround: (body: { embedding_model_ref: string; chapter_ids: string[] }) => Promise<GroundResult | null>;
  busy: boolean;
}) {
  const { t } = useTranslation('enrichment');
  const { accessToken } = useAuth();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [embedModel, setEmbedModel] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['book-chapters', bookId],
    // book-service caps `limit` at 100 (an out-of-range value falls back to the
    // default 20 — NOT a clamp), so request exactly the max. For a book with more
    // chapters we surface a "showing N of total" notice below (no silent cap).
    queryFn: () => booksApi.listChapters(accessToken!, bookId, { lifecycle_state: 'active', limit: 100 }),
    enabled: !!accessToken && !!bookId,
  });
  const chapters = [...(data?.items ?? [])].sort((a, b) => a.sort_order - b.sort_order);
  const total = data?.total ?? 0;
  const truncated = chapters.length < total;

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const submit = async () => {
    if (!embedModel || selected.size === 0) return;
    const r = await onGround({ embedding_model_ref: embedModel, chapter_ids: [...selected] });
    if (r) setSelected(new Set());
  };

  return (
    <div className="space-y-3 rounded-lg border bg-card p-3" data-testid="chapter-selection-picker">
      <div className="flex items-center gap-1.5">
        <Layers className="h-3.5 w-3.5 text-primary" />
        <h4 className="text-xs font-semibold">{t('ground.title')}</h4>
      </div>
      <p className="text-[11px] text-muted-foreground">{t('ground.subtitle')}</p>
      {truncated && (
        <p data-testid="ground-truncated" className="text-[11px] text-warning">
          {t('ground.showing', { shown: chapters.length, total })}
        </p>
      )}

      {isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : chapters.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">{t('ground.no_chapters')}</p>
      ) : (
        <div className="max-h-48 space-y-1 overflow-y-auto rounded border bg-background p-2">
          {chapters.map((c) => (
            <label key={c.chapter_id} className="flex items-center gap-2 text-[11px]">
              <input
                type="checkbox"
                checked={selected.has(c.chapter_id)}
                onChange={() => toggle(c.chapter_id)}
                data-testid={`ground-chapter-${c.chapter_id}`}
              />
              <span className="text-muted-foreground">#{c.sort_order}</span>
              <span className="truncate font-serif">{c.title || t('untitled')}</span>
            </label>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <select
          aria-label={t('sources.embed_model')}
          value={embedModel}
          onChange={(e) => setEmbedModel(e.target.value)}
          className="rounded border bg-background px-2 py-1"
        >
          <option value="">{t('gaps.select_model')}</option>
          {embeds.map((m) => (
            <option key={m.user_model_id} value={m.user_model_id}>
              {m.alias || m.provider_model_name}
            </option>
          ))}
        </select>
        <button
          type="button"
          data-testid="ground-submit"
          disabled={busy || selected.size === 0 || !embedModel}
          onClick={() => void submit()}
          className="rounded-md bg-primary px-3 py-1.5 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {busy ? t('ground.ingesting') : t('ground.ingest', { count: selected.size })}
        </button>
      </div>
    </div>
  );
}
