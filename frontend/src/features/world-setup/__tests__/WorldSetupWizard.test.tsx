// World Setup wizard — the three human checkpoints must actually gate the pipeline,
// and honest reporting (skips, unresolved edges) must reach the screen.
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { WorldSetupWizard } from '../components/WorldSetupWizard';
import type { BuildRun } from '../types';

const api = vi.hoisted(() => ({
  createRun: vi.fn(),
  plan: vi.fn(),
  approvePlan: vi.fn(),
  get: vi.fn(),
  projectKg: vi.fn(),
  approveEdges: vi.fn(),
  cancel: vi.fn(),
  list: vi.fn(),
}));
vi.mock('../api', () => ({ worldSetupApi: api }));

const RUN: BuildRun = {
  run_id: 'r1', book_id: 'b1', status: 'draft', params: {},
  worklist: [], edges: [], error_message: null,
};
const planReady: BuildRun = {
  ...RUN, status: 'plan_ready',
  worklist: [
    { name: 'Tô Thanh Dao', kind: 'character', depth: 'deep', why: 'the fiancée' },
    { name: 'Lòng tốt', kind: 'terminology', depth: 'standard' },
  ],
};

function setup() {
  return render(<WorldSetupWizard bookId="b1" token="t" modelRef="m1" />);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.createRun.mockResolvedValue(RUN);
  api.plan.mockResolvedValue(planReady);
});

