// /review-impl cross-hook finding (#16 Phase 1 integration) — useManuscriptCheckpoints (1.2) and
// useRevisionHistory (1.3) are two independent hook instances that both restore the SAME chapter's
// server-side chapter_revision spine. Built in isolation by separate agents, neither knew about the
// other. This suite mounts BOTH against the SAME real ManuscriptUnitProvider (not mocks) to prove
// a restore triggered by ONE hook keeps the OTHER's cached state correct — the actual bug: before
// the fix, a Revision-History-triggered restore left Checkpoints' internal "latest revision" ref
// stale, so the NEXT AI-edit checkpoint captured the WRONG restore point (reverting further back
// than "just before this edit"). Each hook makes its OWN independent `listRevisions` call (they
// don't share a request), so assertions below check functional outcome (what each hook's state
// ends up holding), not brittle call counts.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, render, waitFor } from '@testing-library/react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 't' }) }));

const getDraft = vi.fn();
const patchDraft = vi.fn();
const listRevisions = vi.fn();
const restoreRevision = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: {
    getDraft: (...a: unknown[]) => getDraft(...a),
    patchDraft: (...a: unknown[]) => patchDraft(...a),
    listRevisions: (...a: unknown[]) => listRevisions(...a),
    restoreRevision: (...a: unknown[]) => restoreRevision(...a),
  },
}));
vi.mock('@/lib/tiptap-utils', () => ({ addTextSnapshots: (d: unknown) => d, extractText: () => '' }));
vi.mock('@/features/composition/hooks/useWork', () => ({ useWorkResolution: () => ({ data: null }) }));
vi.mock('@/features/composition/hooks/useProgress', () => ({
  useReportProgress: () => vi.fn(),
  useEnsureBaseline: () => vi.fn(),
}));
vi.mock('@/features/composition/api', () => ({
  compositionApi: { listChapterScenes: vi.fn(async () => ({ items: [] })), patchNode: vi.fn() },
}));
const bus = vi.hoisted(() => ({ activeChapterId: undefined as string | undefined }));
vi.mock('../../../host/StudioHostProvider', () => ({
  useStudioHost: () => ({ bookId: 'b1' }),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useStudioBusSelector: (sel: any) => sel({ activeChapterId: bus.activeChapterId }),
}));

import { ManuscriptUnitProvider, useManuscriptUnit } from '../ManuscriptUnitProvider';
import { useManuscriptCheckpoints } from '../useManuscriptCheckpoints';
import { useRevisionHistory } from '../useRevisionHistory';

const doc = (t: string) => ({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: t }] }] });

type CheckpointsHook = ReturnType<typeof useManuscriptCheckpoints>;
type RevisionHook = ReturnType<typeof useRevisionHistory>;
type UnitHook = ReturnType<typeof useManuscriptUnit>;

let cpApi: CheckpointsHook | null = null;
let revApi: RevisionHook | null = null;
let unitApi: UnitHook = null;

// All three mounted side by side against the SAME unit — exactly how EditorPanel.tsx wires them.
function Harness() {
  const unit = useManuscriptUnit();
  unitApi = unit;
  cpApi = useManuscriptCheckpoints('b1', unit);
  revApi = useRevisionHistory(unit, 'b1');
  return null;
}
const renderHoist = () => render(<ManuscriptUnitProvider bookId="b1"><Harness /></ManuscriptUnitProvider>);

const REV_A_LATEST = { items: [{ revision_id: 'rev-A', created_at: 't1' }], total: 1 };
const REV_B_LATEST = { items: [{ revision_id: 'rev-B', created_at: 't2' }, { revision_id: 'rev-A', created_at: 't1' }], total: 2 };

