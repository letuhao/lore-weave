// 14_utility_panels.md B1 — JobsListPanel: registration/self-title chrome (DOCK-1/3/5), thin-view
// reuse of JobsList/JobsMobile AS-IS (DOCK-2), and row-click opens `job-detail` via
// host.openPanel — never navigate() (DOCK-7).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('@/hooks/useIsMobile', () => ({ useIsMobile: () => false }));
vi.mock('@/features/jobs/context/JobsStreamProvider', () => ({
  JobsStreamProvider: ({ children }: { children: ReactNode }) => (
    <div data-testid="jobs-stream-provider">{children}</div>
  ),
}));
vi.mock('@/features/jobs/components/JobsList', () => ({
  JobsList: ({ onOpenDetail }: { onOpenDetail?: (service: string, jobId: string) => void }) => (
    <button data-testid="open-job" onClick={() => onOpenDetail?.('knowledge', 'j1')}>open</button>
  ),
}));
vi.mock('@/features/jobs/components/mobile/JobsMobile', () => ({
  JobsMobile: () => <div data-testid="jobs-mobile" />,
}));

import { JobsListPanel } from '../JobsListPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(ui: ReactNode) {
  return render(<StudioHostProvider bookId="b1"><HostProbe />{ui}</StudioHostProvider>);
}

describe('JobsListPanel', () => {
  beforeEach(() => { hostRef = null; });

  it('registers with the host as an openable studio tool and self-titles the dock tab', () => {
    const props = dockProps();
    withHost(<JobsListPanel {...props} />);
    expect(hostRef!.getRegisteredTool('jobs-list')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('jobs-list')!.commandId).toBe('studio.openPanel.jobs-list');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('renders the desktop JobsList wrapped in JobsStreamProvider (thin view, no fork)', () => {
    withHost(<JobsListPanel {...dockProps()} />);
    expect(screen.getByTestId('jobs-stream-provider')).toBeTruthy();
    expect(screen.getByTestId('open-job')).toBeTruthy();
    expect(screen.queryByTestId('jobs-mobile')).toBeNull();
  });

  it('row click opens job-detail via host.openPanel with {service, jobId} params, never navigate()', () => {
    withHost(<JobsListPanel {...dockProps()} />);
    const openSpy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByTestId('open-job'));
    expect(openSpy).toHaveBeenCalledWith('job-detail', { params: { service: 'knowledge', jobId: 'j1' } });
  });
});
