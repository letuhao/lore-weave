import { useMemo, useState } from 'react';

import { useDebouncedValue } from '@/features/knowledge/hooks/useDebouncedValue';
import { useJobsList } from './useJobsList';
import { useJobsHistory } from './useJobsHistory';
import { useJobsSummary } from './useJobsSummary';
import type { JobStatus } from '../types';

/** Quick-filter = which summary card is selected. 'active' shows the live Active
 *  table + all History; a terminal value hides Active and filters History to it. */
export type QuickFilter = 'active' | 'completed' | 'failed' | 'cancelled';

const TERMINAL_QUICK: readonly QuickFilter[] = ['completed', 'failed', 'cancelled'];

/** Dashboard controller (CLAUDE.md MVC: owns ALL list logic + state; views render).
 *  Wires the three data sources behind one filter surface:
 *   - Active table  → live keyset list (bucket=active), unpaginated, SSE-updated.
 *   - History table → offset+total list (bucket=history), ORDER BY created_at.
 *   - Summary cards → owner-scoped status counts (also the quick-filter selector).
 *  `kind` + debounced `q` (widened search) apply to BOTH tables. */
export function useJobsDashboard() {
  const [quick, setQuick] = useState<QuickFilter>('active');
  const [kind, setKind] = useState('');
  const [rawQ, setRawQ] = useState('');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(50);

  const q = useDebouncedValue(rawQ.trim(), 300);
  const showActive = quick === 'active';
  const historyStatus = TERMINAL_QUICK.includes(quick) ? (quick as JobStatus) : undefined;

  // Common filter slice shared by both tables (kind + widened search).
  const common = useMemo(() => ({ kind: kind || undefined, q: q || undefined }), [kind, q]);

  const summary = useJobsSummary();
  const active = useJobsList({ ...common, bucket: 'active' });
  const history = useJobsHistory({ ...common, status: historyStatus }, page, pageSize);

  // Changing any filter resets History to page 0 (else an out-of-range offset).
  const selectQuick = (next: QuickFilter) => {
    setQuick(next);
    setPage(0);
  };
  const changeKind = (next: string) => {
    setKind(next);
    setPage(0);
  };
  const changeQ = (next: string) => {
    setRawQ(next);
    setPage(0);
  };
  const changePageSize = (next: number) => {
    setPageSize(next);
    setPage(0);
  };

  return {
    quick,
    selectQuick,
    kind,
    changeKind,
    rawQ,
    changeQ,
    showActive,
    summary,
    active,
    history,
    page,
    setPage,
    pageSize,
    changePageSize,
  };
}
