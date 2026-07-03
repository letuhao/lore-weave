// #12 J1 — multi-instance json-editor: the panel self-titles per instance (doc label + a
// short resource discriminator) and no longer registers with the host registry (two
// instances would corrupt each other's register/unregister — keyed by panelId).
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('@uiw/react-codemirror', () => ({ default: () => <div data-testid="cm" /> }));
vi.mock('@codemirror/lang-json', () => ({ json: () => [] }));
vi.mock('codemirror-json-schema', () => ({ jsonSchema: () => [] }));
vi.mock('../../documents/registry', () => ({
  getJsonDocumentProvider: () => ({ type: 'loreweave.manuscript-unit.v1' }),
}));
vi.mock('../../documents/useJsonDocument', () => ({
  useJsonDocument: () => ({
    handle: null,
    snapshot: { doc: { a: 1 }, etag: null, dirty: false, status: 'idle', detail: null },
    openError: null,
  }),
}));

import { JsonEditorPanel } from '../JsonEditorPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps(params?: Record<string, unknown>) {
  return {
    api: {
      setTitle: vi.fn(),
      onDidParametersChange: () => ({ dispose: () => {} }),
    },
    params,
  } as unknown as IDockviewPanelProps;
}

const withHost = (ui: React.ReactNode) =>
  render(<StudioHostProvider bookId="b1"><HostProbe />{ui}</StudioHostProvider>);

describe('JsonEditorPanel (J1 multi-instance)', () => {
  it('self-titles per instance: doc label + short resource id', () => {
    const props = dockProps({
      docType: 'loreweave.manuscript-unit.v1',
      resourceId: '0199aabb-cccc-dddd-eeee-ffff00001111',
    });
    withHost(<JsonEditorPanel {...props} />);
    expect(props.api.setTitle).toHaveBeenCalledWith('JSON · 0199aabb');
  });

  it('does NOT register in the host registry (a second instance must not clobber the first)', () => {
    hostRef = null;
    withHost(<JsonEditorPanel {...dockProps({
      docType: 'loreweave.manuscript-unit.v1', resourceId: 'r1',
    })} />);
    expect(hostRef!.getRegisteredTool('json-editor')).toBeNull();
  });

  it('empty target renders the affordance hint (no crash, generic title)', () => {
    const props = dockProps();
    withHost(<JsonEditorPanel {...props} />);
    expect(screen.getByTestId('studio-json-editor').textContent).toContain('Open as JSON');
    expect(props.api.setTitle).toHaveBeenCalledWith('JSON');
  });
});
