import { describe, expect, it } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GlobalOperationProgress } from '../GlobalOperationProgress';
import { beginOperation } from '@/lib/operationTracker';

function renderWithClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <GlobalOperationProgress />
    </QueryClientProvider>,
  );
}

describe('GlobalOperationProgress', () => {
  it('stays hidden while there are no active operations', () => {
    renderWithClient();
    expect(screen.queryByTestId('global-operation-progress')).not.toBeInTheDocument();
  });

  it('announces direct API work and clears it when the request ends', () => {
    renderWithClient();
    let end = () => {};
    act(() => {
      end = beginOperation('write');
    });
    expect(screen.getByTestId('global-operation-progress')).toHaveAttribute(
      'aria-label',
      'Сохраняем изменения…',
    );
    act(() => end());
    expect(screen.queryByTestId('global-operation-progress')).not.toBeInTheDocument();
  });
});
