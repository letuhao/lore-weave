import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { FairnessBanner } from '../FairnessBanner';
import type { JobFairness } from '../../types';

const mockUse = vi.fn();
vi.mock('../../hooks/useJobsFairness', () => ({
  useJobsFairness: () => mockUse(),
}));

function setData(data: JobFairness | undefined) {
  mockUse.mockReturnValue({ data });
}

describe('FairnessBanner', () => {
  it('renders nothing when P5 is disabled', () => {
    setData({ enabled: false, owner_cap: 5, lanes: [] });
    const { container } = render(<FairnessBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when enabled but no active lanes (common case)', () => {
    setData({ enabled: true, owner_cap: 5, lanes: [] });
    const { container } = render(<FairnessBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders active lanes; shows queued only when > 0', () => {
    setData({
      enabled: true,
      owner_cap: 2,
      lanes: [
        { lane: 'translation', running: 2, queued: 5, cap: 2 },
        { lane: 'knowledge', running: 1, queued: 0, cap: 2 },
      ],
    });
    render(<FairnessBanner />);
    expect(screen.getByText('fairness.title')).toBeInTheDocument();
    expect(screen.getByText('fairness.lane.translation')).toBeInTheDocument();
    expect(screen.getByText('fairness.lane.knowledge')).toBeInTheDocument();
    // translation has queued>0 → the queued span renders; knowledge (queued=0) does not,
    // so exactly one queued node exists.
    expect(screen.getAllByText('fairness.queued')).toHaveLength(1);
  });
});
