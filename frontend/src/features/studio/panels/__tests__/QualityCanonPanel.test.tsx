// Studio Quality tab — QualityCanonPanel: merges composition's canon-issues (generation-time
// contradictions) with knowledge's canon-flags (extraction-time contradictions) into one list,
// and jumps to a chapter via the existing focusManuscriptUnit host action (no new bus event).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { IDockviewPanelProps } from 'dockview-react';
import type { ReactNode } from 'react';
import { StudioHostProvider, useStudioHost, type StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

// i18next is not initialised under vitest, so a bare `t()` returns the KEY and every assertion on a
// user-visible message would be vacuously true. Resolve defaultValue + interpolate {{vars}} exactly
// as i18next does, so the focus banners are tested for what they actually SAY.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) =>
      String((o?.defaultValue as string) ?? k).replace(
        /\{\{(\w+)\}\}/g,
        (_m, name: string) => String(o?.[name] ?? ''),
      ),
  }),
}));

const useWorkResolution = vi.fn();
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: (bookId: string, token: string | null) => useWorkResolution(bookId, token),
}));

const useBookKnowledgeProject = vi.fn();
vi.mock('@/features/knowledge/hooks/useBookKnowledgeProject', () => ({
  useBookKnowledgeProject: (bookId: string) => useBookKnowledgeProject(bookId),
}));

const getCanonIssues = vi.fn();
const getRuleViolations = vi.fn();
vi.mock('@/features/composition/api', () => ({
  compositionApi: {
    getCanonIssues: (...args: unknown[]) => getCanonIssues(...args),
    getRuleViolations: (...args: unknown[]) => getRuleViolations(...args),
  },
}));

const listCanonFlags = vi.fn();
vi.mock('@/features/knowledge/api', () => ({
  knowledgeApi: { listCanonFlags: (...args: unknown[]) => listCanonFlags(...args) },
}));

import { QualityCanonPanel } from '../QualityCanonPanel';

function dockProps(params?: Record<string, unknown>) {
  return { api: { setTitle: vi.fn() }, params } as unknown as IDockviewPanelProps;
}

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function withHost(bookId: string, ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  hostRef = null;
  useWorkResolution.mockReset();
  useBookKnowledgeProject.mockReset();
  getCanonIssues.mockReset();
  getRuleViolations.mockReset();
  listCanonFlags.mockReset();
  useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
  useBookKnowledgeProject.mockReturnValue({ project: null, projectId: null, isLoading: false });
  getCanonIssues.mockResolvedValue({ items: [] });
  getRuleViolations.mockResolvedValue({ items: [], count: 0, capped: false });
  listCanonFlags.mockResolvedValue({ flags: [] });
});

const ruleRow = (over: Partial<Record<string, unknown>> = {}) => ({
  scene_id: 's1', scene_title: 'Scene A', chapter_id: 'ch1', job_id: 'j1', created_at: 'x',
  rule_id: 'r1', rule_text: 'Magic always costs HP', span: 'she cast it freely', why: 'no cost paid',
  ...over,
});

