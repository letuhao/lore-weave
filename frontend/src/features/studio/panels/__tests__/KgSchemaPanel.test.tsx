// 14_kg_panels.md K6/Phase B — KgSchemaPanel: bundles adopt/schema/views/sync as
// ONE panel with its own internal tab furniture (DOCK-8 judgment-call exception —
// these four views share one editing session over one active schema, unlike
// Glossary's view-switch which was split into sibling panels). Stubs the heavy
// children + hooks so this test stays about the panel's OWN wiring (project
// resolution, self-title, register, tab switch, empty state) — mirrors
// GlossaryPanel.test.tsx's stubbing pattern for a panel with internal tabs.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

const state = vi.hoisted(() => ({
  projectId: null as string | null,
  projectLoading: false,
}));

vi.mock('@/features/knowledge/hooks/useBookKnowledgeProject', () => ({
  useBookKnowledgeProject: () => ({
    project: state.projectId ? { project_id: state.projectId } : null,
    projectId: state.projectId,
    isLoading: state.projectLoading,
  }),
}));

vi.mock('@/features/knowledge/hooks/useGraphSchema', () => ({
  useGraphSchemaList: () => ({ data: { items: [] } }),
  useGraphSchema: () => ({ schema: null }),
}));

const adoptMock = vi.fn();
const clearGateMock = vi.fn();
const acknowledgeLossMock = vi.fn();
vi.mock('@/features/knowledge/hooks/useOntologyAdopt', () => ({
  useOntologyAdopt: () => ({
    adopt: adoptMock,
    isAdopting: false,
    needsGlossary: null,
    clearGate: clearGateMock,
    wouldLose: [],
    lossBlocked: false,
    acknowledgeLoss: acknowledgeLossMock,
  }),
}));

const createViewMock = vi.fn();
vi.mock('@/features/knowledge/hooks/useGraphViews', () => ({
  useGraphViews: () => ({ createView: createViewMock, isMutating: false }),
}));

const applyMock = vi.fn();
vi.mock('@/features/knowledge/hooks/useOntologySync', () => ({
  useOntologySync: () => ({
    changes: [],
    hasUpdates: false,
    getChoice: vi.fn(),
    setDecision: vi.fn(),
    keepAllMine: vi.fn(),
    takeAllTheirs: vi.fn(),
    apply: applyMock,
    isApplying: false,
    decidedCount: 0,
  }),
}));

vi.mock('@/features/knowledge/components/ontology/AdoptPicker', () => ({
  AdoptPicker: ({ onOpenGlossary }: { onOpenGlossary: () => void }) => (
    <div data-testid="stub-adopt-picker">
      <button onClick={onOpenGlossary}>open-glossary</button>
    </div>
  ),
}));

// KgNoProjectState (D-KG-NO-CREATE-CTA) owns the real empty-state + create-project flow,
// tested on its own in KgNoProjectState.test.tsx. Stubbed here so this stays a test of the
// panel's own project-resolution/tab wiring.
vi.mock('@/features/knowledge/components/shell/KgNoProjectState', () => ({
  KgNoProjectState: ({ testId }: { testId: string }) => <div data-testid={testId}>stub-no-project</div>,
}));

vi.mock('@/features/knowledge/components/shell/ProjectSchemaSection', () => ({
  ProjectSchemaSection: ({ projectId, onAdoptCta }: { projectId: string; onAdoptCta?: () => void }) => (
    <div data-testid="stub-project-schema-section" data-project={projectId}>
      <button onClick={onAdoptCta}>go-to-adopt</button>
    </div>
  ),
}));

vi.mock('@/features/knowledge/components/ontology/ViewBuilder', () => ({
  ViewBuilder: () => <div data-testid="stub-view-builder" />,
}));

vi.mock('@/features/knowledge/components/ontology/SyncDiffPanel', () => ({
  SyncDiffPanel: () => <div data-testid="stub-sync-diff-panel" />,
}));

import { KgSchemaPanel } from '../KgSchemaPanel';

let hostRef: StudioHost | null = null;
function HostProbe() {
  hostRef = useStudioHost();
  return null;
}

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  return render(
    <StudioHostProvider bookId={bookId}>
      <HostProbe />
      {ui}
    </StudioHostProvider>,
  );
}

beforeEach(() => {
  hostRef = null;
  state.projectId = 'p1';
  state.projectLoading = false;
  adoptMock.mockReset();
  clearGateMock.mockReset();
  acknowledgeLossMock.mockReset();
  createViewMock.mockReset();
  applyMock.mockReset();
});

describe('KgSchemaPanel', () => {
  it('registers with the host as an openable studio tool tagged with the kg_ MCP prefix', () => {
    withHost('b1', <KgSchemaPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('kg-schema')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('kg-schema')!.commandId).toBe('studio.openPanel.kg-schema');
    expect(hostRef!.getRegisteredTool('kg-schema')!.mcpToolPrefixes).toEqual(['kg_']);
  });

  it('self-titles the dock tab on mount', () => {
    const props = dockProps();
    withHost('b1', <KgSchemaPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('shows the empty state when the book has no knowledge project', () => {
    state.projectId = null;
    withHost('b1', <KgSchemaPanel {...dockProps()} />);
    expect(screen.getByTestId('kg-ontology-no-project')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-adopt-picker')).not.toBeInTheDocument();
  });

  it('defaults to the adopt tab and renders AdoptPicker', () => {
    withHost('b1', <KgSchemaPanel {...dockProps()} />);
    expect(screen.getByTestId('stub-adopt-picker')).toBeInTheDocument();
  });

  it('switches to the schema tab and renders ProjectSchemaSection (project-scoped)', () => {
    withHost('b1', <KgSchemaPanel {...dockProps()} />);
    fireEvent.click(screen.getByTestId('kg-schema-tab-schema'));
    const section = screen.getByTestId('stub-project-schema-section');
    expect(section).toBeInTheDocument();
    expect(section).toHaveAttribute('data-project', 'p1');
    expect(screen.queryByTestId('stub-adopt-picker')).not.toBeInTheDocument();
  });

  it('switches to the views tab and renders ViewBuilder', () => {
    withHost('b1', <KgSchemaPanel {...dockProps()} />);
    fireEvent.click(screen.getByTestId('kg-schema-tab-views'));
    expect(screen.getByTestId('stub-view-builder')).toBeInTheDocument();
  });

  it('switches to the sync tab and renders SyncDiffPanel', () => {
    withHost('b1', <KgSchemaPanel {...dockProps()} />);
    fireEvent.click(screen.getByTestId('kg-schema-tab-sync'));
    expect(screen.getByTestId('stub-sync-diff-panel')).toBeInTheDocument();
  });

  it('routes AdoptPicker\'s "open glossary" action to the sibling glossary panel via host.openPanel (DOCK-7)', () => {
    withHost('b1', <KgSchemaPanel {...dockProps()} />);
    const openPanelSpy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByText('open-glossary'));
    expect(openPanelSpy).toHaveBeenCalledWith('glossary');
  });

  it('CreateSchemaEntry\'s adopt CTA (threaded through ProjectSchemaSection) switches back to the adopt tab, not a route hop (DOCK-7)', () => {
    withHost('b1', <KgSchemaPanel {...dockProps()} />);
    fireEvent.click(screen.getByTestId('kg-schema-tab-schema'));
    fireEvent.click(screen.getByText('go-to-adopt'));
    expect(screen.getByTestId('stub-adopt-picker')).toBeInTheDocument();
  });
});
