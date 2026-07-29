// The keep-or-drop step, and the three things it must never get wrong.
//
// It REUSES PassArtifactEditor rather than adding a second list editor, so these tests are as much
// about that reuse holding as about the new component: the editor's whole-list-back save is what
// makes "I removed this row" actually mean "drop it".
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MaterialReview } from '../MaterialReview';
import type { MaterialReviewState } from '../../hooks/useMaterialReview';
import type { MaterialPacket } from '../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string } & Record<string, unknown>) => {
    let s = o?.defaultValue ?? _k;
    for (const [k, v] of Object.entries(o ?? {})) {
      if (k !== 'defaultValue') s = s.replace(`{{${k}}}`, String(v));
    }
    return s;
  } }),
}));

const PACKET: MaterialPacket = {
  version: 1,
  recovered: ['character_seed'],
  review: [
    {
      kind: 'planner_variables', status: 'unknown', dropped_ungrounded: 1, note: '1 dropped',
      candidates: [
        { quote: 'Ký ức ↓ Nhân cách ↓ Ý chí ↓ Đạo tâm ↓ Chân Linh', why: 'a tracked list' },
        { quote: 'Chân Linh là bất biến.', why: 'looks like a rule' },
      ],
    },
  ],
  ask: [{ kind: 'writing_principles', status: 'absent', question: 'How should the prose read?' }],
  unavailable: [{ kind: 'mechanics', status: 'unknown', reason: 'the search did not complete' }],
  read: { failed: false, unclassified: [], note: '' },
};

function state(over: Partial<MaterialReviewState> = {}): MaterialReviewState {
  return {
    packet: PACKET, busy: false, error: null, result: null,
    kept: { planner_variables: PACKET.review[0].candidates.map((c) => c.quote) },
    find: vi.fn(), setKept: vi.fn(), keep: vi.fn(), reset: vi.fn(),
    ...over,
  };
}

beforeEach(() => vi.clearAllMocks());

it('renders every found line as an editable row', () => {
  render(<MaterialReview state={state()} />);
  expect(screen.getByTestId('material-review-editor')).toBeInTheDocument();
  expect(screen.getByDisplayValue('Ký ức ↓ Nhân cách ↓ Ý chí ↓ Đạo tâm ↓ Chân Linh')).toBeInTheDocument();
  expect(screen.getByDisplayValue('Chân Linh là bất biến.')).toBeInTheDocument();
});

it('an UNAVAILABLE kind is never rendered as a question', () => {
  // The bucket that matters most: the search could not run, so we do not know the material is
  // missing. Presenting it as a gap asks the author to rewrite what they may already have written.
  render(<MaterialReview state={state()} />);
  const unavailable = screen.getByTestId('material-unavailable-mechanics');
  expect(unavailable).toBeInTheDocument();
  expect(unavailable.textContent).not.toContain('?');
  expect(screen.queryByTestId('material-ask-mechanics')).toBeNull();
});

it('an ASK row on an incompletely-read document says the absence is not certain', () => {
  const p = { ...PACKET, ask: [{ kind: 'writing_principles', status: 'unknown' as const, question: 'How?' }] };
  render(<MaterialReview state={state({ packet: p })} />);
  expect(screen.getByTestId('material-ask-writing_principles').textContent)
    .toContain('not fully read');
});

it('dropping a row sends the SURVIVORS, not the original list', async () => {
  // The reuse earning itself: PassArtifactEditor sends the whole list back, so removal is real.
  const setKept = vi.fn();
  const keep = vi.fn();
  render(<MaterialReview state={state({ setKept, keep })} />);

  const removes = screen.getAllByRole('button', { name: /remove|delete|×|✕/i });
  await userEvent.click(removes[1]);              // drop the second, wrong-looking line
  await userEvent.click(screen.getByRole('button', { name: /save/i }));

  await waitFor(() => expect(setKept).toHaveBeenCalled());
  expect(setKept).toHaveBeenCalledWith('planner_variables',
    ['Ký ức ↓ Nhân cách ↓ Ý chí ↓ Đạo tâm ↓ Chân Linh']);
  expect(keep).toHaveBeenCalled();
});

it('dropping EVERY row sends an explicit empty list, not a missing key', async () => {
  // `kinds_to_ask` re-opens a kind whose candidates were all dropped. A missing key would read as
  // "untouched" and the question would never come back — the auto-conclude bug wearing a review UI.
  const setKept = vi.fn();
  render(<MaterialReview state={state({ setKept })} />);
  const removes = screen.getAllByRole('button', { name: /remove|delete|×|✕/i });
  await userEvent.click(removes[1]);
  await userEvent.click(screen.getAllByRole('button', { name: /remove|delete|×|✕/i })[0]);
  await userEvent.click(screen.getByRole('button', { name: /save/i }));
  await waitFor(() => expect(setKept).toHaveBeenCalledWith('planner_variables', []));
});

it('says how many suggestions were discarded as not actually in the document', () => {
  render(<MaterialReview state={state()} />);
  expect(screen.getByTestId('material-dropped-note').textContent).toContain('1');
});

it('a failed read is called out so "missing" is not read as certain', () => {
  const p = { ...PACKET, read: { failed: true, unclassified: [], note: 'x' } };
  render(<MaterialReview state={state({ packet: p })} />);
  expect(screen.getByTestId('material-read-failed')).toBeInTheDocument();
});

it('idle shows what actually happened after a keep, split by destination', () => {
  render(<MaterialReview state={state({
    packet: null,
    result: { run_id: 'r', changed: true,
              applied_to_slot: { writing_principles: 1 },
              carried_as_author_notes: { planner_variables: 1 } },
  })} />);
  const txt = screen.getByTestId('material-review-result').textContent ?? '';
  // "filed as a note" must never read as "added to your plan"
  expect(txt).toContain('Added to the plan: How it should read');
  expect(txt).toContain('Filed as notes: What changes over the story');
});

it('a nothing-missing packet says so instead of rendering three empty headings', () => {
  render(<MaterialReview state={state({
    packet: { ...PACKET, review: [], ask: [], unavailable: [] },
  })} />);
  expect(screen.getByTestId('material-nothing')).toBeInTheDocument();
});

it('the unavailable bucket offers a retry — it told the author to try again with nothing to press', async () => {
  const find = vi.fn();
  render(<MaterialReview state={state({ find })} />);
  await userEvent.click(screen.getByTestId('material-retry-btn'));
  expect(find).toHaveBeenCalled();
});

it('no retry button when nothing was unavailable', () => {
  render(<MaterialReview state={state({ packet: { ...PACKET, unavailable: [] } })} />);
  expect(screen.queryByTestId('material-retry-btn')).toBeNull();
});

it('a STALE packet is shown, not hidden — and says so', () => {
  // The candidates are still the author's own words, so hiding them helps nobody. Silently
  // reviewing a plan that has moved on is the lie.
  render(<MaterialReview state={state({ packet: { ...PACKET, stale: true } })} />);
  expect(screen.getByTestId('material-stale')).toBeInTheDocument();
  expect(screen.getByTestId('material-review-editor')).toBeInTheDocument();
});

it('a fresh packet shows no stale banner', () => {
  render(<MaterialReview state={state()} />);
  expect(screen.queryByTestId('material-stale')).toBeNull();
});
