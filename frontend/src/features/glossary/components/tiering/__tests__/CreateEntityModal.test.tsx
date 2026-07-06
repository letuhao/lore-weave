import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const ontologyState = vi.hoisted(() => ({ value: null as unknown }));
vi.mock('../../../hooks/useBookOntology', () => ({ useBookOntology: () => ontologyState.value }));
vi.mock('../TieredEntityForm', () => ({
  TieredEntityForm: ({ kindId, onBusyChange }: { kindId: string; onBusyChange?: (b: boolean) => void }) => (
    <div data-testid="tiered-form">
      {kindId}
      <button data-testid="go-busy" onClick={() => onBusyChange?.(true)}>busy</button>
    </div>
  ),
}));

import { CreateEntityModal } from '../CreateEntityModal';

const KINDS = [
  { book_kind_id: 'bk1', code: 'character', name: 'Character', icon: '🧍', color: '#000', sort_order: 0, is_hidden: false, source_ref: null },
  { book_kind_id: 'bk2', code: 'location', name: 'Location', icon: '🗺️', color: '#000', sort_order: 1, is_hidden: false, source_ref: null },
];

function setOntology(over: Record<string, unknown> = {}) {
  ontologyState.value = {
    ontology: { book_id: 'book-1', genres: [], kinds: KINDS, kind_genres: [], attributes: [] },
    isAdopted: true,
    isLoading: false,
    ...over,
  };
}

beforeEach(() => setOntology());

describe('CreateEntityModal', () => {
  it('prompts to adopt when the book has no ontology', () => {
    setOntology({ isAdopted: false, ontology: { book_id: 'book-1', genres: [], kinds: [], kind_genres: [], attributes: [] } });
    render(<CreateEntityModal bookId="book-1" onClose={vi.fn()} onCreated={vi.fn()} />);
    expect(screen.getByText('create.not_adopted')).toBeInTheDocument();
  });

  it('lists book kinds and opens the tiered form for the picked kind', () => {
    render(<CreateEntityModal bookId="book-1" onClose={vi.fn()} onCreated={vi.fn()} />);
    expect(screen.getByTestId('create-pick-kind-character')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('create-pick-kind-location'));
    expect(screen.getByTestId('tiered-form')).toHaveTextContent('bk2');
  });

  it('closes on Escape', async () => {
    const onClose = vi.fn();
    render(<CreateEntityModal bookId="book-1" onClose={onClose} onCreated={vi.fn()} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('does NOT close on Escape while a create is in flight', async () => {
    const onClose = vi.fn();
    render(<CreateEntityModal bookId="book-1" onClose={onClose} onCreated={vi.fn()} />);
    fireEvent.click(screen.getByTestId('create-pick-kind-character'));
    fireEvent.click(screen.getByTestId('go-busy')); // form signals busy
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });
});
