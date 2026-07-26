import { useContextHistory } from '../hooks/useContextHistory';
import { ContextHistoryChart } from './ContextHistoryChart';

interface Props {
  /** True while the History tab is the active one. Kept MOUNTED even when
   *  inactive (the panel CSS-hides it) so toggling back doesn't remount +
   *  refetch from zero; `active` gates the hook's fetch to when the tab is
   *  actually open. */
  active: boolean;
}

// W1-residual — the History tab body. A thin controller→view seam: mounts the
// useContextHistory hook (fetch/state) and hands its output to the pure
// ContextHistoryChart. Split out of ContextBreakdownPanel so the panel (and its
// tests) stay decoupled from the auth/session providers the hook depends on.
export function ContextHistoryTab({ active }: Props) {
  const { points, loading, error } = useContextHistory(active);
  return <ContextHistoryChart points={points} loading={loading} error={error} />;
}
