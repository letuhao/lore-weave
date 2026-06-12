import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

// GapsPanel/SourcesPanel both pull embedding models from provider-registry.
const listModelsMock = vi.fn();
vi.mock('@/features/settings/api', () => ({
  providerApi: { listUserModels: (...a: unknown[]) => listModelsMock(...a) },
}));

// Stub the data hook so the panel renders deterministically off our fixture.
const sourcesStub = vi.hoisted(() => ({
  items: [] as unknown[],
  isLoading: false,
  register: vi.fn(),
  ingest: vi.fn(),
  ground: vi.fn(),
  busy: false,
}));
vi.mock('../../hooks/useEnrichmentSources', () => ({
  useEnrichmentSources: () => sourcesStub,
}));

// SourcesPanel now embeds ChapterSelectionPicker, which lists chapters via booksApi.
const listChaptersMock = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: { listChapters: (...a: unknown[]) => listChaptersMock(...a) },
}));

import { SourcesPanel } from '../SourcesPanel';
import { EnrichmentProvider } from '../../context/EnrichmentContext';
import type { Source } from '../../types';

const S = (over: Partial<Source> = {}): Source =>
  ({
    corpus_id: 'c-1',
    project_id: 'proj-9',
    name: '封神演義',
    kind: 'fengshen',
    license: 'public_domain',
    provenance_json: {},
    created_at: '',
    updated_at: '',
    ...over,
  } as Source);

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EnrichmentProvider bookId="book-1">
        <SourcesPanel />
      </EnrichmentProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sourcesStub.items = [];
  sourcesStub.isLoading = false;
  sourcesStub.busy = false;
  listModelsMock.mockResolvedValue({
    items: [{ user_model_id: 'm1', alias: 'qwen', provider_model_name: 'qwen' }],
  });
  listChaptersMock.mockResolvedValue({ items: [], total: 0 });
});

describe('SourcesPanel', () => {
  it('shows a Skeleton while the source list is loading', () => {
    sourcesStub.isLoading = true;
    const { container } = renderPanel();
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
    expect(screen.queryByText('sources.none')).toBeNull();
    expect(screen.queryByTestId('enrichment-source-card')).toBeNull();
  });

  it('renders the sources.none empty state when there are no corpora', () => {
    sourcesStub.items = [];
    renderPanel();
    expect(screen.getByText('sources.none')).toBeInTheDocument();
    expect(screen.queryByTestId('enrichment-source-card')).toBeNull();
  });

  it('renders one SourceCard per item', () => {
    sourcesStub.items = [S({ corpus_id: 'c-1' }), S({ corpus_id: 'c-2', name: '山海經' })];
    renderPanel();
    expect(screen.getAllByTestId('enrichment-source-card')).toHaveLength(2);
    expect(screen.getByText('封神演義')).toBeInTheDocument();
    expect(screen.getByText('山海經')).toBeInTheDocument();
  });

  it('always renders the default_deny footnote', () => {
    renderPanel();
    expect(screen.getByText('sources.default_deny')).toBeInTheDocument();
  });

  it('the register form is hidden until the register button is toggled', () => {
    renderPanel();
    expect(screen.queryByText('sources.name')).toBeNull();
    fireEvent.click(screen.getByText('sources.register'));
    expect(screen.getByText('sources.name')).toBeInTheDocument();
  });

  it('submitting with an empty name is a no-op (does not call register)', () => {
    renderPanel();
    fireEvent.click(screen.getByText('sources.register'));
    // name left blank
    fireEvent.click(screen.getByText('actions.save'));
    expect(sourcesStub.register).not.toHaveBeenCalled();
  });

  it('submitting a valid name calls register with the trimmed name and default kind/license', async () => {
    sourcesStub.register.mockResolvedValue(S());
    renderPanel();
    fireEvent.click(screen.getByText('sources.register'));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '  封神演義  ' } });
    fireEvent.click(screen.getByText('actions.save'));
    expect(sourcesStub.register).toHaveBeenCalledWith({
      name: '封神演義',
      kind: 'history',
      license: 'public_domain',
    });
  });
});
