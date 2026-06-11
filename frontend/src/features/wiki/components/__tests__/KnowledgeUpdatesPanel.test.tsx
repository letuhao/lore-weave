import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) =>
      o?.count != null ? `${k}:${o.count}` : o?.defaultValue != null ? (o.defaultValue as string) : k,
  }),
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
// W6b-1 — the panel renders a react-router Link for the "view source" jump.
vi.mock('react-router-dom', () => ({
  Link: ({ to, children, ...p }: { to: string; children: React.ReactNode }) => (
    <a href={to} {...p}>{children}</a>
  ),
}));
// gen-config (cost basis) — return a flat $0.50/article so the batch estimate is deterministic.
vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: { cost_per_article_usd: 0.5 } }),
}));

const dismiss = vi.fn();
const dismissMany = vi.fn();
const rescan = vi.fn();
const useWikiStalenessMock = vi.fn();
vi.mock('../../hooks/useWikiStaleness', () => ({
  useWikiStaleness: () => useWikiStalenessMock(),
}));

import { KnowledgeUpdatesPanel } from '../KnowledgeUpdatesPanel';
import type { WikiStalenessRow } from '../../types';

const kind = { kind_id: 'k', code: 'character', name: 'Character', icon: '🧍', color: '#abc' };
function row(over: Partial<WikiStalenessRow>): WikiStalenessRow {
  return {
    staleness_id: 's1', article_id: 'a1', entity_id: 'e1', display_name: 'Mina',
    kind, reason_code: 'entity_changed', severity: 'content', source_ref: {},
    detected_at: '2026-06-11T00:00:00Z', ...over,
  };
}

const baseHook = () => ({
  rows: [
    row({ staleness_id: 's1', entity_id: 'e1', display_name: 'Mina', reason_code: 'citation_broken', severity: 'hard' }),
    row({ staleness_id: 's2', entity_id: 'e1', display_name: 'Mina', reason_code: 'entity_changed', severity: 'content' }),
    row({ staleness_id: 's3', entity_id: 'e2', display_name: 'Lucy', reason_code: 'entity_changed', severity: 'content' }),
  ],
  count: 3, isLoading: false, dismiss, dismissing: null, dismissMany, rescan, rescanning: false,
});

beforeEach(() => {
  vi.clearAllMocks();
  useWikiStalenessMock.mockReturnValue(baseHook());
});

describe('KnowledgeUpdatesPanel', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <KnowledgeUpdatesPanel bookId="b" open={false} onClose={() => {}} onRegenerate={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows the empty state when there are no stale rows', () => {
    useWikiStalenessMock.mockReturnValue({ ...baseHook(), rows: [], count: 0 });
    render(<KnowledgeUpdatesPanel bookId="b" open onClose={() => {}} onRegenerate={() => {}} />);
    expect(screen.getByTestId('staleness-empty')).toBeTruthy();
  });

  it('lists all stale rows grouped', () => {
    render(<KnowledgeUpdatesPanel bookId="b" open onClose={() => {}} onRegenerate={() => {}} />);
    expect(screen.getAllByTestId('staleness-row')).toHaveLength(3);
  });

  it('regenerate is disabled until rows are selected, then passes DEDUPED entity ids', () => {
    const onRegenerate = vi.fn();
    render(<KnowledgeUpdatesPanel bookId="b" open onClose={() => {}} onRegenerate={onRegenerate} />);
    const btn = screen.getByTestId('staleness-regenerate') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);

    const checks = screen.getAllByRole('checkbox');
    fireEvent.click(checks[0]); // s1 → entity e1
    fireEvent.click(checks[1]); // s2 → entity e1 (same entity!)
    fireEvent.click(checks[2]); // s3 → entity e2
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    // e1 appears twice across rows but regen is per-entity → deduped to [e1, e2]
    expect(onRegenerate).toHaveBeenCalledWith(['e1', 'e2'], expect.any(String));
  });

  it('dismiss calls the hook for that row', () => {
    render(<KnowledgeUpdatesPanel bookId="b" open onClose={() => {}} onRegenerate={() => {}} />);
    fireEvent.click(screen.getAllByTestId('staleness-dismiss')[0]);
    expect(dismiss).toHaveBeenCalledWith('s1');
  });

  it('rescan button triggers a sweep', () => {
    render(<KnowledgeUpdatesPanel bookId="b" open onClose={() => {}} onRegenerate={() => {}} />);
    fireEvent.click(screen.getByTestId('staleness-rescan'));
    expect(rescan).toHaveBeenCalledOnce();
  });

  it('dismiss-selected is disabled until a row is checked, then batch-dismisses the selected ids', () => {
    render(<KnowledgeUpdatesPanel bookId="b" open onClose={() => {}} onRegenerate={() => {}} />);
    const btn = screen.getByTestId('staleness-dismiss-all') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(screen.getAllByRole('checkbox')[0]); // s1
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    expect(dismissMany).toHaveBeenCalledWith(['s1']);
  });

  it('shows a batch cost estimate scaled by the deduped entity count (2 × $0.50 = $1.00)', () => {
    render(<KnowledgeUpdatesPanel bookId="b" open onClose={() => {}} onRegenerate={() => {}} />);
    expect(screen.queryByTestId('staleness-cost')).toBeNull(); // hidden until a selection
    const checks = screen.getAllByRole('checkbox');
    fireEvent.click(checks[0]); // e1
    fireEvent.click(checks[2]); // e2 → 2 distinct entities
    expect(screen.getByTestId('staleness-cost').textContent).toContain('~$1.00');
  });

  // W6b-1 — the per-row "view source" jump.
  it('renders a view-source jump for entity/block rows and closes the panel on click', () => {
    const onClose = vi.fn();
    useWikiStalenessMock.mockReturnValue({
      ...baseHook(),
      rows: [
        row({ staleness_id: 's1', reason_code: 'entity_changed', source_ref: { source_type: 'entity', source_id: 'e9' } }),
        row({ staleness_id: 's2', reason_code: 'chapter_regrounded', source_ref: { source_type: 'block', source_id: 'ch7' } }),
        row({ staleness_id: 's3', reason_code: 'recipe_drift', source_ref: { source_type: 'recipe' } }),
      ],
    });
    render(<KnowledgeUpdatesPanel bookId="b" open onClose={onClose} onRegenerate={() => {}} />);
    const jumps = screen.getAllByTestId('staleness-source-jump');
    expect(jumps).toHaveLength(2); // entity + block; recipe drift has no jump
    expect(jumps[0].getAttribute('href')).toBe('/books/b/glossary');
    expect(jumps[1].getAttribute('href')).toBe('/books/b/chapters/ch7/read');
    fireEvent.click(jumps[0]);
    expect(onClose).toHaveBeenCalled();
  });
});
