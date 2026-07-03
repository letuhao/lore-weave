// Extensions hub dock panel (§13b) — plugins · MCP servers · skills · commands.
// P1 slice wires the Skills tab (real) + placeholders for the later-phase tabs.
// Same components mount on the standalone route (two shells, one controller).
import { useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { SkillsView } from '@/features/extensions/components/SkillsView';
import { McpServersView } from '@/features/extensions/components/McpServersView';
import { useStudioPanel } from './useStudioPanel';

type Tab = 'skills' | 'plugins' | 'mcp' | 'commands';

export function ExtensionsPanel(props: IDockviewPanelProps) {
  useStudioPanel('extensions', props.api);
  const [tab, setTab] = useState<Tab>('skills');
  return (
    <div data-testid="studio-extensions-panel" className="flex h-full min-h-0 flex-col p-3">
      <div className="mb-3 flex gap-1 text-xs">
        <TabBtn active={tab === 'skills'} onClick={() => setTab('skills')} label="Skills" testid="ext-tab-skills" />
        <TabBtn active={tab === 'plugins'} onClick={() => setTab('plugins')} label="Plugins" testid="ext-tab-plugins" />
        <TabBtn active={tab === 'mcp'} onClick={() => setTab('mcp')} label="MCP Servers" testid="ext-tab-mcp" />
        <TabBtn active={tab === 'commands'} onClick={() => setTab('commands')} label="Commands & Hooks" testid="ext-tab-commands" />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {/* Never-unmount: keep each tab's view mounted, hide inactive (wizard/detail
            state survives a tab switch or panel hide/show). */}
        <div className={tab === 'skills' ? '' : 'hidden'}><SkillsView /></div>
        <div className={tab === 'mcp' ? '' : 'hidden'}><McpServersView /></div>
        {(tab === 'plugins' || tab === 'commands') && (
          <div className="rounded-md border border-dashed px-6 py-8 text-center text-xs text-muted-foreground">
            {tab === 'plugins' && 'Plugin management — arrives with the bundling phase.'}
            {tab === 'commands' && 'Slash commands & hooks — arrives with the commands phase.'}
          </div>
        )}
      </div>
    </div>
  );
}

function TabBtn({ active, onClick, label, testid }: { active: boolean; onClick: () => void; label: string; testid: string }) {
  return (
    <button
      onClick={onClick}
      data-testid={testid}
      className={`rounded-md px-2.5 py-1 ${active ? 'bg-muted font-semibold text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
    >
      {label}
    </button>
  );
}
