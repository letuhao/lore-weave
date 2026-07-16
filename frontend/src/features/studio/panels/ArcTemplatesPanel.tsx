// 34 arc-templates (category storyBible) — the arc-template LIBRARY as a first-class S2 panel.
// Lifts the motif Arc* surface (D-S2-ARC-SEAM: reuse ArcTimelineEditor + ArcApplyPreview in place,
// no edits to S4's files) and adds the CRUD the library was missing a UI for — New / Adopt / Archive
// (AT-2 tiers). ArcConformancePanel is DROPPED (AT-7 — dead at HEAD, and it is spec-33's surface).
// Logic in useArcTemplates; this file renders. Catalog + Import&Deconstruct tabs land in later slices.
import { useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';

import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { useArcTemplates, type ArcTemplatesState } from './useArcTemplates';
import { ArcTimelineEditor } from '@/features/composition/motif/components/ArcTimelineEditor';
import { ArcApplyPreview } from '@/features/composition/motif/components/ArcApplyPreview';
import { ImportDeconstructSection } from '@/features/composition/arcImport/ImportDeconstructSection';
import { listCatalog } from '@/features/composition/arcTemplates/api';
import type { ArcTemplate } from '@/features/composition/motif/arcTypes';

const TIERS = [
  { key: 'all', label: 'All' },
  { key: 'mine', label: 'Mine' },
  { key: 'system', label: 'System' },
  { key: 'book', label: 'Book' },   // 34a — the book's SHARED tier (collaborators co-own)
] as const;

export function ArcTemplatesPanel(props: IDockviewPanelProps) {
  useStudioPanel('arc-templates', props.api);
  const host = useStudioHost();
  const state = useArcTemplates(host.bookId);
  const [view, setView] = useState<'library' | 'catalog' | 'deconstruct'>('library');
  const tab = (key: typeof view, label: string) => (
    <button type="button" role="tab" data-testid={`arc-tab-${key}`} aria-selected={view === key}
      className={`rounded px-2 py-0.5 text-xs ${view === key ? 'bg-muted font-medium' : 'text-muted-foreground hover:bg-muted/50'}`}
      onClick={() => setView(key)}>{label}</button>
  );

  return (
    <div data-testid="studio-arc-templates-panel" className="flex h-full min-h-0 flex-col text-sm">
      <div className="flex gap-1 border-b p-1" role="tablist">
        {tab('library', 'Library')}
        {tab('catalog', 'Catalog')}
        {tab('deconstruct', 'Import & Deconstruct')}
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {view === 'deconstruct' ? (
          <div className="h-full overflow-auto"><ImportDeconstructSection token={state.token} /></div>
        ) : view === 'catalog' ? (
          <CatalogView state={state} />
        ) : state.selected ? (
          <ArcDetail state={state} arc={state.selected} />
        ) : (
          <ArcLibrary state={state} />
        )}
      </div>
    </div>
  );
}

function ArcLibrary({ state }: { state: ArcTemplatesState }) {
  const { t } = useTranslation('composition');
  const [creating, setCreating] = useState(false);

  return (
    <>
      <div className="flex items-center gap-2 border-b p-2">
        <div className="flex gap-1" role="tablist">
          {TIERS.map((tr) => (
            <button key={tr.key} type="button" data-testid={`arc-tier-${tr.key}`}
              aria-selected={state.tier === tr.key}
              className={`rounded px-2 py-0.5 text-xs ${state.tier === tr.key ? 'bg-primary text-primary-fg' : 'text-muted-foreground hover:bg-muted'}`}
              onClick={() => state.setTier(tr.key)}>{tr.label}</button>
          ))}
        </div>
        <button type="button" data-testid="arc-new" disabled={state.busy}
          className="ml-auto rounded border border-border px-2 py-0.5 text-xs font-semibold hover:border-ring disabled:opacity-50"
          onClick={() => setCreating(true)}>+ New</button>
      </div>

      {creating && <CreateForm state={state} onDone={() => setCreating(false)} />}
      {state.actionError && <p data-testid="arc-templates-error" className="border-b p-2 text-xs text-destructive">{state.actionError}</p>}

      <div className="min-h-0 flex-1 overflow-auto">
        {state.loading ? (
          <p data-testid="arc-templates-loading" className="p-4 text-center text-xs text-muted-foreground">Loading…</p>
        ) : state.isError ? (
          <div className="p-4 text-center text-xs text-destructive">Could not load templates. <button type="button" className="underline" onClick={state.refetch}>Retry</button></div>
        ) : state.templates.length === 0 ? (
          <p data-testid="arc-templates-empty" className="p-4 text-center text-xs text-muted-foreground">
            {t('motif.arc.libraryEmpty', { defaultValue: 'No arc templates yet. Create one, or import a story to deconstruct.' })}
          </p>
        ) : (
          <ul className="flex flex-col">
            {state.templates.map((a) => <Row key={a.id} state={state} arc={a} />)}
          </ul>
        )}
      </div>
    </>
  );
}

function Row({ state, arc }: { state: ArcTemplatesState; arc: ArcTemplate }) {
  const tier = state.tierOf(arc);
  return (
    <li className="flex items-center gap-2 border-b px-2 py-1.5 hover:bg-muted/50">
      <button type="button" data-testid={`arc-row-${arc.id}`} className="min-w-0 flex-1 text-left" onClick={() => state.select(arc)}>
        <span className="block truncate text-xs font-medium">{arc.name}</span>
        <span className="block truncate text-[10px] text-muted-foreground">
          {arc.chapter_span ?? 0} chapters{arc.genre_tags.length ? ` · ${arc.genre_tags.join(', ')}` : ''}
        </span>
      </button>
      <span data-testid={`arc-tier-chip-${arc.id}`} className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
        {tier === 'system' ? 'System' : tier === 'mine' ? 'Mine' : 'Public'}
      </span>
      {tier === 'mine' ? (
        <button type="button" data-testid={`arc-archive-${arc.id}`} disabled={state.busy}
          className="shrink-0 text-[10px] text-muted-foreground underline-offset-2 hover:underline disabled:opacity-50"
          onClick={() => void state.archive(arc.id)}>archive</button>
      ) : (
        <button type="button" data-testid={`arc-adopt-${arc.id}`} disabled={state.busy}
          className="shrink-0 text-[10px] text-primary underline-offset-2 hover:underline disabled:opacity-50"
          onClick={() => void state.adopt(arc.id)}>adopt</button>
      )}
    </li>
  );
}

function CreateForm({ state, onDone }: { state: ArcTemplatesState; onDone: () => void }) {
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [shareToBook, setShareToBook] = useState(state.tier === 'book');
  const submit = async () => {
    if (!code.trim() || !name.trim()) return;
    await state.create({ code: code.trim(), name: name.trim(), shareToBook });
    onDone();
  };
  return (
    <div data-testid="arc-create-form" className="flex flex-col gap-1.5 border-b bg-muted/30 p-2">
      <input data-testid="arc-create-code" className="rounded border bg-background px-2 py-1 text-xs" placeholder="code (unique)" value={code} onChange={(e) => setCode(e.target.value)} />
      <input data-testid="arc-create-name" className="rounded border bg-background px-2 py-1 text-xs" placeholder="name" value={name} onChange={(e) => setName(e.target.value)} />
      <label className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <input type="checkbox" data-testid="arc-create-share" checked={shareToBook} onChange={(e) => setShareToBook(e.target.checked)} />
        Share with this book&apos;s collaborators (book tier)
      </label>
      <div className="flex gap-2">
        <button type="button" data-testid="arc-create-submit" disabled={state.busy || !code.trim() || !name.trim()}
          className="rounded bg-primary px-2 py-0.5 text-xs font-semibold text-primary-fg disabled:opacity-50" onClick={() => void submit()}>Create</button>
        <button type="button" className="rounded px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted" onClick={onDone}>Cancel</button>
      </div>
    </div>
  );
}

function CatalogView({ state }: { state: ArcTemplatesState }) {
  // 34 AT-2 — others' PUBLIC arc templates (a paged allow-list projection). Adopt clones one
  // into your own library (the only write available on a foreign row).
  const cat = useQuery({
    queryKey: ['composition', 'arc-templates', 'catalog'],
    queryFn: () => listCatalog({ limit: 50 }, state.token!),
    enabled: !!state.token,
  });
  if (cat.isLoading) return <p data-testid="arc-catalog-loading" className="p-4 text-center text-xs text-muted-foreground">Loading…</p>;
  if (cat.isError) return <div className="p-4 text-center text-xs text-destructive">Could not load the catalog. <button type="button" className="underline" onClick={() => cat.refetch()}>Retry</button></div>;
  const items = cat.data?.items ?? [];
  if (items.length === 0) return <p data-testid="arc-catalog-empty" className="p-4 text-center text-xs text-muted-foreground">No public arc templates yet.</p>;
  return (
    <ul className="min-h-0 flex-1 overflow-auto" data-testid="arc-catalog">
      {items.map((it) => (
        <li key={it.id} className="flex items-center gap-2 border-b px-2 py-1.5 hover:bg-muted/50">
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-medium">{it.name}</span>
            <span className="block truncate text-[10px] text-muted-foreground">{it.chapter_span ?? 0} chapters{it.genre_tags.length ? ` · ${it.genre_tags.join(', ')}` : ''}</span>
          </span>
          <button type="button" data-testid={`catalog-adopt-${it.id}`} disabled={state.busy}
            className="shrink-0 text-[10px] text-primary underline-offset-2 hover:underline disabled:opacity-50"
            onClick={() => void state.adopt(it.id)}>adopt</button>
        </li>
      ))}
    </ul>
  );
}

function ArcDetail({ state, arc }: { state: ArcTemplatesState; arc: ArcTemplate }) {
  return (
    <div data-testid="arc-template-detail" className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b p-2">
        <button type="button" data-testid="arc-back" className="text-[11px] text-primary hover:underline" onClick={() => state.select(null)}>← All templates</button>
        <span className="truncate text-xs font-medium">{arc.name}</span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <ArcTimelineEditor arcId={arc.id} token={state.token} />
        <div className="border-t p-2">
          <ArcApplyPreview arc={arc} token={state.token} projectId={state.projectId} />
        </div>
      </div>
    </div>
  );
}
