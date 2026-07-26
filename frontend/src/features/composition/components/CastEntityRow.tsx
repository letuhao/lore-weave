// LOOM Composition (T2.1) — one Cast & Codex row: collapsed shows the entity's
// spoiler-safe story-state (active|gone); expanding lazy-loads aliases, 1-hop
// relations, recent (windowed) events, and known facts. Render-only; the lazy
// hooks are gated on `open` so a closed row costs nothing.
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Pencil, Archive } from 'lucide-react';
import { useEntityDetail, useEntityEvents, useEntityFacts, type CastRow } from '../hooks/useCast';

export function CastEntityRow({
  row, bookId, chapterId, token, onViewArc, onRename, onEdit, onArchive,
}: {
  row: CastRow;
  bookId: string;
  chapterId: string;
  token: string | null;
  /** T2.4: open the Character Arc tab for this entity. */
  onViewArc?: (entityId: string) => void;
  // s7-4 — ADDITIVE edit affordances (DP-3). The legacy ChapterEditorPage mount
  // passes NONE → the row renders exactly as before (no edit UI). The dock panel
  // passes them → the row grows inline rename + a pencil + an archive control.
  // ONE component, two hosts — never a forked "editable row".
  /** commit an inline rename (PATCH name, If-Match version). */
  onRename?: (args: { entityId: string; name: string; version: number }) => void;
  /** open the reused EntityEditDialog (aliases/kind) for this row. */
  onEdit?: (row: CastRow) => void;
  /** soft-archive (retire) this entity. */
  onArchive?: (row: CastRow) => void;
}) {
  const { t } = useTranslation('composition');
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const detail = useEntityDetail(row.id, token, open);
  const facts = useEntityFacts(row.id, chapterId, token, open);
  const events = useEntityEvents(row.id, chapterId, token, open);

  const gone = row.state?.status === 'gone';
  const relations = detail.data?.relations ?? [];

  // Inline rename (only when onRename is supplied).
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(row.name);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (renaming) {
      setDraft(row.name);
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [renaming, row.name]);
  const commitRename = () => {
    const next = draft.trim();
    setRenaming(false);
    if (next && next !== row.name) {
      onRename?.({ entityId: row.id, name: next, version: row.version });
    }
  };

  return (
    <div data-testid="cast-row" data-entity={row.id} data-status={gone ? 'gone' : 'active'} className="rounded border">
      {/* Toggle + arc launcher are SIBLINGS (a button inside a button is invalid HTML). */}
      <div className="flex items-center">
        {renaming ? (
          <div className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1">
            <span aria-hidden className={'h-2 w-2 shrink-0 rounded-full ' + (gone ? 'bg-rose-500' : 'bg-emerald-500')} />
            <input
              ref={inputRef}
              data-testid="cast-row-rename-input"
              className="min-w-0 flex-1 rounded border bg-background px-1 py-0.5 text-xs"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); commitRename(); }
                else if (e.key === 'Escape') { e.preventDefault(); setRenaming(false); }
              }}
              onBlur={commitRename}
            />
          </div>
        ) : (
          <button
            type="button"
            data-testid="cast-row-toggle"
            aria-expanded={open}
            className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1 text-left text-xs hover:bg-accent/50"
            onClick={() => setOpen((o) => !o)}
          >
            <span aria-hidden className={'h-2 w-2 shrink-0 rounded-full ' + (gone ? 'bg-rose-500' : 'bg-emerald-500')} />
            <span className="min-w-0 flex-1 truncate font-medium">{row.name}</span>
            <span
              data-testid="cast-row-state"
              className={'shrink-0 text-[10px] ' + (gone ? 'text-rose-600' : 'text-muted-foreground')}
            >
              {gone ? t('codex.gone', { defaultValue: 'gone' }) : t('codex.active', { defaultValue: 'active' })}
            </span>
            <span aria-hidden className="shrink-0 text-[10px] text-muted-foreground">{open ? '▾' : '▸'}</span>
          </button>
        )}
        {onRename && !renaming && (
          <button
            type="button"
            data-testid="cast-row-rename"
            aria-label={t('codex.rename', { defaultValue: 'Rename' })}
            title={t('codex.rename', { defaultValue: 'Rename' })}
            className="shrink-0 px-1.5 py-1 text-[11px] text-muted-foreground hover:text-primary"
            onClick={() => setRenaming(true)}
          >
            ✎
          </button>
        )}
        {onEdit && (
          <button
            type="button"
            data-testid="cast-row-edit"
            aria-label={t('codex.editEntity', { defaultValue: 'Edit aliases & kind' })}
            title={t('codex.editEntity', { defaultValue: 'Edit aliases & kind' })}
            className="shrink-0 px-1.5 py-1 text-muted-foreground hover:text-primary"
            onClick={() => onEdit(row)}
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}
        {onArchive && (
          <button
            type="button"
            data-testid="cast-row-archive"
            aria-label={t('codex.archive', { defaultValue: 'Retire entity' })}
            title={t('codex.archive', { defaultValue: 'Retire entity' })}
            className="shrink-0 px-1.5 py-1 text-muted-foreground hover:text-destructive"
            onClick={() => onArchive(row)}
          >
            <Archive className="h-3.5 w-3.5" />
          </button>
        )}
        {onViewArc && (
          <button
            type="button"
            data-testid="cast-row-arc"
            aria-label={t('codex.viewArc', { defaultValue: 'View character arc' })}
            title={t('codex.viewArc', { defaultValue: 'View character arc' })}
            className="shrink-0 px-1.5 py-1 text-[11px] text-muted-foreground hover:text-primary"
            onClick={() => onViewArc(row.id)}
          >
            📈
          </button>
        )}
      </div>

      {open && (
        <div data-testid="cast-row-detail" className="space-y-1.5 border-t px-2 py-1.5 text-[11px]">
          {row.aliases.length > 0 && (
            <div className="text-muted-foreground">
              <span className="font-medium">{t('codex.aliases', { defaultValue: 'aka' })}:</span> {row.aliases.join(', ')}
            </div>
          )}

          <Section label={t('codex.relations', { defaultValue: 'Relations' })} count={detail.data?.total_relations}>
            {relations.length === 0
              ? <Empty>{t('codex.noRelations', { defaultValue: 'none' })}</Empty>
              : relations.slice(0, 8).map((r) => (
                  <div key={r.id} data-testid="cast-relation" className="truncate">
                    {r.subject_id === row.id
                      ? <>→ {r.predicate} {r.object_name ?? r.object_id}</>
                      : <>{r.subject_name ?? r.subject_id} {r.predicate} →</>}
                  </div>
                ))}
          </Section>

          <Section label={t('codex.events', { defaultValue: 'Recent events' })}>
            {(events.data ?? []).length === 0
              ? <Empty>{t('codex.noEvents', { defaultValue: 'none yet' })}</Empty>
              : (events.data ?? []).map((e) => (
                  <button
                    key={e.id} type="button" data-testid="cast-event"
                    className="block w-full truncate text-left hover:text-primary"
                    onClick={() => e.chapter_id && navigate(`/books/${bookId}/chapters/${e.chapter_id}/edit`)}
                  >
                    {e.title}
                  </button>
                ))}
          </Section>

          <Section label={t('codex.facts', { defaultValue: 'Known facts' })}>
            {(facts.data?.facts ?? []).length === 0
              ? <Empty>{t('codex.noFacts', { defaultValue: 'none yet' })}</Empty>
              : (facts.data?.facts ?? []).map((f) => (
                  <div key={f.id} data-testid="cast-fact" className="truncate">
                    <span className="text-muted-foreground">{f.type}:</span> {f.content}
                  </div>
                ))}
          </Section>
        </div>
      )}
    </div>
  );
}

function Section({ label, count, children }: { label: string; count?: number; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground/70">
        {label}{count != null ? ` (${count})` : ''}
      </div>
      <div className="mt-0.5 flex flex-col gap-0.5">{children}</div>
    </div>
  );
}

const Empty = ({ children }: { children: React.ReactNode }) => (
  <span className="italic text-muted-foreground/50">{children}</span>
);
