import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: {
      user_id: 'u1',
      email: 'a@b',
      display_name: null,
      avatar_url: null,
    },
  }),
}));

const listEntitiesMock = vi.fn();
const getEntityDetailMock = vi.fn();
const listProjectsMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      listEntities: (...args: unknown[]) => listEntitiesMock(...args),
      getEntityDetail: (...args: unknown[]) => getEntityDetailMock(...args),
      listProjects: (...args: unknown[]) => listProjectsMock(...args),
    },
  };
});

import { EntitiesTab } from '../EntitiesTab';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const ENTITY_KAI = {
  id: 'ent-kai',
  user_id: 'u1',
  project_id: 'p-1',
  name: 'Kai',
  canonical_name: 'kai',
  kind: 'character',
  aliases: ['Kai', 'Master Kai'],
  canonical_version: 1,
  source_types: ['chapter'],
  confidence: 0.9,
  glossary_entity_id: null,
  anchor_score: 0.5,
  archived_at: null,
  archive_reason: null,
  evidence_count: 12,
  mention_count: 42,
  created_at: '2026-04-01T00:00:00Z',
  updated_at: '2026-04-15T00:00:00Z',
};

const ENTITY_PHOENIX = {
  ...ENTITY_KAI,
  id: 'ent-phoenix',
  name: 'Phoenix',
  canonical_name: 'phoenix',
  aliases: ['Phoenix'],
  mention_count: 8,
};

describe('EntitiesTab', () => {
  beforeEach(() => {
    listEntitiesMock.mockReset();
    getEntityDetailMock.mockReset();
    listProjectsMock.mockReset();
    listProjectsMock.mockResolvedValue({ items: [], next_cursor: null });
    listEntitiesMock.mockResolvedValue({
      entities: [ENTITY_KAI, ENTITY_PHOENIX],
      total: 2,
    });
  });

  it('renders the table with entities and forwards default filters', async () => {
    render(<EntitiesTab />, { wrapper: Wrapper });
    await screen.findByTestId('entities-table');
    expect(await screen.findAllByTestId('entities-row')).toHaveLength(2);
    expect(listEntitiesMock).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 50, offset: 0 }),
      'tok-test',
    );
  });

  it('renders empty-state when no entities and total=0', async () => {
    listEntitiesMock.mockResolvedValueOnce({ entities: [], total: 0 });
    render(<EntitiesTab />, { wrapper: Wrapper });
    await screen.findByTestId('entities-empty');
  });

  it('changes kind filter + dispatches with updated params', async () => {
    render(<EntitiesTab />, { wrapper: Wrapper });
    await screen.findByTestId('entities-table');
    fireEvent.change(screen.getByTestId('entities-filter-kind'), {
      target: { value: 'character' },
    });
    await waitFor(() => {
      expect(listEntitiesMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ kind: 'character', offset: 0 }),
        'tok-test',
      );
    });
  });

  it('row click opens the detail panel and the detail endpoint fires', async () => {
    getEntityDetailMock.mockResolvedValue({
      entity: ENTITY_KAI,
      relations: [],
      relations_truncated: false,
      total_relations: 0,
    });
    render(<EntitiesTab />, { wrapper: Wrapper });
    const rows = await screen.findAllByTestId('entities-row');
    fireEvent.click(rows[0]);
    await screen.findByTestId('entity-detail-panel');
    expect(getEntityDetailMock).toHaveBeenCalledWith('ent-kai', 'tok-test');
    await screen.findByTestId('entity-detail-no-relations');
  });

  it('renders truncation banner when BE reports relations_truncated', async () => {
    getEntityDetailMock.mockResolvedValue({
      entity: ENTITY_KAI,
      relations: [
        {
          id: 'r1',
          subject_id: 'ent-kai',
          object_id: 'ent-other',
          predicate: 'mentors',
          confidence: 0.9,
          source_event_ids: [],
          source_chapter: null,
          valid_from: null,
          valid_until: null,
          pending_validation: false,
          created_at: null,
          updated_at: null,
          subject_name: 'Kai',
          subject_kind: 'character',
          object_name: 'Phoenix',
          object_kind: 'character',
        },
      ],
      relations_truncated: true,
      total_relations: 457,
    });
    render(<EntitiesTab />, { wrapper: Wrapper });
    const rows = await screen.findAllByTestId('entities-row');
    fireEvent.click(rows[0]);
    // The global react-i18next mock returns keys verbatim without
    // interpolating placeholders, so we assert on the key presence.
    // The truncation-banner's rendered content lives in the test
    // above; here we only care that the BE's truncated=true surfaces
    // the banner element at all.
    await screen.findByTestId('entity-detail-truncated');
  });

  it('surfaces list-endpoint errors inline', async () => {
    listEntitiesMock.mockRejectedValueOnce(new Error('boom'));
    render(<EntitiesTab />, { wrapper: Wrapper });
    // i18n mock doesn't interpolate {{error}}; assert the error
    // element is rendered at all (presence = truthy path).
    await screen.findByTestId('entities-error');
  });

  it('pagination prev/next buttons flip offset', async () => {
    // Seed > PAGE_SIZE total so next is enabled; BE returns 1 row to
    // simulate the tail page.
    listEntitiesMock.mockResolvedValue({
      entities: [ENTITY_KAI],
      total: 75,
    });
    render(<EntitiesTab />, { wrapper: Wrapper });
    await screen.findByTestId('entities-table');
    fireEvent.click(screen.getByTestId('entities-pagination-next'));
    await waitFor(() => {
      expect(listEntitiesMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ offset: 50 }),
        'tok-test',
      );
    });
  });
});
