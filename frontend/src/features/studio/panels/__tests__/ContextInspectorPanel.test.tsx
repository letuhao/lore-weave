import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { IDockviewPanelProps } from 'dockview-react';

// Verify-by-EFFECT for the §11 dockable panel wrapper: when the studio mounts the
// `context-inspector` panel it (a) actually renders the shared inspector view
// (mounts — not a silent no-op) and (b) self-titles via props.api.setTitle. The
// heavy view + host registration are stubbed so this stays a bare unit; the
// enum⊆catalog side is covered by panelCatalogContract.test.ts.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));
vi.mock('../../host/StudioHostProvider', () => ({ useRegisterStudioTool: vi.fn() }));
vi.mock('@/features/chat/inspector/ContextInspectorView', () => ({
  ContextInspectorView: () => <div data-testid="civ-mounted" />,
}));

import { ContextInspectorPanel } from '../ContextInspectorPanel';

describe('ContextInspectorPanel (dockable §11)', () => {
  it('mounts the shared inspector view and self-titles via api.setTitle', () => {
    const setTitle = vi.fn();
    const api = { setTitle } as unknown as IDockviewPanelProps['api'];
    render(<ContextInspectorPanel api={api} {...({} as IDockviewPanelProps)} />);
    // (a) the panel actually mounts the view (not a silent no-op)
    expect(screen.getByTestId('studio-context-inspector-panel')).toBeInTheDocument();
    expect(screen.getByTestId('civ-mounted')).toBeInTheDocument();
    // (b) self-titles from the localized label
    expect(setTitle).toHaveBeenCalledWith('panels.context-inspector.title');
  });
});
