import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ReferencesPanel } from '../ReferencesPanel';

// Mock the controller hook (the view test owns rendering + wiring, not data).
const h = vi.hoisted(() => ({
  add: vi.fn(),
  remove: vi.fn(),
  setPin: vi.fn(),
  state: {
    references: [] as any[],
    embedModelSet: false,
    isLoading: false,
    hits: [] as any[],
    searchUnavailable: false,
    isSearching: false,
  },
}));
vi.mock('../../hooks/useReferences', () => ({
  useReferences: () => ({
    ...h.state,
    add: { mutate: h.add, isPending: false },
    remove: { mutate: h.remove },
    setPin: h.setPin,
  }),
}));

const EMBED_MODEL = {
  user_model_id: 'm-embed', provider_kind: 'openai', provider_model_name: 'bge-m3',
  is_active: true, is_favorite: false, capability_flags: { embed: true }, tags: [], created_at: '',
} as any;

beforeEach(() => {
  h.add.mockReset(); h.remove.mockReset(); h.setPin.mockReset();
  h.state = { references: [], embedModelSet: false, isLoading: false, hits: [],
              searchUnavailable: false, isSearching: false };
});

const renderPanel = (over: Record<string, any> = {}) =>
  render(<ReferencesPanel projectId="p1" sceneId="s1" token="t" models={[EMBED_MODEL]} {...over} />);

describe('ReferencesPanel (T3.6)', () => {
  it('shows the embedding-model picker when the work has no model yet, and adds with it', () => {
    renderPanel();
    // model select appears (embedModelSet=false + an embedding-capable model exists)
    expect(screen.getByTestId('references-model-select')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('references-add-content'), { target: { value: 'the spice must flow' } });
    fireEvent.change(screen.getByTestId('references-model-select'), { target: { value: 'm-embed' } });
    fireEvent.click(screen.getByTestId('references-add-submit'));
    expect(h.add).toHaveBeenCalledTimes(1);
    expect(h.add.mock.calls[0][0]).toMatchObject({ content: 'the spice must flow', model_ref: 'm-embed', model_source: 'user_model' });
  });

  it('hides the model picker once the work has an embedding model', () => {
    h.state.embedModelSet = true;
    renderPanel();
    expect(screen.queryByTestId('references-model-select')).toBeNull();
  });

  it('warns when no embedding-capable model is configured (add disabled)', () => {
    renderPanel({ models: [] });
    expect(screen.getByTestId('references-no-embed-model')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('references-add-content'), { target: { value: 'x' } });
    expect(screen.getByTestId('references-add-submit')).toBeDisabled();
  });

  it('does not add when content is empty', () => {
    h.state.embedModelSet = true;
    renderPanel();
    expect(screen.getByTestId('references-add-submit')).toBeDisabled();
    fireEvent.click(screen.getByTestId('references-add-submit'));
    expect(h.add).not.toHaveBeenCalled();
  });

  it('renders per-scene hits with score and pins one', () => {
    h.state.embedModelSet = true;
    h.state.hits = [{ id: 'r1', title: 'Dune', content: 'spice', score: 0.82, pinned: false, excluded: false }];
    renderPanel();
    const row = screen.getByTestId('references-hit-r1');
    expect(row).toHaveTextContent('Dune');
    expect(row).toHaveTextContent('82%');
    fireEvent.click(screen.getByTestId('references-pin-r1'));
    expect(h.setPin).toHaveBeenCalledWith(h.state.hits[0], 'pin');
  });

  it('un-pins an already-pinned hit (toggles to none)', () => {
    h.state.embedModelSet = true;
    h.state.hits = [{ id: 'r1', title: 'Dune', content: 'spice', score: 0.5, pinned: true, excluded: false }];
    renderPanel();
    fireEvent.click(screen.getByTestId('references-pin-r1'));
    expect(h.setPin).toHaveBeenCalledWith(h.state.hits[0], 'none');
  });

  it('shows the retrieval-unavailable banner on a provider outage', () => {
    h.state.embedModelSet = true;
    h.state.searchUnavailable = true;
    renderPanel();
    expect(screen.getByTestId('references-unavailable')).toBeInTheDocument();
  });

  it('lists the library and deletes a reference', () => {
    h.state.references = [{ id: 'r9', title: 'Influence', author: 'X', content: 'body', embedding_model: 'bge-m3', embedding_dim: 3, created_at: null }];
    renderPanel();
    expect(screen.getByTestId('references-lib-r9')).toHaveTextContent('Influence');
    fireEvent.click(screen.getByTestId('references-delete-r9'));
    expect(h.remove).toHaveBeenCalledWith('r9');
  });

  it('shows the empty-library state', () => {
    renderPanel();
    expect(screen.getByTestId('references-empty')).toBeInTheDocument();
  });
});