describe('QualityCanonPanel', () => {
  it('shows an empty state when every source ACTUALLY RAN and found nothing', async () => {
    // NOTE the work must RESOLVE. This test previously left it at 'none' and still asserted the
    // empty state — i.e. it pinned the false-clean below as correct behaviour.
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('quality-canon-empty')).toBeInTheDocument());
  });

  it('lists a composition (generation-time) issue with a jump-to-chapter action', async () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });
    getCanonIssues.mockResolvedValue({
      items: [{ scene_id: 's1', scene_title: 'Scene A', chapter_id: 'ch1', job_id: 'j1', created_at: 'x', status: 'checked', violations: [{ why: 'Alice is gone but present' }] }],
    });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);

    await waitFor(() => expect(screen.getByTestId('quality-canon-composition-item')).toBeInTheDocument());
    expect(screen.getByText(/Alice is gone but present/)).toBeInTheDocument();

    const jumpSpy = vi.spyOn(hostRef!, 'focusManuscriptUnit');
    fireEvent.click(screen.getByTestId('quality-canon-jump'));
    expect(jumpSpy).toHaveBeenCalledWith('ch1');
  });

  it('lists a knowledge (extraction-time) flag, resolving chapter_id from context.source_id', async () => {
    useBookKnowledgeProject.mockReturnValue({ project: { project_id: 'kproj-1' }, projectId: 'kproj-1', isLoading: false });
    listCanonFlags.mockResolvedValue({
      flags: [{
        log_id: 1, job_id: 'j1', user_id: 'u1', level: 'warning',
        message: "Canon check: 'Alice' referenced as active despite being marked gone",
        context: { event: 'pass2_canon_flag', source_type: 'chapter', source_id: 'ch-99', name: 'Alice' },
        created_at: 'x',
      }],
    });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);

    await waitFor(() => expect(screen.getByTestId('quality-canon-extraction-item')).toBeInTheDocument());
    const jumpSpy = vi.spyOn(hostRef!, 'focusManuscriptUnit');
    fireEvent.click(screen.getByTestId('quality-canon-jump'));
    expect(jumpSpy).toHaveBeenCalledWith('ch-99');
  });

  it('renders both sources together when both have issues', async () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });
    useBookKnowledgeProject.mockReturnValue({ project: { project_id: 'kproj-1' }, projectId: 'kproj-1', isLoading: false });
    getCanonIssues.mockResolvedValue({
      items: [{ scene_id: 's1', scene_title: 'Scene A', chapter_id: 'ch1', job_id: 'j1', created_at: 'x', status: 'checked', violations: [] }],
    });
    listCanonFlags.mockResolvedValue({
      flags: [{ log_id: 1, job_id: 'j2', user_id: 'u1', level: 'warning', message: 'flag', context: { event: 'pass2_canon_flag' }, created_at: 'x' }],
    });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);
    await waitFor(() => {
      expect(screen.getByTestId('quality-canon-composition-section')).toBeInTheDocument();
      expect(screen.getByTestId('quality-canon-extraction-section')).toBeInTheDocument();
    });
  });

  // /review-impl: a fetch error must never silently render as "no issues" — that's a
  // false-negative (the checker didn't run, it isn't clean).
  it('shows an error banner (never the empty state) when the composition query fails', async () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });
    getCanonIssues.mockRejectedValue(new Error('boom'));
    withHost('b1', <QualityCanonPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('quality-canon-composition-error')).toBeInTheDocument());
    expect(screen.queryByTestId('quality-canon-empty')).toBeNull();
  });

  it('shows an error banner (never the empty state) when the extraction query fails', async () => {
    useBookKnowledgeProject.mockReturnValue({ project: { project_id: 'kproj-1' }, projectId: 'kproj-1', isLoading: false });
    listCanonFlags.mockRejectedValue(new Error('boom'));
    withHost('b1', <QualityCanonPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('quality-canon-extraction-error')).toBeInTheDocument());
    expect(screen.queryByTestId('quality-canon-empty')).toBeNull();
  });
});

// ── 24 PH18 / RUN-STATE D-04 option B — the RULE lane ────────────────────────────────────────
// The lane that carries a rule_id, and therefore the only one a canon deep-link can filter on.
describe('QualityCanonPanel — the canon-RULE lane (D-04 B)', () => {
  const found = () =>
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'found', work: { project_id: 'proj-1' } } });

  it('lists a broken rule with its text, the judge’s reason, and a jump to the chapter', async () => {
    found();
    getRuleViolations.mockResolvedValue({ items: [ruleRow()] });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);

    await waitFor(() => expect(screen.getByTestId('quality-canon-rule-item')).toBeInTheDocument());
    expect(screen.getByText(/Magic always costs HP/)).toBeInTheDocument();
    expect(screen.getByText(/no cost paid/)).toBeInTheDocument();

    const jumpSpy = vi.spyOn(hostRef!, 'focusManuscriptUnit');
    fireEvent.click(screen.getByTestId('quality-canon-jump'));
    expect(jumpSpy).toHaveBeenCalledWith('ch1');
  });

  it('HOISTS and highlights the focused rule — and hides nothing', async () => {
    found();
    getRuleViolations.mockResolvedValue({
      items: [ruleRow({ rule_id: 'r1', rule_text: 'Rule one' }), ruleRow({ rule_id: 'r2', rule_text: 'Rule two', job_id: 'j2' })],
    });
    withHost('b1', <QualityCanonPanel {...dockProps({ focusRuleId: 'r2' })} />);

    await waitFor(() => expect(screen.getAllByTestId('quality-canon-rule-item')).toHaveLength(2));
    const rows = screen.getAllByTestId('quality-canon-rule-item');
    expect(rows[0].getAttribute('data-focused')).toBe('true');
    expect(rows[0].textContent).toContain('Rule two');
    expect(rows[1].getAttribute('data-focused')).toBeNull();
    expect(screen.getByTestId('quality-canon-rule-focus').textContent).toContain('Rule two');
  });

  // The bug this whole decision exists to kill: a deep-link that opens the panel, matches
  // nothing, and LOOKS like it worked. If the focused rule is clean, the panel must SAY so.
  it('SAYS SO when the focused rule has no open violations', async () => {
    found();
    getRuleViolations.mockResolvedValue({ items: [ruleRow({ rule_id: 'r1' })] });
    withHost('b1', <QualityCanonPanel {...dockProps({ focusRuleId: 'r-clean' })} />);

    await waitFor(() => expect(screen.getByTestId('quality-canon-rule-focus')).toBeInTheDocument());
    expect(screen.getByTestId('quality-canon-rule-focus').textContent).toMatch(/no open violations/i);
  });

  // An unattributable violation is still a REAL finding. Rendering it as nothing would fake a
  // clean book — the exact false-negative the error banners already guard against.
  it('renders a violation whose rule no longer resolves, rather than dropping it', async () => {
    found();
    getRuleViolations.mockResolvedValue({ items: [ruleRow({ rule_text: null, why: 'contradicts a retired rule' })] });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);

    await waitFor(() => expect(screen.getByTestId('quality-canon-rule-item')).toBeInTheDocument());
    expect(screen.getByText(/no longer exists/i)).toBeInTheDocument();
    expect(screen.getByText(/contradicts a retired rule/)).toBeInTheDocument();
    expect(screen.queryByTestId('quality-canon-empty')).toBeNull();
  });

  it('a failed rule query shows its own banner, never the empty state', async () => {
    found();
    getRuleViolations.mockRejectedValue(new Error('boom'));
    withHost('b1', <QualityCanonPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('quality-canon-rule-error')).toBeInTheDocument());
    expect(screen.queryByTestId('quality-canon-empty')).toBeNull();
  });

  it('a CAPPED rule list says so, with the exact total (OUT-5 — no silent truncation)', async () => {
    found();
    getRuleViolations.mockResolvedValue({ items: [ruleRow()], count: 137, capped: true });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);
    await waitFor(() => expect(screen.getByTestId('quality-canon-rules-capped')).toBeInTheDocument());
    expect(screen.getByTestId('quality-canon-rules-capped').textContent).toContain('137');
  });
});

