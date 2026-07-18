import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// S-10 O3 — the panel now uses the studio host (Jobs/Generation launch the jobs-list panel) and
// renders the real Issues feed. Mock both so this stays a thin render/routing test.
const openPanel = vi.hoisted(() => vi.fn());
vi.mock('../../host/StudioHostProvider', () => ({
  useStudioHost: () => ({ bookId: 'b1', openPanel }),
}));
vi.mock('../StudioIssuesFeed', () => ({
  StudioIssuesFeed: () => <div data-testid="studio-issues-feed-stub" />,
}));

import { StudioBottomPanel } from '../StudioBottomPanel';

describe('StudioBottomPanel', () => {
  it('defaults to Jobs, which launches the jobs-list panel', () => {
    render(<StudioBottomPanel onClose={vi.fn()} />);
    const launch = screen.getByTestId('studio-bottom-open-jobs-jobs');
    fireEvent.click(launch);
    expect(openPanel).toHaveBeenCalledWith('jobs-list', { focus: true });
  });

  it('switches to the Issues tab and renders the real problems feed', () => {
    render(<StudioBottomPanel onClose={vi.fn()} />);
    expect(screen.queryByTestId('studio-issues-feed-stub')).toBeNull();
    fireEvent.click(screen.getByText('bottom.issues'));
    expect(screen.getByTestId('studio-issues-feed-stub')).toBeInTheDocument();
  });

  it('generation tab also launches the jobs feed (no dead stub)', () => {
    render(<StudioBottomPanel onClose={vi.fn()} />);
    fireEvent.click(screen.getByText('bottom.generation'));
    expect(screen.getByTestId('studio-bottom-open-jobs-generation')).toBeInTheDocument();
  });

  it('fires onClose from the collapse control', () => {
    const onClose = vi.fn();
    render(<StudioBottomPanel onClose={onClose} />);
    fireEvent.click(screen.getByTitle('bottom.collapse'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
