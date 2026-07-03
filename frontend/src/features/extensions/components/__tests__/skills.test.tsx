// M5 checklist §4 — SkillsView was fully built (search/tier/sort/pager/empty/error)
// but never tested, so its checklist lines couldn't be honestly ticked (memory
// checklist-is-self-report-enforce-by-tests: a tick needs a test asserting the EFFECT).
// These assert the built behavior through the real hook → api boundary.
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));
vi.mock('@/features/extensions/context/ExtensionScope', () => ({
  useExtensionScope: () => ({ bookId: null, setBookId: () => {} }),
  ExtensionScopeProvider: ({ children }: { children: React.ReactNode }) => children,
}));

const api = vi.hoisted(() => ({
  listSkills: vi.fn(),
  setSkillEnabled: vi.fn(),
  deleteSkill: vi.fn(),
}));
vi.mock('@/features/extensions/api', () => ({ extensionsApi: api }));

import { SkillsView } from '../SkillsView';

const skill = (over: Record<string, unknown> = {}) => ({
  skill_id: 's1', tier: 'user', slug: 'my-skill', description: 'd', body_md: '',
  surfaces: [], status: 'published', source: 'user', used_count: 0,
  created_at: '', updated_at: '', ...over,
});

beforeEach(() => {
  Object.values(api).forEach((f) => (f as ReturnType<typeof vi.fn>).mockReset());
  api.listSkills.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
});

describe('SkillsView §4 — toolbar + states', () => {
  it('shows the empty state when there are no skills', async () => {
    render(<SkillsView />);
    await waitFor(() => expect(screen.getByText(/No skills yet/i)).toBeTruthy());
  });

  it('shows an error banner when the list load fails', async () => {
    api.listSkills.mockRejectedValueOnce(new Error('Registry unreachable'));
    render(<SkillsView />);
    await waitFor(() => expect(screen.getByText(/Registry unreachable/i)).toBeTruthy());
  });

  it('search input re-queries with the server-side q', async () => {
    render(<SkillsView />);
    await waitFor(() => expect(api.listSkills).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId('skills-search-input'), { target: { value: 'dragon' } });
    await waitFor(() => expect(api.listSkills.mock.calls.at(-1)?.[1]).toMatchObject({ q: 'dragon', offset: 0 }));
  });

  it('tier filter re-queries with the tier', async () => {
    render(<SkillsView />);
    await waitFor(() => expect(api.listSkills).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId('skills-tier-filter'), { target: { value: 'system' } });
    await waitFor(() => expect(api.listSkills.mock.calls.at(-1)?.[1]).toMatchObject({ tier: 'system' }));
  });

  it('sort select re-queries with the sort key', async () => {
    render(<SkillsView />);
    await waitFor(() => expect(api.listSkills).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId('skills-sort'), { target: { value: 'name' } });
    await waitFor(() => expect(api.listSkills.mock.calls.at(-1)?.[1]).toMatchObject({ sort: 'name' }));
  });
});

describe('SkillsView §4 — pager', () => {
  it('shows "X–Y of N" and pages forward (offset advances); ‹ disabled at page 0', async () => {
    api.listSkills.mockResolvedValue({ items: [skill()], total: 45, limit: 20, offset: 0 });
    render(<SkillsView />);
    await waitFor(() => expect(screen.getByText(/1–20 of 45/)).toBeTruthy());
    const prev = screen.getByText('‹') as HTMLButtonElement;
    expect(prev.disabled).toBe(true);
    fireEvent.click(screen.getByText('›'));
    await waitFor(() => expect(api.listSkills.mock.calls.at(-1)?.[1]).toMatchObject({ offset: 20 }));
  });
});

describe('SkillsView §4 — rows', () => {
  it('renders tier badge, toggle → setSkillEnabled, delete → deleteSkill (User row)', async () => {
    api.listSkills.mockResolvedValue({ items: [skill()], total: 1, limit: 20, offset: 0 });
    api.setSkillEnabled.mockResolvedValue({});
    api.deleteSkill.mockResolvedValue({});
    render(<SkillsView />);
    await waitFor(() => expect(screen.getByTestId('skill-row')).toBeTruthy());
    expect(screen.getByText('user')).toBeTruthy(); // tier badge
    fireEvent.click(screen.getByTestId('skill-toggle'));
    await waitFor(() => expect(api.setSkillEnabled).toHaveBeenCalledWith('test-token', 's1', false));
    fireEvent.click(screen.getByTestId('skill-delete'));
    await waitFor(() => expect(api.deleteSkill).toHaveBeenCalledWith('test-token', 's1'));
  });

  it('a System row has no delete button (read-only)', async () => {
    api.listSkills.mockResolvedValue({ items: [skill({ tier: 'system', skill_id: 'sys1' })], total: 1, limit: 20, offset: 0 });
    render(<SkillsView />);
    await waitFor(() => expect(screen.getByTestId('skill-row')).toBeTruthy());
    expect(screen.queryByTestId('skill-delete')).toBeNull();
  });
});
