import { useEffect, useState } from 'react';
import { booksApi, type Chapter } from '@/features/books/api';
import { glossaryApi } from '../api';
import type { GlossaryEntity, Relevance } from '../types';

const RELEVANCE_OPTIONS: { value: Relevance; label: string }[] = [
  { value: 'major', label: 'Major' },
  { value: 'appears', label: 'Appears' },
  { value: 'mentioned', label: 'Mentioned' },
];

type Props = {
  entity: GlossaryEntity;
  bookId: string;
  token: string;
  onRefresh: () => void;
};

export function ChapterLinkEditor({ entity, bookId, token, onRefresh }: Props) {
  const [bookChapters, setBookChapters] = useState<Chapter[]>([]);
  const [isAddingLink, setIsAddingLink] = useState(false);
  const [selectedChapterId, setSelectedChapterId] = useState('');
  const [relevance, setRelevance] = useState<Relevance>('appears');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [unlinkingId, setUnlinkingId] = useState<string | null>(null);
  const [chaptersLoaded, setChaptersLoaded] = useState(false);

  // Load book chapters once on mount
  useEffect(() => {
    setChaptersLoaded(false);
    booksApi
      .listChapters(token, bookId, { lifecycle_state: 'active', limit: 500 })
      .then((res) => setBookChapters(res.items))
      .catch(() => {})
      .finally(() => setChaptersLoaded(true));
  }, [token, bookId]);

  const linkedChapterIds = new Set(entity.chapter_links.map((cl) => cl.chapter_id));
  const availableChapters = bookChapters.filter((ch) => !linkedChapterIds.has(ch.chapter_id));

  // Sort links: chapter_index ASC (null last), then added_at ASC
  const sortedLinks = [...entity.chapter_links].sort((a, b) => {
    const ai = a.chapter_index ?? Infinity;
    const bi = b.chapter_index ?? Infinity;
    if (ai !== bi) return ai - bi;
    return a.added_at.localeCompare(b.added_at);
  });

  async function handleAdd() {
    if (!selectedChapterId) return;
    setSaving(true);
    setError('');
    try {
      await glossaryApi.createChapterLink(
        bookId,
        entity.entity_id,
        { chapter_id: selectedChapterId, relevance, note: note || undefined },
        token,
      );
      setIsAddingLink(false);
      setSelectedChapterId('');
      setNote('');
      setRelevance('appears');
      onRefresh();
    } catch (e: unknown) {
      const msg = (e as Error).message || 'Failed to link chapter';
      if (msg.includes('GLOSS_DUPLICATE_CHAPTER_LINK')) {
        setError('This chapter is already linked.');
      } else if (msg.includes('GLOSS_CHAPTER_NOT_IN_BOOK')) {
        setError('This chapter does not belong to this book.');
      } else {
        setError(msg);
      }
    } finally {
      setSaving(false);
    }
  }

  function cancelAdd() {
    setIsAddingLink(false);
    setSelectedChapterId('');
    setNote('');
    setRelevance('appears');
    setError('');
  }

  async function handleUnlink(linkId: string) {
    setUnlinkingId(linkId);
    setError('');
    try {
      await glossaryApi.deleteChapterLink(bookId, entity.entity_id, linkId, token);
      onRefresh();
    } catch (e: unknown) {
      setError((e as Error).message || 'Failed to unlink chapter');
    } finally {
      setUnlinkingId(null);
    }
  }

  return (
    <div className="space-y-2">
      {/* Link list */}
      {sortedLinks.length === 0 && !isAddingLink && (
        <p className="text-xs text-muted-foreground">No chapter links yet.</p>
      )}
      {sortedLinks.length > 0 && (
        <ul className="space-y-1">
          {sortedLinks.map((cl) => (
            <li key={cl.link_id} className="flex items-center gap-2 text-xs">
              <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-medium capitalize">
                {cl.relevance}
              </span>
              <span className="min-w-0 flex-1 truncate text-muted-foreground">
                {cl.chapter_title ?? cl.chapter_id}
              </span>
              {cl.note && (
                <span className="max-w-[120px] truncate italic text-muted-foreground">
                  "{cl.note}"
                </span>
              )}
              <button
                onClick={() => handleUnlink(cl.link_id)}
                disabled={unlinkingId === cl.link_id}
                className="ml-auto shrink-0 rounded p-0.5 text-muted-foreground hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50"
                aria-label="Unlink chapter"
              >
                {unlinkingId === cl.link_id ? '…' : '✕'}
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Error banner */}
      {error && <p className="text-xs text-destructive">{error}</p>}

      {/* Add form */}
      {isAddingLink ? (
        <div className="space-y-1.5 rounded border p-2">
          <select
            value={selectedChapterId}
            onChange={(e) => setSelectedChapterId(e.target.value)}
            className="w-full rounded border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">Select chapter…</option>
            {availableChapters.map((ch) => (
              <option key={ch.chapter_id} value={ch.chapter_id}>
                {ch.title ?? ch.original_filename}
              </option>
            ))}
          </select>

          <select
            value={relevance}
            onChange={(e) => setRelevance(e.target.value as Relevance)}
            className="w-full rounded border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {RELEVANCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>

          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (optional)"
            className="w-full rounded border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          />

          <div className="flex gap-1">
            <button
              onClick={handleAdd}
              disabled={!selectedChapterId || saving}
              className="rounded border px-2 py-0.5 text-xs font-medium hover:bg-muted disabled:opacity-50"
            >
              {saving ? 'Linking…' : 'Link'}
            </button>
            <button
              onClick={cancelAdd}
              className="rounded border px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : !chaptersLoaded ? (
        <p className="text-xs text-muted-foreground">Loading chapters…</p>
      ) : bookChapters.length === 0 ? (
        <p className="text-xs text-muted-foreground">No chapters in this book yet.</p>
      ) : availableChapters.length === 0 ? (
        <p className="text-xs text-muted-foreground">All chapters linked.</p>
      ) : (
        <button
          onClick={() => setIsAddingLink(true)}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          + Link chapter
        </button>
      )}
    </div>
  );
}
