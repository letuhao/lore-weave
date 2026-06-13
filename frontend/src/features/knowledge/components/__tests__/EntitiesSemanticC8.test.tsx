import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

// C8 — FE entities semantic layer: status glyphs, anchor badge, legend,
// status filter, semantic-search box, route-scoping.

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
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
import { EntitiesTable } from '../EntitiesTable';
import {
  deriveEntityStatus,
  entityStatus,
  statusGlyph,
  anchorPercent,
} from '../../lib/entityStatus';
import type { Entity } from '../../api';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const BASE: Entity = {
  id: 'ent-1',
  user_id: 'u1',
  project_id: 'p-1',
  name: 'Zhang Ruochen',
  canonical_name: 'zhang ruochen',
  kind: 'character',
  aliases: ['Zhang Ruochen'],
  canonical_version: 1,
  source_types: ['chapter'],
  confidence: 0.9,
  glossary_entity_id: null,
  anchor_score: 0.5,
  archived_at: null,
  archive_reason: null,
  evidence_count: 3,
  mention_count: 42,
  user_edited: false,
  version: 1,
  created_at: '2026-04-01T00:00:00Z',
  updated_at: '2026-04-15T00:00:00Z',
};

const DISCOVERED = { ...BASE, id: 'd', status: 'discovered' as const };
const CANONICAL = {
  ...BASE,
  id: 'c',
  glossary_entity_id: 'g-1',
  anchor_score: 1,
  status: 'canonical' as const,
};
const ARCHIVED = {
  ...BASE,
  id: 'a',
  archived_at: '2026-05-01T00:00:00Z',
  status: 'archived' as const,
};

// ── lib helpers ──────────────────────────────────────────────────────

describe('entityStatus lib', () => {
  it('derives precedence archived > canonical > discovered', () => {
    expect(deriveEntityStatus({ archived_at: null, glossary_entity_id: null })).toBe('discovered');
    expect(deriveEntityStatus({ archived_at: null, glossary_entity_id: 'g' })).toBe('canonical');
    expect(deriveEntityStatus({ archived_at: 'x', glossary_entity_id: 'g' })).toBe('archived');
  });

  it('prefers the BE-provided status field when present', () => {
    expect(entityStatus({ ...BASE, glossary_entity_id: null, status: 'canonical' })).toBe('canonical');
  });

  it('maps each status to its glyph', () => {
    expect(statusGlyph(DISCOVERED)).toBe('💭');
    expect(statusGlyph(CANONICAL)).toBe('⭐');
    expect(statusGlyph(ARCHIVED)).toBe('📦');
  });

  it('clamps anchor percent to 0..100', () => {
    expect(anchorPercent(0.5)).toBe(50);
    expect(anchorPercent(1.5)).toBe(100);
    expect(anchorPercent(NaN)).toBe(0);
  });
});

// ── EntitiesTable rows: glyph + anchor badge ─────────────────────────

describe('EntitiesTable (C8 glyph + anchor badge)', () => {
  it('renders a status glyph per row reflecting derived status', () => {
    render(
      <EntitiesTable
        entities={[DISCOVERED, CANONICAL, ARCHIVED]}
        selectedEntityId={null}
        onSelect={() => {}}
      />,
      { wrapper: Wrapper },
    );
    const glyphs = screen.getAllByTestId('entity-status-glyph');
    // 3 rows × 2 trees (desktop + mobile) = 6 glyphs.
    expect(glyphs.length).toBeGreaterThanOrEqual(3);
    const statuses = glyphs.map((g) => g.getAttribute('data-status'));
    expect(statuses).toContain('discovered');
    expect(statuses).toContain('canonical');
    expect(statuses).toContain('archived');
  });

  it('renders an anchor badge per row', () => {
    render(
      <EntitiesTable entities={[CANONICAL]} selectedEntityId={null} onSelect={() => {}} />,
      { wrapper: Wrapper },
    );
    // 1 row × 2 trees (desktop + mobile) = 2 badges. (i18n returns raw
    // keys in this test env, so we assert presence + count, not the
    // interpolated percent text.)
    const badges = screen.getAllByTestId('entity-anchor-badge');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });
});

// ── EntitiesTab: legend, status filter, semantic box ─────────────────

describe('EntitiesTab (C8 controls)', () => {
  beforeEach(() => {
    listEntitiesMock.mockReset();
    getEntityDetailMock.mockReset();
    listProjectsMock.mockReset();
    listProjectsMock.mockResolvedValue({ items: [], next_cursor: null });
    listEntitiesMock.mockResolvedValue({ entities: [DISCOVERED], total: 1 });
  });

  it('renders the status legend', async () => {
    render(<EntitiesTab />, { wrapper: Wrapper });
    await screen.findByTestId('entities-status-legend');
  });

  it('status filter dispatches the status param', async () => {
    render(<EntitiesTab />, { wrapper: Wrapper });
    await screen.findByTestId('entities-table');
    fireEvent.change(screen.getByTestId('entities-filter-status'), {
      target: { value: 'discovered' },
    });
    await waitFor(() => {
      expect(listEntitiesMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: 'discovered' }),
        'tok-test',
      );
    });
  });

  it('list query requests anchor_score sort', async () => {
    render(<EntitiesTab />, { wrapper: Wrapper });
    await screen.findByTestId('entities-table');
    expect(listEntitiesMock).toHaveBeenCalledWith(
      expect.objectContaining({ sort_by: 'anchor_score' }),
      'tok-test',
    );
  });

  it('semantic box appears ONLY when route-scoped + dispatches semantic_query', async () => {
    // Unscoped: no semantic box.
    const { unmount } = render(<EntitiesTab />, { wrapper: Wrapper });
    await screen.findByTestId('entities-table');
    expect(screen.queryByTestId('entities-semantic-search')).toBeNull();
    unmount();

    // Scoped: semantic box present + dispatches the param.
    render(<EntitiesTab scopedProjectId="p-9" />, { wrapper: Wrapper });
    await screen.findByTestId('entities-semantic-search');
    fireEvent.change(screen.getByTestId('entities-filter-semantic'), {
      target: { value: '神器' },
    });
    await waitFor(() => {
      expect(listEntitiesMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ semantic_query: '神器', project_id: 'p-9' }),
        'tok-test',
      );
    });
  });

  it('semantic_query and search are mutually exclusive (semantic wins)', async () => {
    render(<EntitiesTab scopedProjectId="p-9" />, { wrapper: Wrapper });
    await screen.findByTestId('entities-semantic-search');
    fireEvent.change(screen.getByTestId('entities-filter-search'), {
      target: { value: 'zhang' },
    });
    fireEvent.change(screen.getByTestId('entities-filter-semantic'), {
      target: { value: '神器' },
    });
    await waitFor(() => {
      const lastCall = listEntitiesMock.mock.calls.at(-1)![0];
      expect(lastCall.semantic_query).toBe('神器');
      expect(lastCall.search).toBeUndefined();
    });
  });

  it('does not render the project <select> when route-scoped (G6)', async () => {
    render(<EntitiesTab scopedProjectId="p-9" />, { wrapper: Wrapper });
    await screen.findByTestId('entities-table');
    expect(screen.queryByTestId('entities-filter-project')).toBeNull();
  });
});
