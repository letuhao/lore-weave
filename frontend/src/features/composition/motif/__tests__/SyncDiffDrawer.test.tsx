// WI-4 (D-MOTIF-SYNC-3WAY-BASE) — the upstream-merge review: only upstream-changed fields
// show, conflicts are flagged, accept→apply passes the chosen fields, keep-mine applies [].
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SyncDiffDrawer } from '../components/SyncDiffDrawer';
import type { SyncDiff } from '../types';

const DIFF: SyncDiff = {
  diff_mode: 'three_way',
  base_available: true,
  pinned_source_version: 1,
  upstream_version: 4,
  update_available: true,
  fields: {
    // both edited away from base, to different values → conflict
    summary: { base: 'orig', ours: 'mine', theirs: 'theirs', ours_changed: true, theirs_changed: true, conflict: true },
    // only upstream changed → clean take
    genre_tags: { base: ['a'], ours: ['a'], theirs: ['a', 'b'], ours_changed: false, theirs_changed: true, conflict: false },
    // nobody changed → must NOT appear
    beats: { base: [], ours: [], theirs: [], ours_changed: false, theirs_changed: false, conflict: false },
  },
};

function fakeSync(mutate = vi.fn()) {
  return {
    isAdopted: true, diff: DIFF, hasUpdate: true, isLoading: false, isError: false,
    apply: { mutate, isPending: false, isError: false, error: null },
  } as unknown as Parameters<typeof SyncDiffDrawer>[0]['sync'];
}

describe('SyncDiffDrawer', () => {
  it('shows only upstream-changed fields and flags conflicts', () => {
    render(<SyncDiffDrawer diff={DIFF} sync={fakeSync()} onClose={() => {}} />);
    expect(screen.getByTestId('sync-diff-field-summary')).toBeInTheDocument();
    expect(screen.getByTestId('sync-diff-field-genre_tags')).toBeInTheDocument();
    expect(screen.queryByTestId('sync-diff-field-beats')).toBeNull();   // unchanged → hidden
    expect(screen.getByTestId('sync-diff-conflict-summary')).toBeInTheDocument();
    expect(screen.queryByTestId('sync-diff-conflict-genre_tags')).toBeNull();
  });

  it('apply is disabled until a field is selected, then passes the accepted fields', () => {
    const mutate = vi.fn();
    render(<SyncDiffDrawer diff={DIFF} sync={fakeSync(mutate)} onClose={() => {}} />);
    expect(screen.getByTestId('sync-diff-apply')).toBeDisabled();
    fireEvent.click(screen.getByTestId('sync-diff-accept-genre_tags'));
    expect(screen.getByTestId('sync-diff-apply')).not.toBeDisabled();
    fireEvent.click(screen.getByTestId('sync-diff-apply'));
    expect(mutate).toHaveBeenCalledWith(['genre_tags']);
  });

  it('keep-all-mine applies an empty accept (re-pin only)', () => {
    const mutate = vi.fn();
    render(<SyncDiffDrawer diff={DIFF} sync={fakeSync(mutate)} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId('sync-diff-keep-mine'));
    expect(mutate).toHaveBeenCalledWith([]);
  });
});
