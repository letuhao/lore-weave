import { useEffect, useRef, useState } from 'react';
import { KindBadge } from './KindBadge';
import type { GlossaryEntity } from '../types';

type Props = {
  entity: GlossaryEntity | null;
  isLoading: boolean;
  isSaving: boolean;
  onClose: () => void;
  onPatch: (changes: { status?: string; tags?: string[] }) => Promise<void>;
};

const STATUS_OPTIONS = ['draft', 'active', 'inactive'] as const;

export function EntityDetailPanel({ entity, isLoading, isSaving, onClose, onPatch }: Props) {
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
              {/* Chapter Links section — placeholder until SP-3 */}
              <section className="p-4">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Chapter Links
                </p>
                {entity.chapter_links.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No chapter links yet. (Chapter link editor added in SP-3.)
                  </p>
                ) : (
                  <ul className="space-y-1">
                    {entity.chapter_links.map((cl) => (
                      <li key={cl.link_id} className="flex items-center gap-2 text-xs">
                        <span className="rounded bg-muted px-1.5 py-0.5">{cl.relevance}</span>
                        <span className="text-muted-foreground">
                          {cl.chapter_title ?? cl.chapter_id}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {/* Attributes section — placeholder until SP-4 */}
              <section className="p-4">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Attributes ({entity.attribute_values.length})
                </p>
                <div className="space-y-1">
                  {entity.attribute_values.slice(0, 5).map((av) => (
                    <div key={av.attr_value_id} className="flex items-center gap-2 text-xs">
                      <span className="w-28 shrink-0 text-muted-foreground">
                        {av.attribute_def.name}
                        {av.attribute_def.is_required && (
                          <span className="ml-0.5 text-destructive">*</span>
                        )}
                      </span>
                      <span className="truncate">{av.original_value || '—'}</span>
                    </div>
                  ))}
                  {entity.attribute_values.length > 5 && (
                    <p className="text-xs text-muted-foreground">
                      +{entity.attribute_values.length - 5} more attributes (inline editor in SP-4)
                    </p>
                  )}
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
