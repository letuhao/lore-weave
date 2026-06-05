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
vi.mock('../../hooks/useCompositionStream', () => ({ useCompositionStream: () => mockStream }));
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

const baseProps = { projectId: 'p', sceneId: 's', modelRef: 'm', token: 'tok' };

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
    const onAccept = vi.fn();
    render(<ComposeView {...baseProps} onAccept={onAccept} />);
    fireEvent.click(screen.getByText('accept'));
    expect(onAccept).toHaveBeenCalledWith('drafted prose');
    expect(mockCritique.critique.mutate).toHaveBeenCalledWith({ jobId: 'job-1', passage: 'drafted prose' });
    expect(mockStream.clearGhost).toHaveBeenCalled();
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
