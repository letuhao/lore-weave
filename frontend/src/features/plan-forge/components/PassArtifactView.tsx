// PlanForge S3 (F-1) — a human-readable, per-artifact-kind render of a pass artifact, so an author
// reviewing a checkpoint reads a CAST LIST / a BEAT LIST, not raw JSON. Coverage run 1 found the
// raw-JSON viewer "view-inadequate" for an author. Known kinds get a structured read; anything else
// falls back to formatted JSON (never a blank — degrade-safe). READ-ONLY (the only artifact mutation
// is /checkpoint's deep-merge, PF-3). Shares the render the future structured editor will build on.
import type { PlanArtifactKind } from '../types';

interface Props {
  kind: PlanArtifactKind;
  content: unknown;
}

/** Pull an array field off an object content, tolerating a missing/mis-shaped artifact. */
function arr(content: unknown, key: string): Record<string, unknown>[] {
  const v = (content as Record<string, unknown> | null)?.[key];
  return Array.isArray(v) ? (v as Record<string, unknown>[]) : [];
}

const str = (v: unknown): string => (typeof v === 'string' ? v : v == null ? '' : String(v));

export function PassArtifactView({ kind, content }: Props) {
  // cast_plan → the roster: name · role · archetype · summary.
  //
  // `trait` was the third column here, and `run_cast` has never emitted it — its rows are
  // {name, role, archetype, summary, is_new, attributes}. So the checkpoint that asks the author
  // "who ARE these characters?" showed only a name and a role, hiding the two fields that actually
  // answer the question. `trait` is still read as a fallback because artifacts edited under the
  // old FE genuinely contain it.
  if (kind === 'cast_plan') {
    const roster = arr(content, 'cast').length ? arr(content, 'cast') : arr(content, 'roster');
    if (!roster.length) return <Empty label="No cast members in this plan yet." />;
    return (
      <ul data-testid="artifact-cast" className="space-y-1">
        {roster.map((m, i) => {
          const detail = str(m.summary ?? m.trait ?? '');
          return (
            <li key={`${str(m.name)}-${i}`} className="rounded bg-muted/40 px-2 py-1">
              <span className="font-medium text-foreground">{str(m.name) || '—'}</span>
              {m.role != null && <span className="ml-1 rounded bg-secondary px-1 text-[9px] uppercase text-muted-foreground">{str(m.role)}</span>}
              {m.archetype != null && str(m.archetype) !== '' && (
                <span className="ml-1 rounded bg-accent/15 px-1 text-[9px] text-accent">{str(m.archetype)}</span>
              )}
              {/* `is_new` is the difference between "we are inventing this person" and "this is
                  someone your book already has" — the single most useful thing to know before
                  accepting a cast. */}
              {m.is_new === false && <span className="ml-1 text-[9px] text-muted-foreground/70">existing</span>}
              {detail !== '' && <span className="ml-1 text-[10px] text-muted-foreground">— {detail}</span>}
            </li>
          );
        })}
      </ul>
    );
  }

  // beat_plan → the story SHAPE: each chapter's beat role + its tension target, plus any beat the
  // plan never hits.
  //
  // This read `content.beats` — a key the producer (`run_beats`) has never emitted; its output is
  // {chapters, tension_curve, unmapped_beats}. So the blocking checkpoint where the author decides
  // "what shape does this story take?" rendered "No beats in this plan yet." on EVERY real run,
  // and `tension_curve`/`unmapped_beats` were never shown at all. Verified against live artifacts.
  if (kind === 'beat_plan') {
    const chapters = arr(content, 'chapters');
    const curve = arr(content, 'tension_curve');
    // `unmapped_beats` is a list of STRINGS, not objects — `arr()` would yield garbage.
    const unmappedKeys = Array.isArray((content as Record<string, unknown> | null)?.unmapped_beats)
      ? ((content as Record<string, unknown>).unmapped_beats as unknown[]).map(str).filter(Boolean)
      : [];
    if (!chapters.length) return <Empty label="No chapter beats in this plan yet." />;
    const tensionByIndex = new Map<number, string>();
    curve.forEach((c) => {
      const idx = typeof c.chapter_index === 'number' ? c.chapter_index : Number(c.chapter_index);
      if (Number.isFinite(idx)) tensionByIndex.set(idx, str(c.tension_target));
    });
    return (
      <div className="space-y-1">
        {/* A beat nothing hits is the checkpoint's whole safety signal — show it FIRST, loudly. */}
        {unmappedKeys.length > 0 && (
          <p data-testid="artifact-unmapped-beats" className="rounded bg-warning/15 px-2 py-1 text-[10px] text-foreground">
            Never reached by any chapter: <span className="font-medium">{unmappedKeys.join(', ')}</span>
          </p>
        )}
        <ol data-testid="artifact-beats" className="space-y-1">
          {chapters.map((c, i) => {
            const ordinal = typeof c.ordinal === 'number' ? c.ordinal : i + 1;
            const tension = tensionByIndex.get(ordinal);
            return (
              <li key={`${str(c.event_id)}-${i}`} className="flex gap-2 rounded bg-muted/40 px-2 py-1">
                <span className="font-mono text-[10px] text-muted-foreground/60">{ordinal}</span>
                <span className="min-w-0">
                  <span className="font-medium text-foreground">{str(c.title) || '—'}</span>
                  {/* An unassigned role is not cosmetic: that chapter gets a neutral tension band
                      and no structural intent, so name it rather than rendering a blank. */}
                  <span className={`ml-1 rounded px-1 text-[9px] uppercase ${c.beat_role ? 'bg-secondary text-muted-foreground' : 'bg-destructive/15 text-destructive'}`}>
                    {str(c.beat_role) || 'no beat'}
                  </span>
                  {tension != null && <span className="ml-1 text-[9px] text-accent">tension {tension}</span>}
                  {c.intent != null && str(c.intent) !== '' && (
                    <span className="ml-1 text-[10px] text-muted-foreground">— {str(c.intent)}</span>
                  )}
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    );
  }

  // motif_plan → the selected motifs. An EMPTY selection is called out rather than left blank:
  // every motif_plan in the live database was empty for months (the `auto` language sentinel
  // matched 0 of 147 rows), and a silent blank is precisely why nobody noticed.
  if (kind === 'motif_plan') {
    const motifs = arr(content, 'motifs').length ? arr(content, 'motifs') : arr(content, 'selected_motifs');
    const warning = str((content as Record<string, unknown> | null)?.warning ?? '');
    if (!motifs.length) {
      return (
        <p data-testid="artifact-motifs-empty" className="rounded bg-warning/15 px-2 py-1 text-[10px] text-foreground">
          {warning || 'No motifs selected — scenes will be planned with no motif layer.'}
        </p>
      );
    }
    return (
      <ul data-testid="artifact-motifs" className="space-y-1">
        {motifs.map((m, i) => (
          <li key={`${str(m.code)}-${i}`} className="rounded bg-muted/40 px-2 py-1">
            <span className="font-medium text-foreground">{str(m.name) || '—'}</span>
            {m.arc_role != null && str(m.arc_role) !== '' && (
              <span className="ml-1 rounded bg-accent/15 px-1 text-[9px] text-accent">{str(m.arc_role)}</span>
            )}
            {m.why != null && str(m.why) !== '' && (
              <span className="ml-1 text-[10px] text-muted-foreground">— {str(m.why)}</span>
            )}
          </li>
        ))}
      </ul>
    );
  }

  // world_plan → the proposed places/factions/concepts.
  if (kind === 'world_plan') {
    const entities = arr(content, 'entities');
    if (!entities.length) return <Empty label="No world entities in this plan yet." />;
    return (
      <ul data-testid="artifact-world" className="space-y-1">
        {entities.map((e, i) => (
          <li key={`${str(e.name)}-${i}`} className="rounded bg-muted/40 px-2 py-1">
            <span className="font-medium text-foreground">{str(e.name) || '—'}</span>
            {e.kind != null && <span className="ml-1 rounded bg-secondary px-1 text-[9px] uppercase text-muted-foreground">{str(e.kind)}</span>}
            {e.is_new === false && <span className="ml-1 text-[9px] text-muted-foreground/70">existing</span>}
            {e.summary != null && str(e.summary) !== '' && (
              <span className="ml-1 text-[10px] text-muted-foreground">— {str(e.summary)}</span>
            )}
          </li>
        ))}
      </ul>
    );
  }

  // char_arc_plan → who changes, how, and where they walk on.
  if (kind === 'char_arc_plan') {
    const arcs = arr(content, 'character_arcs');
    if (!arcs.length) return <Empty label="No character arcs in this plan yet." />;
    return (
      <ul data-testid="artifact-char-arcs" className="space-y-1">
        {arcs.map((a, i) => (
          <li key={`${str(a.name)}-${i}`} className="rounded bg-muted/40 px-2 py-1">
            <span className="font-medium text-foreground">{str(a.name) || '—'}</span>
            {a.role != null && <span className="ml-1 rounded bg-secondary px-1 text-[9px] uppercase text-muted-foreground">{str(a.role)}</span>}
            {a.introduce_at_chapter != null && (
              <span className="ml-1 text-[9px] text-accent">enters ch.{str(a.introduce_at_chapter)}</span>
            )}
            {a.arc != null && str(a.arc) !== '' && (
              <span className="ml-1 text-[10px] text-muted-foreground">— {str(a.arc)}</span>
            )}
          </li>
        ))}
      </ul>
    );
  }

  // scene_plan → chapter → scenes. Read-only: the list is NESTED, so the flat structured editor
  // cannot represent it (a dedicated nested editor is tracked separately).
  if (kind === 'scene_plan') {
    const chapters = arr(content, 'chapters');
    if (!chapters.length) return <Empty label="No scenes in this plan yet." />;
    return (
      <ol data-testid="artifact-scenes" className="space-y-1">
        {chapters.map((c, i) => {
          const chapter = (c.chapter ?? {}) as Record<string, unknown>;
          const scenes = Array.isArray(c.scenes) ? (c.scenes as Record<string, unknown>[]) : [];
          return (
            <li key={`${str(chapter.chapter_id)}-${i}`} className="rounded bg-muted/40 px-2 py-1">
              <span className="font-medium text-foreground">{str(chapter.title) || '—'}</span>
              <span className="ml-1 text-[9px] text-muted-foreground">{scenes.length} scene{scenes.length === 1 ? '' : 's'}</span>
              {/* A chapter the decomposer flagged is the one worth a human's attention. */}
              {c.warning != null && str(c.warning) !== '' && (
                <span className="ml-1 rounded bg-warning/20 px-1 text-[9px] text-foreground">{str(c.warning)}</span>
              )}
              <ul className="mt-0.5 space-y-0.5 pl-3">
                {scenes.map((s, si) => (
                  <li key={si} className="text-[10px] text-muted-foreground">
                    {str(s.title) || '—'}
                    {s.tension != null && <span className="ml-1 text-accent">t{str(s.tension)}</span>}
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ol>
    );
  }

  // Unknown kind → formatted JSON (still read-only; better a raw view than a blank).
  return (
    <pre data-testid="artifact-json" className="max-h-40 overflow-auto rounded bg-muted/40 p-1.5 font-mono text-[10px] leading-relaxed text-muted-foreground">
      {JSON.stringify(content, null, 2)}
    </pre>
  );
}

function Empty({ label }: { label: string }) {
  return <p className="text-[10px] text-muted-foreground">{label}</p>;
}
