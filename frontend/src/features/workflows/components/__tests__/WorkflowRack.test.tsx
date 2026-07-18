import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { WorkflowRack } from '../WorkflowRack';
import type { WorkflowMeta } from '../../types';

const wf = (slug: string, tier: WorkflowMeta['tier'], title = slug): WorkflowMeta => ({
  slug,
  title,
  description: `desc for ${slug}`,
  tier,
  status: 'published',
});

describe('WorkflowRack (M5 — presentational)', () => {
  it('renders each workflow as a pickable card, grouped by tier', () => {
    const workflows = [
      wf('vision-to-book', 'system', 'Build a book'),
      wf('canon-check', 'system', 'Check for contradictions'),
      wf('my-recipe', 'user', 'My recipe'),
    ];
    render(<WorkflowRack workflows={workflows} loading={false} error={null} />);

    // every workflow surfaces as its own card
    expect(screen.getByTestId('workflow-card-vision-to-book')).toHaveTextContent('Build a book');
    expect(screen.getByTestId('workflow-card-canon-check')).toBeInTheDocument();
    expect(screen.getByTestId('workflow-card-my-recipe')).toBeInTheDocument();

    // grouped: a "Built-in" section and a "Yours" section both present
    expect(screen.getByRole('region', { name: 'Built-in' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Yours' })).toBeInTheDocument();
  });

  it('fires onPick with the slug when a card is clicked', () => {
    const onPick = vi.fn();
    render(
      <WorkflowRack workflows={[wf('canon-check', 'system')]} loading={false} error={null} onPick={onPick} />,
    );
    fireEvent.click(screen.getByTestId('workflow-card-canon-check'));
    expect(onPick).toHaveBeenCalledWith('canon-check');
  });

  it('shows loading, error, and empty states distinctly', () => {
    const { rerender } = render(<WorkflowRack workflows={[]} loading error={null} />);
    expect(screen.getByTestId('workflow-rack-loading')).toBeInTheDocument();

    rerender(<WorkflowRack workflows={[]} loading={false} error="boom" />);
    expect(screen.getByTestId('workflow-rack-error')).toHaveTextContent('boom');

    rerender(<WorkflowRack workflows={[]} loading={false} error={null} />);
    expect(screen.getByTestId('workflow-rack-empty')).toBeInTheDocument();
  });

  it('does not render an empty tier section (no orphan headings)', () => {
    render(<WorkflowRack workflows={[wf('a', 'system')]} loading={false} error={null} />);
    expect(screen.queryByRole('region', { name: 'Yours' })).toBeNull();
    expect(screen.queryByRole('region', { name: 'This book' })).toBeNull();
  });
});
