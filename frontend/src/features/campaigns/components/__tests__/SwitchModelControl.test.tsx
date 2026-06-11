import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SwitchModelControl } from '../SwitchModelControl';
import type { CampaignDetail } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const h = vi.hoisted(() => ({
  updateMutate: vi.fn(),
  resumeMutate: vi.fn(),
  captured: { onSuccess: undefined as undefined | ((c: { campaign_id: string }) => void) },
}));

vi.mock('../../hooks/useCampaignMutations', () => ({
  useUpdateCampaign: (opts: { onSuccess?: (c: { campaign_id: string }) => void }) => {
    h.captured.onSuccess = opts.onSuccess;
    return { mutate: h.updateMutate, isPending: false };
  },
  useResumeCampaign: () => ({ mutate: h.resumeMutate, isPending: false }),
}));

// Stub the BYOK picker as a button that flips the value (simulates a re-pick).
vi.mock('../ModelRolePicker', () => ({
  ModelRolePicker: ({ label, value, onChange }: { label: string; value: string | null; onChange: (v: string | null) => void }) => (
    <button onClick={() => onChange(`new-${label}`)}>{label}={value ?? 'none'}</button>
  ),
}));

const campaign = {
  campaign_id: 'cmp1',
  translation_model_ref: 'tr-old',
  knowledge_model_ref: 'kn-old',
  verifier_model_ref: 'vf-old',
  eval_judge_model_ref: null,
} as CampaignDetail;

describe('SwitchModelControl', () => {
  beforeEach(() => { h.updateMutate.mockReset(); h.resumeMutate.mockReset(); });

  it('reveals all four role pickers (pre-filled) when expanded', async () => {
    render(<SwitchModelControl campaign={campaign} />);
    // collapsed: pickers hidden
    expect(screen.queryByText(/monitor.translationModel/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByText('monitor.switchModel'));
    expect(screen.getByText('monitor.translationModel=tr-old')).toBeInTheDocument();
    expect(screen.getByText('monitor.knowledgeModel=kn-old')).toBeInTheDocument();
    expect(screen.getByText('monitor.verifierModel=vf-old')).toBeInTheDocument();
    expect(screen.getByText('monitor.evalJudgeModel=none')).toBeInTheDocument();
  });

  it('PATCHes the picked models then chains resume on success', async () => {
    render(<SwitchModelControl campaign={campaign} />);
    await userEvent.click(screen.getByText('monitor.switchModel'));   // expand (toggle)
    await userEvent.click(screen.getByText('monitor.translationModel=tr-old'));  // re-pick translation
    // two elements read 'monitor.switchModel' now: [0] the toggle, [1] the action button.
    await userEvent.click(screen.getAllByText('monitor.switchModel')[1]);

    expect(h.updateMutate).toHaveBeenCalledTimes(1);
    const arg = h.updateMutate.mock.calls[0][0];
    expect(arg.campaignId).toBe('cmp1');
    // translation switched to the new pick (user_model source), others unchanged
    expect(arg.patch.translation_model_ref).toBe('new-monitor.translationModel');
    expect(arg.patch.translation_model_source).toBe('user_model');
    expect(arg.patch.knowledge_model_ref).toBe('kn-old');
    // verifier + eval-judge are now part of the patch (D-FACTORY-SWITCH-VERIFIER-EVAL-UI)
    expect(arg.patch.verifier_model_ref).toBe('vf-old');
    expect(arg.patch.verifier_model_source).toBe('user_model');
    expect(arg.patch.eval_judge_model_ref).toBe(null);   // was null → cleared (source null too)
    expect(arg.patch.eval_judge_model_source).toBe(null);

    // the update's onSuccess chains a resume
    h.captured.onSuccess?.({ campaign_id: 'cmp1' });
    expect(h.resumeMutate).toHaveBeenCalledWith('cmp1');
  });
});
