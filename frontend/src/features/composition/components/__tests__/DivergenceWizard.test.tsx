import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const deriveWorkMock = vi.fn();
vi.mock('../../api', () => ({
  compositionApi: { deriveWork: (...a: unknown[]) => deriveWorkMock(...a) },
}));
// Step bodies fetch chapters/entities — stub the data layers so the view renders.
vi.mock('../../../books/api', () => ({
  booksApi: { listChapters: vi.fn().mockResolvedValue({ items: [], total: 0 }) },
}));
vi.mock('../../../knowledge/api', () => ({
  knowledgeApi: { listEntities: vi.fn().mockResolvedValue({ entities: [], total: 0 }) },
}));

import { DivergenceWizard } from '../DivergenceWizard';
import type { Work } from '../../types';

const sourceWork: Work = {
  project_id: 'src-proj', user_id: 'u', book_id: 'book-1',
  active_template_id: null, status: 'active', settings: {}, version: 1,
};

function renderWizard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <Wrapper>
      <DivergenceWizard open onOpenChange={() => {}} sourceWork={sourceWork} token="tok" />
    </Wrapper>,
  );
}

beforeEach(() => deriveWorkMock.mockReset());

describe('DivergenceWizard (DPS1 — 4-step view)', () => {
  it('renders the 4-step rail and all 4 step bodies stay MOUNTED (no conditional unmount)', () => {
    renderWizard();
    expect(screen.getByTestId('divergence-rail')).toBeTruthy();
    // All four step bodies are present in the DOM even though only step 1 is visible
    // (internal branching via CSS hidden — NOT a ternary that unmounts the others).
    expect(screen.getByTestId('divergence-step-1')).toBeTruthy();
    expect(screen.getByTestId('divergence-step-2')).toBeTruthy();
    expect(screen.getByTestId('divergence-step-3')).toBeTruthy();
    expect(screen.getByTestId('divergence-step-4')).toBeTruthy();
  });

  it('Next advances through the steps to the Spawn submit', () => {
    renderWizard();
    expect(screen.getByTestId('divergence-next')).toBeTruthy();
    fireEvent.click(screen.getByTestId('divergence-next')); // 1→2
    fireEvent.click(screen.getByTestId('divergence-next')); // 2→3
    fireEvent.click(screen.getByTestId('divergence-next')); // 3→4
    // step 4 → submit button appears
    expect(screen.getByTestId('divergence-submit')).toBeTruthy();
  });

  it('picking the character-transform type + naming + Spawn submits a derive', async () => {
    deriveWorkMock.mockResolvedValue({ project_id: 'deriv', source_work_id: 'sw' });
    renderWizard();
    fireEvent.click(screen.getByTestId('divergence-next')); // →2
    fireEvent.click(screen.getByTestId('divergence-type-character_transform'));
    fireEvent.click(screen.getByTestId('divergence-next')); // →3
    fireEvent.click(screen.getByTestId('divergence-next')); // →4
    fireEvent.change(screen.getByTestId('divergence-name'), { target: { value: 'Genderbend AU' } });
    fireEvent.click(screen.getByTestId('divergence-submit'));
    // derive.mutate defers the mutationFn to a microtask — await the call.
    await waitFor(() =>
      expect(deriveWorkMock).toHaveBeenCalledWith('src-proj', expect.objectContaining({
        divergence: expect.objectContaining({ taxonomy: 'character_transform' }),
      }), 'tok'),
    );
  });
});
