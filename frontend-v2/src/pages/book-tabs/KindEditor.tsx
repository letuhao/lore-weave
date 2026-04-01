import { useEffect, useState, useCallback } from 'react';
import { Settings2, Plus, Trash2, Save, Loader2, ChevronRight, X } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { type EntityKind, type AttributeDefinition, type FieldType } from '@/features/glossary/types';
import { Skeleton } from '@/components/shared/Skeleton';
import { ConfirmDialog } from '@/components/shared';
import { cn } from '@/lib/utils';

const FIELD_TYPE_OPTIONS: { value: FieldType; label: string }[] = [
  { value: 'text', label: 'Text' },
  { value: 'textarea', label: 'Long text' },
  { value: 'select', label: 'Select' },
  { value: 'number', label: 'Number' },
  { value: 'date', label: 'Date' },
  { value: 'tags', label: 'Tags' },
  { value: 'url', label: 'URL' },
  { value: 'boolean', label: 'Boolean' },
];

export function KindEditor({ onClose }: { onClose: () => void }) {
  const { accessToken } = useAuth();
  const [kinds, setKinds] = useState<EntityKind[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Edit state for selected kind
  const [editName, setEditName] = useState('');
  const [editIcon, setEditIcon] = useState('');
  const [editColor, setEditColor] = useState('');
  const [kindDirty, setKindDirty] = useState(false);
  const [savingKind, setSavingKind] = useState(false);

  // Delete confirm
  const [deleteTarget, setDeleteTarget] = useState<EntityKind | null>(null);
  const [deleteAttrTarget, setDeleteAttrTarget] = useState<AttributeDefinition | null>(null);

  // New kind dialog
  const [showNewKind, setShowNewKind] = useState(false);
  const [newCode, setNewCode] = useState('');
  const [newName, setNewName] = useState('');

  // New attribute
  const [showNewAttr, setShowNewAttr] = useState(false);
  const [newAttrCode, setNewAttrCode] = useState('');
  const [newAttrName, setNewAttrName] = useState('');
  const [newAttrType, setNewAttrType] = useState<FieldType>('text');

  const loadKinds = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const k = await glossaryApi.getKinds(accessToken);
      setKinds(k);
      if (k.length > 0 && !selectedId) setSelectedId(k[0].kind_id);
    } catch (e) { toast.error((e as Error).message); }
    setLoading(false);
  }, [accessToken]);

  useEffect(() => { void loadKinds(); }, [loadKinds]);

  const selected = kinds.find((k) => k.kind_id === selectedId);

  // Sync edit state when selection changes
  useEffect(() => {
    if (selected) {
      setEditName(selected.name);
      setEditIcon(selected.icon);
      setEditColor(selected.color);
      setKindDirty(false);
    }
  }, [selected?.kind_id]);

  const handleSaveKind = async () => {
    if (!accessToken || !selected) return;
    setSavingKind(true);
    try {
      await glossaryApi.patchKind(accessToken, selected.kind_id, {
        name: editName, icon: editIcon, color: editColor,
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

  const handleCreateAttr = async () => {
    if (!accessToken || !selected || !newAttrCode || !newAttrName) return;
    try {
      await glossaryApi.createAttrDef(accessToken, selected.kind_id, {
        code: newAttrCode, name: newAttrName, field_type: newAttrType,
        sort_order: (selected.default_attributes.length + 1) * 10,
      });
      toast.success('Attribute added');
      setShowNewAttr(false);
      setNewAttrCode('');
      setNewAttrName('');
      setNewAttrType('text');
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
                <button
                  key={k.kind_id}
                  onClick={() => setSelectedId(k.kind_id)}
                  className={cn(
                    'flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-xs transition-colors border-b',
                    selectedId === k.kind_id ? 'bg-primary/5 border-l-2 border-l-primary' : 'hover:bg-card/50',
                  )}
                >
                  <span className="text-base">{k.icon}</span>
                  <div className="flex-1 min-w-0">
                    <span className="font-medium truncate block">{k.name}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {k.default_attributes.length} attr{k.default_attributes.length !== 1 ? 's' : ''}
                    </span>
                  </div>
                  {selectedId === k.kind_id && <ChevronRight className="h-3 w-3 text-primary" />}
                </button>
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
                  </div>
                  <div className="flex items-center gap-2">
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
              </div>

              {/* Attributes */}
              <div className="px-6 py-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold">Attributes ({selected.default_attributes.length})</span>
                  <button
                    onClick={() => setShowNewAttr(true)}
                    className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-[10px] font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                  >
                    <Plus className="h-3 w-3" /> Add Attribute
                  </button>
                </div>

                {/* New attribute form */}
                {showNewAttr && (
                  <div className="rounded-lg border bg-card p-3 mb-3 space-y-2">
                    <div className="grid grid-cols-3 gap-2">
                      <input
                        value={newAttrCode}
                        onChange={(e) => setNewAttrCode(e.target.value)}
                        placeholder="code"
                        className="rounded-md border bg-background px-2 py-1.5 text-xs font-mono focus:border-ring focus:outline-none"
                      />
                      <input
                        value={newAttrName}
                        onChange={(e) => setNewAttrName(e.target.value)}
                        placeholder="Display Name"
                        className="rounded-md border bg-background px-2 py-1.5 text-xs focus:border-ring focus:outline-none"
                      />
                      <select
                        value={newAttrType}
                        onChange={(e) => setNewAttrType(e.target.value as FieldType)}
                        className="rounded-md border bg-background px-2 py-1.5 text-xs focus:border-ring focus:outline-none"
                      >
                        {FIELD_TYPE_OPTIONS.map((ft) => (
                          <option key={ft.value} value={ft.value}>{ft.label}</option>
                        ))}
                      </select>
                    </div>
                    <div className="flex justify-end gap-2">
                      <button onClick={() => setShowNewAttr(false)} className="rounded-md border px-3 py-1 text-[10px] text-muted-foreground hover:bg-secondary">Cancel</button>
                      <button
                        onClick={() => void handleCreateAttr()}
                        disabled={!newAttrCode || !newAttrName}
                        className="rounded-md bg-primary px-3 py-1 text-[10px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                      >
                        Add
                      </button>
                    </div>
                  </div>
                )}

                {selected.default_attributes.length === 0 ? (
                  <p className="text-xs text-muted-foreground italic py-4">No attributes defined. Click "Add Attribute" to create one.</p>
                ) : (
                  <div className="rounded-lg border divide-y">
                    {[...selected.default_attributes]
                      .sort((a, b) => a.sort_order - b.sort_order)
                      .map((attr) => (
                        <div key={attr.attr_def_id} className="flex items-center gap-3 px-4 py-2.5 group hover:bg-card/50 transition-colors">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-medium">{attr.name}</span>
                              <span className="rounded bg-secondary px-1.5 py-0.5 text-[9px] text-muted-foreground">{attr.field_type}</span>
                              {attr.is_required && <span className="rounded bg-amber-400/15 px-1 py-0.5 text-[9px] font-medium text-amber-400">required</span>}
                              {attr.is_system && <span className="rounded bg-blue-500/15 px-1 py-0.5 text-[9px] font-medium text-blue-400">SYS</span>}
                            </div>
                            <span className="text-[10px] text-muted-foreground font-mono">{attr.code}</span>
                          </div>
                          {!attr.is_system && (
                            <button
                              onClick={() => setDeleteAttrTarget(attr)}
                              className="opacity-0 group-hover:opacity-100 rounded p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
                              title="Delete attribute"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      ))}
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
    </div>
  );
}