describe('WorldSetupWizard', () => {
  it('plans from a description and shows the worklist BEFORE anything is built', async () => {
    const user = userEvent.setup();
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));

    await screen.findByTestId('world-setup-worklist');
    expect(screen.getByText('Tô Thanh Dao')).toBeInTheDocument();
    expect(screen.getByText('deep profile')).toBeInTheDocument();
    // checkpoint 1: nothing is built until the human approves
    expect(api.approvePlan).not.toHaveBeenCalled();
  });

  it('[checkpoint 1] sends only the items the human KEPT', async () => {
    const user = userEvent.setup();
    api.approvePlan.mockResolvedValue({ ...planReady, status: 'building', items: [] });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));
    await screen.findByTestId('world-setup-worklist');

    await user.click(screen.getByLabelText('Include Lòng tốt'));   // untick one
    await user.click(screen.getByTestId('world-setup-approve-plan'));

    expect(api.approvePlan).toHaveBeenCalledWith(
      'r1', [expect.objectContaining({ name: 'Tô Thanh Dao' })], 't',
    );
  });

  it('reports SKIPPED items honestly instead of only counting successes', async () => {
    const user = userEvent.setup();
    api.approvePlan.mockResolvedValue({
      ...planReady, status: 'proposed',
      items: [
        { item_id: 'i1', ordinal: 0, name: 'Tô Thanh Dao', kind: 'character', depth: 'deep',
          status: 'proposed', skip_reason: null, proposed_entity_id: 'e1', relations: [], section_count: 6 },
        { item_id: 'i2', ordinal: 1, name: 'Lòng tốt', kind: 'terminology', depth: 'standard',
          status: 'skipped', skip_reason: 'invalid model output after retry',
          proposed_entity_id: null, relations: [], section_count: 0 },
      ],
    });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));
    await screen.findByTestId('world-setup-worklist');
    await user.click(screen.getByTestId('world-setup-approve-plan'));

    const skipped = await screen.findByTestId('world-setup-skipped');
    expect(skipped).toHaveTextContent('Lòng tốt');
    expect(skipped).toHaveTextContent('invalid model output after retry');
  });

  it('[checkpoint 3] writes only RESOLVED edges and surfaces the unresolved ones', async () => {
    const user = userEvent.setup();
    api.approvePlan.mockResolvedValue({ ...planReady, status: 'proposed', items: [] });
    api.projectKg.mockResolvedValue({
      ...planReady, status: 'edges_ready', items: [],
      edges: [
        { source_name: 'A', source_id: 's1', target_name: 'B', target_id: 't1',
          type: 'loves', unresolved: false },
        { source_name: 'A', source_id: 's1', target_name: 'Ghost', target_id: null,
          type: 'ally_of', unresolved: true },
      ],
    });
    api.approveEdges.mockResolvedValue({ ...planReady, status: 'done', items: [] });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));
    await screen.findByTestId('world-setup-worklist');
    await user.click(screen.getByTestId('world-setup-approve-plan'));

    await user.click(await screen.findByTestId('world-setup-project-kg'));
    await screen.findByTestId('world-setup-edges');
    // the unresolved one is VISIBLE (never silently dropped)…
    expect(screen.getByTestId('world-setup-unresolved')).toHaveTextContent('Ghost');
    // …but only the resolved one is offered for saving
    await user.click(screen.getByTestId('world-setup-approve-edges'));
    expect(api.approveEdges).toHaveBeenCalledWith(
      'r1', [expect.objectContaining({ target_name: 'B' })], 't',
    );
  });

  it('surfaces a server error code+message instead of failing silently', async () => {
    const user = userEvent.setup();
    api.plan.mockRejectedValue({ body: { detail: { code: 'EMPTY_PLAN', message: 'planner produced no items' } } });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));

    await waitFor(() => expect(screen.getByTestId('world-setup-error'))
      .toHaveTextContent('EMPTY_PLAN: planner produced no items'));
  });

  it('cannot start without a model (BYOK ref is required)', () => {
    render(<WorldSetupWizard bookId="b1" token="t" modelRef={null} />);
    expect(screen.getByTestId('world-setup-start')).toBeDisabled();
  });

  // The lore exists but nothing can RETRIEVE it. This degrade used to be invisible:
  // the packer's lore lens searched passages, `source_type='glossary'` had no producer,
  // and a book with no embedding model quietly drafted from bare names.
  it('warns when built lore was saved but could NOT be indexed for retrieval', async () => {
    const user = userEvent.setup();
    api.approvePlan.mockResolvedValue({ ...planReady, status: 'proposed', items: [] });
    api.projectKg.mockResolvedValue({
      ...planReady, status: 'edges_ready', edges: [],
      params: { lore_index: { entities_seen: 12, outcomes: { no_embedding_model: 12 } } },
    });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));
    await screen.findByTestId('world-setup-worklist');
    await user.click(screen.getByTestId('world-setup-approve-plan'));
    await user.click(screen.getByTestId('world-setup-project-kg'));

    const warn = await screen.findByTestId('world-setup-lore-not-indexed');
    expect(warn).toHaveTextContent('12');
    expect(warn).toHaveTextContent('not searchable');
  });

  // The banner used to sum EVERY non-indexing outcome and then explain the total with a
  // single cause. The server emits five outcomes needing three different fixes, so an
  // author could be sent to change a setting that was already correct.
  it('names the REAL reason per outcome instead of assuming one cause', async () => {
    const user = userEvent.setup();
    api.approvePlan.mockResolvedValue({ ...planReady, status: 'proposed', items: [] });
    api.projectKg.mockResolvedValue({
      ...planReady, status: 'edges_ready', edges: [],
      params: {
        lore_index: {
          entities_seen: 12,
          outcomes: { indexed: 4, unsupported_dim: 5, embed_failed: 3 },
        },
      },
    });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));
    await screen.findByTestId('world-setup-worklist');
    await user.click(screen.getByTestId('world-setup-approve-plan'));
    await user.click(screen.getByTestId('world-setup-project-kg'));

    const warn = await screen.findByTestId('world-setup-lore-not-indexed');
    expect(warn).toHaveTextContent('8');  // 5 + 3, NOT the 4 that indexed fine
    expect(screen.getByTestId('world-setup-lore-reason-unsupported_dim'))
      .toHaveTextContent('vector size is not supported');
    expect(screen.getByTestId('world-setup-lore-reason-embed_failed'))
      .toHaveTextContent('embedding calls failed');
    // The wrong advice must NOT appear: nothing here is about a missing model.
    expect(warn).not.toHaveTextContent('no embedding model');
  });

  // `empty` means the entity had no prose to index — expected, not a degrade. Counting
  // it reported a healthy book as broken.
  it('does not treat an entity with nothing to index as a failure', async () => {
    const user = userEvent.setup();
    api.approvePlan.mockResolvedValue({ ...planReady, status: 'proposed', items: [] });
    api.projectKg.mockResolvedValue({
      ...planReady, status: 'edges_ready', edges: [],
      params: { lore_index: { entities_seen: 12, outcomes: { indexed: 10, empty: 2 } } },
    });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));
    await screen.findByTestId('world-setup-worklist');
    await user.click(screen.getByTestId('world-setup-approve-plan'));
    await user.click(screen.getByTestId('world-setup-project-kg'));
    await screen.findByTestId('world-setup-edges');

    expect(screen.queryByTestId('world-setup-lore-not-indexed')).toBeNull();
  });

  // The property worth keeping from the first version: a reason added server-side later
  // must still surface rather than silently read as "all good".
  it('still surfaces an outcome token it has never seen', async () => {
    const user = userEvent.setup();
    api.approvePlan.mockResolvedValue({ ...planReady, status: 'proposed', items: [] });
    api.projectKg.mockResolvedValue({
      ...planReady, status: 'edges_ready', edges: [],
      params: { lore_index: { entities_seen: 5, outcomes: { quota_exhausted: 5 } } },
    });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));
    await screen.findByTestId('world-setup-worklist');
    await user.click(screen.getByTestId('world-setup-approve-plan'));
    await user.click(screen.getByTestId('world-setup-project-kg'));

    expect(await screen.findByTestId('world-setup-lore-reason-quota_exhausted'))
      .toHaveTextContent('unrecognised reason');
  });

  it('stays quiet when everything indexed', async () => {
    const user = userEvent.setup();
    api.approvePlan.mockResolvedValue({ ...planReady, status: 'proposed', items: [] });
    api.projectKg.mockResolvedValue({
      ...planReady, status: 'edges_ready', edges: [],
      params: { lore_index: { entities_seen: 12, outcomes: { indexed: 9, unchanged: 3 } } },
    });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));
    await screen.findByTestId('world-setup-worklist');
    await user.click(screen.getByTestId('world-setup-approve-plan'));
    await user.click(screen.getByTestId('world-setup-project-kg'));
    await screen.findByTestId('world-setup-edges');

    expect(screen.queryByTestId('world-setup-lore-not-indexed')).toBeNull();
  });
});

