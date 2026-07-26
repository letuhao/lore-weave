// #20_agent_mode.md — shared status → Tailwind class mapping for the 7 real
// AuthoringRunStatus values (D header: "Status badge matches the 7 real states
// with correct color coding"). Kept as a tiny pure helper so RunsListView and
// RunHeader render the SAME palette.
import type { AuthoringRunStatus } from '@/features/composition/authoringRuns/types';

export function runStatusBadgeClass(status: AuthoringRunStatus): string {
  switch (status) {
    case 'draft': return 'bg-secondary text-muted-foreground';
    case 'gated': return 'bg-info/10 text-info';
    case 'running': return 'bg-success/10 text-success';
    case 'paused': return 'bg-warning/10 text-warning';
    case 'failed': return 'bg-destructive/10 text-destructive';
    case 'report_ready': return 'bg-accent/10 text-accent-foreground';
    case 'closed': return 'bg-secondary text-muted-foreground';
    default: return 'bg-secondary text-muted-foreground';
  }
}
