import { useEffect, useState, useCallback, useMemo } from 'react';
import { Settings2, Plus, Trash2, Save, Loader2, ChevronRight, X, Pencil, GripVertical, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { type EntityKind, type AttributeDefinition, type GenreGroup } from '@/features/glossary/types';
import { Skeleton } from '@/components/shared/Skeleton';
import { ConfirmDialog } from '@/components/shared';
import { cn } from '@/lib/utils';
import { SEED_KINDS, countKindModifications, isAttrModified } from './seedDefaults';
import { AttrEditorModal } from './AttrEditorModal';

function AttrRow({ attr, kindCode, onEdit, onToggle, onDelete, dragProps, isOver, genreColorMap }: {
  attr: import('@/features/glossary/types').AttributeDefinition;
  kindCode?: string;
  onEdit: () => void;
  onToggle: () => void;
  onDelete: (() => void) | undefined;
  dragProps?: { draggable: true; onDragStart: () => void; onDragOver: (e: React.DragEvent) => void; onDragEnd: () => void; onDrop: () => void };
  isOver?: boolean;
  genreColorMap?: Map<string, string>;
}) {
  const modified = kindCode ? isAttrModified(kindCode, attr) : false;
  const inactive = attr.is_active === false;
  return (
    <div
      {...dragProps}
      className={cn(
        "flex items-center gap-2 border-b px-4 py-2.5 group hover:bg-card/50 transition-colors last:border-b-0",
        inactive && "opacity-50",
        isOver && "border-t-2 border-t-primary",
      )}
    >
      {dragProps && <GripVertical className="h-3 w-3 text-muted-foreground/30 group-hover:text-muted-foreground/70 flex-shrink-0 cursor-grab" />}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={cn("text-xs font-medium", inactive && "line-through")}>{attr.name}</span>
          <span className="rounded bg-secondary px-1.5 py-0.5 text-[9px] text-muted-foreground">{attr.field_type}</span>
          {attr.is_system ? (
            <span className="rounded bg-blue-500/15 px-1 py-0.5 text-[9px] font-medium text-blue-400">SYS</span>
          ) : (
            <span className="rounded bg-primary/15 px-1 py-0.5 text-[9px] font-medium text-primary">USR</span>
          )}
          {modified && <span className="text-[9px] font-medium text-amber-400 italic">modified</span>}
          {(attr.auto_fill_prompt || attr.translation_hint) && (
            <span className="inline-flex items-center gap-1 rounded bg-accent/12 px-1 py-0.5 text-[8px] font-semibold text-accent">AI</span>
          )}
          {(attr.genre_tags ?? []).map((tag) => {
            const color = genreColorMap?.get(tag);
            return (
              <span key={tag} className="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[8px] font-medium"
                style={color ? { background: color + '18', color } : { background: 'rgba(139,92,246,0.15)', color: '#a78bfa' }}>
                <span className="h-1 w-1 rounded-sm flex-shrink-0" style={{ background: color || '#8b5cf6' }} />
                {tag}
              </span>
            );
          })}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground font-mono">{attr.code}</span>
          {attr.description && <span className="text-[10px] text-muted-foreground truncate max-w-[200px]">{attr.description}</span>}
        </div>
      </div>
      <span className="text-[10px] text-muted-foreground">{attr.is_required ? 'required' : 'optional'}</span>
      <button
        onClick={onToggle}
        className={cn(
          "relative h-[18px] w-8 rounded-full transition-colors flex-shrink-0",
          inactive ? "bg-secondary" : "bg-green-500",
        )}
        title={inactive ? 'Activate' : 'Deactivate'}
      >
        <span className={cn(
          "absolute top-[2px] h-[14px] w-[14px] rounded-full transition-all",
          inactive ? "left-[2px] bg-muted-foreground" : "left-[16px] bg-white",
        )} />
      </button>
      <button
        onClick={onEdit}
        className="opacity-0 group-hover:opacity-100 rounded p-1 text-muted-foreground hover:text-foreground hover:bg-secondary transition-all"
        title="Edit attribute"
      >
        <Pencil className="h-3 w-3" />
      </button>
      {onDelete && (
        <button
          onClick={onDelete}
          className="opacity-0 group-hover:opacity-100 rounded p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
          title="Delete attribute"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

export function KindEditor({ bookId, onClose }: { bookId: string; onClose: () => void }) {
  const { accessToken } = useAuth();
  const [kinds, setKinds] = useState<EntityKind[]>([]);
  const [genres, setGenres] = useState<GenreGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Edit state for selected kind
  const [editName, setEditName] = useState('');
  const [editIcon, setEditIcon] = useState('');
  const [editColor, setEditColor] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editGenreTags, setEditGenreTags] = useState<string[]>([]);
  const [kindDirty, setKindDirty] = useState(false);
  const [savingKind, setSavingKind] = useState(false);

  // Delete confirm
  const [deleteTarget, setDeleteTarget] = useState<EntityKind | null>(null);
  const [deleteAttrTarget, setDeleteAttrTarget] = useState<AttributeDefinition | null>(null);

  // Revert confirm
  const [revertTarget, setRevertTarget] = useState<EntityKind | null>(null);

  // New kind dialog
  const [showNewKind, setShowNewKind] = useState(false);
  const [newCode, setNewCode] = useState('');
  const [newName, setNewName] = useState('');

  // Attr editor modal
  const [editAttr, setEditAttr] = useState<AttributeDefinition | null>(null);

  // Drag reorder kinds
  const [dragKindId, setDragKindId] = useState<string | null>(null);
  const [overKindId, setOverKindId] = useState<string | null>(null);

  // Drag reorder attrs
  const [dragAttrId, setDragAttrId] = useState<string | null>(null);
  const [overAttrId, setOverAttrId] = useState<string | null>(null);

  // Create attr via modal
  const [showCreateAttr, setShowCreateAttr] = useState(false);

  const loadKinds = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const [k, g] = await Promise.all([
        glossaryApi.getKinds(accessToken),
        glossaryApi.listGenres(bookId, accessToken).catch(() => [] as GenreGroup[]),
      ]);
      setKinds(k);
      setGenres(g);
      if (k.length > 0 && !selectedId) setSelectedId(k[0].kind_id);
    } catch (e) { toast.error((e as Error).message); }
    setLoading(false);
  }, [accessToken, bookId]);

  useEffect(() => { void loadKinds(); }, [loadKinds]);

  const selected = kinds.find((k) => k.kind_id === selectedId);

  // Sync edit state when selection changes
  useEffect(() => {
    if (selected) {
      setEditName(selected.name);
      setEditIcon(selected.icon);
      setEditColor(selected.color);
      setEditDescription(selected.description ?? '');
      setEditGenreTags(selected.genre_tags ?? []);
      setKindDirty(false);
    }
  }, [selected?.kind_id]);

  const handleSaveKind = async () => {
    if (!accessToken || !selected) return;
    setSavingKind(true);
    try {
      await glossaryApi.patchKind(accessToken, selected.kind_id, {
        name: editName, icon: editIcon, color: editColor,
        description: editDescription || null, genre_tags: editGenreTags,
      });
      toast.success('Kind saved');
      setKindDirty(false);
      await loadKinds();
    } catch (e) { toast.error((e as Error).message); }
    setSavingKind(false);
  };

  const handleCreateKind = async () => {
    if (!accessToken || !newCode || !newName) return;
    try {
      const k = await glossaryApi.createKind(accessToken, { code: newCode, name: newName });
      toast.success(`Kind "${k.name}" created`);
      setShowNewKind(false);
      setNewCode('');
      setNewName('');
      await loadKinds();
      setSelectedId(k.kind_id);
    } catch (e) { toast.error((e as Error).message); }
  };

  const handleDeleteKind = async () => {
    if (!accessToken || !deleteTarget) return;
    try {
      await glossaryApi.deleteKind(accessToken, deleteTarget.kind_id);
      toast.success('Kind deleted');
      setDeleteTarget(null);
      if (selectedId === deleteTarget.kind_id) setSelectedId(null);
      await loadKinds();
    } catch (e) { toast.error((e as Error).message); }
  };

  const handleRevertKind = async () => {
    if (!accessToken || !revertTarget) return;
    const seed = SEED_KINDS[revertTarget.code];
    if (!seed) return;
    try {
      await glossaryApi.patchKind(accessToken, revertTarget.kind_id, {
        name: seed.name, icon: seed.icon, color: seed.color,
      });
      const attrPatches = revertTarget.default_attributes
        .filter((a) => a.is_system && seed.attrs[a.code] && a.name !== seed.attrs[a.code].name)
        .map((a) => glossaryApi.patchAttrDef(accessToken, revertTarget.kind_id, a.attr_def_id, { name: seed.attrs[a.code].name }));
      await Promise.allSettled(attrPatches);
      toast.success('Reverted to defaults');
      setRevertTarget(null);
      await loadKinds();
    } catch (e) { toast.error((e as Error).message); }
  };

  const handleKindDrop = async (fromId: string, toId: string) => {
    if (!accessToken || fromId === toId) return;
    const ordered = kinds.map((k) => k.kind_id);
    const fromIdx = ordered.indexOf(fromId);
    const toIdx = ordered.indexOf(toId);
    if (fromIdx < 0 || toIdx < 0) return;
    ordered.splice(fromIdx, 1);
    ordered.splice(toIdx, 0, fromId);
    // Optimistic: reorder local state
    const reordered = ordered.map((id) => kinds.find((k) => k.kind_id === id)!).filter(Boolean);
    setKinds(reordered);
    try {
      await glossaryApi.reorderKinds(accessToken, ordered);
    } catch (e) {
      toast.error('Reorder failed');
      await loadKinds();
    }
  };

  const handleAttrDrop = async (fromId: string, toId: string) => {
    if (!accessToken || !selected || fromId === toId) return;
    const attrs = [...selected.default_attributes].sort((a, b) => a.sort_order - b.sort_order);
    const ordered = attrs.map((a) => a.attr_def_id);
    const fromIdx = ordered.indexOf(fromId);
    const toIdx = ordered.indexOf(toId);
    if (fromIdx < 0 || toIdx < 0) return;
    ordered.splice(fromIdx, 1);
    ordered.splice(toIdx, 0, fromId);
    try {
      await glossaryApi.reorderAttrDefs(accessToken, selected.kind_id, ordered);
      await loadKinds();
    } catch (e) {
      toast.error('Reorder failed');
      await loadKinds();
    }
  };

  const handleToggleAttr = async (attr: AttributeDefinition) => {
    if (!accessToken || !selected) return;
    try {
      await glossaryApi.patchAttrDef(accessToken, selected.kind_id, attr.attr_def_id, {
        is_active: !attr.is_active,
      });
      await loadKinds();
    } catch (e) { toast.error((e as Error).message); }
  };

  const handleDeleteAttr = async () => {
    if (!accessToken || !selected || !deleteAttrTarget) return;
    try {
      await glossaryApi.deleteAttrDef(accessToken, selected.kind_id, deleteAttrTarget.attr_def_id);
      toast.success('Attribute deleted');
      setDeleteAttrTarget(null);
      await loadKinds();
    } catch (e) { toast.error((e as Error).message); }
  };

  const systemKinds = kinds.filter((k) => k.is_default);
  const userKinds = kinds.filter((k) => !k.is_default);

  const genreColorMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const g of genres) map.set(g.name, g.color);
    return map;
  }, [genres]);

  if (loading) {
    return (
      <div className="space-y-3 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Settings2 className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Entity Kinds</h3>
          <span className="text-xs text-muted-foreground">{kinds.length} kinds</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowNewKind(true)}
            className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-3 w-3" /> New Kind
          </button>
          <button
            onClick={onClose}
            className="rounded-md border px-3 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            Back to Glossary
          </button>
        </div>
      </div>

      {/* Two-panel layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: kind list */}
        <div className="w-64 flex-shrink-0 border-r overflow-y-auto">
          {[{ label: 'System Kinds', items: systemKinds, isSystem: true },
            { label: 'User Kinds', items: userKinds, isSystem: false }]
            .filter((g) => g.items.length > 0)
            .map((group) => (
            <div key={group.label}>
              <div className={cn('px-4 py-2 text-[10px] font-semibold uppercase tracking-wider', group.isSystem ? 'text-muted-foreground' : 'text-primary')}>
                {group.label}
              </div>
              {group.items.map((k) => (
                <div
                  key={k.kind_id}
                  draggable
                  onDragStart={() => setDragKindId(k.kind_id)}
                  onDragOver={(e) => { e.preventDefault(); setOverKindId(k.kind_id); }}
                  onDragEnd={() => { setDragKindId(null); setOverKindId(null); }}
                  onDrop={() => {
                    if (dragKindId && dragKindId !== k.kind_id) void handleKindDrop(dragKindId, k.kind_id);
                    setDragKindId(null);
                    setOverKindId(null);
                  }}
                  className={cn(
                    'flex w-full items-center gap-1.5 px-2 py-2.5 text-left text-xs transition-colors border-b cursor-pointer group/kind',
                    selectedId === k.kind_id ? 'bg-primary/5 border-l-2 border-l-primary' : 'hover:bg-card/50',
                    overKindId === k.kind_id && dragKindId && dragKindId !== k.kind_id && 'border-t-2 border-t-primary',
                  )}
                  onClick={() => setSelectedId(k.kind_id)}
                >
                  <GripVertical className="h-3 w-3 text-muted-foreground/30 group-hover/kind:text-muted-foreground/70 flex-shrink-0 cursor-grab" />
                  <span className="text-base">{k.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium truncate">{k.name}</span>
                      {k.is_default ? (
                        <span className="rounded bg-blue-500/15 px-1.5 py-0.5 text-[8px] font-medium text-blue-400 flex-shrink-0">System</span>
                      ) : (
                        <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[8px] font-medium text-primary flex-shrink-0">Custom</span>
                      )}
                      {k.is_default && countKindModifications(k) > 0 && (
                        <span className="text-[8px] font-medium text-amber-400 italic flex-shrink-0">modified</span>
                      )}
                    </div>
                    <span className="text-[10px] text-muted-foreground">
                      {k.default_attributes.length} attr{k.default_attributes.length !== 1 ? 's' : ''}
                      {' · '}{k.entity_count} entit{k.entity_count !== 1 ? 'ies' : 'y'}
                    </span>
                  </div>
                  {selectedId === k.kind_id && <ChevronRight className="h-3 w-3 text-primary" />}
                </div>
              ))}
            </div>
          ))}
        </div>

        {/* Right: kind detail + attributes */}
        <div className="flex-1 overflow-y-auto">
          {selected ? (
            <div>
              {/* Kind edit form */}
              <div className="border-b px-6 py-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-muted-foreground">{selected.code}</span>
                    {selected.is_default && <span className="rounded bg-secondary px-1.5 py-0.5 text-[9px] text-muted-foreground">system</span>}
                    <span className="text-[10px] text-muted-foreground">
                      {selected.default_attributes.length} attrs · {selected.entity_count} entit{selected.entity_count !== 1 ? 'ies' : 'y'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {selected.is_default && countKindModifications(selected) > 0 && (
                      <button
                        onClick={() => setRevertTarget(selected)}
                        className="inline-flex items-center gap-1 rounded-md border border-dashed border-blue-500/40 px-2 py-1 text-[10px] font-medium text-blue-400 hover:bg-blue-500/10 transition-colors"
                        title="Revert all changes to system defaults"
                      >
                        <RotateCcw className="h-3 w-3" />
                        Revert to Default
                      </button>
                    )}
                    {!selected.is_default && (
                      <button
                        onClick={() => setDeleteTarget(selected)}
                        className="rounded p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
                        title="Delete kind"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                    {kindDirty && (
                      <button
                        onClick={() => void handleSaveKind()}
                        disabled={savingKind}
                        className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                      >
                        {savingKind ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                        Save
                      </button>
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-[auto_1fr_auto] gap-3 items-end">
                  <div>
                    <label className="text-[10px] text-muted-foreground">Icon</label>
                    <input
                      value={editIcon}
                      onChange={(e) => { setEditIcon(e.target.value); setKindDirty(true); }}
                      className="mt-1 w-14 rounded-md border bg-background px-2 py-1.5 text-center text-base focus:border-ring focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-muted-foreground">Name</label>
                    <input
                      value={editName}
                      onChange={(e) => { setEditName(e.target.value); setKindDirty(true); }}
                      className="mt-1 w-full rounded-md border bg-background px-3 py-1.5 text-xs focus:border-ring focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-muted-foreground">Color</label>
                    <input
                      type="color"
                      value={editColor}
                      onChange={(e) => { setEditColor(e.target.value); setKindDirty(true); }}
                      className="mt-1 h-8 w-10 cursor-pointer rounded border bg-background"
                    />
                  </div>
                </div>
                <div>
                  <label className="text-[10px] text-muted-foreground">Description</label>
                  <textarea
                    value={editDescription}
                    onChange={(e) => { setEditDescription(e.target.value); setKindDirty(true); }}
                    placeholder="What this kind represents..."
                    rows={2}
                    className="mt-1 w-full resize-none rounded-md border bg-background px-3 py-1.5 text-xs focus:border-ring focus:outline-none placeholder:text-muted-foreground/50"
                  />
                </div>
              </div>

              {/* Genre tags */}
              <div className="flex items-center gap-2 border-b bg-card/30 px-6 py-2.5">
                <span className="flex-shrink-0 text-[10px] font-medium text-muted-foreground">Genres:</span>
                <div className="flex flex-1 flex-wrap items-center gap-1.5">
                  {editGenreTags.map((tag) => {
                    const gColor = genreColorMap.get(tag);
                    return (
                    <span
                      key={tag}
                      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
                      style={tag === 'universal'
                        ? { background: 'rgba(59,130,246,0.15)', color: '#60a5fa' }
                        : gColor
                          ? { background: gColor + '18', color: gColor }
                          : { background: 'var(--secondary)', color: 'var(--foreground)' }}
                    >
                      {gColor && <span className="h-1.5 w-1.5 rounded-sm flex-shrink-0" style={{ background: gColor }} />}
                      {tag}
                      <button
                        onClick={() => {
                          setEditGenreTags(editGenreTags.filter((t) => t !== tag));
                          setKindDirty(true);
                        }}
                        className="ml-0.5 rounded-full p-px text-muted-foreground/60 hover:text-foreground transition-colors"
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </span>
                  );})}
                  <input
                    placeholder="+ Add genre"
                    className="w-24 bg-transparent text-[10px] outline-none placeholder:text-muted-foreground/50"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        const val = (e.target as HTMLInputElement).value.trim();
                        if (val && !editGenreTags.includes(val)) {
                          setEditGenreTags([...editGenreTags, val]);
                          setKindDirty(true);
                        }
                        (e.target as HTMLInputElement).value = '';
                        e.preventDefault();
                      }
                    }}
                  />
                </div>
                <span className="flex-shrink-0 text-[9px] text-muted-foreground">
                  Empty = all books
                </span>
              </div>

              {/* Attributes */}
              <div className="px-6 py-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold">Attributes ({selected.default_attributes.length})</span>
                  <button
                    onClick={() => setShowCreateAttr(true)}
                    className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-[10px] font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                  >
                    <Plus className="h-3 w-3" /> Add Attribute
                  </button>
                </div>

                {selected.default_attributes.length === 0 ? (
                  <p className="text-xs text-muted-foreground italic py-4">No attributes defined. Click "Add Attribute" to create one.</p>
                ) : (
                  <div className="rounded-lg border overflow-hidden">
                    {/* System attributes */}
                    {selected.default_attributes.some((a) => a.is_system) && (
                      <>
                        <div className="px-3 py-1.5" style={{ background: 'rgba(24,20,18,0.3)' }}>
                          <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-blue-400">
                            <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />
                            System Attributes
                          </span>
                        </div>
                        {[...selected.default_attributes]
                          .filter((a) => a.is_system)
                          .sort((a, b) => a.sort_order - b.sort_order)
                          .map((attr) => (
                            <div key={attr.attr_def_id}>
                              <AttrRow attr={attr} kindCode={selected.code} onEdit={() => setEditAttr(attr)} onToggle={() => void handleToggleAttr(attr)} onDelete={undefined}
                                genreColorMap={genreColorMap}
                                isOver={overAttrId === attr.attr_def_id && dragAttrId !== attr.attr_def_id}
                                dragProps={{
                                  draggable: true,
                                  onDragStart: () => setDragAttrId(attr.attr_def_id),
                                  onDragOver: (e) => { e.preventDefault(); setOverAttrId(attr.attr_def_id); },
                                  onDragEnd: () => { setDragAttrId(null); setOverAttrId(null); },
                                  onDrop: () => { if (dragAttrId) void handleAttrDrop(dragAttrId, attr.attr_def_id); setDragAttrId(null); setOverAttrId(null); },
                                }} />
                            </div>
                          ))}
                      </>
                    )}
                    {/* User attributes */}
                    {selected.default_attributes.some((a) => !a.is_system) && (
                      <>
                        <div className="px-3 py-1.5" style={{ background: 'rgba(24,20,18,0.3)' }}>
                          <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
                            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                            User Attributes
                          </span>
                        </div>
                        {[...selected.default_attributes]
                          .filter((a) => !a.is_system)
                          .sort((a, b) => a.sort_order - b.sort_order)
                          .map((attr) => (
                            <div key={attr.attr_def_id}>
                              <AttrRow attr={attr} kindCode={selected.code} onEdit={() => setEditAttr(attr)} onToggle={() => void handleToggleAttr(attr)} onDelete={() => setDeleteAttrTarget(attr)}
                                genreColorMap={genreColorMap}
                                isOver={overAttrId === attr.attr_def_id && dragAttrId !== attr.attr_def_id}
                                dragProps={{
                                  draggable: true,
                                  onDragStart: () => setDragAttrId(attr.attr_def_id),
                                  onDragOver: (e) => { e.preventDefault(); setOverAttrId(attr.attr_def_id); },
                                  onDragEnd: () => { setDragAttrId(null); setOverAttrId(null); },
                                  onDrop: () => { if (dragAttrId) void handleAttrDrop(dragAttrId, attr.attr_def_id); setDragAttrId(null); setOverAttrId(null); },
                                }} />
                            </div>
                          ))}
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
              Select a kind to view and edit
            </div>
          )}
        </div>
      </div>

      {/* New Kind dialog */}
      {showNewKind && (
        <>
          <div className="fixed inset-0 z-50 bg-black/50" onClick={() => setShowNewKind(false)} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="w-full max-w-sm rounded-lg border bg-background shadow-xl" onClick={(e) => e.stopPropagation()}>
              <div className="border-b px-5 py-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold">New Entity Kind</h3>
                <button onClick={() => setShowNewKind(false)} className="rounded p-1 text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
              </div>
              <div className="px-5 py-4 space-y-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Code</label>
                  <input
                    value={newCode}
                    onChange={(e) => setNewCode(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                    placeholder="e.g. spell, faction, vehicle"
                    className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-xs font-mono focus:border-ring focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Display Name</label>
                  <input
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="e.g. Spell, Faction, Vehicle"
                    className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-xs focus:border-ring focus:outline-none"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 border-t px-5 py-3">
                <button onClick={() => setShowNewKind(false)} className="rounded-md border px-4 py-1.5 text-xs text-muted-foreground hover:bg-secondary">Cancel</button>
                <button
                  onClick={() => void handleCreateKind()}
                  disabled={!newCode || !newName}
                  className="rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  Create Kind
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Confirm dialogs */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        title="Delete kind?"
        description={`"${deleteTarget?.name}" and all its attribute definitions will be permanently deleted. This cannot be undone.`}
        confirmLabel="Delete Kind"
        variant="destructive"
        onConfirm={() => void handleDeleteKind()}
      />
      <ConfirmDialog
        open={!!deleteAttrTarget}
        onOpenChange={(open) => { if (!open) setDeleteAttrTarget(null); }}
        title="Delete attribute?"
        description={`"${deleteAttrTarget?.name}" will be removed from this kind. Existing entity values for this attribute will be deleted.`}
        confirmLabel="Delete Attribute"
        variant="destructive"
        onConfirm={() => void handleDeleteAttr()}
      />
      <ConfirmDialog
        open={!!revertTarget}
        onOpenChange={(open) => { if (!open) setRevertTarget(null); }}
        title="Revert to defaults?"
        description={`"${revertTarget?.name}" will be reset to its original name, icon, color, and attribute names. Genre tags and custom attributes will not be affected.`}
        confirmLabel="Revert"
        variant="destructive"
        onConfirm={() => void handleRevertKind()}
      />

      {/* Attr Editor Modal (edit) */}
      {editAttr && selected && (
        <AttrEditorModal
          kindId={selected.kind_id}
          kindCode={selected.code}
          attr={editAttr}
          genreColorMap={genreColorMap}
          onClose={() => setEditAttr(null)}
          onSaved={() => void loadKinds()}
          onDelete={!editAttr.is_system ? () => { setDeleteAttrTarget(editAttr); setEditAttr(null); } : undefined}
        />
      )}

      {/* Attr Editor Modal (create) */}
      {showCreateAttr && selected && (
        <AttrEditorModal
          kindId={selected.kind_id}
          kindCode={selected.code}
          existingAttrCount={selected.default_attributes.length}
          genreColorMap={genreColorMap}
          onClose={() => setShowCreateAttr(false)}
          onSaved={() => void loadKinds()}
        />
      )}
    </div>
  );
}
