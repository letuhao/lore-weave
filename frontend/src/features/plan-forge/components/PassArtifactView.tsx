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
  // cast_plan → the roster: name · role · trait.
  if (kind === 'cast_plan') {
    const roster = arr(content, 'cast').length ? arr(content, 'cast') : arr(content, 'roster');
    if (!roster.length) return <Empty label="No cast members in this plan yet." />;
    return (
      <ul data-testid="artifact-cast" className="space-y-1">
        {roster.map((m, i) => (
          <li key={`${str(m.name)}-${i}`} className="rounded bg-muted/40 px-2 py-1">
            <span className="font-medium text-foreground">{str(m.name) || '—'}</span>
            {m.role != null && <span className="ml-1 rounded bg-secondary px-1 text-[9px] uppercase text-muted-foreground">{str(m.role)}</span>}
            {m.trait != null && <span className="ml-1 text-[10px] text-muted-foreground">— {str(m.trait)}</span>}
          </li>
        ))}
      </ul>
    );
  }

  // beat_plan → the ordered beats: beat · tension · one-line.
  if (kind === 'beat_plan') {
    const beats = arr(content, 'beats');
    if (!beats.length) return <Empty label="No beats in this plan yet." />;
    return (
      <ol data-testid="artifact-beats" className="space-y-1">
        {beats.map((b, i) => (
          <li key={i} className="flex gap-2 rounded bg-muted/40 px-2 py-1">
            <span className="font-mono text-[10px] text-muted-foreground/60">{i + 1}</span>
            <span className="min-w-0">
              <span className="font-medium text-foreground">{str(b.beat) || str(b.name) || str(b.role) || '—'}</span>
              {b.tension != null && <span className="ml-1 text-[9px] text-accent">tension {str(b.tension)}</span>}
              {(b.synopsis != null || b.summary != null) && (
                <span className="ml-1 text-[10px] text-muted-foreground">— {str(b.synopsis ?? b.summary)}</span>
              )}
            </span>
          </li>
        ))}
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
