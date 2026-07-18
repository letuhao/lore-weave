// Presentational workflow rack (M5) — render-only, all data via props (MVC: no logic here).
// The container (WorkflowRackPanel) supplies data from useWorkflows.
import type { WorkflowMeta, WorkflowTier } from '../types';

const TIER_LABEL: Record<WorkflowTier, string> = {
  system: 'Built-in',
  user: 'Yours',
  book: 'This book',
};
const TIER_ORDER: WorkflowTier[] = ['system', 'user', 'book'];

export interface WorkflowRackProps {
  workflows: WorkflowMeta[];
  loading: boolean;
  error: string | null;
  onPick?: (slug: string) => void;
}

export function WorkflowRack({ workflows, loading, error, onPick }: WorkflowRackProps) {
  if (loading) {
    return (
      <div className="p-4 text-sm text-muted-foreground" data-testid="workflow-rack-loading">
        Loading recipes…
      </div>
    );
  }
  if (error) {
    return (
      <div className="p-4 text-sm text-destructive" role="alert" data-testid="workflow-rack-error">
        {error}
      </div>
    );
  }
  if (workflows.length === 0) {
    return (
      <div className="p-4 text-sm text-muted-foreground" data-testid="workflow-rack-empty">
        No recipes available yet.
      </div>
    );
  }

  const byTier = TIER_ORDER.map((tier) => ({
    tier,
    items: workflows.filter((w) => w.tier === tier),
  })).filter((g) => g.items.length > 0);

  return (
    <div className="flex flex-col gap-4 p-3" data-testid="workflow-rack">
      {byTier.map(({ tier, items }) => (
        <section key={tier} aria-label={TIER_LABEL[tier]}>
          <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {TIER_LABEL[tier]}
          </h3>
          <ul className="flex flex-col gap-1.5">
            {items.map((w) => (
              <li key={w.slug}>
                <button
                  type="button"
                  onClick={() => onPick?.(w.slug)}
                  className="w-full rounded-md border border-border bg-card px-3 py-2 text-left transition-colors hover:border-primary hover:bg-accent focus:outline-none focus:ring-2 focus:ring-primary"
                  data-testid={`workflow-card-${w.slug}`}
                >
                  <div className="text-sm font-medium text-foreground">{w.title}</div>
                  <div className="text-xs text-muted-foreground">{w.description}</div>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
