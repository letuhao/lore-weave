import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WorkspaceShell } from '../WorkspaceShell';
import { useLiveStream } from '../../../context/LiveStateContext';
import { useWorkspaceLayout } from '../../../context/WorkspaceLayoutContext';

vi.mock('../../../hooks/useCompositionStream', () => ({
  useCompositionStream: () => ({ ghost: '', streaming: false, start: vi.fn(), stop: vi.fn(), clearGhost: vi.fn() }),
}));

function Probe() {
  const stream = useLiveStream();
  const ws = useWorkspaceLayout();
  return <div data-testid="probe">{`${typeof stream.start}:${ws.enabled}`}</div>;
}

describe('WorkspaceShell (T5.4 M1)', () => {
  it('renders children and provides both the live-state and layout contexts', () => {
    render(
      <WorkspaceShell token="t" bookId="b1">
        <div data-testid="child">studio</div>
        <Probe />
      </WorkspaceShell>,
    );
    expect(screen.getByTestId('child')).toHaveTextContent('studio');
    // a descendant can read the hoisted stream + the layout (flag default OFF)
    expect(screen.getByTestId('probe')).toHaveTextContent('function:false');
  });
});
