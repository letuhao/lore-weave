import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { JobParametersPanel } from '../JobParametersPanel';
import { JobCostUsagePanel } from '../JobCostUsagePanel';
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
