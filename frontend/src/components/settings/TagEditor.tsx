import { useState } from 'react';
import { ModelTag } from '@/features/ai-models/api';

type Props = {
  tags: ModelTag[];
  onChange: (tags: ModelTag[]) => void;
  disabled?: boolean;
};

function sortTags(tags: ModelTag[]): ModelTag[] {
  return [...tags].sort((a, b) => a.tag_name.toLowerCase().localeCompare(b.tag_name.toLowerCase()));
}

export function TagEditor({ tags, onChange, disabled }: Props) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editNote, setEditNote] = useState('');
  const [adding, setAdding] = useState(false);
  const [addName, setAddName] = useState('');
  const [addNote, setAddNote] = useState('');

  const isDuplicateName = (name: string, excludeIndex?: number) =>
    tags.some((t, i) => t.tag_name.toLowerCase() === name.toLowerCase() && i !== excludeIndex);

  const startEdit = (index: number) => {
    setAdding(false);
    setEditingIndex(index);
    setEditName(tags[index].tag_name);
    setEditNote(tags[index].note ?? '');
  };

  const saveEdit = () => {
    if (editingIndex === null) return;
    const updated = tags.map((t, i) =>
      i === editingIndex ? { tag_name: editName.trim(), note: editNote.trim() } : t,
    );
    onChange(sortTags(updated));
    setEditingIndex(null);
  };

  const cancelEdit = () => setEditingIndex(null);

  const removeTag = (index: number) => {
    onChange(tags.filter((_, i) => i !== index));
  };

  const startAdding = () => {
    setEditingIndex(null);
    setAdding((prev) => !prev);
    setAddName('');
    setAddNote('');
  };

  const addTag = () => {
    const name = addName.trim();
    if (!name) return;
    onChange(sortTags([...tags, { tag_name: name, note: addNote.trim() }]));
    setAdding(false);
    setAddName('');
    setAddNote('');
  };

  const cancelAdd = () => {
    setAdding(false);
    setAddName('');
    setAddNote('');
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {tags.map((tag, i) => (
          <div key={i} className="flex items-center gap-1 rounded border px-2 py-0.5 text-sm">
            {editingIndex === i ? (
              <div className="flex flex-col gap-1 py-1">
                <div className="flex gap-1">
                  <input
                    className="rounded border px-1 py-0.5 text-xs w-28"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    placeholder="Tag name"
                    disabled={disabled}
                    autoFocus
                  />
                  <input
                    className="rounded border px-1 py-0.5 text-xs w-36"
                    value={editNote}
                    onChange={(e) => setEditNote(e.target.value)}
                    placeholder="Note (optional)"
                    disabled={disabled}
                  />
                </div>
                {isDuplicateName(editName, i) && (
                  <p className="text-xs text-red-600">Tag name already exists</p>
                )}
                <div className="flex gap-1">
                  <button
                    type="button"
                    className="rounded bg-primary px-2 py-0.5 text-xs text-primary-foreground disabled:opacity-50"
                    onClick={saveEdit}
                    disabled={!editName.trim() || isDuplicateName(editName, i)}
                  >
                    Save
                  </button>
                  <button type="button" className="rounded border px-2 py-0.5 text-xs" onClick={cancelEdit}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <button
                  type="button"
                  className="font-medium hover:underline"
                  onClick={() => !disabled && startEdit(i)}
                  disabled={disabled}
                >
                  {tag.tag_name}
                </button>
                {tag.note && (
                  <span className="italic text-muted-foreground text-xs">{tag.note}</span>
                )}
                <button
                  type="button"
                  className="ml-1 text-muted-foreground hover:text-destructive"
                  onClick={() => removeTag(i)}
                  disabled={disabled}
                  aria-label={`Remove ${tag.tag_name}`}
                >
                  ×
                </button>
              </>
            )}
          </div>
        ))}
      </div>

      {adding && (
        <div className="rounded border p-2 space-y-1">
          <div className="flex gap-1">
            <input
              className="rounded border px-2 py-1 text-sm w-32"
              value={addName}
              onChange={(e) => setAddName(e.target.value)}
              placeholder="Tag name *"
              disabled={disabled}
              autoFocus
            />
            <input
              className="rounded border px-2 py-1 text-sm w-40"
              value={addNote}
              onChange={(e) => setAddNote(e.target.value)}
              placeholder="Note (optional)"
              disabled={disabled}
            />
          </div>
          {isDuplicateName(addName) && (
            <p className="text-xs text-red-600">Tag name already exists</p>
          )}
          <div className="flex gap-1">
            <button
              type="button"
              className="rounded bg-primary px-2 py-1 text-sm text-primary-foreground disabled:opacity-50"
              onClick={addTag}
              disabled={!addName.trim() || isDuplicateName(addName)}
            >
              Add
            </button>
            <button type="button" className="rounded border px-2 py-1 text-sm" onClick={cancelAdd}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <button
        type="button"
        className="text-sm text-muted-foreground hover:text-foreground"
        onClick={startAdding}
        disabled={disabled}
      >
        + Add tag
      </button>
    </div>
  );
}
