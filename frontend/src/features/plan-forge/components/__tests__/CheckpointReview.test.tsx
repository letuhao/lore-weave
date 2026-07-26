import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CheckpointReview } from '../CheckpointReview';
import type { PlanPass } from '../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));

const api = vi.hoisted(() => ({
  getArtifact: vi.fn(),
  bootstrapGet: vi.fn(),
  bootstrapApprove: vi.fn(),
  bootstrapApply: vi.fn(),
}));
vi.mock('../../api', () => ({ planForgeApi: api }));

function pass(over: Partial<PlanPass>): PlanPass {
  return {
    pass_id: 'cast', checkpoint: 'blocking', output_kind: 'cast_plan', depends_on: [],
    status: 'completed', decision: 'pending', artifact_id: 'art1', job_id: null,
    fresh: true, blockers: [], ...over,
  };
}
const proposal = (status: string) => ({
  id: 'prop1', run_id: 'r1', book_id: 'b1', owner_user_id: 'u1', status,
  diff: { new_chapters: [], new_glossary_entities: [] }, applied_results: {},
  error_detail: null, created_at: '', updated_at: '',
});

beforeEach(() => {
  api.getArtifact.mockReset().mockResolvedValue({ artifact_id: 'art1', kind: 'cast_plan', content: { roster: [{ name: 'Alice' }] }, created_at: null });
  api.bootstrapGet.mockReset();
  api.bootstrapApprove.mockReset();
  api.bootstrapApply.mockReset();
});

const props = (over?: Partial<React.ComponentProps<typeof CheckpointReview>>) => ({
  pass: pass({}), bookId: 'b1', runId: 'r1', token: 't', busy: false,
  onReview: vi.fn(), onSaveEdits: vi.fn(), onClose: vi.fn(), ...over,
});

describe('CheckpointReview (M4-CP)', () => {
  it('renders the artifact content the checkpoint is approving', async () => {
    render(<CheckpointReview {...props()} />);
    await waitFor(() => expect(screen.getByTestId('review-content').textContent).toContain('Alice'));
  });

  it('cast seed gate PENDING → Apply shown, Approve disabled (PF-7)', async () => {
    api.bootstrapGet.mockResolvedValue(proposal('pending'));
    render(<CheckpointReview {...props({ pass: pass({ bootstrap_proposal_id: 'prop1' }) })} />);
    await waitFor(() => expect(screen.getByTestId('review-apply-seed')).toBeInTheDocument());
    expect((screen.getByTestId('review-approve') as HTMLButtonElement).disabled).toBe(true);
  });

  it('cast seed gate APPLIED → Approve enabled', async () => {
    api.bootstrapGet.mockResolvedValue(proposal('applied'));
    render(<CheckpointReview {...props({ pass: pass({ bootstrap_proposal_id: 'prop1' }) })} />);
    await waitFor(() => expect(screen.getByTestId('review-seed-gate').textContent).toContain('applied'));
    expect((screen.getByTestId('review-approve') as HTMLButtonElement).disabled).toBe(false);
  });

  it('Apply seed → approve then apply the proposal', async () => {
    api.bootstrapGet.mockResolvedValue(proposal('pending'));
    api.bootstrapApprove.mockResolvedValue(proposal('approved'));
    api.bootstrapApply.mockResolvedValue(proposal('applied'));
    render(<CheckpointReview {...props({ pass: pass({ bootstrap_proposal_id: 'prop1' }) })} />);
    await waitFor(() => screen.getByTestId('review-apply-seed'));
    fireEvent.click(screen.getByTestId('review-apply-seed'));
    await waitFor(() => expect(api.bootstrapApply).toHaveBeenCalled());
    expect(api.bootstrapApprove).toHaveBeenCalled();
  });

  it('Approve calls onReview(true)', async () => {
    const onReview = vi.fn();
    render(<CheckpointReview {...props({ pass: pass({ checkpoint: 'blocking', bootstrap_proposal_id: undefined }), onReview })} />);
    await waitFor(() => screen.getByTestId('review-content'));
    fireEvent.click(screen.getByTestId('review-approve'));
    expect(onReview).toHaveBeenCalledWith(true);
  });

  it('no RAW-JSON editor — the artifact view is read-only until the structured editor is opened', async () => {
    // The draft bans a raw-JSON textarea as an un-derived write channel. The STRUCTURED editor
    // (D-S3-CHECKPOINT-STRUCTURED-EDITS) is the sanctioned edit path, but it is NOT open by default.
    render(<CheckpointReview {...props()} />);
    await waitFor(() => screen.getByTestId('review-content'));
    expect(screen.queryByTestId('artifact-json')).toBeNull();          // no raw JSON for cast
    expect(screen.queryByTestId('pass-artifact-editor')).toBeNull();   // editor closed by default
    expect(screen.getByTestId('review-edit')).toBeInTheDocument();     // but the Edit door is offered
  });

  it('Edit → structured editor; removing a row + Save sends the WHOLE list so the delete sticks', async () => {
    api.getArtifact.mockResolvedValue({
      artifact_id: 'art1', kind: 'cast_plan', created_at: null,
      content: { cast: [{ name: 'Alice' }, { name: 'Bob' }] },
    });
    const onSaveEdits = vi.fn();
    render(<CheckpointReview {...props({ onSaveEdits })} />);
    await waitFor(() => screen.getByTestId('review-content'));
    fireEvent.click(screen.getByTestId('review-edit'));
    await waitFor(() => screen.getByTestId('pass-artifact-editor'));
    fireEvent.click(screen.getByTestId('edit-remove-1'));               // drop Bob
    fireEvent.click(screen.getByTestId('edit-save'));
    expect(onSaveEdits).toHaveBeenCalledTimes(1);
    const edits = onSaveEdits.mock.calls[0][0] as { cast: { name: string }[] };
    expect(edits.cast.map((c) => c.name)).toEqual(['Alice']);          // Bob is GONE from the list
  });

  it('an advisory (non-editable) kind offers no Edit door', async () => {
    api.getArtifact.mockResolvedValue({ artifact_id: 'art1', kind: 'motif_plan', content: { motifs: [] }, created_at: null });
    render(<CheckpointReview {...props({ pass: pass({ output_kind: 'motif_plan', checkpoint: 'advisory' }) })} />);
    await waitFor(() => screen.getByTestId('review-content'));
    expect(screen.queryByTestId('review-edit')).toBeNull();
  });

  it('Reject calls onReview(false)', async () => {
    const onReview = vi.fn();
    render(<CheckpointReview {...props({ onReview })} />);
    await waitFor(() => screen.getByTestId('review-content'));
    fireEvent.click(screen.getByTestId('review-reject'));
    expect(onReview).toHaveBeenCalledWith(false);
  });
});
