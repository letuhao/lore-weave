import { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Plus, Pencil, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '../api';
import type { GenreGroup, EntityKind } from '../types';
import { ConfirmDialog } from '@/components/shared';
import { cn } from '@/lib/utils';
import { GenreFormModal } from './GenreFormModal';

type Props = {
  bookId: string;
  kinds: EntityKind[];
  onClose: () => void;
};

export function GenreGroupsPanel({ bookId, kinds, onClose }: Props) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [modalMode, setModalMode] = useState<'create' | 'edit' | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<GenreGroup | null>(null);

  const { data: genres = [], isLoading } = useQuery({
    queryKey: ['glossary-genres', bookId],
    queryFn: () => glossaryApi.listGenres(bookId, accessToken!),
    enabled: !!accessToken,
  });

  const selected = genres.find((g) => g.id === selectedId) ?? genres[0] ?? null;

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['glossary-genres', bookId] });

  // Compute kind/attr counts for selected genre
  const taggedKinds = useMemo(() => {
    if (!selected) return [];
    return kinds.filter((k) => k.genre_tags.includes(selected.name));
  }, [kinds, selected]);

  const taggedAttrs = useMemo(() => {
    if (!selected) return new Map<string, { kind: EntityKind; attrs: EntityKind['default_attributes'] }>();
    const map = new Map<string, { kind: EntityKind; attrs: EntityKind['default_attributes'] }>();
    for (const k of kinds) {
      const matching = k.default_attributes.filter((a) => a.genre_tags.includes(selected.name));
      if (matching.length > 0) {
        map.set(k.kind_id, { kind: k, attrs: matching });
      }
    }
    return map;
  }, [kinds, selected]);

  const totalAttrCount = useMemo(() => {
    let n = 0;
    taggedAttrs.forEach((v) => (n += v.attrs.length));
    return n;
  }, [taggedAttrs]);

  const handleCreate = async (data: { name: string; color: string; description: string }) => {
    await glossaryApi.createGenre(bookId, data, accessToken!);
    toast.success('Genre created');
    setModalMode(null);
    invalidate();
  };

  const handleEdit = async (data: { name: string; color: string; description: string }) => {
    if (!selected) return;
    await glossaryApi.patchGenre(bookId, selected.id, data, accessToken!);
    toast.success('Genre updated');
    setModalMode(null);
    invalidate();
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await glossaryApi.deleteGenre(bookId, deleteTarget.id, accessToken!);
      toast.success('Genre deleted');
      if (selectedId === deleteTarget.id) setSelectedId(null);
      setDeleteTarget(null);
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-3 border-b px-4 py-3">
        <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <h3 className="text-sm font-semibold">Genre Groups</h3>
        <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">
          {genres.length}
        </span>
      </div>

      {/* Two-panel layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: genre list */}
        <div className="w-64 flex-shrink-0 border-r overflow-y-auto">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="text-xs font-medium text-muted-foreground">Genres</span>
            <button
              onClick={() => setModalMode('create')}
              className="inline-flex items-center gap-1 rounded-md bg-primary px-2 py-1 text-[10px] font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <Plus className="h-3 w-3" />
              New
            </button>
          </div>

          {isLoading && (
            <div className="space-y-2 p-3">
              {[1, 2, 3].map((i) => <div key={i} className="h-10 animate-pulse rounded-md bg-secondary" />)}
            </div>
          )}

          {!isLoading && genres.length === 0 && (
            <div className="p-4 text-center text-xs text-muted-foreground">
              No genres yet. Create one to organize glossary attributes by genre.
            </div>
          )}

          {genres.map((g) => (
            <button
              key={g.id}
              onClick={() => setSelectedId(g.id)}
              className={cn(
                'flex w-full items-center gap-2.5 border-b px-3 py-2.5 text-left transition-colors',
                selected?.id === g.id ? 'border-l-2 border-l-primary bg-primary/5' : 'hover:bg-secondary/50',
              )}
            >
              <div className="h-2 w-2 flex-shrink-0 rounded-sm" style={{ background: g.color }} />
              <div className="flex-1 min-w-0">
                <div className="truncate text-[13px] font-medium">{g.name}</div>
                <div className="text-[10px] text-muted-foreground">
                  {kinds.filter((k) => k.genre_tags.includes(g.name)).length} kinds
                </div>
              </div>
            </button>
          ))}
        </div>

        {/* Right: genre detail */}
        <div className="flex-1 overflow-y-auto">
          {!selected ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              {genres.length === 0 ? 'Create a genre to get started' : 'Select a genre'}
            </div>
          ) : (
            <div>
              {/* Header */}
              <div className="flex items-center justify-between border-b px-4 py-3">
                <div className="flex items-center gap-2.5">
                  <div className="h-2.5 w-2.5 rounded-sm" style={{ background: selected.color }} />
                  <span className="text-sm font-semibold">{selected.name}</span>
                </div>
                <div className="flex gap-1.5">
                  <button
                    onClick={() => setModalMode('edit')}
                    className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-[11px] font-medium text-foreground hover:bg-secondary transition-colors"
                  >
                    <Pencil className="h-3 w-3" />
                    Edit
                  </button>
                  <button
                    onClick={() => setDeleteTarget(selected)}
                    className="rounded-md border px-2.5 py-1 text-[11px] font-medium text-destructive hover:bg-destructive/10 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {/* Info bar */}
              <div className="border-b px-4 py-3" style={{ background: selected.color + '08' }}>
                {selected.description && (
                  <p className="mb-2 text-xs text-muted-foreground">{selected.description}</p>
                )}
                <div className="flex gap-5 text-xs">
                  <div>
                    <span className="block text-[10px] text-muted-foreground">Kinds tagged</span>
                    <span className="font-semibold">{taggedKinds.length}</span>
                  </div>
                  <div>
                    <span className="block text-[10px] text-muted-foreground">Attributes tagged</span>
                    <span className="font-semibold">{totalAttrCount}</span>
                  </div>
                </div>
              </div>

              {/* Tagged kinds */}
              <div className="border-b px-4 py-3">
                <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Kinds with this genre tag
                </h4>
                {taggedKinds.length === 0 ? (
                  <p className="text-[11px] text-muted-foreground">No kinds are tagged with &ldquo;{selected.name}&rdquo; yet.</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {taggedKinds.map((k) => (
                      <span
                        key={k.kind_id}
                        className="inline-flex items-center gap-1 rounded-md border bg-secondary px-2.5 py-1 text-[11px]"
                      >
                        <span>{k.icon}</span>
                        {k.name}
                      </span>
                    ))}
                  </div>
                )}
                <p className="mt-1.5 text-[10px] text-muted-foreground">
                  To tag/untag a kind, go to Kinds &amp; Attributes &rarr; Genres row.
                </p>
              </div>

              {/* Tagged attributes grouped by kind */}
              <div className="px-4 py-3">
                <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Attributes scoped to this genre
                </h4>
                {totalAttrCount === 0 ? (
                  <p className="text-[11px] text-muted-foreground">No attributes are scoped to &ldquo;{selected.name}&rdquo; yet.</p>
                ) : (
                  <div className="space-y-3">
                    {[...taggedAttrs.entries()].map(([kindId, { kind, attrs }]) => (
                      <div key={kindId}>
                        <div className="mb-1 flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
                          <span>{kind.icon}</span>
                          {kind.name}
                        </div>
                        <div className="flex flex-wrap gap-1 pl-3.5">
                          {attrs.map((a) => (
                            <span
                              key={a.attr_def_id}
                              className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px]"
                              style={{ background: selected.color + '12', border: `1px solid ${selected.color}25` }}
                            >
                              {a.name}
                              <span className="rounded bg-secondary px-1 py-px font-mono text-[9px] text-muted-foreground">
                                {a.field_type}
                              </span>
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <p className="mt-2 text-[10px] text-muted-foreground">
                  To scope an attribute to a genre, edit the attribute in Kinds &amp; Attributes tab.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      {modalMode === 'create' && (
        <GenreFormModal bookId={bookId} onSave={handleCreate} onClose={() => setModalMode(null)} />
      )}
      {modalMode === 'edit' && selected && (
        <GenreFormModal bookId={bookId} genre={selected} onSave={handleEdit} onClose={() => setModalMode(null)} />
      )}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        title="Delete Genre"
        description={`Delete "${deleteTarget?.name}"? This will not delete any entities or attributes — it only removes the genre group definition.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
}
