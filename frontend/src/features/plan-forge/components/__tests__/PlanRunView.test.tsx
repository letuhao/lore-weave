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

  // Regression: live browser smoke (D-PLANFORGE-GUI-AUDIT) found the SAME bug
  // class again — compile() legitimately returns pipeline_job_id=null when
  // run_pipeline wasn't requested (the only path this compact form offers),
  // and the render called .slice(0, 8) on it unguarded, white-screening the
  // entire Studio (no error boundary). Confirmed live: POST .../compile
  // returned 200 with pipeline_job_id: null in the real response body.
  it('renders a null compile pipeline_job_id without crashing', () => {
    render(
      <PlanRunView
        run={RUN}
        polling={false}
        busy={false}
        selfCheck={null}
        validation={null}
        compileResult={{ package: {}, work_id: 'w1', pipeline_job_id: null }}
        onSelfCheck={noop}
        onValidate={noop}
        onCompile={noop}
      />,
    );
    expect(screen.getByTestId('plan-compile-result').textContent).toContain(
      'package compiled (no pipeline run requested)',
    );
  });

  it('renders a real compile pipeline_job_id when a pipeline run was requested', () => {
    render(
      <PlanRunView
        run={RUN}
        polling={false}
        busy={false}
        selfCheck={null}
        validation={null}
        compileResult={{ package: {}, work_id: 'w1', pipeline_job_id: '019f356a-d2d2-77c2' }}
        onSelfCheck={noop}
        onValidate={noop}
        onCompile={noop}
      />,
    );
    expect(screen.getByTestId('plan-compile-result').textContent).toContain('019f356a');
  });
});
