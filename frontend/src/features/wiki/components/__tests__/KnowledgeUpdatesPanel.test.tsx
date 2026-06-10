import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) =>
      o?.count != null ? `${k}:${o.count}` : o?.defaultValue != null ? (o.defaultValue as string) : k,
  }),
}));

const dismiss = vi.fn();
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

beforeEach(() => {
  vi.clearAllMocks();
  useWikiStalenessMock.mockReturnValue({
    rows: [
      row({ staleness_id: 's1', entity_id: 'e1', display_name: 'Mina', reason_code: 'citation_broken', severity: 'hard' }),
      row({ staleness_id: 's2', entity_id: 'e1', display_name: 'Mina', reason_code: 'entity_changed', severity: 'content' }),
      row({ staleness_id: 's3', entity_id: 'e2', display_name: 'Lucy', reason_code: 'entity_changed', severity: 'content' }),
    ],
    count: 3, isLoading: false, dismiss, dismissing: null,
  });
});

describe('KnowledgeUpdatesPanel', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <KnowledgeUpdatesPanel bookId="b" open={false} onClose={() => {}} onRegenerate={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows the empty state when there are no stale rows', () => {
    useWikiStalenessMock.mockReturnValue({ rows: [], count: 0, isLoading: false, dismiss, dismissing: null });
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
});
