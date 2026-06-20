import { FormEvent, useState } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useGenresAdmin } from './hooks/useGenresAdmin';
import { Modal } from './components/Modal';
import { StatusBanner } from './components/StatusBanner';
import { Field, ModalActions, inputCls } from './components/FormBits';
import type { SystemGenre } from './types';

type Draft = {
  name: string;
  code: string;
  icon: string;
  color: string;
  sort_order: string;
};

const EMPTY: Draft = { name: '', code: '', icon: '', color: '', sort_order: '' };

function toDraft(g: SystemGenre): Draft {
  return {
    name: g.name,
    code: g.code,
    icon: g.icon ?? '',
    color: g.color ?? '',
    sort_order: String(g.sort_order ?? ''),
  };
}

export function GenresAdminPanel() {
  const { list, create, update, remove, status, clearStatus } = useGenresAdmin();
  const [editing, setEditing] = useState<SystemGenre | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<Draft>(EMPTY);

  const submitting = create.isPending || update.isPending;

  function openCreate() {
    setDraft(EMPTY);
    setCreating(true);
    setEditing(null);
  }

  function openEdit(g: SystemGenre) {
    setDraft(toDraft(g));
    setEditing(g);
    setCreating(false);
  }

  function close() {
    setCreating(false);
    setEditing(null);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const sort = draft.sort_order.trim() === '' ? undefined : Number(draft.sort_order);
    if (editing) {
      update.mutate(
        {
          id: editing.genre_id,
          body: {
            name: draft.name.trim(),
            icon: draft.icon.trim() || undefined,
            color: draft.color.trim() || undefined,
            sort_order: sort,
          },
        },
        { onSuccess: close },
      );
    } else {
      create.mutate(
        {
          name: draft.name.trim(),
          code: draft.code.trim() || undefined,
          icon: draft.icon.trim() || undefined,
          color: draft.color.trim() || undefined,
          sort_order: sort,
        },
        { onSuccess: close },
      );
    }
  }

  function onDelete(g: SystemGenre) {
    if (window.confirm(`Delete system genre “${g.name}”? This affects every tenant.`)) {
      remove.mutate(g.genre_id);
    }
  }

  return (
    <section className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Genres</h2>
          <p className="text-sm text-muted-foreground">System-tier genre standards.</p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          <Plus className="h-4 w-4" /> New genre
        </button>
      </header>

      <StatusBanner status={status} onDismiss={clearStatus} />

      {list.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {list.isError && (
        <p className="text-sm text-destructive">Failed to load genres.</p>
      )}

      {list.data && (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-left text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Icon</th>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Code</th>
                <th className="px-3 py-2 font-medium">Sort</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {list.data.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-center text-muted-foreground">
                    No system genres.
                  </td>
                </tr>
              )}
              {list.data.map((g) => (
                <tr key={g.genre_id} className="border-t border-border">
                  <td className="px-3 py-2">{g.icon || '—'}</td>
                  <td className="px-3 py-2 font-medium text-foreground">{g.name}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{g.code}</td>
                  <td className="px-3 py-2 text-muted-foreground">{g.sort_order}</td>
                  <td className="px-3 py-2">
                    <div className="flex justify-end gap-1">
                      <button
                        type="button"
                        aria-label={`Edit ${g.name}`}
                        onClick={() => openEdit(g)}
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary/60"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete ${g.name}`}
                        onClick={() => onDelete(g)}
                        disabled={remove.isPending}
                        className="rounded-md p-1.5 text-destructive hover:bg-destructive/10 disabled:opacity-50"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(creating || editing) && (
        <Modal title={editing ? 'Edit genre' : 'New genre'} onClose={close}>
          <form onSubmit={onSubmit} className="space-y-3">
            <Field label="Name" required>
              <input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                required
                className={inputCls}
              />
            </Field>
            {!editing && (
              <Field label="Code (optional — auto from name)">
                <input
                  value={draft.code}
                  onChange={(e) => setDraft({ ...draft, code: e.target.value })}
                  className={inputCls}
                />
              </Field>
            )}
            <Field label="Icon (optional)">
              <input
                value={draft.icon}
                onChange={(e) => setDraft({ ...draft, icon: e.target.value })}
                className={inputCls}
              />
            </Field>
            <Field label="Color (optional)">
              <input
                value={draft.color}
                onChange={(e) => setDraft({ ...draft, color: e.target.value })}
                placeholder="#7c3aed"
                className={inputCls}
              />
            </Field>
            <Field label="Sort order (optional)">
              <input
                type="number"
                value={draft.sort_order}
                onChange={(e) => setDraft({ ...draft, sort_order: e.target.value })}
                className={inputCls}
              />
            </Field>
            <ModalActions submitting={submitting} onCancel={close} editing={!!editing} />
          </form>
        </Modal>
      )}
    </section>
  );
}
