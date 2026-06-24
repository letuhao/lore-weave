import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { JobProgress } from '../JobProgress';

describe('JobProgress (null-safe)', () => {
  it('renders nothing when both progress and detail_status are absent', () => {
    const { container } = render(<JobProgress progress={null} detailStatus={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows done/total when progress is present', () => {
    render(<JobProgress progress={{ done: 3, total: 10 }} detailStatus={null} />);
    expect(screen.getByText('3/10')).toBeInTheDocument();
  });

  it('shows detail_status passthrough even without a progress bar', () => {
    render(<JobProgress progress={null} detailStatus="summarizing" />);
    expect(screen.getByText('summarizing')).toBeInTheDocument();
  });
});
