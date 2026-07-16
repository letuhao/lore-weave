import { render, screen, fireEvent } from '@testing-library/react';
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
  arcs: [],
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

// ⑨ Repair strip — appears only when self-check surfaced gaps; each action is paid (PS-6 confirm).
describe('PlanRunView — repair strip', () => {
  const repairProps = {
    run: RUN, polling: false, busy: false, validation: null, compileResult: null,
    onSelfCheck: noop, onValidate: noop, onCompile: noop,
    repairOutput: null, canRepair: true, onExplain: noop, onApplyFix: noop, onAutofix: noop,
  };

  it('is HIDDEN when self-check found no gaps (no always-on paid buttons)', () => {
    render(<PlanRunView {...repairProps} selfCheck={{ gaps: [], fidelity_score: null }} />);
    expect(screen.queryByTestId('plan-repair-strip')).toBeNull();
  });

  it('appears when gaps > 0, and a paid action confirms before firing (PS-6)', () => {
    const onAutofix = vi.fn();
    render(<PlanRunView {...repairProps} onAutofix={onAutofix}
      selfCheck={{ gaps: [{ path: 'arcs.0', severity: 'error', message: 'missing climax' }], fidelity_score: null }} />);
    expect(screen.getByTestId('plan-repair-strip')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('plan-repair-autofix'));
    expect(onAutofix).not.toHaveBeenCalled();                 // not until confirmed
    fireEvent.click(screen.getByTestId('plan-repair-confirm-btn'));
    expect(onAutofix).toHaveBeenCalledTimes(1);
  });

  it('disables the actions when no chat model is chosen (canRepair=false)', () => {
    render(<PlanRunView {...repairProps} canRepair={false}
      selfCheck={{ gaps: [{ path: 'x', severity: 'error', message: 'y' }], fidelity_score: null }} />);
    expect((screen.getByTestId('plan-repair-autofix') as HTMLButtonElement).disabled).toBe(true);
  });
});

// D-PLANFORGE-ARC-PICKER: Compile's arc_id used to be a bare text input a writer
// had no way to fill in correctly (they don't know the spec's internal arc ids).
describe('PlanRunView — arc picker', () => {
  it('with no arcs yet, explains why instead of showing a blind text box', () => {
    render(
      <PlanRunView
        run={RUN} polling={false} busy={false} selfCheck={null} validation={null} compileResult={null}
        onSelfCheck={noop} onValidate={noop} onCompile={noop}
      />,
    );
    expect(screen.getByTestId('plan-arc-none')).toBeTruthy();
    expect(screen.queryByTestId('plan-arc-picker')).toBeNull();
    expect(screen.queryByTestId('plan-compile-btn')).toBeNull();
  });

  it('with arcs, offers a picker by TITLE (never a raw arc_id text box) and compiles the selected id', () => {
    const onCompile = vi.fn();
    render(
      <PlanRunView
        run={{ ...RUN, arcs: [{ id: 'arc_1', title: 'Origins' }, { id: 'arc_2', title: 'Bước Lên Tiên Lộ' }] }}
        polling={false} busy={false} selfCheck={null} validation={null} compileResult={null}
        onSelfCheck={noop} onValidate={noop} onCompile={onCompile}
      />,
    );
    const picker = screen.getByTestId('plan-arc-picker') as HTMLSelectElement;
    expect(picker.textContent).toContain('Origins');
    expect(picker.textContent).toContain('Bước Lên Tiên Lộ');
    expect(picker.value).toBe('arc_1'); // defaults to the first arc, never blank

    screen.getByTestId('plan-compile-btn').click();
    expect(onCompile).toHaveBeenCalledWith('arc_1');
  });

  it('an arc with no title falls back to showing its id, never a blank option', () => {
    render(
      <PlanRunView
        run={{ ...RUN, arcs: [{ id: 'arc_3', title: 'arc_3' }] }}
        polling={false} busy={false} selfCheck={null} validation={null} compileResult={null}
        onSelfCheck={noop} onValidate={noop} onCompile={noop}
      />,
    );
    expect(screen.getByTestId('plan-arc-picker').textContent).toContain('arc_3');
  });
});
