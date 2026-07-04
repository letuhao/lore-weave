import { cn } from '@/lib/utils';
import type { ContextTraceFrame } from '../types';
import { CATEGORY_COLORS, computeBreakdown } from '../components/ContextBreakdownPanel';
import { kfmt } from './inspectorMath';

// The allocation map — where the compiled tokens went, per category. Reuses the
// SAME computeBreakdown math + CATEGORY_COLORS as the header meter (single source
// of truth, no fork): a segmented bar (width ∝ tokens) + a legend row per non-zero
// category. Pure render.

/** Humanize a category key for display: `frontend_tool_schemas` → `frontend tool schemas`. */
function catLabel(key: string): string {
  return key.replace(/_/g, ' ');
}

export function AllocationMap({ frame }: { frame: ContextTraceFrame }) {
  const { rows } = computeBreakdown(frame);
  const total = rows.reduce((a, r) => a + r.tokens, 0);

  return (
    <div className="rounded-xl border border-border bg-card p-4" data-testid="inspector-allocation">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Allocation map — where the tokens went ({kfmt(total)})
        </div>
      </div>
      {total > 0 ? (
        <>
          <div className="flex h-9 w-full overflow-hidden rounded-lg border border-border">
            {rows.map((r) => (
              <div
                key={r.key}
                className={cn('transition-[width] duration-500', CATEGORY_COLORS[r.key])}
                style={{ width: `${(r.tokens / total) * 100}%` }}
                title={`${catLabel(r.key)} · ${r.tokens.toLocaleString()} tok · ${Math.round((r.tokens / total) * 100)}%`}
                data-alloc-seg={r.key}
              />
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
            {rows.map((r) => (
              <div key={r.key} className="flex items-center gap-1.5 text-[11px]">
                <span className={cn('h-2.5 w-2.5 rounded-[3px]', CATEGORY_COLORS[r.key])} />
                <span className="text-muted-foreground">{catLabel(r.key)}</span>
                <span className="font-mono text-foreground">{r.tokens.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="py-4 text-center text-xs text-muted-foreground">
          no per-category allocation recorded for this turn
        </div>
      )}
    </div>
  );
}
