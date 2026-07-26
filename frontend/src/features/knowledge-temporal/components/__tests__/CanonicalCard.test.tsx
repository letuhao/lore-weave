import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CanonicalCard } from '../CanonicalCard';
import type { CanonicalSnapshot } from '../../types';

// i18n: honour the inline fallback (t(key, default)) so we can assert human text.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, def?: unknown) => {
      if (def && typeof def === 'object' && 'ordinal' in (def as Record<string, unknown>)) {
        return `as of chapter ${(def as { ordinal: number }).ordinal}`;
      }
      return typeof def === 'string' ? def : k;
    },
  }),
}));

// asOf is irrelevant to CanonicalCard's render branches (it only feeds the hook); pin it to head.
vi.mock('../../context/AsOfContext', () => ({
  useAsOf: () => ({ asOf: undefined, setAsOf: vi.fn() }),
}));

const useCanonicalMock = vi.fn();
vi.mock('../../hooks/useTemporalReads', () => ({
  useCanonical: (...args: unknown[]) => useCanonicalMock(...args),
}));

function setCanonical(
  over: Partial<CanonicalSnapshot> | null,
  state: { isLoading?: boolean; error?: Error | null } = {},
) {
  useCanonicalMock.mockReturnValue({
    canonical:
      over === null
        ? null
        : ({
            entity_id: 'e1',
            content: 'A weary swordsman.',
            as_of_ordinal: 4,
            canonical_status: 'current',
            source: 'snapshot',
            ...over,
          } as CanonicalSnapshot),
    isLoading: state.isLoading ?? false,
    error: state.error ?? null,
  });
}

describe('CanonicalCard', () => {
  beforeEach(() => {
    useCanonicalMock.mockReset();
  });

  it('renders a loading skeleton while the read is in flight', () => {
    setCanonical(null, { isLoading: true });
    render(<CanonicalCard bookId="b1" entityId="e1" />);
    const card = screen.getByTestId('canonical-card');
    expect(card.getAttribute('aria-busy')).toBe('true');
    expect(card.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('renders an inline error message on a failed read (never crashes)', () => {
    setCanonical(null, { error: new Error('boom') });
    render(<CanonicalCard bookId="b1" entityId="e1" />);
    const card = screen.getByTestId('canonical-card');
    expect(card.getAttribute('role')).toBe('alert');
    expect(card.textContent).toMatch(/could not load/i);
  });

  it('renders the folded content + a current status chip + as-of-chapter label (happy path)', () => {
    setCanonical({ content: 'A weary swordsman.', as_of_ordinal: 4, canonical_status: 'current' });
    render(<CanonicalCard bookId="b1" entityId="e1" />);
    expect(screen.getByTestId('canonical-content').textContent).toBe('A weary swordsman.');
    expect(screen.getByTestId('canonical-status').getAttribute('data-status')).toBe('current');
    expect(screen.getByTestId('canonical-asof-label').textContent).toBe('as of chapter 4');
  });

  it('shows "current" (not a chapter) when as_of_ordinal is the cold-start sentinel (-1)', () => {
    setCanonical({ as_of_ordinal: -1 });
    render(<CanonicalCard bookId="b1" entityId="e1" />);
    expect(screen.getByTestId('canonical-asof-label').textContent).toBe('current');
  });

  it('renders a degrade-safe message for an unbuildable canonical', () => {
    setCanonical({ canonical_status: 'unbuildable', content: '' });
    render(<CanonicalCard bookId="b1" entityId="e1" />);
    expect(screen.queryByTestId('canonical-content')).toBeNull();
    const degrade = screen.getByTestId('canonical-unbuildable');
    expect(degrade.textContent).toMatch(/degrade-safe/i);
    expect(screen.getByTestId('canonical-status').getAttribute('data-status')).toBe('unbuildable');
  });

  it('marks the stale status and notes the canon-content degrade source subtly', () => {
    setCanonical({ canonical_status: 'stale', source: 'canon-content', content: 'Older snapshot.' });
    render(<CanonicalCard bookId="b1" entityId="e1" />);
    expect(screen.getByTestId('canonical-status').getAttribute('data-status')).toBe('stale');
    expect(screen.getByTestId('canonical-source-note')).toBeTruthy();
    expect(screen.getByTestId('canonical-content').textContent).toBe('Older snapshot.');
  });

  it('passes the asOf (head=undefined) through to useCanonical', () => {
    setCanonical({});
    render(<CanonicalCard bookId="b1" entityId="e1" />);
    expect(useCanonicalMock).toHaveBeenCalledWith('b1', 'e1', undefined);
  });
});
