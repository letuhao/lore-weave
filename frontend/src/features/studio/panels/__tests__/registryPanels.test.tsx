// E2E-P1-G deterministic form ("assert the host effect") — the live browser
// panel-open smoke is blocked by a concurrent agent holding the shared Playwright
// browser (D-REG-P1G-BROWSER). This mounts the real dock components host.openPanel
// would build for 'extensions'/'proposals'/'skill-editor' and asserts they render
// without throwing — proving the catalog mapping (panelCatalogContract) resolves to
// a functioning, rendering panel, not just a registered id.
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'test-token' }) }));
vi.mock('@/features/studio/host/StudioHostProvider', () => ({ useRegisterStudioTool: () => undefined }));
vi.mock('@/features/extensions/api', () => ({
  extensionsApi: {
    listSkills: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 }),
    listProposals: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 }),
    usage: vi.fn().mockResolvedValue({
      plugins: 0, skills: { used: 0, limit: 50 }, mcp_servers: { used: 0, limit: 10 },
      commands: { used: 0, limit: 20 }, proposals_pending: 0,
    }),
  },
}));

import { STUDIO_PANEL_COMPONENTS } from '../catalog';

// Minimal dockview panel props — only api.setTitle is used by useStudioPanel.
const fakeProps = () => ({ api: { setTitle: vi.fn() } }) as never;

describe('registry studio panels mount (E2E-P1-G deterministic)', () => {
  it('the extensions/proposals/skill-editor ids resolve to real components', () => {
    for (const id of ['extensions', 'proposals', 'skill-editor']) {
      expect(typeof STUDIO_PANEL_COMPONENTS[id]).toBe('function');
    }
  });

  it('ExtensionsPanel mounts and renders its Skills tab', () => {
    const Extensions = STUDIO_PANEL_COMPONENTS['extensions'];
    render(<Extensions {...fakeProps()} />);
    expect(screen.getByTestId('studio-extensions-panel')).toBeTruthy();
    expect(screen.getByTestId('ext-tab-skills')).toBeTruthy();
    expect(screen.getByTestId('extensions-skills-view')).toBeTruthy();
  });

  it('ProposalsPanel mounts and renders the proposals view', () => {
    const Proposals = STUDIO_PANEL_COMPONENTS['proposals'];
    render(<Proposals {...fakeProps()} />);
    expect(screen.getByTestId('studio-proposals-panel')).toBeTruthy();
    expect(screen.getByTestId('extensions-proposals-view')).toBeTruthy();
  });

  it('SkillEditorPanel mounts (no skillId → prompt state)', () => {
    const Editor = STUDIO_PANEL_COMPONENTS['skill-editor'];
    render(<Editor {...fakeProps()} />);
    expect(screen.getByTestId('studio-skill-editor-panel')).toBeTruthy();
  });
});
