// Container for the workflow rack (M5): wires the useWorkflows controller to the presentational
// WorkflowRack. Keeps the "components render only, hooks own logic" separation.
import { useWorkflows } from '../hooks/useWorkflows';
import { WorkflowRack } from './WorkflowRack';

export interface WorkflowRackPanelProps {
  bookId?: string;
  onPick?: (slug: string) => void;
}

export function WorkflowRackPanel({ bookId, onPick }: WorkflowRackPanelProps) {
  const { workflows, loading, error } = useWorkflows(bookId);
  return <WorkflowRack workflows={workflows} loading={loading} error={error} onPick={onPick} />;
}
