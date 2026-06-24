import { FormEvent, useMemo, useState } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useAttributesAdmin } from './hooks/useAttributesAdmin';
import { useAttributeMatrix } from './hooks/useAttributeMatrix';
import { Modal } from './components/Modal';
import { StatusBanner } from './components/StatusBanner';
import { Field, ModalActions, inputCls } from './components/FormBits';
import { SearchInput, matchesQuery } from './components/SearchInput';
import { FieldTypeBadge } from './components/FieldTypeBadge';
import { AttributeInspector } from './components/AttributeInspector';
import { AttributeMatrix, type CellRef } from './components/AttributeMatrix';
import {
  FIELD_TYPES,
  type FieldType,
  type SystemAttribute,
  type SystemGenre,
  type SystemKind,
} from './types';

type Draft = {
  name: string;
  code: string;
  description: string;
  field_type: FieldType;
  is_required: boolean;
  sort_order: string;
  options: string; // one per line
  auto_fill_prompt: string;
  translation_hint: string;
};

const EMPTY: Draft = {
  name: '',
  code: '',
  description: '',
  field_type: 'text',
  is_required: false,
  sort_order: '',
  options: '',
  auto_fill_prompt: '',
  translation_hint: '',
};

// G-C3 — options only apply to choice-style field types. The backend accepts options on
// any type (no field_type/options validation in createSystemAttribute), so we mirror the
// user-tier AttributeFormModal which shows options for select AND tags.
function fieldTypeHasOptions(ft: FieldType): boolean {
  return ft === 'select' || ft === 'tags';
}

function toDraft(a: SystemAttribute): Draft {
  return {
    name: a.name,
    code: a.code,
    description: a.description ?? '',
    field_type: a.field_type,
    is_required: !!a.is_required,
    sort_order: String(a.sort_order ?? ''),
    options: (a.options ?? []).join('\n'),
    auto_fill_prompt: a.auto_fill_prompt ?? '',
    translation_hint: a.translation_hint ?? '',
  };
}

function parseOptions(raw: string): string[] | undefined {
  const lines = raw
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
  return lines.length ? lines : undefined;
}

type View = 'list' | 'matrix';

