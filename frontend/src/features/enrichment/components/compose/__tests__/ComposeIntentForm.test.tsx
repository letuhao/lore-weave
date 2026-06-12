import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ComposeIntentForm } from '../ComposeIntentForm';

function renderForm(over: Partial<React.ComponentProps<typeof ComposeIntentForm>> = {}) {
  const props = {
    intentText: '',
    onIntentChange: vi.fn(),
    onResolve: vi.fn(),
    resolving: false,
    canResolve: true,
    rationale: '',
    resolvedTechnique: null,
    dimensions: [],
    ...over,
  };
  render(<ComposeIntentForm {...props} />);
  return props;
}

describe('ComposeIntentForm', () => {
  it('reports intent text changes', () => {
    const props = renderForm();
    fireEvent.change(screen.getByTestId('compose-intent-text'), { target: { value: 'the kings advisor' } });
    expect(props.onIntentChange).toHaveBeenCalledWith('the kings advisor');
  });

  it('Resolve triggers onResolve when enabled', () => {
    const props = renderForm({ canResolve: true });
    fireEvent.click(screen.getByTestId('compose-intent-resolve'));
    expect(props.onResolve).toHaveBeenCalledTimes(1);
  });

  it('Resolve is disabled when canResolve is false or while resolving', () => {
    renderForm({ canResolve: false });
    expect(screen.getByTestId('compose-intent-resolve')).toBeDisabled();
  });

  it('shows the rationale + technique after a resolve', () => {
    renderForm({ rationale: 'matches an existing entity', resolvedTechnique: 'retrieval' });
    const r = screen.getByTestId('compose-intent-rationale');
    expect(r).toHaveTextContent('matches an existing entity');
    expect(r).toHaveTextContent('retrieval');
  });

  it('hides the rationale block when empty', () => {
    renderForm({ rationale: '' });
    expect(screen.queryByTestId('compose-intent-rationale')).toBeNull();
  });

  it('shows the suggested dimensions when resolved', () => {
    renderForm({ rationale: 'r', dimensions: ['历史', '能力'] });
    const dims = screen.getByTestId('compose-intent-dimensions');
    expect(dims).toHaveTextContent('历史');
    expect(dims).toHaveTextContent('能力');
  });
});
