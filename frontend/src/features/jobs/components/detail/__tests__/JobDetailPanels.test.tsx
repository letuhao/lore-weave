import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import { JobParametersPanel } from '../JobParametersPanel';
import { JobCostUsagePanel } from '../JobCostUsagePanel';
import { JobProgressPanel } from '../JobProgressPanel';
import type { Job } from '../../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));

// The panel resolves `user_model_id`s to display names, so it now reaches the
// model registry — which reads the auth token. Stub it the way the other panel
// tests do; `userModels` is per-test so the id→name substitution can be asserted
// rather than merely tolerated.
let userModels: { user_model_id: string; alias: string; provider_model_name: string }[] = [];
vi.mock('@/components/model-picker', () => ({
  useUserModels: () => ({ models: userModels }),
}));

const job: Job = {
  service: 'knowledge', job_id: 'j1', owner_user_id: 'u', kind: 'extraction',
  status: 'running', parent_job_id: null, detail_status: null, progress: null,
  control_caps: [], title: 't', error: null,
  model: 'qwen2.5-7b-instruct', cost_usd: 2.74, tokens_in: 980142, tokens_out: 180553,
  params: { model: 'qwen2.5-7b-instruct', concurrency: 4, targets: ['entities', 'relations'], max_spend_usd: 10 },
  created_at: '2026-06-16T00:00:00Z', updated_at: '2026-06-16T00:00:00Z', child_count: 0,
};

describe('JobParametersPanel', () => {
  beforeEach(() => {
    userModels = [];
  });

  it('renders every param key/value dynamically (schema-free)', () => {
    render(<JobParametersPanel params={job.params} />);
    expect(screen.getByText('concurrency')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    // array values join with the middot separator
    expect(screen.getByText('entities · relations')).toBeInTheDocument();
  });

  it('renders nothing when there are no params', () => {
    const { container } = render(<JobParametersPanel params={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('excludes the call-count keys (shown in the Progress panel instead)', () => {
    render(
      <JobParametersPanel
        params={{ model: 'm', estimated_llm_calls: 16, llm_calls_done: 11 }}
      />,
    );
    expect(screen.getByText('model')).toBeInTheDocument();
    expect(screen.queryByText('estimated_llm_calls')).not.toBeInTheDocument();
    expect(screen.queryByText('llm_calls_done')).not.toBeInTheDocument();
  });

  it('shows a registered model by name instead of its opaque user_model_id', () => {
    userModels = [{
      user_model_id: '019d5e3c-7cc5-7e6a-8b27-000000000001',
      alias: 'Gemma 4 26B (local)',
      provider_model_name: 'google/gemma-4-26b-a4b-qat',
    }];
    render(<JobParametersPanel params={{ model: '019d5e3c-7cc5-7e6a-8b27-000000000001' }} />);
    expect(screen.getByText('Gemma 4 26B (local)')).toBeInTheDocument();
    expect(screen.queryByText('019d5e3c-7cc5-7e6a-8b27-000000000001')).not.toBeInTheDocument();
  });

  it('leaves an unrecognised id alone rather than blanking the row', () => {
    userModels = [];
    render(<JobParametersPanel params={{ model: 'not-in-the-registry' }} />);
    expect(screen.getByText('not-in-the-registry')).toBeInTheDocument();
  });
});

describe('JobProgressPanel — LLM call counts (bug #37)', () => {
  it('shows "done / total" when an estimate is present', () => {
    const j: Job = { ...job, params: { estimated_llm_calls: 16, llm_calls_done: 11 } };
    render(<JobProgressPanel job={j} />);
    expect(screen.getByText('LLM calls')).toBeInTheDocument();
    expect(screen.getByText('11 / 16')).toBeInTheDocument();
  });

  it('defaults done to 0 when only the estimate is present', () => {
    const j: Job = { ...job, params: { estimated_llm_calls: 16 } };
    render(<JobProgressPanel job={j} />);
    expect(screen.getByText('0 / 16')).toBeInTheDocument();
  });

  it('shows a bare running count when no estimate is present', () => {
    const j: Job = { ...job, params: { llm_calls_done: 7 } };
    render(<JobProgressPanel job={j} />);
    expect(screen.getByText('LLM calls')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
  });

  it('hides the LLM-calls row when neither key is present', () => {
    const j: Job = { ...job, params: { model: 'm' } };
    render(<JobProgressPanel job={j} />);
    expect(screen.queryByText('LLM calls')).not.toBeInTheDocument();
  });
});

describe('JobCostUsagePanel', () => {
  it('shows cost (reliable) + tokens (best-effort) + model', () => {
    render(<JobCostUsagePanel job={job} />);
    expect(screen.getByText('$2.74')).toBeInTheDocument();
    expect(screen.getByText('980,142')).toBeInTheDocument();
    expect(screen.getByText('qwen2.5-7b-instruct')).toBeInTheDocument();
  });

  it('renders nothing when the job carries no usage at all', () => {
    const bare: Job = { ...job, model: null, cost_usd: null, tokens_in: null, tokens_out: null };
    const { container } = render(<JobCostUsagePanel job={bare} />);
    expect(container).toBeEmptyDOMElement();
  });
});
