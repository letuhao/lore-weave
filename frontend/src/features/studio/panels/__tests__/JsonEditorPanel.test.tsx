// #12 J1 — multi-instance json-editor: the panel self-titles per instance (doc label + a
// short resource discriminator) and no longer registers with the host registry (two
// instances would corrupt each other's register/unregister — keyed by panelId).
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

// Mutable mock state so a test can vary the provider (readOnly) + the handle (save spy).
const mocks = vi.hoisted(() => ({
  provider: { type: 'loreweave.manuscript-unit.v1' } as { type: string; readOnly?: boolean },
  handle: null as { save: () => void; revert: () => void; update: () => void } | null,
  dirty: false,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
vi.mock('@uiw/react-codemirror', () => ({ default: () => <div data-testid="cm" /> }));
vi.mock('@codemirror/lang-json', () => ({ json: () => [] }));
vi.mock('codemirror-json-schema', () => ({ jsonSchema: () => [] }));
vi.mock('../../documents/registry', () => ({
  getJsonDocumentProvider: () => mocks.provider,
}));
vi.mock('../../documents/useJsonDocument', () => ({
  useJsonDocument: () => ({
    handle: mocks.handle,
    snapshot: { doc: { a: 1 }, etag: null, dirty: mocks.dirty, status: 'idle', detail: null },
    openError: null,
  }),
}));

import { JsonEditorPanel } from '../JsonEditorPanel';

beforeEach(() => {
  mocks.provider = { type: 'loreweave.manuscript-unit.v1' };
  mocks.handle = null;
  mocks.dirty = false;
});

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

describe('JsonEditorPanel (FE-1 read-only viewer)', () => {
  const openProps = () =>
    dockProps({ docType: 'loreweave.plan-artifact.v1', resourceId: 'run1:art1' });

  it('a read-only provider HIDES Save and Revert (not disabled — an immutable doc has nothing to save)', () => {
    mocks.provider = { type: 'loreweave.plan-artifact.v1', readOnly: true };
    mocks.handle = { save: vi.fn(), revert: vi.fn(), update: vi.fn() };
    withHost(<JsonEditorPanel {...openProps()} />);
    expect(screen.queryByTestId('json-editor-save')).toBeNull();
    expect(screen.queryByTestId('json-editor-revert')).toBeNull();
    expect(screen.getByTestId('json-editor-readonly')).toBeInTheDocument();
  });

  it('⌘S/Ctrl-S does NOT save a read-only doc (no window listener registered at all)', () => {
    mocks.provider = { type: 'loreweave.plan-artifact.v1', readOnly: true };
    const save = vi.fn();
    mocks.handle = { save, revert: vi.fn(), update: vi.fn() };
    withHost(<JsonEditorPanel {...openProps()} />);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 's', ctrlKey: true }));
    expect(save).not.toHaveBeenCalled();
  });

  it('REGRESSION: an editable provider still renders Save and still saves on ⌘S', () => {
    mocks.provider = { type: 'loreweave.manuscript-unit.v1' }; // no readOnly
    const save = vi.fn();
    mocks.handle = { save, revert: vi.fn(), update: vi.fn() };
    mocks.dirty = true;
    withHost(<JsonEditorPanel {...openProps()} />);
    expect(screen.getByTestId('json-editor-save')).toBeInTheDocument();
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 's', ctrlKey: true }));
    expect(save).toHaveBeenCalledTimes(1);
  });
});
