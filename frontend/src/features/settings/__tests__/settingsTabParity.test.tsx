// The settings tab list is consumed by TWO surfaces — the /settings page and the Studio
// settings dock panel. It used to be declared in both, and it drifted: `chat-ai` shipped to
// the page (spec 2026-07-05-chat-ai-settings.md) and was never added to the dock, so a user
// working inside the Studio could not reach Chat & AI settings at all. Built, mounted,
// unreachable — the bug class this repo keeps re-learning.
//
// These tests pin the registry AND prove both surfaces render exactly what it yields, so a
// tab can never again exist in one surface and not the other.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { IDockviewPanelProps } from 'dockview-react';

// Every tab's content is stubbed: these tests are about WHICH tabs exist and that each one
// mounts its own content — not about the tabs' internals, which own their tests.
vi.mock('../AccountTab', () => ({ AccountTab: () => <div data-testid="c-account" /> }));
vi.mock('../ProvidersTab', () => ({ ProvidersTab: () => <div data-testid="c-providers" /> }));
vi.mock('../TranslationTab', () => ({ TranslationTab: () => <div data-testid="c-translation" /> }));
vi.mock('../ReadingTab', () => ({ ReadingTab: () => <div data-testid="c-reading" /> }));
vi.mock('../LanguageTab', () => ({ LanguageTab: () => <div data-testid="c-language" /> }));
vi.mock('../McpAccessTab', () => ({ McpAccessTab: () => <div data-testid="c-mcp" /> }));
vi.mock('@/features/chat-ai-settings/components/ChatAiSettingsPanel', () => ({
  ChatAiSettingsPanel: () => <div data-testid="c-chat-ai" />,
}));
vi.mock('@/features/modeBindings/components/BindingSettingsPanel', () => ({
  BindingSettingsPanel: () => <div data-testid="c-workflow-bindings" />,
}));

const authState = { user: { public_mcp_enabled: false } as { public_mcp_enabled: boolean } | null };
vi.mock('@/auth', () => ({ useAuth: () => authState }));

vi.mock('../../studio/panels/useStudioPanel', () => ({ useStudioPanel: () => undefined }));

import { settingsTabsFor, isSettingsTab, SettingsTabContent } from '../tabs';
import { SettingsPage } from '@/pages/SettingsPage';
import { SettingsPanel } from '@/features/studio/panels/SettingsPanel';

const EXPECTED_BASE = ['account', 'chat-ai', 'providers', 'translation', 'reading', 'language', 'workflow-bindings'];

beforeEach(() => {
  authState.user = { public_mcp_enabled: false };
});

describe('settings tab registry', () => {
  it('lists every base tab, Chat & AI included, in display order', () => {
    expect(settingsTabsFor(false).map((t) => t.id)).toEqual(EXPECTED_BASE);
  });

  it('appends the public-MCP tab only behind the platform flag (Q-GATE)', () => {
    expect(settingsTabsFor(false).map((t) => t.id)).not.toContain('mcp');
    expect(settingsTabsFor(true).map((t) => t.id)).toEqual([...EXPECTED_BASE, 'mcp']);
    expect(settingsTabsFor(undefined).map((t) => t.id)).not.toContain('mcp');
  });

  it('narrows only real tab ids', () => {
    expect(isSettingsTab('chat-ai')).toBe(true);
    expect(isSettingsTab('mcp')).toBe(true); // a gated tab is still a VALID id
    expect(isSettingsTab('nope')).toBe(false);
    expect(isSettingsTab(undefined)).toBe(false);
    expect(isSettingsTab(7)).toBe(false);
  });

  it('renders content for every id — no tab can be listed without a body', () => {
    for (const { id } of settingsTabsFor(true)) {
      const { unmount } = render(<SettingsTabContent tab={id} />);
      expect(screen.getByTestId(`c-${id}`)).toBeInTheDocument();
      unmount();
    }
  });
});

function renderPage(tab: string) {
  return render(
    <MemoryRouter initialEntries={[`/settings/${tab}`]}>
      <Routes>
        <Route path="/settings/:tab" element={<SettingsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderDock() {
  const props = {
    api: { onDidParametersChange: () => ({ dispose: () => undefined }) },
    params: {},
  } as unknown as IDockviewPanelProps;
  return render(<SettingsPanel {...props} />);
}

describe('both surfaces render exactly the registry', () => {
  it('the /settings page offers every registry tab', () => {
    renderPage('account');
    const rendered = screen.getAllByRole('tab').map((el) => el.textContent?.trim());
    expect(rendered).toEqual(EXPECTED_BASE.map((id) => `page.tab.${id}`));
  });

  it('the Studio settings dock offers every registry tab — including chat-ai', () => {
    renderDock();
    for (const id of EXPECTED_BASE) {
      expect(screen.getByTestId(`studio-settings-tab-${id}`)).toBeInTheDocument();
    }
  });

  it('the Studio dock can actually OPEN Chat & AI (the drift that shipped)', () => {
    renderDock();
    fireEvent.click(screen.getByTestId('studio-settings-tab-chat-ai'));
    expect(screen.getByTestId('c-chat-ai')).toBeInTheDocument();
  });

  it('the /settings page can open Chat & AI', () => {
    renderPage('chat-ai');
    expect(screen.getByTestId('c-chat-ai')).toBeInTheDocument();
  });

  it('both surfaces gate the MCP tab on the same flag', () => {
    authState.user = { public_mcp_enabled: false };
    const dockOff = renderDock();
    expect(screen.queryByTestId('studio-settings-tab-mcp')).toBeNull();
    dockOff.unmount();

    authState.user = { public_mcp_enabled: true };
    renderDock();
    expect(screen.getByTestId('studio-settings-tab-mcp')).toBeInTheDocument();
  });
});
