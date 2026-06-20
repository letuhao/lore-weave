import { FormEvent, useState } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useKindsAdmin } from './hooks/useKindsAdmin';
import { Modal } from './components/Modal';
import { StatusBanner } from './components/StatusBanner';
import { Field, ModalActions, inputCls } from './components/FormBits';
import type { SystemKind } from './types';

type Draft = {
  name: string;
  code: string;
  description: string;
  icon: string;
  color: string;
  is_hidden: boolean;
  sort_order: string;
};

const EMPTY: Draft = {
  name: '',
  code: '',
  description: '',
  icon: '',
  color: '',
  is_hidden: false,
  sort_order: '',
};

function toDraft(k: SystemKind): Draft {
  return {
    name: k.name,
    code: k.code,
    description: k.description ?? '',
    icon: k.icon ?? '',
    color: k.color ?? '',
    is_hidden: !!k.is_hidden,
    sort_order: String(k.sort_order ?? ''),
  };
}

export function KindsAdminPanel() {
  const { list, create, update, remove, status, clearStatus } = useKindsAdmin();
  const [editing, setEditing] = useState<SystemKind | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<Draft>(EMPTY);

  const submitting = create.isPending || update.isPending;

  function openCreate() {
    setDraft(EMPTY);
    setCreating(true);
    setEditing(null);
  }

  function openEdit(k: SystemKind) {
    setDraft(toDraft(k));
    setEditing(k);
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
          id: editing.kind_id,
          body: {
            name: draft.name.trim(),
            description: draft.description.trim() || undefined,
            icon: draft.icon.trim() || undefined,
            color: draft.color.trim() || undefined,
            is_hidden: draft.is_hidden,
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
          description: draft.description.trim() || undefined,
          icon: draft.icon.trim() || undefined,
          color: draft.color.trim() || undefined,
          is_hidden: draft.is_hidden,
          sort_order: sort,
        },
        { onSuccess: close },
      );
    }
  }

  function onDelete(k: SystemKind) {
    if (window.confirm(`Delete system kind “${k.name}”? This affects every tenant.`)) {
      remove.mutate(k.kind_id);
    }
  }

  return (
    <section className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Kinds</h2>
          <p className="text-sm text-muted-foreground">System-tier entity-kind standards.</p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          <Plus className="h-4 w-4" /> New kind
        </button>
      </header>

      <StatusBanner status={status} onDismiss={clearStatus} />

      {list.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {list.isError && <p className="text-sm text-destructive">Failed to load kinds.</p>}

      {list.data && (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-left text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Icon</th>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Code</th>
                <th className="px-3 py-2 font-medium">Hidden</th>
                <th className="px-3 py-2 font-medium">Sort</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {list.data.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-center text-muted-foreground">
                    No system kinds.
                  </td>
                </tr>
              )}
              {list.data.map((k) => (
                <tr key={k.kind_id} className="border-t border-border">
                  <td className="px-3 py-2">{k.icon || '—'}</td>
                  <td className="px-3 py-2 font-medium text-foreground">{k.name}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{k.code}</td>
                  <td className="px-3 py-2 text-muted-foreground">{k.is_hidden ? 'yes' : '—'}</td>
                  <td className="px-3 py-2 text-muted-foreground">{k.sort_order}</td>
                  <td className="px-3 py-2">
                    <div className="flex justify-end gap-1">
                      <button
                        type="button"
                        aria-label={`Edit ${k.name}`}
                        onClick={() => openEdit(k)}
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary/60"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete ${k.name}`}
                        onClick={() => onDelete(k)}
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
        <Modal title={editing ? 'Edit kind' : 'New kind'} onClose={close}>
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
            <Field label="Description (optional)">
              <textarea
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                rows={3}
                className={inputCls}
              />
            </Field>
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
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={draft.is_hidden}
                onChange={(e) => setDraft({ ...draft, is_hidden: e.target.checked })}
                className="h-4 w-4 rounded border-input"
              />
              Hidden (not offered in extraction / pickers)
            </label>
            <ModalActions submitting={submitting} onCancel={close} editing={!!editing} />
          </form>
        </Modal>
      )}
    </section>
  );
}
