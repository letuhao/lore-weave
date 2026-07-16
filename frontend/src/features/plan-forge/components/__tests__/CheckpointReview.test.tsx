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
  onReview: vi.fn(), onClose: vi.fn(), ...over,
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

  it('Edit → Save edits sends the parsed JSON as edits with approved=false (F-P10)', async () => {
    const onReview = vi.fn();
    render(<CheckpointReview {...props({ onReview })} />);
    await waitFor(() => screen.getByTestId('review-content'));
    fireEvent.click(screen.getByTestId('review-edit-toggle'));
    fireEvent.change(screen.getByTestId('review-edit'), { target: { value: '{"roster":[{"name":"Bob"}]}' } });
    fireEvent.click(screen.getByTestId('review-save-edits'));
    expect(onReview).toHaveBeenCalledWith(false, { roster: [{ name: 'Bob' }] });
  });
});
