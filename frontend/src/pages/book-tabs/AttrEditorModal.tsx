import { useEffect, useState } from 'react';
import { X, Save, Loader2, Trash2, RotateCcw, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { type AttributeDefinition, type FieldType } from '@/features/glossary/types';
import { cn } from '@/lib/utils';
import { ConfirmDialog } from '@/components/shared';
import { SEED_KINDS, isAttrModified } from './seedDefaults';

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

const VARIABLES = ['{{entity_name}}', '{{kind_name}}', '{{book_title}}', '{{genre}}'];

interface AttrEditorModalProps {
  kindId: string;
  kindCode: string;
  attr?: AttributeDefinition; // undefined = create mode
  existingAttrCount?: number; // for sort_order on create
  genreColorMap: Map<string, string>;
  onClose: () => void;
  onSaved: () => void;
  onDelete?: () => void;
}

export function AttrEditorModal({ kindId, kindCode, attr, existingAttrCount = 0, genreColorMap, onClose, onSaved, onDelete }: AttrEditorModalProps) {
  const { accessToken } = useAuth();
  const [saving, setSaving] = useState(false);
  const isCreate = !attr;

  // Create-only field
  const [code, setCode] = useState('');

  // Core fields
  const [name, setName] = useState(attr?.name ?? '');
  const [description, setDescription] = useState(attr?.description ?? '');
  const [fieldType, setFieldType] = useState<FieldType>((attr?.field_type as FieldType) ?? 'text');
  const [isRequired, setIsRequired] = useState(attr?.is_required ?? false);
  const [isActive, setIsActive] = useState(attr?.is_active ?? true);

  // Genre tags
  const [genreTags, setGenreTags] = useState<string[]>(attr?.genre_tags ?? []);

  // Options (for select type)
  const [options, setOptions] = useState<string[]>(attr?.options ?? []);

  // AI prompts
  const [autoFillPrompt, setAutoFillPrompt] = useState(attr?.auto_fill_prompt ?? '');
  const [translationHint, setTranslationHint] = useState(attr?.translation_hint ?? '');

  // Revert confirm
  const [showRevert, setShowRevert] = useState(false);

  const modified = attr ? isAttrModified(kindCode, attr) : false;
  const seedAttr = attr ? SEED_KINDS[kindCode]?.attrs[attr.code] : undefined;
  const hasAI = !!(autoFillPrompt.trim() || translationHint.trim());

  // Esc to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  const handleSave = async () => {
    if (!accessToken || !name.trim()) return;
    if (isCreate && !code.trim()) { toast.error('Code is required'); return; }
    setSaving(true);
    try {
      if (isCreate) {
        await glossaryApi.createAttrDef(accessToken, kindId, {
          code: code.trim().toLowerCase().replace(/[^a-z0-9_]/g, ''),
          name: name.trim(),
          description: description.trim() || undefined,
          field_type: fieldType,
          is_required: isRequired,
          sort_order: (existingAttrCount + 1) * 10,
          genre_tags: genreTags.length > 0 ? genreTags : undefined,
          options: fieldType === 'select' ? options.filter(Boolean) : undefined,
          auto_fill_prompt: autoFillPrompt.trim() || undefined,
          translation_hint: translationHint.trim() || undefined,
        });
        toast.success('Attribute created');
      } else {
        await glossaryApi.patchAttrDef(accessToken, kindId, attr!.attr_def_id, {
          name: name.trim(),
          description: description.trim() || null,
          field_type: fieldType,
          is_required: isRequired,
          is_active: isActive,
          genre_tags: genreTags,
          options: fieldType === 'select' ? options.filter(Boolean) : undefined,
          auto_fill_prompt: autoFillPrompt.trim() || null,
          translation_hint: translationHint.trim() || null,
        });
        toast.success('Attribute updated');
      }
      onSaved();
      onClose();
    } catch (e) { toast.error((e as Error).message); }
    setSaving(false);
  };

  const handleRevert = () => {
    if (!seedAttr) return;
    setName(seedAttr.name);
    setShowRevert(false);
    toast.success('Name reverted to default');
  };

  const insertVariable = (v: string, setter: (fn: (prev: string) => string) => void) => {
    setter((prev) => prev + (prev && !prev.endsWith(' ') ? ' ' : '') + v);
  };

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/60" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
        <div
          className="flex w-full max-w-[640px] flex-col overflow-hidden rounded-xl border bg-background shadow-2xl"
          style={{ maxHeight: 'calc(100vh - 48px)' }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b bg-card px-5 py-3.5 flex-shrink-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">{isCreate ? 'New Attribute' : 'Edit Attribute'}</span>
              {!isCreate && (attr!.is_system ? (
                <span className="rounded bg-blue-500/15 px-1.5 py-0.5 text-[9px] font-medium text-blue-400">System</span>
              ) : (
                <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[9px] font-medium text-primary">Custom</span>
              ))}
              {modified && <span className="text-[9px] font-medium text-amber-400 italic">modified</span>}
              {hasAI && (
                <span className="inline-flex items-center gap-1 rounded bg-accent/12 px-1.5 py-0.5 text-[9px] font-semibold text-accent">
                  AI
                </span>
              )}
            </div>
            <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors">
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">

            {/* Section: Core */}
            <div className="rounded-lg border overflow-hidden">
              <div className="flex items-center gap-2 border-b bg-card/50 px-4 py-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-foreground">Core</span>
              </div>
              <div className="p-4 space-y-3">
                <div className="grid grid-cols-[1fr_auto] gap-3">
                  <div>
                    <label className="text-[10px] font-medium text-muted-foreground">Display Name</label>
                    <input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="mt-1 w-full rounded-md border bg-input px-3 py-1.5 text-xs focus:border-ring focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] font-medium text-muted-foreground">Field Type</label>
                    <select
                      value={fieldType}
                      onChange={(e) => setFieldType(e.target.value as FieldType)}
                      className="mt-1 w-[130px] rounded-md border bg-input px-2 py-1.5 text-xs focus:border-ring focus:outline-none"
                    >
                      {FIELD_TYPE_OPTIONS.map((ft) => (
                        <option key={ft.value} value={ft.value}>{ft.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="flex items-center gap-5">
                  {isCreate ? (
                    <div>
                      <label className="text-[10px] font-medium text-muted-foreground">Internal Code</label>
                      <input
                        value={code}
                        onChange={(e) => setCode(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                        placeholder="e.g. power_level"
                        className="mt-1 w-[140px] rounded-md border bg-input px-2 py-1.5 font-mono text-[10px] focus:border-ring focus:outline-none placeholder:text-muted-foreground/50"
                        autoFocus
                      />
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-medium text-muted-foreground">Internal Code</span>
                      <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{attr!.code}</span>
                    </div>
                  )}
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} className="h-3.5 w-3.5 rounded border-border accent-primary" />
                    <span className="text-[10px] font-medium text-muted-foreground">Required</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} className="h-3.5 w-3.5 rounded border-border accent-green-500" />
                    <span className="text-[10px] font-medium text-muted-foreground">Active</span>
                  </label>
                </div>

                <div>
                  <label className="text-[10px] font-medium text-muted-foreground">Description</label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What this attribute represents..."
                    rows={2}
                    className="mt-1 w-full resize-none rounded-md border bg-input px-3 py-1.5 text-xs focus:border-ring focus:outline-none placeholder:text-muted-foreground/50"
                  />
                  <p className="mt-1 text-[9px] text-muted-foreground/70">Shown as help text when filling in entity attributes.</p>
                </div>
              </div>
            </div>

            {/* Section: Options (only for select type) */}
            {fieldType === 'select' && (
              <div className="rounded-lg border overflow-hidden">
                <div className="flex items-center justify-between border-b bg-card/50 px-4 py-2">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-foreground">Options</span>
                  <span className="text-[9px] text-muted-foreground">{options.length} options</span>
                </div>
                <div className="p-3 space-y-1.5">
                  {options.map((opt, idx) => (
                    <div key={idx} className="flex items-center gap-2 group">
                      <input
                        value={opt}
                        onChange={(e) => { const next = [...options]; next[idx] = e.target.value; setOptions(next); }}
                        className="flex-1 rounded-md border bg-input px-2 py-1 text-xs focus:border-ring focus:outline-none"
                      />
                      <button
                        onClick={() => setOptions(options.filter((_, i) => i !== idx))}
                        className="opacity-0 group-hover:opacity-100 max-md:opacity-100 text-destructive transition-opacity"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                  <button
                    onClick={() => setOptions([...options, ''])}
                    className="flex w-full items-center justify-center gap-1 rounded-md border border-dashed py-1.5 text-[10px] text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                  >
                    <Plus className="h-3 w-3" /> Add Option
                  </button>
                </div>
              </div>
            )}

            {/* Section: Genre Scoping */}
            <div className="rounded-lg border overflow-hidden">
              <div className="flex items-center justify-between border-b bg-card/50 px-4 py-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-blue-400">Genre Scoping</span>
                <span className="text-[9px] text-muted-foreground">Empty = visible for all genres</span>
              </div>
              <div className="p-4">
                <div className="flex flex-wrap items-center gap-1.5">
                  {genreTags.map((tag) => {
                    const color = genreColorMap.get(tag);
                    return (
                      <span
                        key={tag}
                        className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
                        style={color ? { background: color + '18', color } : { background: 'rgba(139,92,246,0.15)', color: '#a78bfa' }}
                      >
                        {color && <span className="h-1.5 w-1.5 rounded-sm" style={{ background: color }} />}
                        {tag}
                        <button onClick={() => setGenreTags(genreTags.filter((t) => t !== tag))} className="ml-0.5 opacity-60 hover:opacity-100">
                          <X className="h-2.5 w-2.5" />
                        </button>
                      </span>
                    );
                  })}
                  <input
                    placeholder="+ Add genre"
                    className="w-20 bg-transparent text-[10px] outline-none placeholder:text-muted-foreground/50"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        const val = (e.target as HTMLInputElement).value.trim();
                        if (val && !genreTags.includes(val)) setGenreTags([...genreTags, val]);
                        (e.target as HTMLInputElement).value = '';
                      }
                    }}
                  />
                </div>
              </div>
            </div>

            {/* Section: AI Assistance */}
            <div className="rounded-lg border overflow-hidden">
              <div className="flex items-center justify-between border-b bg-card/50 px-4 py-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-accent">AI Assistance</span>
                {hasAI ? (
                  <span className="inline-flex items-center gap-1 rounded bg-accent/12 px-1.5 py-0.5 text-[8px] font-semibold text-accent">Configured</span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded bg-secondary px-1.5 py-0.5 text-[8px] font-medium text-muted-foreground">Not configured</span>
                )}
              </div>
              <div className="p-4 space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[10px] font-medium text-muted-foreground">Auto-fill Prompt</label>
                    <span className="text-[9px] text-muted-foreground/70">Used when user clicks "AI Fill" on this attribute</span>
                  </div>
                  <textarea
                    value={autoFillPrompt}
                    onChange={(e) => setAutoFillPrompt(e.target.value)}
                    placeholder="Prompt template for AI auto-fill. Use {{variable}} for entity fields."
                    rows={3}
                    className="w-full resize-none rounded-md border bg-input px-3 py-1.5 font-mono text-[11px] leading-relaxed focus:border-ring focus:outline-none placeholder:text-muted-foreground/50"
                  />
                  <div className="mt-1.5 flex flex-wrap items-center gap-1">
                    <span className="text-[9px] text-muted-foreground mr-1">Variables:</span>
                    {VARIABLES.map((v) => (
                      <button
                        key={v}
                        onClick={() => insertVariable(v, setAutoFillPrompt)}
                        className="rounded border border-accent/20 bg-accent/5 px-1.5 py-px font-mono text-[9px] text-accent hover:bg-accent/15 transition-colors"
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[10px] font-medium text-muted-foreground">Translation Hint</label>
                    <span className="text-[9px] text-muted-foreground/70">Injected into translation system prompt</span>
                  </div>
                  <textarea
                    value={translationHint}
                    onChange={(e) => setTranslationHint(e.target.value)}
                    placeholder="Optional hint for translators working on this attribute."
                    rows={2}
                    className="w-full resize-none rounded-md border bg-input px-3 py-1.5 font-mono text-[11px] leading-relaxed focus:border-ring focus:outline-none placeholder:text-muted-foreground/50"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t bg-card px-5 py-3 flex-shrink-0">
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
              {!isCreate && attr!.is_system && modified && seedAttr && (
                <button
                  onClick={() => setShowRevert(true)}
                  className="inline-flex items-center gap-1 text-amber-400 hover:text-amber-300 transition-colors"
                >
                  <RotateCcw className="h-3 w-3" />
                  Revert to default name
                </button>
              )}
              {!isCreate && !attr!.is_system && onDelete && (
                <button
                  onClick={onDelete}
                  className="inline-flex items-center gap-1 text-destructive hover:text-destructive/80 transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                  Delete Attribute
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button onClick={onClose} className="rounded-md border px-3 py-1.5 text-xs text-muted-foreground hover:bg-secondary transition-colors">
                Cancel
              </button>
              <button
                onClick={() => void handleSave()}
                disabled={saving || !name.trim() || (isCreate && !code.trim())}
                className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                {isCreate ? 'Create Attribute' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Revert confirm */}
      <ConfirmDialog
        open={showRevert}
        onOpenChange={setShowRevert}
        title="Revert attribute name?"
        description={`Reset name from "${name}" back to "${seedAttr?.name}". Other fields are not affected.`}
        confirmLabel="Revert"
        variant="destructive"
        onConfirm={handleRevert}
      />
    </>
  );
}
