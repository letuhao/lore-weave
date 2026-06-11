// LOOM Composition (T2.1) — one Cast & Codex row: collapsed shows the entity's
// spoiler-safe story-state (active|gone); expanding lazy-loads aliases, 1-hop
// relations, recent (windowed) events, and known facts. Render-only; the lazy
// hooks are gated on `open` so a closed row costs nothing.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useEntityDetail, useEntityEvents, useEntityFacts, type CastRow } from '../hooks/useCast';

export function CastEntityRow({
  row, bookId, chapterId, token, onViewArc,
}: {
  row: CastRow;
  bookId: string;
  chapterId: string;
  token: string | null;
  /** T2.4: open the Character Arc tab for this entity. */
  onViewArc?: (entityId: string) => void;
}) {
  const { t } = useTranslation('composition');
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const detail = useEntityDetail(row.id, token, open);
  const facts = useEntityFacts(row.id, chapterId, token, open);
  const events = useEntityEvents(row.id, chapterId, token, open);

  const gone = row.state?.status === 'gone';
  const relations = detail.data?.relations ?? [];

  return (
    <div data-testid="cast-row" data-entity={row.id} data-status={gone ? 'gone' : 'active'} className="rounded border">
      {/* Toggle + arc launcher are SIBLINGS (a button inside a button is invalid HTML). */}
      <div className="flex items-center">
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
