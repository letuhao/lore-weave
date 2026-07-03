import { useContextHistory } from '../hooks/useContextHistory';
import { ContextHistoryChart } from './ContextHistoryChart';

// W1-residual — the History tab body. A thin controller→view seam: mounts the
// useContextHistory hook (fetch/state) and hands its output to the pure
// ContextHistoryChart. Split out of ContextBreakdownPanel so the panel (and its
// tests) stay decoupled from the auth/session providers the hook depends on —
// mounted only while the History tab is active.
export function ContextHistoryTab() {
  const { points, loading, error } = useContextHistory(true);
  return <ContextHistoryChart points={points} loading={loading} error={error} />;
}
