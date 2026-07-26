import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { JobParametersPanel } from '../JobParametersPanel';
import { JobCostUsagePanel } from '../JobCostUsagePanel';
import { JobProgressPanel } from '../JobProgressPanel';
import type { Job } from '../../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
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
