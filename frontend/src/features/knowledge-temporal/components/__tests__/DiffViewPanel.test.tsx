import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { Fact } from '../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_k: string, def?: string, opts?: Record<string, unknown>) => {
      let out = def ?? _k;
      if (opts) {
        for (const [key, val] of Object.entries(opts)) {
          out = out.replace(new RegExp(`{{\\s*${key}\\s*}}`, 'g'), String(val));
        }
      }
      return out;
    },
  }),
}));

// useFacts dispatches on the asOf opt so the head read and the as-of read return distinct fixtures.
const factsByAsOf = vi.fn();
vi.mock('../../hooks/useTemporalReads', () => ({
  useFacts: (_bookId: string, _entityId: string, opts?: { asOf?: number }) => factsByAsOf(opts?.asOf),
}));

const asOfValue = vi.fn();
vi.mock('../../context/AsOfContext', () => ({
  useAsOf: () => ({ asOf: asOfValue(), setAsOf: vi.fn() }),
}));

import { DiffViewPanel } from '../DiffViewPanel';

function fact(over: Partial<Fact>): Fact {
  return {
    fact_id: 'f-' + Math.random().toString(36).slice(2),
    entity_id: 'e1',
    fact_kind: 'attribute',
    attr_or_predicate: 'rank',
    value: 'Copper',
    valid_from_ordinal: 1,
    valid_to_ordinal: null,
    cardinality: 'single',
    ...over,
  };
}

const result = (
  over: Partial<{ facts: Fact[]; isLoading: boolean; error: Error | null }>,
) => ({ facts: [], isLoading: false, error: null, temporalCapability: undefined, ...over });

beforeEach(() => {
  factsByAsOf.mockReset();
  asOfValue.mockReset();
});

function renderPanel() {
  return render(<DiffViewPanel bookId="b1" entityId="e1" />);
}

describe('DiffViewPanel', () => {
  it('hints to move the slider when no as-of is set (head)', () => {
    asOfValue.mockReturnValue(undefined);
    factsByAsOf.mockReturnValue(result({}));
    renderPanel();
    expect(screen.getByTestId('diff-hint')).toBeInTheDocument();
    expect(screen.queryByTestId('diff-list')).toBeNull();
  });

  it('shows a loading state while either read is in flight', () => {
    asOfValue.mockReturnValue(5);
    factsByAsOf.mockImplementation((asOf?: number) =>
      asOf === undefined ? result({ isLoading: true }) : result({}),
    );
    renderPanel();
    expect(screen.getByTestId('diff-loading')).toBeInTheDocument();
  });

  it('shows an inline error without crashing', () => {
    asOfValue.mockReturnValue(5);
    factsByAsOf.mockImplementation((asOf?: number) =>
      asOf === undefined ? result({}) : result({ error: new Error('as-of read failed') }),
    );
    renderPanel();
    expect(screen.getByTestId('diff-error')).toHaveTextContent('as-of read failed');
  });

  it('computes ADDED / REMOVED / CHANGED across as-of vs head', () => {
    asOfValue.mockReturnValue(7);
    // as-of (chapter 7): has `rank=Iron` (will change) and `title=Outer Disciple` (will be removed).
    // head: has `rank=Silver` (changed) and `affinity=Fire` (added). `title` is gone (removed).
    factsByAsOf.mockImplementation((asOf?: number) => {
      if (asOf === undefined) {
        return result({
          facts: [
            fact({ attr_or_predicate: 'rank', value: 'Silver' }),
            fact({ attr_or_predicate: 'affinity', value: 'Fire' }),
          ],
        });
      }
      return result({
        facts: [
          fact({ attr_or_predicate: 'rank', value: 'Iron' }),
          fact({ attr_or_predicate: 'title', value: 'Outer Disciple' }),
        ],
      });
    });
    renderPanel();

    expect(screen.getByTestId('diff-list')).toBeInTheDocument();
    // Column headers interpolate the as-of ordinal.
    expect(screen.getByTestId('diff-col-asof')).toHaveTextContent('At chapter 7');
    expect(screen.getByTestId('diff-col-head')).toHaveTextContent('Current');

    // CHANGED: rank Iron → Silver.
    const changed = screen.getByTestId('diff-row-changed');
    expect(changed).toHaveTextContent('rank');
    expect(changed).toHaveTextContent('Iron');
    expect(changed).toHaveTextContent('Silver');

    // ADDED: affinity present only at head.
    const added = screen.getByTestId('diff-row-added');
    expect(added).toHaveTextContent('affinity');
    expect(added).toHaveTextContent('Fire');

    // REMOVED: title present only at as-of.
    const removed = screen.getByTestId('diff-row-removed');
    expect(removed).toHaveTextContent('title');
    expect(removed).toHaveTextContent('Outer Disciple');
  });

  it('omits unchanged attrs and shows the no-changes card when nothing differs', () => {
    asOfValue.mockReturnValue(3);
    factsByAsOf.mockReturnValue(result({ facts: [fact({ attr_or_predicate: 'rank', value: 'Copper' })] }));
    renderPanel();
    expect(screen.getByTestId('diff-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('diff-list')).toBeNull();
  });

  it('ignores multi-valued facts (no single current value to diff)', () => {
    asOfValue.mockReturnValue(4);
    factsByAsOf.mockImplementation((asOf?: number) => {
      if (asOf === undefined) {
        return result({ facts: [fact({ attr_or_predicate: 'allies', value: 'Mei', cardinality: 'multi' })] });
      }
      return result({ facts: [] });
    });
    renderPanel();
    // The multi-valued add is not surfaced as a diff row.
    expect(screen.getByTestId('diff-empty')).toBeInTheDocument();
  });
});
