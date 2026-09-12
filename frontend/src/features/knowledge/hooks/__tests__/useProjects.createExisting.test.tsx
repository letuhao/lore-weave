// T20 — creating a knowledge project for a book that already has one must SAY so.
//
// `POST /v1/knowledge/projects` is idempotent on the book-binding path by design
// (D-COMP-POST-WORK-RACE): a second same-book create returns the EXISTING project with 200 rather
// than a duplicate with 201. Correct — and it means everything the author typed into the dialog
// was not applied. The UI closed on success either way, so a 2026-09-06 run filled the form,
// clicked Create, and saw nothing: the project kept its old name and the typed values vanished.
// That run recorded it as a silent no-op; it is really an idempotent return the UI never surfaced.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => {
      let s = (o?.defaultValue as string | undefined) ?? k;
      for (const [key, val] of Object.entries(o ?? {})) {
        if (key !== 'defaultValue') s = s.replaceAll(`{{${key}}}`, String(val));
      }
      return s;
    },
  }),
}));

const info = vi.fn();
// The whole surface, not just the method under test: a partial mock makes any OTHER code path in
// this module graph throw "toast.error is not a function" — an unhandled error that does not fail
// a single test but pollutes the run. Same lesson as T18's react-i18next mock.
vi.mock('sonner', () => ({
  toast: {
    info: (...a: unknown[]) => info(...a),
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}));

const createProjectMock = vi.fn();
vi.mock('../../api', () => ({
  knowledgeApi: {
    listProjects: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    createProject: (...a: unknown[]) => createProjectMock(...a),
  },
}));

import { useProjects } from '../useProjects';

let create: (p: { name: string; book_id?: string }) => Promise<unknown>;

function Harness() {
  const { createProject } = useProjects({ includeArchived: false });
  create = createProject as typeof create;
  return <div />;
}

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <Harness />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  info.mockReset();
  createProjectMock.mockReset();
});

describe('useProjects — creating over an existing book project (T20)', () => {
  it('tells the author their input was not applied, and names what came back', async () => {
    createProjectMock.mockResolvedValue({ project_id: 'p1', name: 'The Old Placeholder Name' });
    mount();
    await create({ name: 'The Name The Author Typed', book_id: 'b1' });

    await waitFor(() => expect(info).toHaveBeenCalledTimes(1));
    const msg = String(info.mock.calls[0][0]);
    expect(msg).toContain('The Old Placeholder Name');
    expect(msg).toMatch(/not applied/i);
  });

  it('stays silent when the project really was created as asked (NV-7)', async () => {
    // A notice on every create would train the author to ignore it, which is worse than none.
    createProjectMock.mockResolvedValue({ project_id: 'p2', name: 'A Brand New Project' });
    mount();
    await create({ name: 'A Brand New Project', book_id: 'b2' });

    await waitFor(() => expect(createProjectMock).toHaveBeenCalled());
    expect(info).not.toHaveBeenCalled();
  });

  it('ignores surrounding whitespace rather than crying wolf over it', async () => {
    createProjectMock.mockResolvedValue({ project_id: 'p3', name: 'Same Name' });
    mount();
    await create({ name: '  Same Name  ', book_id: 'b3' });

    await waitFor(() => expect(createProjectMock).toHaveBeenCalled());
    expect(info).not.toHaveBeenCalled();
  });
});
