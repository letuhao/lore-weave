// Standalone /extensions route (§13b two-shells) — the SAME SkillsView +
// ProposalsView that mount in the studio ExtensionsPanel/ProposalsPanel, here as
// a full page. Logic stays in the hooks; this is a render-only shell.
import { useState } from 'react';
import { useUsage } from '../hooks/useExtensions';
import { SkillsView } from '../components/SkillsView';
import { ProposalsView } from '../components/ProposalsView';
import { McpServersView } from '../components/McpServersView';
import { CommandsHooksView } from '../components/CommandsHooksView';
import { PluginsView } from '../components/PluginsView';
import { SubagentsView } from '../components/SubagentsView';
import { ActivityView } from '../components/ActivityView';
import { AdminIngestView } from '../components/AdminIngestView';
import { useIsAdmin } from '../adminGate';

type Tab = 'skills' | 'mcp' | 'commands' | 'subagents' | 'plugins' | 'proposals' | 'activity' | 'ingest';

export function ExtensionsPage() {
  const [tab, setTab] = useState<Tab>('skills');
  const usage = useUsage();
  const isAdmin = useIsAdmin();
  return (
    <div className="mx-auto max-w-4xl p-6" data-testid="extensions-page">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Extensions</h1>
        {usage && (
          <div className="flex gap-4 text-xs text-muted-foreground" data-testid="extensions-quota">
            <span>Skills <b className="text-foreground">{usage.skills.used}/{usage.skills.limit}</b></span>
            <span>MCP servers <b className="text-foreground">{usage.mcp_servers.used}/{usage.mcp_servers.limit}</b></span>
            {usage.proposals_pending > 0 && <span>Proposals <b className="text-foreground">{usage.proposals_pending}</b></span>}
          </div>
        )}
      </div>
      <div className="mb-4 flex gap-1 text-sm">
        <button
          onClick={() => setTab('skills')}
          data-testid="ext-page-tab-skills"
          className={`rounded-md px-3 py-1.5 ${tab === 'skills' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >Skills</button>
        <button
          onClick={() => setTab('mcp')}
          data-testid="ext-page-tab-mcp"
          className={`rounded-md px-3 py-1.5 ${tab === 'mcp' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >MCP Servers</button>
        <button
          onClick={() => setTab('commands')}
          data-testid="ext-page-tab-commands"
          className={`rounded-md px-3 py-1.5 ${tab === 'commands' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >Commands & Hooks</button>
        <button
          onClick={() => setTab('subagents')}
          data-testid="ext-page-tab-subagents"
          className={`rounded-md px-3 py-1.5 ${tab === 'subagents' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >Subagents</button>
        <button
          onClick={() => setTab('plugins')}
          data-testid="ext-page-tab-plugins"
          className={`rounded-md px-3 py-1.5 ${tab === 'plugins' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >Plugins</button>
        <button
          onClick={() => setTab('proposals')}
          data-testid="ext-page-tab-proposals"
          className={`rounded-md px-3 py-1.5 ${tab === 'proposals' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >Proposals{usage && usage.proposals_pending > 0 ? ` (${usage.proposals_pending})` : ''}</button>
        <button
          onClick={() => setTab('activity')}
          data-testid="ext-page-tab-activity"
          className={`rounded-md px-3 py-1.5 ${tab === 'activity' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >Activity log</button>
        {isAdmin && (
          <button
            onClick={() => setTab('ingest')}
            data-testid="ext-page-tab-ingest"
            className={`rounded-md px-3 py-1.5 ${tab === 'ingest' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
          >Registry sources</button>
        )}
      </div>
      <div className={tab === 'skills' ? '' : 'hidden'}><SkillsView /></div>
      <div className={tab === 'mcp' ? '' : 'hidden'}><McpServersView /></div>
      <div className={tab === 'commands' ? '' : 'hidden'}><CommandsHooksView /></div>
      <div className={tab === 'subagents' ? '' : 'hidden'}><SubagentsView /></div>
      <div className={tab === 'plugins' ? '' : 'hidden'}><PluginsView /></div>
      {tab === 'proposals' && <ProposalsView />}
      {/* keep-mounted (CLAUDE.md: never conditionally unmount stateful components) —
          ActivityView owns kind/range filter state, so hide it, don't unmount it. */}
      <div className={tab === 'activity' ? '' : 'hidden'}><ActivityView /></div>
      {/* admin-only; non-admins never mount it (tab hidden + API 403s). For admins it's
          keep-mounted-hidden like the others (owns status-filter state — don't unmount). */}
      {isAdmin && <div className={tab === 'ingest' ? '' : 'hidden'}><AdminIngestView /></div>}
    </div>
  );
}
