import { useEffect, useState, useCallback } from 'react';
import { X, Save, Loader2, Link2, Tag } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { type GlossaryEntity, type AttributeValue, type FieldType } from '@/features/glossary/types';
import { Skeleton } from '@/components/shared/Skeleton';
import { cn } from '@/lib/utils';

interface EntityEditorProps {
  bookId: string;
  entityId: string;
  onClose: () => void;
  onSaved: () => void;
}

function FieldInput({ attr, onChange }: {
  attr: AttributeValue;
  onChange: (value: string) => void;
}) {
  const def = attr.attribute_def;
  const value = attr.original_value ?? '';

  switch (def.field_type as FieldType) {
    case 'textarea':
      return (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          className="w-full rounded-md border bg-background px-3 py-2 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring resize-y"
        />
      );
    case 'number':
      return (
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-md border bg-background px-3 py-2 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
        />
      );
    case 'date':
      return (
        <input
          type="date"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-md border bg-background px-3 py-2 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
        />
      );
    case 'boolean':
      return (
        <label className="inline-flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={value === 'true'}
            onChange={(e) => onChange(e.target.checked ? 'true' : 'false')}
            className="h-4 w-4 rounded border-border accent-primary"
          />
          <span className="text-xs text-muted-foreground">{value === 'true' ? 'Yes' : 'No'}</span>
        </label>
      );
    case 'select':
      return (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-md border bg-background px-3 py-2 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="">Select...</option>
          {(def.options ?? []).map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      );
    case 'url':
      return (
        <input
          type="url"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="https://..."
          className="w-full rounded-md border bg-background px-3 py-2 text-xs font-mono focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
        />
      );
    case 'tags':
      return <TagsInput value={value} onChange={onChange} />;
    default: // 'text'
      return (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-md border bg-background px-3 py-2 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
        />
      );
  }
}

function TagsInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const tags = value ? value.split(',').map((t) => t.trim()).filter(Boolean) : [];
  const [input, setInput] = useState('');

  const addTag = () => {
    const trimmed = input.trim();
    if (trimmed && !tags.includes(trimmed)) {
      onChange([...tags, trimmed].join(', '));
    }
    setInput('');
  };

  const removeTag = (tag: string) => {
    onChange(tags.filter((t) => t !== tag).join(', '));
  };

  return (
    <div className="flex flex-wrap gap-1.5 rounded-md border bg-background p-2">
      {tags.map((tag) => (
        <span key={tag} className="inline-flex items-center gap-1 rounded bg-secondary px-2 py-0.5 text-[11px]">
          {tag}
          <button onClick={() => removeTag(tag)} className="text-muted-foreground hover:text-foreground">
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } }}
        onBlur={addTag}
        placeholder="+ Add tag"
        className="flex-1 min-w-[80px] bg-transparent text-xs outline-none px-1 py-0.5"
      />
    </div>
  );
}

export function EntityEditor({ bookId, entityId, onClose, onSaved }: EntityEditorProps) {
  const { accessToken } = useAuth();
  const [entity, setEntity] = useState<GlossaryEntity | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pendingChanges, setPendingChanges] = useState<Map<string, string>>(new Map());

  const load = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const e = await glossaryApi.getEntity(bookId, entityId, accessToken);
      setEntity(e);
      setPendingChanges(new Map());
    } catch (e) {
      toast.error((e as Error).message);
    }
    setLoading(false);
  }, [accessToken, bookId, entityId]);

  useEffect(() => { void load(); }, [load]);

  const handleAttrChange = (attrValueId: string, value: string) => {
    setPendingChanges((prev) => new Map(prev).set(attrValueId, value));
  };

  const getDisplayValue = (attr: AttributeValue): string => {
    return pendingChanges.get(attr.attr_value_id) ?? attr.original_value ?? '';
  };

  const isDirty = pendingChanges.size > 0;

  const handleSave = async () => {
    if (!accessToken || !entity || pendingChanges.size === 0) return;
    setSaving(true);
    try {
      for (const [attrValueId, value] of pendingChanges) {
        await glossaryApi.patchAttributeValue(bookId, entityId, attrValueId, { original_value: value }, accessToken);
      }
      toast.success('Entity saved');
      setPendingChanges(new Map());
      onSaved();
      await load();
    } catch (e) {
      toast.error((e as Error).message);
    }
    setSaving(false);
  };

  const handleStatusChange = async (status: string) => {
    if (!accessToken || !entity) return;
    try {
      await glossaryApi.patchEntity(bookId, entityId, { status }, accessToken);
      toast.success(`Status changed to ${status}`);
      await load();
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col h-full">
        <div className="border-b px-5 py-3">
          <Skeleton className="h-6 w-48" />
        </div>
        <div className="p-5 space-y-4">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      </div>
    );
  }

  if (!entity) {
    return (
      <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
        Entity not found
      </div>
    );
  }

  const sortedAttrs = [...entity.attribute_values].sort(
    (a, b) => a.attribute_def.sort_order - b.attribute_def.sort_order,
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-5 py-3 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-lg">{entity.kind.icon}</span>
          <span className="text-sm font-semibold font-serif truncate">
            {entity.display_name || 'Untitled'}
          </span>
          <span
            className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
            style={{ backgroundColor: entity.kind.color + '18', color: entity.kind.color }}
          >
            {entity.kind.name}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Status selector */}
          <select
            value={entity.status}
            onChange={(e) => void handleStatusChange(e.target.value)}
            className="rounded-md border bg-background px-2 py-1 text-[10px] font-medium focus:outline-none"
          >
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
          {isDirty && (
            <button
              onClick={() => void handleSave()}
              disabled={saving}
              className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
              Save
            </button>
          )}
          <button
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Scrollable form */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {/* Metadata */}
        <div className="flex items-center gap-4 text-[10px] text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Link2 className="h-3 w-3" />
            {entity.chapter_link_count} chapter{entity.chapter_link_count !== 1 ? 's' : ''}
          </span>
          <span className="inline-flex items-center gap-1">
            <Tag className="h-3 w-3" />
            {entity.translation_count} translation{entity.translation_count !== 1 ? 's' : ''}
          </span>
          {entity.tags.length > 0 && (
            <span>{entity.tags.join(', ')}</span>
          )}
        </div>

        {/* Attribute fields */}
        {sortedAttrs.map((attr) => {
          const def = attr.attribute_def;
          const displayValue = getDisplayValue(attr);
          const changed = pendingChanges.has(attr.attr_value_id);

          return (
            <div key={attr.attr_value_id}>
              <div className="flex items-center gap-2 mb-1.5">
                <label className="text-xs font-medium">{def.name}</label>
                {def.is_required && (
                  <span className="text-[9px] text-destructive">*</span>
                )}
                <span className="font-mono text-[9px] text-muted-foreground">{def.code}</span>
                {changed && (
                  <span className="rounded bg-amber-400/15 px-1 py-0.5 text-[8px] font-medium text-amber-400">modified</span>
                )}
              </div>
              <FieldInput
                attr={{ ...attr, original_value: displayValue }}
                onChange={(v) => handleAttrChange(attr.attr_value_id, v)}
              />
            </div>
          );
        })}

        {sortedAttrs.length === 0 && (
          <p className="text-xs text-muted-foreground italic py-4">
            No attributes defined for this entity kind.
          </p>
        )}
      </div>
    </div>
  );
}
