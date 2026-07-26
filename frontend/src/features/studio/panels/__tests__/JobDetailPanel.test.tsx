// 14_utility_panels.md B2 — JobDetailPanel: params-retargeting singleton (json-editor/
// skill-editor precedent, DOCK-6), thin-view reuse of JobMonitor AS-IS (DOCK-2) with its
// back-breadcrumb hidden via `hideBack` instead of a route hop (DOCK-7).
import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('@/features/jobs/context/JobsStreamProvider', () => ({
  JobsStreamProvider: ({ children }: { children: ReactNode }) => (
    <div data-testid="jobs-stream-provider">{children}</div>
  ),
}));
vi.mock('@/features/jobs/components/JobMonitor', () => ({
  JobMonitor: ({ service, jobId, hideBack }: { service: string; jobId: string; hideBack?: boolean }) => (
    <div data-testid="job-monitor" data-service={service} data-job-id={jobId} data-hide-back={String(hideBack)} />
  ),
}));

import { JobDetailPanel } from '../JobDetailPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps(params?: Record<string, unknown>) {
  const listeners = new Set<(p: Record<string, unknown>) => void>();
  const props = {
    api: {
      setTitle: vi.fn(),
      onDidParametersChange: (cb: (p: Record<string, unknown>) => void) => {
        listeners.add(cb);
        return { dispose: () => listeners.delete(cb) };
      },
    },
    params,
  } as unknown as IDockviewPanelProps;
  return { props, fireParams: (p: Record<string, unknown>) => listeners.forEach((l) => l(p)) };
}

function withHost(ui: ReactNode) {
  return render(<StudioHostProvider bookId="b1"><HostProbe />{ui}</StudioHostProvider>);
}

describe('JobDetailPanel', () => {
  it('empty params: shows the affordance hint (no crash, generic title)', () => {
    const { props } = dockProps();
    withHost(<JobDetailPanel {...props} />);
    expect(screen.getByTestId('studio-job-detail-panel').textContent).toContain(
      'Open a job from the Jobs panel to watch it here.',
    );
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('{service, jobId} params: renders JobMonitor with hideBack=true (no back-breadcrumb)', () => {
    const { props } = dockProps({ service: 'knowledge', jobId: 'j1' });
    withHost(<JobDetailPanel {...props} />);
    const el = screen.getByTestId('job-monitor');
    expect(el.getAttribute('data-service')).toBe('knowledge');
    expect(el.getAttribute('data-job-id')).toBe('j1');
    expect(el.getAttribute('data-hide-back')).toBe('true');
  });

  it('registers with the host (singleton — same shape as SkillEditorPanel, not the multi-instance json-editor case)', () => {
    hostRef = null;
    const { props } = dockProps({ service: 'knowledge', jobId: 'j1' });
    withHost(<JobDetailPanel {...props} />);
    expect(hostRef!.getRegisteredTool('job-detail')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('job-detail')!.commandId).toBe('studio.openPanel.job-detail');
  });

  it('retargets on updateParameters (a repeat open from a different job row lands)', () => {
    const { props, fireParams } = dockProps({ service: 'knowledge', jobId: 'j1' });
    withHost(<JobDetailPanel {...props} />);
    expect(screen.getByTestId('job-monitor').getAttribute('data-job-id')).toBe('j1');

    act(() => { fireParams({ service: 'translation', jobId: 'j2' }); });
    expect(screen.getByTestId('job-monitor').getAttribute('data-service')).toBe('translation');
    expect(screen.getByTestId('job-monitor').getAttribute('data-job-id')).toBe('j2');
  });
});
