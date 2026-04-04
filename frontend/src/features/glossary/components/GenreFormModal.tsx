import { useState, useEffect } from 'react';
import { X, Plus, Pencil } from 'lucide-react';
import type { GenreGroup } from '../types';

const COLOR_PRESETS = [
  '#8b5cf6', '#ec4899', '#06b6d4', '#f97316', '#3dba6a',
  '#e8a832', '#dc4e4e', '#64748b', '#8b5e3c', '#a855f7',
];

type Props = {
  bookId: string;
  genre?: GenreGroup | null;
  onSave: (data: { name: string; color: string; description: string }) => Promise<void>;
  onClose: () => void;
};

export function GenreFormModal({ genre, onSave, onClose }: Props) {
  const isEdit = !!genre;
  const [name, setName] = useState(genre?.name ?? '');
  const [color, setColor] = useState(genre?.color ?? COLOR_PRESETS[0]);
  const [description, setDescription] = useState(genre?.description ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const handleSubmit = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Name is required');
      return;
    }
    if (trimmed.length > 200) {
      setError('Name too long (max 200 characters)');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await onSave({ name: trimmed, color, description: description.trim() });
    } catch (e) {
      setError((e as Error).message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="w-full max-w-md rounded-xl border bg-background shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b bg-card px-5 py-4">
            <div className="flex items-center gap-2">
              {isEdit ? (
                <>
                  <div className="h-3 w-3 rounded-sm" style={{ background: color }} />
                  <span className="text-sm font-semibold">Edit Genre &mdash; {genre.name}</span>
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" />
                  <span className="text-sm font-semibold">New Genre Group</span>
                </>
              )}
            </div>
            <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Body */}
          <div className="flex flex-col gap-4 p-5">
            {/* Name */}
            <div>
              <label className="mb-1.5 block text-xs font-medium">
                Genre Name <span className="text-destructive">*</span>
              </label>
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Wuxia, Gothic Horror, Cyberpunk..."
                className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              />
            </div>

            {/* Color */}
            <div>
              <label className="mb-1.5 block text-xs font-medium">Color</label>
              <div className="flex flex-wrap gap-2">
                {COLOR_PRESETS.map((c) => (
                  <button
                    key={c}
                    onClick={() => setColor(c)}
                    className="h-7 w-7 rounded-md transition-transform hover:scale-110"
                    style={{
                      background: c,
                      boxShadow: color === c ? `0 0 0 2px var(--background), 0 0 0 4px ${c}` : undefined,
                    }}
                  />
                ))}
              </div>
              <p className="mt-1.5 text-[11px] text-muted-foreground">Used in badges, filter chips, and genre tag pills</p>
            </div>

            {/* Description */}
            <div>
              <label className="mb-1.5 block text-xs font-medium">
                Description <span className="font-normal text-muted-foreground">(optional)</span>
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Brief note about what this genre covers..."
                rows={2}
                className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30 resize-vertical"
              />
            </div>

            {/* Error */}
            {error && <p className="text-xs text-destructive">{error}</p>}

            {/* Footer */}
            <div className="flex justify-end gap-2 border-t pt-4">
              <button
                onClick={onClose}
                className="rounded-md border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-secondary transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleSubmit()}
                disabled={saving || !name.trim()}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {saving ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Genre'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
