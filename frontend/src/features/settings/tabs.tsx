// The ONE settings-tab registry — id, icon, and content component in a single place.
//
// Why this exists: the tab list used to be duplicated in `pages/SettingsPage.tsx` and
// `features/studio/panels/SettingsPanel.tsx`. When the Chat & AI surface shipped
// (spec 2026-07-05-chat-ai-settings.md) it was added to the page and MISSED on the studio
// dock, so a user working in the Studio could not reach Chat & AI settings at all — the
// shipped-but-unreachable bug class. Two copies of a list drift; one copy cannot.
//
// Both surfaces render their own chrome (the page uses <Link> + routes, the dock uses
// buttons + panel state) and import the tabs + content from here. Adding a tab is now a
// one-line change that lands on both, and `settingsTabParity` proves it.
import type { ReactElement } from 'react';
import { User, MessagesSquare, Cpu, Languages, BookOpen, Globe, KeyRound, Workflow } from 'lucide-react';

import { AccountTab } from './AccountTab';
import { ProvidersTab } from './ProvidersTab';
import { TranslationTab } from './TranslationTab';
import { ReadingTab } from './ReadingTab';
import { LanguageTab } from './LanguageTab';
import { McpAccessTab } from './McpAccessTab';
import { ChatAiSettingsPanel } from '@/features/chat-ai-settings/components/ChatAiSettingsPanel';
import { BindingSettingsPanel } from '@/features/modeBindings/components/BindingSettingsPanel';

export type SettingsTabId =
  | 'account'
  | 'chat-ai'
  | 'providers'
  | 'translation'
  | 'reading'
  | 'language'
  | 'workflow-bindings'
  | 'mcp';

type TabIcon = React.ComponentType<{ className?: string }>;
export type SettingsTab = { id: SettingsTabId; icon: TabIcon };

/** Always-present tabs, in display order. */
const BASE_TABS: SettingsTab[] = [
  { id: 'account', icon: User },
  { id: 'chat-ai', icon: MessagesSquare },
  { id: 'providers', icon: Cpu },
  { id: 'translation', icon: Languages },
  { id: 'reading', icon: BookOpen },
  { id: 'language', icon: Globe },
  // S-12 (G-WORKFLOWS): mode→workflow auto-injection bindings, surfaced as a real setting
  // (effective value + source tier already come from getModeBinding, SET-1..8). Was
  // write-only-behavior — the UI existed only on the /extensions route until now.
  { id: 'workflow-bindings', icon: Workflow },
];

/** Q-GATE: the public-MCP tab exists only when the platform flag is on for this user. */
const MCP_TAB: SettingsTab = { id: 'mcp', icon: KeyRound };

/** The tabs this user may see. Both surfaces call exactly this — the gate cannot drift. */
export function settingsTabsFor(publicMcpEnabled: boolean | undefined): SettingsTab[] {
  return publicMcpEnabled ? [...BASE_TABS, MCP_TAB] : BASE_TABS;
}

const ALL_TAB_IDS: readonly SettingsTabId[] = [...BASE_TABS, MCP_TAB].map((t) => t.id);

/** Narrow an unknown (a route param, a dock `params.tab`) to a real tab id. */
export function isSettingsTab(value: unknown): value is SettingsTabId {
  return typeof value === 'string' && (ALL_TAB_IDS as readonly string[]).includes(value);
}

/**
 * Render one tab's content. A `switch` (not a lookup map of elements) so TypeScript's
 * exhaustiveness check fails the build when a new `SettingsTabId` has no content — the
 * compiler, not a reviewer, catches the half-added tab.
 */
export function SettingsTabContent({ tab }: { tab: SettingsTabId }): ReactElement {
  switch (tab) {
    case 'account':
      return <AccountTab />;
    case 'chat-ai':
      return <ChatAiSettingsPanel />;
    case 'providers':
      return <ProvidersTab />;
    case 'translation':
      return <TranslationTab />;
    case 'reading':
      return <ReadingTab />;
    case 'language':
      return <LanguageTab />;
    case 'workflow-bindings':
      return <BindingSettingsPanel />;
    case 'mcp':
      return <McpAccessTab />;
  }
}
