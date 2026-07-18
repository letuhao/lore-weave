import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { GlossaryEntitySummary } from '../../types';

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const hookMocks = vi.hoisted(() => ({
  promote: vi.fn(),
  reject: vi.fn(),
  state: { items: [] as unknown[], total: 0, isLoading: false, error: null as unknown },
}));
vi.mock('../../hooks/useAiSuggestions', () => ({
  useAiSuggestions: () => ({
    items: hookMocks.state.items,
    total: hookMocks.state.total,
    isLoading: hookMocks.state.isLoading,
    error: hookMocks.state.error,
    refetch: vi.fn(),
    promote: hookMocks.promote,
    reject: hookMocks.reject,
  }),
}));

import { AiSuggestionsPanel } from '../AiSuggestionsPanel';

const ent = (id: string, name: string): GlossaryEntitySummary => ({
  entity_id: id,
  book_id: 'book-1',
  kind_id: 'k1',
  kind: { code: 'character', name: 'Character' } as GlossaryEntitySummary['kind'],
  display_name: name,
  display_name_translation: null,
  status: 'draft',
  tags: ['ai-suggested'],
  chapter_link_count: 5,
  translation_count: 0,
  evidence_count: 2,
  created_at: '2026-06-06T00:00:00Z',
  updated_at: '2026-06-06T00:00:00Z',
});

function renderPanel() {
  return render(<AiSuggestionsPanel bookId="book-1" onClose={vi.fn()} />);
}

beforeEach(() => {
  hookMocks.promote.mockReset().mockResolvedValue(undefined);
  hookMocks.reject.mockReset().mockResolvedValue(undefined);
  Object.values(toastMocks).forEach((m) => m.mockReset());
  hookMocks.state = { items: [ent('e1', '姜子牙'), ent('e2', '哪吒')], total: 2, isLoading: false, error: null };
});

describe('AiSuggestionsPanel', () => {
  it('renders the ai-suggested queue', () => {
    renderPanel();
    expect(screen.getByText('姜子牙')).toBeInTheDocument();
    expect(screen.getByText('哪吒')).toBeInTheDocument();
    expect(screen.getByText('ai_suggestions.title')).toBeInTheDocument();
  });

  it('promotes an entity and toasts', async () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('ai-promote-e1'));
    await waitFor(() => expect(hookMocks.promote).toHaveBeenCalledTimes(1));
    expect(hookMocks.promote.mock.calls[0][0].entity_id).toBe('e1');
    expect(toastMocks.success).toHaveBeenCalledWith('ai_suggestions.toast_promoted');
  });

  it('rejects an entity and toasts', async () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('ai-reject-e2'));
    await waitFor(() => expect(hookMocks.reject).toHaveBeenCalledTimes(1));
    expect(hookMocks.reject.mock.calls[0][0].entity_id).toBe('e2');
    expect(toastMocks.success).toHaveBeenCalledWith('ai_suggestions.toast_rejected');
  });

  it('shows the empty state when there is nothing to review', () => {
    hookMocks.state = { items: [], total: 0, isLoading: false, error: null };
    renderPanel();
    expect(screen.getByText('ai_suggestions.empty_title')).toBeInTheDocument();
  });

  it('shows a scope_label badge only for entities that have one set', () => {
    hookMocks.state = {
      items: [{ ...ent('e1', '姜子牙'), scope_label: 'World A' }, ent('e2', '哪吒')],
      total: 2,
      isLoading: false,
      error: null,
    };
    renderPanel();
    expect(screen.getByText('World A')).toBeInTheDocument();
  });
});
