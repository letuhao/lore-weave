import { useMemo } from 'react';
import type { SystemAttribute, SystemGenre } from '../types';
import { FieldTypeBadge } from './FieldTypeBadge';

export interface CellRef {
  code: string;
  genreId: string;
}

type Props = {
  activeGenres: SystemGenre[];
  attributes: SystemAttribute[]; // already merged across this kind's genres
  selectedCell: CellRef | null;
  onSelectCell: (cell: CellRef) => void;
};

// G-C1 — attributes for one kind across its active genres. A code present in 2+ genre
// columns is a keep-both conflict (amber). System tier has no source_ref, so the cell
// renders the FieldTypeBadge only (no TierChip).
export function AttributeMatrix({ activeGenres, attributes, selectedCell, onSelectCell }: Props) {
  const { codes, byCodeGenre, spanByCode } = useMemo(() => {
    const byCodeGenre = new Map<string, Map<string, SystemAttribute>>();
    for (const a of attributes) {
      if (!byCodeGenre.has(a.code)) byCodeGenre.set(a.code, new Map());
      byCodeGenre.get(a.code)!.set(a.genre_id, a);
    }
    const activeIds = new Set(activeGenres.map((g) => g.genre_id));
    const spanByCode = new Map<string, number>();
    for (const [code, m] of byCodeGenre) {
      spanByCode.set(code, [...m.keys()].filter((gid) => activeIds.has(gid)).length);
    }
    const codes = [...byCodeGenre.keys()].sort();
    return { codes, byCodeGenre, spanByCode };
  }, [attributes, activeGenres]);

  if (activeGenres.length === 0) {
    return (
      <p className="rounded-lg border border-border bg-card p-6 text-center text-xs text-muted-foreground">
        No active genres. Create a System genre first.
      </p>
    );
  }

  return (
    <div className="overflow-auto rounded-lg border border-border bg-card">
      <table className="w-full text-left text-[13px]">
        <thead className="border-b border-border bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-semibold">Attribute</th>
            {activeGenres.map((g) => (
              <th
                key={g.genre_id}
                className="px-3 py-2 font-semibold"
                style={g.color ? { color: g.color } : undefined}
              >
                {g.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {codes.length === 0 && (
            <tr>
              <td
                colSpan={activeGenres.length + 1}
                className="px-3 py-4 text-center text-muted-foreground"
              >
                No attributes for this kind.
              </td>
            </tr>
          )}
          {codes.map((code) => {
            const conflict = (spanByCode.get(code) ?? 0) > 1;
            return (
              <tr key={code} className={conflict ? 'bg-amber-50 dark:bg-amber-950/30' : ''}>
                <td className="px-3 py-2 align-top">
                  <div className="font-mono font-semibold text-foreground">{code}</div>
                  {conflict && (
                    <div className="text-[10px] text-amber-700 dark:text-amber-400">
                      ⚠ in {spanByCode.get(code)} genres
                    </div>
                  )}
                </td>
                {activeGenres.map((g) => {
                  const attr = byCodeGenre.get(code)?.get(g.genre_id);
                  if (!attr) {
                    return (
                      <td key={g.genre_id} className="px-3 py-2 text-muted-foreground/50">
                        —
                      </td>
                    );
                  }
                  const sel =
                    selectedCell?.code === code && selectedCell?.genreId === g.genre_id;
                  return (
                    <td key={g.genre_id} className="px-2 py-1.5 align-top">
                      <button
                        type="button"
                        onClick={() => onSelectCell({ code, genreId: g.genre_id })}
                        data-testid={`matrix-cell-${code}-${g.code}`}
                        className={`flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left transition-colors ${
                          sel ? 'ring-1 ring-primary' : 'hover:bg-secondary'
                        }`}
                      >
                        <FieldTypeBadge fieldType={attr.field_type} />
                      </button>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