// ── ACTIVE_RUN must have a way out (2026-08-03) ──────────────────────────────────────────
//
// The server allows one in-flight run per book and answers ACTIVE_RUN. The panel printed
// that code and stopped: no run id, no resume, no cancel. Found on a real book — a run had
// sat at `edges_ready` since 27 July, so `/plan` refused with ACTIVE_RUN while `/cancel`
// refused with BAD_STATE (that half is fixed in the service). From the UI the book simply
// could not be set up again, and nothing on screen said why or what to do.

const ACTIVE_RUN_ERROR = {
  body: { detail: { code: 'ACTIVE_RUN', message: 'this book already has a build run in progress' } },
};

describe('WorldSetupWizard — ACTIVE_RUN', () => {
  it('offers the blocking run instead of only printing the code', async () => {
    const user = userEvent.setup();
    api.plan.mockRejectedValue(ACTIVE_RUN_ERROR);
    api.list.mockResolvedValue({ items: [{ ...RUN, run_id: 'stuck', status: 'edges_ready' }] });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));

    const box = await screen.findByTestId('world-setup-blocked');
    // by CONTENT, not by presence: a box rendering `undefined` is present and visible
    expect(box.textContent).toContain('edges_ready');
    expect(box.textContent).toContain('Relationships');
    expect(screen.getByTestId('world-setup-blocked-resume')).toBeInTheDocument();
    expect(screen.getByTestId('world-setup-blocked-cancel')).toBeInTheDocument();
    // the raw code no longer occupies the screen alone
    expect(screen.queryByTestId('world-setup-error')).toBeNull();
  });

  it('RESUME jumps to the checkpoint the stuck run is waiting at', async () => {
    const user = userEvent.setup();
    api.plan.mockRejectedValue(ACTIVE_RUN_ERROR);
    api.list.mockResolvedValue({
      items: [{ ...planReady, run_id: 'stuck', status: 'plan_ready' }],
    });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));
    await user.click(await screen.findByTestId('world-setup-blocked-resume'));

    // step 1 — the plan the earlier run had already produced, not a fresh empty one
    await screen.findByTestId('world-setup-worklist');
    expect(screen.getByText('Tô Thanh Dao')).toBeInTheDocument();
  });

  it('CANCEL releases the slot and returns to Describe', async () => {
    const user = userEvent.setup();
    api.plan.mockRejectedValue(ACTIVE_RUN_ERROR);
    api.list.mockResolvedValue({ items: [{ ...RUN, run_id: 'stuck', status: 'edges_ready' }] });
    api.cancel.mockResolvedValue({ ...RUN, run_id: 'stuck', status: 'cancelled' });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));
    await user.click(await screen.findByTestId('world-setup-blocked-cancel'));

    await waitFor(() => expect(api.cancel).toHaveBeenCalledWith('stuck', 't'));
    await waitFor(() => expect(screen.queryByTestId('world-setup-blocked')).toBeNull());
    expect(screen.getByTestId('world-setup-text')).toBeInTheDocument();
  });

  it('CONTROL — an ordinary error still renders as an error, with no escape offered', async () => {
    // Without this the box could be shown for every failure, which would tell an author to
    // resume a run that does not exist.
    const user = userEvent.setup();
    api.plan.mockRejectedValue({ body: { detail: { code: 'BAD_STATE', message: 'nope' } } });
    setup();
    await user.type(screen.getByTestId('world-setup-text'), 'my story');
    await user.click(screen.getByTestId('world-setup-start'));

    await screen.findByTestId('world-setup-error');
    expect(screen.queryByTestId('world-setup-blocked')).toBeNull();
    expect(api.list).not.toHaveBeenCalled();
  });
});
