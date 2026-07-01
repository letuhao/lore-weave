// #06a Quick Open (⌘P) — jump to a manuscript location (arc / chapter / scene) from anywhere.
// Server-backed via the SHARED useManuscriptJump (the same layer the sidebar jump box uses — not
// a second query path). Selecting a hit resolves it (v1: switch to Manuscript + highlight; dock
// open + tree reveal land with #03 / the reveal-in-tree debt).
import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useManuscriptJump } from '../manuscript/useManuscriptJump';
import type { JumpResult } from '../manuscript/types';
import { StudioPaletteShell } from './StudioPaletteShell';
import type { PaletteEntry } from './types';

interface Props {
  open: boolean;
  onClose: () => void;
  bookId: string;
  token: string | null;
  onResolve: (result: JumpResult) => void;
}

export function QuickOpen({ open, onClose, bookId, token, onResolve }: Props) {
  const { t } = useTranslation('studio');
  const jump = useManuscriptJump(bookId, token);

  // Clear the query each time the palette opens (fresh jump).
  useEffect(() => { if (open) jump.setQuery(''); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const entries: PaletteEntry[] = useMemo(() => jump.results.map((r) => ({
    id: r.id,
    label: r.title,
    sublabel: r.path.length ? r.path.join(' › ') : undefined,
    icon: <span className={cn('h-1.5 w-1.5 rounded-full',
      r.kind === 'arc' ? 'bg-accent' : r.kind === 'scene' ? 'bg-border' : 'bg-muted-foreground/60')} />,
    meta: (
      <>
        {r.number != null && <span className="font-mono text-[10px] text-muted-foreground/50">{String(r.number).padStart(4, '0')}</span>}
        {r.status && (
          <span className={cn('font-mono text-[9px] uppercase',
            r.status === 'done' ? 'text-success'
              : r.status === 'drafting' ? 'text-warning'
              : 'text-muted-foreground/60')}>
            {r.status}
          </span>
        )}
      </>
    ),
  })), [jump.results]);

  const onSelect = (e: PaletteEntry) => {
    const r = jump.results.find((x) => x.id === e.id);
    if (r) { onResolve(r); onClose(); }
  };

  return (
    <StudioPaletteShell
      open={open}
      onClose={onClose}
      query={jump.query}
      onQueryChange={jump.setQuery}
      placeholder={t('palette.quickOpenPlaceholder', { defaultValue: 'Go to chapter, scene, arc…' })}
      entries={entries}
      onSelect={onSelect}
      searching={jump.searching}
      emptyText={jump.active
        ? t('manuscript.noMatch', { defaultValue: 'No matches.' })
        : t('palette.quickOpenHint', { defaultValue: 'Type to search chapters, scenes & arcs' })}
      testid="quick-open"
    />
  );
}
