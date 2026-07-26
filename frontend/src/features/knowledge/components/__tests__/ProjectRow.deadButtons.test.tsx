/**
 * AUDIT 2026-07-17 — the "kg-overview 3-noop-buttons" regression guard.
 *
 * The studio's production-ready bar cites this exact bug as its canonical dead-button example, and
 * it was STILL live when the completeness audit swept for it: `ProjectRow` required onArchive /
 * onRestore / onDelete, so `OverviewSection` — where the decision is that destructive CRUD belongs
 * with the projects LIST — satisfied the types with `noop`. The result was a live Archive icon and
 * a live Delete icon in the `kg-overview` panel that did nothing on click: no dialog, no toast, no
 * error. Bar #2 (no dead buttons) and #4 (no silent failure), both violated, for months.
 *
 * It survived every existing test because OverviewSection's own suite STUBS ProjectRow out
 * entirely — so nothing ever rendered the real buttons. This tests the real component: omitting a
 * destructive handler must HIDE its button, and supplying one must show it (or the guard would
 * pass by rendering nothing at all).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import type { Project } from '../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: () => ({ data: undefined, isLoading: false }),
  useMutation: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 't' }) }));
vi.mock('../../api', () => ({ knowledgeApi: {} }));
vi.mock('../../hooks/useProjectState', () => ({
  PROJECT_ACTION_KEYS: {},
  useProjectState: () => ({ state: 'complete', actions: {}, job: null }),
}));
// The state card + confirm dialog are unrelated surfaces with heavy deps; the buttons under test
// live in ProjectRow's own action row.
vi.mock('../ProjectStateCard', () => ({ ProjectStateCard: () => <div data-testid="stub-state-card" /> }));
vi.mock('@/components/shared', () => ({ ConfirmDialog: () => null, FormDialog: () => null }));

import { ProjectRow } from '../ProjectRow';

const project = {
  id: 'p1',
  name: 'Test',
  is_archived: false,
  description: '',
  book_id: null,
  embedding_model: { model_source: 'user_model', model_ref: 'e1' },
  // ProjectRow's rebuildModels reads `extraction_config.llm_model` — the field is
  // `extraction_config`, not `extraction_settings`.
  extraction_config: { llm_model: { model_source: 'user_model', model_ref: 'm1' } },
  created_at: '2026-07-17T00:00:00Z',
  updated_at: '2026-07-17T00:00:00Z',
} as unknown as Project;

const archiveBtn = () => screen.queryByTitle('projects.card.archive');
const restoreBtn = () => screen.queryByTitle('projects.card.restore');
const deleteBtn = () => screen.queryByTitle('projects.card.delete');

describe('ProjectRow destructive affordances', () => {
  it('renders NO archive/delete button when the handlers are omitted (the Overview case)', () => {
    render(<ProjectRow project={project} onEdit={vi.fn()} />);
    // Before the fix these rendered and did nothing — a click into the void.
    expect(archiveBtn()).toBeNull();
    expect(deleteBtn()).toBeNull();
  });

  it('renders them when handled (the projects-browser case) — so the guard above is not vacuous', () => {
    render(
      <ProjectRow project={project} onEdit={vi.fn()} onArchive={vi.fn()} onDelete={vi.fn()} />,
    );
    expect(archiveBtn()).not.toBeNull();
    expect(deleteBtn()).not.toBeNull();
  });

  it('swaps archive for restore on an archived project, and still hides it when unhandled', () => {
    const archived = { ...project, is_archived: true } as Project;
    const { unmount } = render(<ProjectRow project={archived} onEdit={vi.fn()} onRestore={vi.fn()} />);
    expect(restoreBtn()).not.toBeNull();
    expect(archiveBtn()).toBeNull();
    unmount();

    render(<ProjectRow project={archived} onEdit={vi.fn()} />);
    expect(restoreBtn()).toBeNull();
  });
});