beforeEach(() => {
  getDraft.mockReset();
  patchDraft.mockReset();
  listRevisions.mockReset();
  restoreRevision.mockReset();
  bus.activeChapterId = undefined;
  cpApi = null;
  revApi = null;
  unitApi = null;
  getDraft.mockResolvedValue({ chapter_id: 'ch1', body: doc('v1'), draft_version: 1, text_content: 'v1' });
  listRevisions.mockResolvedValue(REV_A_LATEST);
  restoreRevision.mockResolvedValue({});
});

// The real ManuscriptUnitProvider.applyProposedEdit delegates to editorRef.current — EditorPanel
// wires that to the live TiptapEditor; here there is none, so give it a fake handle (same shape
// ManuscriptUnitProvider.test.tsx uses) or every applyProposedEdit call silently returns false.
function wireFakeEditor() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  unitApi!.editorRef.current = { replaceSelection: () => true, insertAtCursor: () => true } as any;
}

describe('Checkpoints + Revision History cross-hook sync (#16 Phase 1 /review-impl fix)', () => {
  it('a Revision-History-triggered restore refreshes the Checkpoints restore point (no stale preRevisionId)', async () => {
    renderHoist();
    await act(async () => { await unitApi!.openUnit('ch1'); });
    wireFakeEditor();
    await waitFor(() => expect(cpApi!.visibleCheckpoints).toEqual([])); // settled, no crash

    // An AI edit lands NOW, before any restore — captures a checkpoint pinned to rev-A (the only
    // revision that exists at this point).
    act(() => { cpApi!.applyProposedEdit({ operation: 'insert_at_cursor', text: 'ai text' }); });
    expect(cpApi!.visibleCheckpoints[0].preRevisionId).toBe('rev-A');

    // The USER restores via the Revision History panel (a DIFFERENT hook instance) — this bumps
    // state.version via reload(), and the server's "latest" moves to "rev-B".
    getDraft.mockResolvedValue({ chapter_id: 'ch1', body: doc('restored'), draft_version: 2, text_content: 'restored' });
    listRevisions.mockResolvedValue(REV_B_LATEST);
    await act(async () => { await revApi!.restore('rev-A'); });

    // Wait for the shared version-watch to settle (proxied via the SIBLING hook's own list, which
    // is driven by the identical version signal and thus a reliable "both effects have flushed"
    // marker) BEFORE capturing a new checkpoint — calling applyProposedEdit repeatedly inside a
    // retrying waitFor would pollute the list with duplicate captures.
    await waitFor(() => expect(revApi!.revisions[0].revision_id).toBe('rev-B'));

    // Checkpoints' OWN restore-point tracking must have picked up the new latest ("rev-B") too —
    // NOT still be pointing at the pre-restore "rev-A". Prove it the only observable way: capture
    // a NEW checkpoint now and check its preRevisionId advanced.
    act(() => { cpApi!.applyProposedEdit({ operation: 'insert_at_cursor', text: 'second ai text' }); });
    expect(cpApi!.visibleCheckpoints[0].preRevisionId).toBe('rev-B');
  });

  it('a Checkpoints-triggered restore refreshes the Revision History list', async () => {
    renderHoist();
    await act(async () => { await unitApi!.openUnit('ch1'); });
    wireFakeEditor();
    await waitFor(() => expect(revApi!.revisions).toHaveLength(1));
    expect(revApi!.revisions[0].revision_id).toBe('rev-A');

    act(() => { cpApi!.applyProposedEdit({ operation: 'insert_at_cursor', text: 'ai text' }); });
    const cp = cpApi!.visibleCheckpoints[0];

    getDraft.mockResolvedValue({ chapter_id: 'ch1', body: doc('v1'), draft_version: 2, text_content: 'v1' });
    listRevisions.mockResolvedValue(REV_B_LATEST);
    await act(async () => { await cpApi!.restore(cp.id); });

    // Revision History's list refreshed too — same mechanism, opposite direction. Without the
    // fix, this would still show only rev-A until the user switched chapters and back.
    await waitFor(() => expect(revApi!.revisions[0].revision_id).toBe('rev-B'));
  });
});
