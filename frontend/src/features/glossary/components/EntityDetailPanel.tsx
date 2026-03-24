import { useEffect, useRef, useState } from 'react';
import { KindBadge } from './KindBadge';
import { ChapterLinkEditor } from './ChapterLinkEditor';
import { AttributeRow } from './AttributeRow';
import type { GlossaryEntity } from '../types';

type Props = {
  entity: GlossaryEntity | null;
  bookId: string;
  token: string;
  isLoading: boolean;
  isSaving: boolean;
  onClose: () => void;
  onPatch: (changes: { status?: string; tags?: string[] }) => Promise<void>;
  onRefresh: () => void;
};

const STATUS_OPTIONS = ['draft', 'active', 'inactive'] as const;

export function EntityDetailPanel({ entity, bookId, token, isLoading, isSaving, onClose, onPatch, onRefresh }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [tagInput, setTagInput] = useState('');
  const [localTags, setLocalTags] = useState<string[]>([]);
  const [tagsChanged, setTagsChanged] = useState(false);

  // Sync local tags when entity changes
  useEffect(() => {
    if (entity) {
      setLocalTags(entity.tags ?? []);
      setTagsChanged(false);
    }
  }, [entity]);

  // Close on ESC
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  function addTag(val: string) {
    const tag = val.trim();
    if (!tag || localTags.includes(tag)) return;
    const next = [...localTags, tag];
    setLocalTags(next);
    setTagsChanged(true);
    setTagInput('');
  }

  function removeTag(tag: string) {
    const next = localTags.filter((t) => t !== tag);
    setLocalTags(next);
    setTagsChanged(true);
  }

  async function saveTags() {
    await onPatch({ tags: localTags });
    setTagsChanged(false);
  }

  if (!entity && !isLoading) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/20"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        ref={panelRef}
        className="fixed right-0 top-0 z-50 flex h-full w-full max-w-lg flex-col border-l bg-background shadow-xl"
      >
        {/* ── Header ─────────────────────────────────────────────────────────── */}
        <div className="flex items-start gap-3 border-b p-4">
          {entity && <KindBadge kind={entity.kind} size="md" />}
          <div className="min-w-0 flex-1">
            <p className="truncate text-base font-semibold">
              {entity?.display_name || '(unnamed)'}
            </p>
            {entity && (
              <select
                value={entity.status}
                disabled={isSaving}
                onChange={(e) => onPatch({ status: e.target.value })}
                className="mt-1 rounded border bg-background px-1.5 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            )}
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* ── Body ───────────────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto">
          {isLoading && (
            <div className="space-y-3 p-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-10 animate-pulse rounded bg-muted" />
              ))}
            </div>
          )}

          {entity && !isLoading && (
            <div className="divide-y">
              {/* Chapter Links section */}
              <section className="p-4">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Chapter Links
                </p>
                <ChapterLinkEditor
                  entity={entity}
                  bookId={bookId}
                  token={token}
                  onRefresh={onRefresh}
                />
              </section>

              {/* Attributes section */}
              <section className="p-4">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Attributes ({entity.attribute_values.length})
                </p>
                <div>
                  {entity.attribute_values.map((av) => (
                    <AttributeRow
                      key={av.attr_value_id}
                      av={av}
                      bookId={bookId}
                      entityId={entity.entity_id}
                      token={token}
                      onRefresh={onRefresh}
                    />
                  ))}
                </div>
              </section>
            </div>
          )}
        </div>

        {/* ── Footer: tags + timestamps ───────────────────────────────────────── */}
        {entity && (
          <div className="border-t p-4 space-y-3">
            {/* Tags editor */}
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Tags
              </p>
              <div className="flex flex-wrap gap-1.5">
                {localTags.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 rounded-full border bg-muted px-2 py-0.5 text-xs"
                  >
                    #{tag}
                    <button
                      onClick={() => removeTag(tag)}
                      className="hover:text-destructive"
                      aria-label={`Remove tag ${tag}`}
                    >
                      ✕
                    </button>
                  </span>
                ))}
                <input
                  type="text"
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ',') {
                      e.preventDefault();
                      addTag(tagInput);
                    }
                  }}
                  placeholder="Add tag…"
                  className="h-6 w-24 rounded border bg-background px-2 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              {tagsChanged && (
                <button
                  onClick={saveTags}
                  disabled={isSaving}
                  className="mt-2 rounded border px-2 py-1 text-xs font-medium hover:bg-muted disabled:opacity-50"
                >
                  {isSaving ? 'Saving…' : 'Save tags'}
                </button>
              )}
            </div>

            {/* Timestamps */}
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span>Created {new Date(entity.created_at).toLocaleDateString()}</span>
              <span>Updated {new Date(entity.updated_at).toLocaleDateString()}</span>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
