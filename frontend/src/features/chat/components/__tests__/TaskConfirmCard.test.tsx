import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// ext-tasks (T1c(3)) — the durable-gate confirm card. Confirm resumes the suspended
// run with an accept outcome (chat-service then drives the domain's provide-input
// tool → real write); Dismiss cancels. Nothing writes until Confirm.

const submitToolResult = vi.fn().mockResolvedValue('');
vi.mock('../../providers', () => ({ useChatStream: () => ({ submitToolResult }) }));

import { TaskConfirmCard } from '../TaskConfirmCard';
import type { ToolCallRecord } from '../../types';

function record(task: ToolCallRecord['task']): ToolCallRecord {
  return {
    tool: 'composition_create_derivative', ok: true, pending: true,
    runId: 'r1', toolCallId: 'c1', task,
  };
}

describe('TaskConfirmCard — durable-gate confirm', () => {
  beforeEach(() => submitToolResult.mockClear());

  it('renders the inputRequests title', () => {
    render(<TaskConfirmCard record={record({
      taskId: 'task_z', status: 'input_required',
      inputRequests: { title: 'Spawn a dị bản “AU”?' },
    })} />);
    expect(screen.getByTestId('task-confirm-card')).toBeInTheDocument();
    expect(screen.getByText('Spawn a dị bản “AU”?')).toBeInTheDocument();
  });

  it('Confirm resumes the run with an accept outcome (action_done)', async () => {
    render(<TaskConfirmCard record={record({
      taskId: 'task_z', status: 'input_required', inputRequests: { title: 'Confirm?' },
    })} />);
    fireEvent.click(screen.getByTestId('task-confirm'));
    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'action_done'));
  });

  it('Dismiss resumes with cancelled (no accept)', async () => {
    render(<TaskConfirmCard record={record({
      taskId: 'task_z', status: 'input_required', inputRequests: { title: 'Confirm?' },
    })} />);
    fireEvent.click(screen.getByTestId('task-dismiss'));
    await waitFor(() =>
      expect(submitToolResult).toHaveBeenCalledWith('r1', 'c1', 'cancelled'));
  });

  it('does not double-submit once a decision was taken', async () => {
    render(<TaskConfirmCard record={record({
      taskId: 'task_z', status: 'input_required', inputRequests: { title: 'Confirm?' },
    })} />);
    fireEvent.click(screen.getByTestId('task-confirm'));
    await waitFor(() => expect(submitToolResult).toHaveBeenCalledTimes(1));
    // the buttons are gone after a decision → no second submit possible
    expect(screen.queryByTestId('task-confirm')).not.toBeInTheDocument();
  });
});