export function AttributesAdminPanel() {
  const [kindId, setKindId] = useState('');
  const [genreId, setGenreId] = useState('');
  const { kinds, genres, attributes, selected, create, update, remove, status, clearStatus } =
    useAttributesAdmin(kindId, genreId);

  const [view, setView] = useState<View>('list');
  const [editing, setEditing] = useState<SystemAttribute | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [query, setQuery] = useState('');
  const [selectedAttrId, setSelectedAttrId] = useState<string | null>(null);

  const submitting = create.isPending || update.isPending;
  const showOptions = fieldTypeHasOptions(draft.field_type);

  const rows = attributes.data ?? [];
  const filtered = useMemo(
    () => rows.filter((a) => matchesQuery(query, a.name, a.code)),
    [rows, query],
  );
  const selectedAttr = useMemo(
    () => rows.find((a) => a.attr_id === selectedAttrId) ?? null,
    [rows, selectedAttrId],
  );

  function openCreate() {
    setDraft(EMPTY);
    setCreating(true);
    setEditing(null);
  }

  function openEdit(a: SystemAttribute) {
    setDraft(toDraft(a));
    setEditing(a);
    setCreating(false);
  }

  function close() {
    setCreating(false);
    setEditing(null);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const name = draft.name.trim();
    if (!name) return;
    const sort = draft.sort_order.trim() === '' ? undefined : Number(draft.sort_order);
    // G-C3: only send options for option-bearing types; for select, require ≥1 option.
    const options = showOptions ? parseOptions(draft.options) : undefined;
    if (draft.field_type === 'select' && !options) return;
    if (editing) {
      update.mutate(
        {
          id: editing.attr_id,
          body: {
            name,
            description: draft.description.trim() || undefined,
            field_type: draft.field_type,
            is_required: draft.is_required,
            sort_order: sort,
            options,
            auto_fill_prompt: draft.auto_fill_prompt.trim() || undefined,
            translation_hint: draft.translation_hint.trim() || undefined,
          },
        },
        { onSuccess: close },
      );
    } else {
      create.mutate(
        {
          kind_id: kindId,
          genre_id: genreId,
          name,
          code: draft.code.trim() || undefined,
          description: draft.description.trim() || undefined,
          field_type: draft.field_type,
          is_required: draft.is_required,
          sort_order: sort,
          options,
          auto_fill_prompt: draft.auto_fill_prompt.trim() || undefined,
          translation_hint: draft.translation_hint.trim() || undefined,
        },
        { onSuccess: close },
      );
    }
  }

  function onDelete(a: SystemAttribute) {
    if (window.confirm(`Delete system attribute “${a.name}”? This affects every tenant.`)) {
      remove.mutate(a.attr_id);
    }
  }

  return (
    <section className="space-y-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Attributes</h2>
          <p className="text-sm text-muted-foreground">
            System-tier attribute standards, keyed by kind × genre.
          </p>
        </div>
        <div className="inline-flex rounded-md border border-border p-0.5">
          <button
            type="button"
            onClick={() => setView('list')}
            className={`rounded px-3 py-1 text-sm ${
              view === 'list'
                ? 'bg-secondary font-medium text-foreground'
                : 'text-muted-foreground hover:bg-secondary/60'
            }`}
          >
            List
          </button>
          <button
            type="button"
            onClick={() => setView('matrix')}
            className={`rounded px-3 py-1 text-sm ${
              view === 'matrix'
                ? 'bg-secondary font-medium text-foreground'
                : 'text-muted-foreground hover:bg-secondary/60'
            }`}
          >
            Matrix
          </button>
        </div>
      </header>

      <StatusBanner status={status} onDismiss={clearStatus} />

      {view === 'list' ? (
        <ListView
          kindId={kindId}
          genreId={genreId}
          setKindId={setKindId}
          setGenreId={setGenreId}
          kinds={kinds.data ?? []}
          genres={genres.data ?? []}
          selected={selected}
          attributes={attributes}
          filtered={filtered}
          rows={rows}
          query={query}
          setQuery={setQuery}
          selectedAttr={selectedAttr}
          selectedGenreId={genreId}
          onSelectRow={setSelectedAttrId}
          onCreate={openCreate}
          onEdit={openEdit}
          onDelete={onDelete}
          removePending={remove.isPending}
        />
      ) : (
        <MatrixView kindId={kindId} setKindId={setKindId} kinds={kinds.data ?? []} />
      )}

      {(creating || editing) && (
        <Modal title={editing ? 'Edit attribute' : 'New attribute'} onClose={close}>
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
                rows={2}
                className={inputCls}
              />
            </Field>
            <Field label="Field type">
              <select
                value={draft.field_type}
                onChange={(e) => setDraft({ ...draft, field_type: e.target.value as FieldType })}
                className={inputCls}
              >
                {FIELD_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </Field>
            {showOptions && (
              <Field label="Options (one per line)">
                <textarea
                  value={draft.options}
                  onChange={(e) => setDraft({ ...draft, options: e.target.value })}
                  rows={3}
                  placeholder={'option-a\noption-b'}
                  className={inputCls}
                />
                {draft.field_type === 'select' && !parseOptions(draft.options) && (
                  <span className="text-xs text-destructive">
                    A select attribute needs at least one option.
                  </span>
                )}
              </Field>
            )}
            <Field label="Sort order (optional)">
              <input
                type="number"
                value={draft.sort_order}
                onChange={(e) => setDraft({ ...draft, sort_order: e.target.value })}
                className={inputCls}
              />
            </Field>
            <Field label="Auto-fill prompt (optional)">
              <textarea
                value={draft.auto_fill_prompt}
                onChange={(e) => setDraft({ ...draft, auto_fill_prompt: e.target.value })}
                rows={2}
                placeholder="How the AI fills this attribute from chapter text"
                className={inputCls}
              />
            </Field>
            <Field label="Translation hint (optional)">
              <textarea
                value={draft.translation_hint}
                onChange={(e) => setDraft({ ...draft, translation_hint: e.target.value })}
                rows={2}
                placeholder="Guidance injected when translating this attribute's value"
                className={inputCls}
              />
            </Field>
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={draft.is_required}
                onChange={(e) => setDraft({ ...draft, is_required: e.target.checked })}
                className="h-4 w-4 rounded border-input"
              />
              Required
            </label>
            <ModalActions submitting={submitting} onCancel={close} editing={!!editing} />
          </form>
        </Modal>
      )}
    </section>
  );
}

// ---- List view (the kind×genre picker + table + side inspector) ----------

type ListViewProps = {
  kindId: string;
  genreId: string;
  setKindId: (v: string) => void;
  setGenreId: (v: string) => void;
  kinds: SystemKind[];
  genres: SystemGenre[];
  selected: boolean;
  attributes: { isLoading: boolean; isError: boolean; data?: SystemAttribute[] };
  filtered: SystemAttribute[];
  rows: SystemAttribute[];
  query: string;
  setQuery: (v: string) => void;
  selectedAttr: SystemAttribute | null;
  selectedGenreId: string;
  onSelectRow: (id: string) => void;
  onCreate: () => void;
  onEdit: (a: SystemAttribute) => void;
  onDelete: (a: SystemAttribute) => void;
  removePending: boolean;
};

function ListView(p: ListViewProps) {
  const inspectorGenre =
    p.genres.find((g) => g.genre_id === p.selectedGenreId) ?? null;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <label className="space-y-1">
          <span className="block text-sm text-muted-foreground">Kind</span>
          <select
            value={p.kindId}
            onChange={(e) => p.setKindId(e.target.value)}
            className={`${inputCls} min-w-48`}
          >
            <option value="">Select a kind…</option>
            {p.kinds.map((k) => (
              <option key={k.kind_id} value={k.kind_id}>
                {k.name}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="block text-sm text-muted-foreground">Genre</span>
          <select
            value={p.genreId}
            onChange={(e) => p.setGenreId(e.target.value)}
            className={`${inputCls} min-w-48`}
          >
            <option value="">Select a genre…</option>
            {p.genres.map((g) => (
              <option key={g.genre_id} value={g.genre_id}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-end">
          <button
            type="button"
            onClick={p.onCreate}
            disabled={!p.selected}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            <Plus className="h-4 w-4" /> New attribute
          </button>
        </div>
      </div>

      {!p.selected && (
        <p className="text-sm text-muted-foreground">Pick a kind and a genre to view attributes.</p>
      )}

      {p.selected && p.attributes.isLoading && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}
      {p.selected && p.attributes.isError && (
        <p className="text-sm text-destructive">Failed to load attributes.</p>
      )}

      {p.selected && p.attributes.data && (
        <>
          {p.rows.length > 0 && (
            <SearchInput value={p.query} onChange={p.setQuery} placeholder="Search attributes…" />
          )}
          <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
            <div className="overflow-hidden rounded-md border border-border">
              <table className="w-full text-sm">
                <thead className="bg-secondary/40 text-left text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Name</th>
                    <th className="px-3 py-2 font-medium">Code</th>
                    <th className="px-3 py-2 font-medium">Type</th>
                    <th className="px-3 py-2 font-medium">Required</th>
                    <th className="px-3 py-2 font-medium">Sort</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {p.filtered.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-3 py-4 text-center text-muted-foreground">
                        {p.rows.length === 0
                          ? 'No attributes for this kind × genre.'
                          : 'No attributes match your search.'}
                      </td>
                    </tr>
                  )}
                  {p.filtered.map((a) => (
                    <tr
                      key={a.attr_id}
                      onClick={() => p.onSelectRow(a.attr_id)}
                      className={`cursor-pointer border-t border-border ${
                        p.selectedAttr?.attr_id === a.attr_id ? 'bg-secondary/40' : ''
                      }`}
                    >
                      <td className="px-3 py-2 font-medium text-foreground">{a.name}</td>
                      <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{a.code}</td>
                      <td className="px-3 py-2">
                        <FieldTypeBadge fieldType={a.field_type} />
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">
                        {a.is_required ? 'yes' : '—'}
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{a.sort_order}</td>
                      <td className="px-3 py-2">
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            aria-label={`Edit ${a.name}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              p.onEdit(a);
                            }}
                            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary/60"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            aria-label={`Delete ${a.name}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              p.onDelete(a);
                            }}
                            disabled={p.removePending}
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
            <AttributeInspector
              attribute={p.selectedAttr}
              genre={p.selectedAttr ? inspectorGenre : null}
            />
          </div>
        </>
      )}
    </div>
  );
}

// ---- Matrix view (kind picker + cross-genre grid + cell inspector) -------

function MatrixView({
  kindId,
  setKindId,
  kinds,
}: {
  kindId: string;
  setKindId: (v: string) => void;
  kinds: SystemKind[];
}) {
  const { activeGenres, attributes, isLoading, isError } = useAttributeMatrix(kindId);
  const [cell, setCell] = useState<CellRef | null>(null);

  const selectedAttr = useMemo(
    () =>
      cell
        ? attributes.find((a) => a.code === cell.code && a.genre_id === cell.genreId) ?? null
        : null,
    [attributes, cell],
  );
  const selectedGenre = useMemo(
    () => (cell ? activeGenres.find((g) => g.genre_id === cell.genreId) ?? null : null),
    [activeGenres, cell],
  );

  return (
    <div className="space-y-4">
      <label className="space-y-1">
        <span className="block text-sm text-muted-foreground">Kind</span>
        <select
          value={kindId}
          onChange={(e) => {
            setKindId(e.target.value);
            setCell(null);
          }}
          className={`${inputCls} min-w-48`}
        >
          <option value="">Select a kind…</option>
          {kinds.map((k) => (
            <option key={k.kind_id} value={k.kind_id}>
              {k.name}
            </option>
          ))}
        </select>
      </label>

      {!kindId && (
        <p className="text-sm text-muted-foreground">Pick a kind to compare its attributes across genres.</p>
      )}
      {kindId && isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {kindId && isError && (
        <p className="text-sm text-destructive">Failed to load the attribute matrix.</p>
      )}

      {kindId && !isLoading && !isError && (
        <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
          <AttributeMatrix
            activeGenres={activeGenres}
            attributes={attributes}
            selectedCell={cell}
            onSelectCell={setCell}
          />
          <AttributeInspector attribute={selectedAttr} genre={selectedGenre} />
        </div>
      )}
    </div>
  );
}
