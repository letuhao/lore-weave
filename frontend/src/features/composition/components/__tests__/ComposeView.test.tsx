import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ComposeView } from '../ComposeView';

// vi.hoisted: vi.mock factories hoist above top-level consts.
const { mockStream, mockCritique, mockAuto, mockCorrection } = vi.hoisted(() => ({
  mockStream: {
    ghost: '', streaming: false, jobId: null as string | null, error: null as string | null,
    start: vi.fn(), stop: vi.fn(), clearGhost: vi.fn(),
  },
  mockCritique: { critique: { mutate: vi.fn(), data: undefined as unknown }, dismiss: { mutate: vi.fn() } },
  mockAuto: { mutate: vi.fn(), reset: vi.fn(), data: undefined as unknown, isPending: false, isError: false },
  mockCorrection: { mutate: vi.fn(), isPending: false },
}));
// T5.4 — the co-writer stream is now consumed via the hoisted LiveStateContext, so
// the mock targets useLiveStream (ComposeView no longer calls useCompositionStream).
vi.mock('../../context/LiveStateContext', () => ({ useLiveStream: () => mockStream }));
vi.mock('../../hooks/useCritique', () => ({ useCritique: () => mockCritique }));
vi.mock('../../hooks/useAutoGenerate', () => ({
  useAutoGenerate: () => mockAuto,
  useCorrection: () => mockCorrection,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mockStream.ghost = '';
  mockStream.streaming = false;
  mockStream.jobId = null;
  mockCritique.critique.data = undefined;
  mockAuto.data = undefined;
  mockAuto.isPending = false;
  mockAuto.isError = false;
});

const baseProps = { projectId: 'p', sceneId: 's', modelRef: 'm', token: 'tok', guide: '', onGuideChange: vi.fn() };

// T3.1: `guide` is now a controlled prop (lifted to CompositionPanel). Tests that
// assert guide MUTATIONS (Revise pre-fill/append) need real state behind it.
function StatefulComposeView(props: Partial<typeof baseProps> & { onAccept: (t: string) => void }) {
  const [guide, setGuide] = useState('');
  return <ComposeView {...baseProps} {...props} guide={guide} onGuideChange={setGuide} />;
}

describe('ComposeView (ghost / accept — §13 SC4)', () => {
  it('does NOT surface the ghost to onAccept while streaming', () => {
    mockStream.ghost = 'streaming prose';
    mockStream.streaming = true;
    const onAccept = vi.fn();
    render(<ComposeView {...baseProps} onAccept={onAccept} />);
    // No Accept button while streaming → ghost can never be accepted/autosaved mid-stream
    expect(screen.queryByText('accept')).toBeNull();
    expect(onAccept).not.toHaveBeenCalled();
  });

  it('Accept inserts the ghost via onAccept, runs critique, and clears the ghost', () => {
    mockStream.ghost = 'drafted prose';
    mockStream.jobId = 'job-1';
    const onAccept = vi.fn(() => true); // insert succeeded → critique + clear proceed
    render(<ComposeView {...baseProps} onAccept={onAccept} />);
    fireEvent.click(screen.getByText('accept'));
    expect(onAccept).toHaveBeenCalledWith('drafted prose');
    // WS-B1: accept also wires an onSuccess that lifts the verdict to the shared store.
    expect(mockCritique.critique.mutate).toHaveBeenCalledWith(
      { jobId: 'job-1', passage: 'drafted prose' },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(mockStream.clearGhost).toHaveBeenCalled();
  });

  it('Accept that FAILS to insert (no editor) keeps the ghost — does NOT clear or critique (S1 GAP-2)', () => {
    mockStream.ghost = 'drafted prose';
    mockStream.jobId = 'job-1';
    const onAccept = vi.fn(() => false); // e.g. no editor open on this chapter in the dock
    render(<ComposeView {...baseProps} onAccept={onAccept} />);
    fireEvent.click(screen.getByText('accept'));
    expect(onAccept).toHaveBeenCalledWith('drafted prose');
    expect(mockStream.clearGhost).not.toHaveBeenCalled(); // draft preserved for a retry
    expect(mockCritique.critique.mutate).not.toHaveBeenCalled();
  });

  it('cowrite Regenerate captures a regenerate correction, then re-streams (slice 5)', () => {
    mockStream.ghost = 'a single draft';
    mockStream.jobId = 'cw-1';
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    fireEvent.click(screen.getByTestId('compose-regenerate'));
    expect(mockCorrection.mutate).toHaveBeenCalledWith({ jobId: 'cw-1', body: { kind: 'regenerate', guidance: '' } });
    expect(mockStream.start).toHaveBeenCalled();
  });

  it('cowrite Discard captures a reject correction, then clears the ghost (slice 5)', () => {
    mockStream.ghost = 'a single draft';
    mockStream.jobId = 'cw-1';
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    fireEvent.click(screen.getByTestId('compose-discard'));
    expect(mockCorrection.mutate).toHaveBeenCalledWith({ jobId: 'cw-1', body: { kind: 'reject' } });
    expect(mockStream.clearGhost).toHaveBeenCalled();
  });

  it('cowrite Accept as-is inserts WITHOUT a correction (H2)', () => {
    mockStream.ghost = 'a single draft';
    mockStream.jobId = 'cw-1';
    const onAccept = vi.fn();
    render(<ComposeView {...baseProps} onAccept={onAccept} />);
    fireEvent.click(screen.getByText('accept'));
    expect(onAccept).toHaveBeenCalledWith('a single draft');
    expect(mockCorrection.mutate).not.toHaveBeenCalled();
  });

  it('Generate is disabled until a scene AND a model are chosen', () => {
    const onAccept = vi.fn();
    const { rerender } = render(<ComposeView {...baseProps} modelRef="" onAccept={onAccept} />);
    expect((screen.getByText('generate') as HTMLButtonElement).disabled).toBe(true);
    rerender(<ComposeView {...baseProps} onAccept={onAccept} />);
    expect((screen.getByText('generate') as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('ComposeView (controlled-auto diverge gate — slice 3)', () => {
  it('with diverge OFF, Generate uses the live stream (not auto)', () => {
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    fireEvent.click(screen.getByTestId('compose-generate'));
    expect(mockStream.start).toHaveBeenCalledTimes(1);
    expect(mockAuto.mutate).not.toHaveBeenCalled();
  });

  it('with diverge ON, Generate runs auto-mode (K options), not the stream', () => {
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox')); // toggle Diverge on
    fireEvent.click(screen.getByTestId('compose-generate'));
    expect(mockAuto.mutate).toHaveBeenCalledTimes(1);
    expect(mockStream.start).not.toHaveBeenCalled();
  });

  it('renders the K candidate cards when auto returns, with the winner badged', () => {
    mockAuto.data = { job_id: 'j1', mode: 'auto', status: 'completed', text: 'B',
      winner_index: 1, k: 3, candidates: ['A', 'B', 'C'] };
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox')); // diverge on → cards show
    expect(screen.getByTestId('candidates-view')).toBeTruthy();
    expect(screen.getAllByTestId('candidate-card')).toHaveLength(3);
    const winner = screen.getAllByTestId('candidate-card').find((c) => c.getAttribute('data-winner') === 'true');
    expect(winner).toBeTruthy();
  });

  it('accepting the WINNER inserts it with NO correction (H2)', () => {
    mockAuto.data = { job_id: 'j1', mode: 'auto', status: 'completed', text: 'B',
      winner_index: 1, k: 3, candidates: ['A', 'B', 'C'] };
    const onAccept = vi.fn();
    render(<ComposeView {...baseProps} onAccept={onAccept} />);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getAllByTestId('candidate-use')[1]); // winner card
    expect(onAccept).toHaveBeenCalledWith('B');
    expect(mockCorrection.mutate).not.toHaveBeenCalled(); // accept-as-is is not a correction
    expect(mockAuto.reset).toHaveBeenCalled();
  });

  it('using a NON-winner captures pick_different then inserts it', () => {
    mockAuto.data = { job_id: 'j1', mode: 'auto', status: 'completed', text: 'B',
      winner_index: 1, k: 3, candidates: ['A', 'B', 'C'] };
    const onAccept = vi.fn();
    render(<ComposeView {...baseProps} onAccept={onAccept} />);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getAllByTestId('candidate-use')[2]); // candidate C (index 2)
    expect(mockCorrection.mutate).toHaveBeenCalledWith({
      jobId: 'j1', body: { kind: 'pick_different', chosen_candidate_index: 2 },
    });
    expect(onAccept).toHaveBeenCalledWith('C');
  });

  it('Reject all captures a reject correction and clears the cards', () => {
    mockAuto.data = { job_id: 'j1', mode: 'auto', status: 'completed', text: 'B',
      winner_index: 1, k: 3, candidates: ['A', 'B', 'C'] };
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByTestId('candidates-reject'));
    expect(mockCorrection.mutate).toHaveBeenCalledWith({ jobId: 'j1', body: { kind: 'reject' } });
    expect(mockAuto.reset).toHaveBeenCalled();
  });

  it('Regenerate captures a regenerate correction on the OLD job, then re-runs auto', () => {
    // /review-impl LOW#1: the regenerate correction must be captured against the
    // current (old) job_id BEFORE auto.mutate re-runs and replaces the result.
    mockAuto.data = { job_id: 'j-old', mode: 'auto', status: 'completed', text: 'B',
      winner_index: 1, k: 3, candidates: ['A', 'B', 'C'] };
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByTestId('candidates-regenerate'));
    expect(mockCorrection.mutate).toHaveBeenCalledWith({ jobId: 'j-old', body: { kind: 'regenerate', guidance: '' } });
    expect(mockAuto.mutate).toHaveBeenCalledTimes(1); // re-ran the generation
  });
});

describe('ComposeView (M1 — adapt from source)', () => {
  it('does NOT offer the adapt action by default (non-derivative / not adaptable)', () => {
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    expect(screen.queryByTestId('compose-adapt')).toBeNull();
  });

  it('offers "Adapt from source" when canAdapt; with diverge OFF it streams the adapt_scene op', () => {
    render(<ComposeView {...baseProps} onAccept={vi.fn()} canAdapt />);
    fireEvent.click(screen.getByTestId('compose-adapt'));
    expect(mockStream.start).toHaveBeenCalledWith(expect.objectContaining({ operation: 'adapt_scene', outlineNodeId: 's' }));
    expect(mockAuto.mutate).not.toHaveBeenCalled();
  });

  it('with diverge ON, adapt runs auto-mode (K cards) with the adapt_scene op', () => {
    render(<ComposeView {...baseProps} onAccept={vi.fn()} canAdapt />);
    fireEvent.click(screen.getByRole('checkbox')); // diverge on
    fireEvent.click(screen.getByTestId('compose-adapt'));
    expect(mockAuto.mutate).toHaveBeenCalledWith(expect.objectContaining({ operation: 'adapt_scene' }));
    expect(mockStream.start).not.toHaveBeenCalled();
  });

  it('the adapt action is hidden mid-stream (the Stop button owns that state)', () => {
    mockStream.streaming = true;
    render(<ComposeView {...baseProps} onAccept={vi.fn()} canAdapt />);
    expect(screen.queryByTestId('compose-adapt')).toBeNull();
  });

  it('shows a "nothing to adapt" hint when the source chapter is empty (no action offered)', () => {
    render(<ComposeView {...baseProps} onAccept={vi.fn()} adaptSourceEmpty />);
    expect(screen.queryByTestId('compose-adapt')).toBeNull();
    expect(screen.getByTestId('compose-adapt-empty')).toBeTruthy();
  });
});

describe('ComposeView (A2-S4a — canon gate panel + Revise)', () => {
  const withCanon = (over: Record<string, unknown> = {}) => ({
    job_id: 'j1', mode: 'auto', status: 'completed', text: 'B', winner_index: 0, k: 1, candidates: ['B'],
    canon: {
      violations: [{ kind: 'gone_entity_present', source: 'llm_judge', entity_id: 'e1',
        name: 'Castor', status: 'gone', matched: 'Castor', confirmed: true, why: 'died in ch3' }],
      resolved: false, iterations: 1, status: 'checked',
    },
    ...over,
  });

  it('renders the canon gate panel (hard) when auto returns a canon verdict', () => {
    mockAuto.data = withCanon();
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox')); // diverge on
    expect(screen.getByTestId('canon-gate-panel')).toBeTruthy();
    expect(screen.getByTestId('canon-hard')).toBeTruthy();
  });

  it('does NOT render the canon panel when the auto result has no canon (replay/cowrite)', () => {
    mockAuto.data = { job_id: 'j1', mode: 'auto', status: 'completed', text: 'B',
      winner_index: 0, k: 1, candidates: ['B'] }; // no canon field
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(screen.queryByTestId('canon-gate-panel')).toBeNull();
  });

  it('Revise pre-fills the guide textarea with the violation context + focuses it', () => {
    mockAuto.data = withCanon();
    render(<StatefulComposeView onAccept={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox'));
    const guide = screen.getByPlaceholderText('guidePlaceholder') as HTMLTextAreaElement;
    expect(guide.value).toBe('');
    fireEvent.click(screen.getByTestId('canon-revise-hard'));
    expect(guide.value).toContain('reviseGuide'); // the i18n key (mock) + the why
    expect(guide.value).toContain('died in ch3');
    expect(document.activeElement).toBe(guide);
  });

  it('Revise PRESERVES existing guidance — appends on a new line, never replaces', () => {
    // /review-impl #2 — the PO intent is "drop the violation context INTO the
    // guide"; author-typed guidance must survive.
    mockAuto.data = withCanon();
    render(<StatefulComposeView onAccept={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox'));
    const guide = screen.getByPlaceholderText('guidePlaceholder') as HTMLTextAreaElement;
    fireEvent.change(guide, { target: { value: 'my own guidance' } });
    fireEvent.click(screen.getByTestId('canon-revise-hard'));
    expect(guide.value).toContain('my own guidance');
    expect(guide.value).toContain('reviseGuide');
    expect(guide.value.indexOf('my own guidance')).toBeLessThan(guide.value.indexOf('reviseGuide'));
  });
});

describe('ComposeView (C26 — derivative override gate surfacing)', () => {
  it('surfaces a BLOCKING override-slip banner + findings + a Regenerate when needs_regeneration', () => {
    mockCritique.critique.data = { critic: {
      coherence: 4, voice_match: 3, pacing: 3, canon_consistency: 5, violations: [],
      needs_regeneration: true, regen_exhausted: false, regen_attempts: 1, regen_cap: 3,
      derivative_findings: [{ kind: 'override_slip', name: '张若尘', field: 'description',
        expected: '现在是女性', found: '少年天才' }],
    } };
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    const gate = screen.getByTestId('compose-override-gate');
    expect(gate).toBeTruthy();
    expect(gate.textContent).toContain('overrideSlipBlocked');
    // a per-finding detail line is rendered (the i18n mock returns the key, so we
    // assert the slip-detail key was used — it interpolates name/expected/found live).
    expect(gate.textContent).toContain('overrideSlipDetail');
    // a Regenerate affordance is offered
    expect(screen.getByTestId('compose-override-regenerate')).toBeTruthy();
  });

  it('FAIL-OPEN: regen_exhausted surfaces the finding but does NOT block (no Regenerate)', () => {
    mockCritique.critique.data = { critic: {
      coherence: 4, voice_match: 3, pacing: 3, canon_consistency: 5, violations: [],
      needs_regeneration: false, regen_exhausted: true, regen_attempts: 4, regen_cap: 3,
      derivative_findings: [{ kind: 'override_slip', name: '张若尘', field: 'description',
        expected: '现在是女性', found: '少年天才' }],
    } };
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    const gate = screen.getByTestId('compose-override-gate');
    expect(gate.textContent).toContain('overrideSlipExhausted');
    expect(screen.queryByTestId('compose-override-regenerate')).toBeNull();
  });

  it('a compliant critic (no derivative gate) renders no override banner', () => {
    mockCritique.critique.data = { critic: {
      coherence: 4, voice_match: 3, pacing: 3, canon_consistency: 5, violations: [],
    } };
    render(<ComposeView {...baseProps} onAccept={vi.fn()} />);
    expect(screen.queryByTestId('compose-override-gate')).toBeNull();
  });
});
