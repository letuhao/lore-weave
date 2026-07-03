import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { PlanRunView } from '../PlanRunView';
import type { PlanRunDetail } from '../../types';

// Regression: a live browser smoke crashed the panel with
// "Cannot read properties of null (reading 'toFixed')" — the validate/self-check
// report returns fidelity_score=null when the fidelity config is absent (v1 is
// fixture-based), and the render called .toFixed() unguarded. The hook test mocked
// a numeric score, so only the live render caught it.

const RUN: PlanRunDetail = {
  id: '019f1f42-0000-0000-0000-000000000000',
  book_id: 'b1',
  status: 'validated',
  mode: 'rules',
  model_ref: null,
  source_checksum: 'abc',
  active_job_id: null,
  job_status: null,
  error_detail: null,
  checkpoint_state: {},
  artifacts: [],
  created_at: null,
  updated_at: null,
};

const noop = vi.fn();

describe('PlanRunView — null fidelity_score', () => {
  it('renders a null validate fidelity_score as — instead of crashing', () => {
    render(
      <PlanRunView
        run={RUN}
        polling={false}
        busy={false}
        selfCheck={null}
        validation={{ passed: false, rules: [], fidelity_score: null, fidelity_report_id: null }}
        compileResult={null}
        onSelfCheck={noop}
        onValidate={noop}
        onCompile={noop}
      />,
    );
    expect(screen.getByTestId('plan-validation').textContent).toContain('—');
  });

  it('renders a null self-check fidelity_score as — instead of crashing', () => {
    render(
      <PlanRunView
        run={RUN}
        polling={false}
        busy={false}
        selfCheck={{ gaps: [], fidelity_score: null }}
        validation={null}
        compileResult={null}
        onSelfCheck={noop}
        onValidate={noop}
        onCompile={noop}
      />,
    );
    expect(screen.getByTestId('plan-selfcheck').textContent).toContain('—');
  });
});
