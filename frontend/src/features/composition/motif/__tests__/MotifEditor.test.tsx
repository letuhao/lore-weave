// WI-2 (D-MOTIF-FULL-EDITOR-FE) — the owned-motif editor: seed → edit → PATCH (If-Match),
// dirty/canSubmit gating, and the 412 conflict surface.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { motifApi } from '../api';
import { useMotifEditor } from '../hooks/useMotifEditor';
import { MotifEditorForm } from '../components/MotifEditorForm';
import type { Motif } from '../types';

const MOTIF: Motif = {
  id: 'm1', owner_user_id: 'u1', code: 'cultivation.x', language: 'en', visibility: 'private',
  kind: 'sequence', category: null, name: 'Old Name', summary: 'old', genre_tags: ['xianxia'],
  roles: [{ key: 'r1', actant: 'subject', label: 'hero' }],
  beats: [{ key: 'b1', label: 'isolation', order: 0 }, { key: 'b2', label: 'reversal', order: 1 }],
  preconditions: [{ text: 'weak' }], effects: [{ text: 'strong' }], tension_target: 3,
  emotion_target: null, info_asymmetry: null, examples: [], abstraction_confidence: null,
  source: 'authored', source_version: null, judge_score: null, mining_support: null,
  status: 'active', version: 7,
};

function Harness({ onSaved, motif = MOTIF }: { onSaved?: (m: Motif) => void; motif?: Motif }) {
  const ctrl = useMotifEditor(motif, 'tok', onSaved);
  return <MotifEditorForm ctrl={ctrl} onCancel={() => {}} />;
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('MotifEditor', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('seeds from the motif and is not submittable until dirty', () => {
    wrap(<Harness />);
    expect((screen.getByTestId('motif-editor-name') as HTMLInputElement).value).toBe('Old Name');
    expect(screen.getByTestId('motif-editor-save')).toBeDisabled();   // pristine
  });

  it('edits a field and PATCHes with the new value + the If-Match version', async () => {
    const patch = vi.spyOn(motifApi, 'patch').mockResolvedValue({ ...MOTIF, name: 'New Name', version: 8 });
    const onSaved = vi.fn();
    wrap(<Harness onSaved={onSaved} />);
    fireEvent.change(screen.getByTestId('motif-editor-name'), { target: { value: 'New Name' } });
    expect(screen.getByTestId('motif-editor-save')).not.toBeDisabled();
    fireEvent.click(screen.getByTestId('motif-editor-save'));
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    const [id, args, version] = patch.mock.calls[0];
    expect(id).toBe('m1');
    expect(version).toBe(7);                                 // optimistic lock = the seeded version
    expect(args).toMatchObject({ name: 'New Name', beats: [{ label: 'isolation' }, { label: 'reversal' }] });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it('reorders a beat (down) before saving', async () => {
    const patch = vi.spyOn(motifApi, 'patch').mockResolvedValue({ ...MOTIF, version: 8 });
    wrap(<Harness />);
    // beat 0 "isolation" moved down → order swaps with "reversal"
    fireEvent.click(screen.getAllByLabelText('down')[0]);
    fireEvent.click(screen.getByTestId('motif-editor-save'));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    const beats = (patch.mock.calls[0][1] as { beats: { label: string; order: number }[] }).beats;
    expect(beats.map((b) => b.label)).toEqual(['reversal', 'isolation']);
    expect(beats.map((b) => b.order)).toEqual([0, 1]);       // re-indexed on submit
  });

  it('does NOT discard in-progress edits when the motif refetches (version bumps)', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(<QueryClientProvider client={qc}><Harness /></QueryClientProvider>);
    fireEvent.change(screen.getByTestId('motif-editor-name'), { target: { value: 'Editing…' } });
    // a background refetch delivers the same motif with a bumped version (e.g. list invalidate)
    rerender(<QueryClientProvider client={qc}><Harness motif={{ ...MOTIF, version: 8, name: 'Old Name' }} /></QueryClientProvider>);
    // the edit survives — the seed effect re-runs only on a DIFFERENT motif id, not a version bump
    expect((screen.getByTestId('motif-editor-name') as HTMLInputElement).value).toBe('Editing…');
  });

  it('surfaces a 412 conflict instead of clobbering', async () => {
    vi.spyOn(motifApi, 'patch').mockRejectedValue(Object.assign(new Error('conflict'), { status: 412 }));
    wrap(<Harness />);
    fireEvent.change(screen.getByTestId('motif-editor-summary'), { target: { value: 'edited' } });
    fireEvent.click(screen.getByTestId('motif-editor-save'));
    await screen.findByTestId('motif-editor-conflict');
  });
});