// ── /review-impl HIGH-1 — UNCONSULTED != CLEAN ────────────────────────────────────────────────
// The two composition lanes are `enabled: !!projectId`. With no project they never run and resolve
// to [] with no error — so a naive `empty` renders "No canon issues found." over a book whose canon
// was NEVER CHECKED. The 3 sibling quality panels (promises/critic/coverage) already guard this via
// QualityNoWorkState; canon was the only one that didn't. And it is not hypothetical: a Work created
// while knowledge-service was down is `pending_project_backfill` and the resolver EXCLUDES it.
describe('QualityCanonPanel — a book it could not check is NOT a clean book', () => {
  it('NO composition Work: says so, and never claims the book is clean', async () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);

    await waitFor(() => expect(screen.getByTestId('quality-canon-no-work')).toBeInTheDocument());
    expect(screen.queryByTestId('quality-canon-empty')).toBeNull();
  });

  it('composition-service UNAVAILABLE: an error banner, never the empty state', async () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'unavailable', work: null } });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);

    await waitFor(() => expect(screen.getByTestId('quality-canon-unavailable')).toBeInTheDocument());
    expect(screen.queryByTestId('quality-canon-empty')).toBeNull();
  });

  it('the knowledge-extraction lane STILL renders — it does not need a composition Work', async () => {
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
    useBookKnowledgeProject.mockReturnValue({ project: { project_id: 'k1' }, projectId: 'k1', isLoading: false });
    listCanonFlags.mockResolvedValue({
      flags: [{ log_id: 1, job_id: 'j', user_id: 'u', level: 'warning', message: 'kg contradiction',
                context: { event: 'pass2_canon_flag' }, created_at: 'x' }],
    });
    withHost('b1', <QualityCanonPanel {...dockProps()} />);

    await waitFor(() => expect(screen.getByTestId('quality-canon-extraction-item')).toBeInTheDocument());
    expect(screen.getByTestId('quality-canon-no-work')).toBeInTheDocument();
  });

  it('a rule deep-link into an unchecked book does NOT say "nothing has broken it"', async () => {
    // The worst version of the bug: you click a canon badge and the panel tells you the rule is fine.
    useWorkResolution.mockReturnValue({ isLoading: false, data: { status: 'none', work: null } });
    withHost('b1', <QualityCanonPanel {...dockProps({ focusRuleId: 'r1' })} />);

    await waitFor(() => expect(screen.getByTestId('quality-canon-rule-focus')).toBeInTheDocument());
    const banner = screen.getByTestId('quality-canon-rule-focus').textContent ?? '';
    // Assert the MEANING, not the phrasing: it must say we could not check, and must NOT say the
    // rule is intact. (The wording moved once already — an English idiom, "a clean bill of health",
    // was inverted outright by the ja/vi translators. Plain copy, and a test that survives rewording.)
    expect(banner).toMatch(/could not be checked/i);
    expect(banner).not.toMatch(/nothing has broken it/i);
  });
});
