import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ComposeView } from '../ComposeView';

// vi.hoisted: vi.mock factories hoist above top-level consts.
const { mockStream, mockCritique } = vi.hoisted(() => ({
  mockStream: {
    ghost: '', streaming: false, jobId: null as string | null, error: null as string | null,
    start: vi.fn(), stop: vi.fn(), clearGhost: vi.fn(),
  },
  mockCritique: { critique: { mutate: vi.fn(), data: undefined as unknown }, dismiss: { mutate: vi.fn() } },
}));
vi.mock('../../hooks/useCompositionStream', () => ({ useCompositionStream: () => mockStream }));
vi.mock('../../hooks/useCritique', () => ({ useCritique: () => mockCritique }));

beforeEach(() => {
  vi.clearAllMocks();
  mockStream.ghost = '';
  mockStream.streaming = false;
  mockStream.jobId = null;
  mockCritique.critique.data = undefined;
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

  it('Generate is disabled until a scene AND a model are chosen', () => {
    const onAccept = vi.fn();
    const { rerender } = render(<ComposeView {...baseProps} modelRef="" onAccept={onAccept} />);
    expect((screen.getByText('generate') as HTMLButtonElement).disabled).toBe(true);
    rerender(<ComposeView {...baseProps} onAccept={onAccept} />);
    expect((screen.getByText('generate') as HTMLButtonElement).disabled).toBe(false);
  });
});
