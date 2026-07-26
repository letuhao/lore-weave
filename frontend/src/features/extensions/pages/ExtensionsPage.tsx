// Standalone /extensions route (§13b two-shells) — the SAME SkillsView +
// ProposalsView that mount in the studio ExtensionsPanel/ProposalsPanel, here as
// a full page. Logic stays in the hooks; this is a render-only shell.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useUsage } from '../hooks/useExtensions';
import { SkillsView } from '../components/SkillsView';
import { ProposalsView } from '../components/ProposalsView';
import { McpServersView } from '../components/McpServersView';
import { CommandsHooksView } from '../components/CommandsHooksView';
import { PluginsView } from '../components/PluginsView';
import { SubagentsView } from '../components/SubagentsView';
import { ActivityView } from '../components/ActivityView';
import { AdminIngestView } from '../components/AdminIngestView';
import { PermissionsView } from '../components/PermissionsView';
import { WorkflowRackPanel } from '@/features/workflows/components/WorkflowRackPanel';
import { BindingSettingsPanel } from '@/features/modeBindings/components/BindingSettingsPanel';
import { useIsAdmin } from '../adminGate';
import { ExtensionScopeProvider, useExtensionScope } from '../context/ExtensionScope';
import { BookPicker } from '@/components/shared/BookPicker';

type Tab = 'skills' | 'workflows' | 'bindings' | 'mcp' | 'commands' | 'subagents' | 'plugins' | 'permissions' | 'proposals' | 'activity' | 'ingest';

// D-REG-BOOK-TIER-FE — pick a book to manage its book-tier extensions (or "My" for the
// user's own). Bound to the shared scope; every capability hook reads it.
function ScopeBar() {
  const { t } = useTranslation('extensions');
  const { bookId, setBookId } = useExtensionScope();
  return (
    <div className="mb-4 flex items-center gap-2 text-xs" data-testid="extensions-scope">
      <span className="text-muted-foreground">{t('scope.label')}</span>
      <button
        onClick={() => setBookId(null)}
        data-testid="scope-user"
        className={`rounded-md px-2 py-1 ${bookId === null ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
      >{t('scope.mine')}</button>
      <span className="text-muted-foreground">{t('scope.orBook')}</span>
      <div className="min-w-[220px]"><BookPicker value={bookId} onChange={setBookId} placeholder={t('scope.bookPlaceholder')} /></div>
      {bookId && <span className="text-amber-500">{t('scope.bookHint')}</span>}
    </div>
  );
}

export function ExtensionsPage() {
  return (
    <ExtensionScopeProvider>
      <ExtensionsPageInner />
    </ExtensionScopeProvider>
  );
}

function ExtensionsPageInner() {
  const { t } = useTranslation('extensions');
  const [tab, setTab] = useState<Tab>('skills');
  const { usage, unavailable } = useUsage();
  const isAdmin = useIsAdmin();
  const { bookId } = useExtensionScope();
  return (
    <div className="mx-auto max-w-4xl p-6" data-testid="extensions-page">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">{t('title')}</h1>
        {usage ? (
          <div className="flex gap-4 text-xs text-muted-foreground" data-testid="extensions-quota">
            <span>{t('quota.skills')} <b className="text-foreground">{usage.skills.used}/{usage.skills.limit}</b></span>
            <span>{t('quota.mcp')} <b className="text-foreground">{usage.mcp_servers.used}/{usage.mcp_servers.limit}</b></span>
            {usage.proposals_pending > 0 && <span>{t('quota.proposals')} <b className="text-foreground">{usage.proposals_pending}</b></span>}
          </div>
        ) : unavailable ? (
          <div className="text-xs text-muted-foreground" data-testid="extensions-quota-unavailable">{t('quota.unavailable')}</div>
        ) : null}
      </div>
      <ScopeBar />
      <div className="mb-4 flex gap-1 text-sm">
        <button
          onClick={() => setTab('skills')}
          data-testid="ext-page-tab-skills"
          className={`rounded-md px-3 py-1.5 ${tab === 'skills' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >{t('tabs.skills')}</button>
        <button
          onClick={() => setTab('workflows')}
          data-testid="ext-page-tab-workflows"
          className={`rounded-md px-3 py-1.5 ${tab === 'workflows' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >{t('tabs.workflows', { defaultValue: 'Recipes' })}</button>
        <button
          onClick={() => setTab('bindings')}
          data-testid="ext-page-tab-bindings"
          className={`rounded-md px-3 py-1.5 ${tab === 'bindings' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >{t('tabs.bindings', { defaultValue: 'Auto-setup' })}</button>
        <button
          onClick={() => setTab('mcp')}
          data-testid="ext-page-tab-mcp"
          className={`rounded-md px-3 py-1.5 ${tab === 'mcp' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >{t('tabs.mcp')}</button>
        <button
          onClick={() => setTab('commands')}
          data-testid="ext-page-tab-commands"
          className={`rounded-md px-3 py-1.5 ${tab === 'commands' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >{t('tabs.commands')}</button>
        <button
          onClick={() => setTab('subagents')}
          data-testid="ext-page-tab-subagents"
          className={`rounded-md px-3 py-1.5 ${tab === 'subagents' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >{t('tabs.subagents')}</button>
        <button
          onClick={() => setTab('plugins')}
          data-testid="ext-page-tab-plugins"
          className={`rounded-md px-3 py-1.5 ${tab === 'plugins' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >{t('tabs.plugins')}</button>
        <button
          onClick={() => setTab('permissions')}
          data-testid="ext-page-tab-permissions"
          className={`rounded-md px-3 py-1.5 ${tab === 'permissions' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >{t('tabs.permissions')}</button>
        <button
          onClick={() => setTab('proposals')}
          data-testid="ext-page-tab-proposals"
          className={`rounded-md px-3 py-1.5 ${tab === 'proposals' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >{t('tabs.proposals')}{usage && usage.proposals_pending > 0 ? ` (${usage.proposals_pending})` : ''}</button>
        <button
          onClick={() => setTab('activity')}
          data-testid="ext-page-tab-activity"
          className={`rounded-md px-3 py-1.5 ${tab === 'activity' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
        >{t('tabs.activity')}</button>
        {isAdmin && (
          <button
            onClick={() => setTab('ingest')}
            data-testid="ext-page-tab-ingest"
            className={`rounded-md px-3 py-1.5 ${tab === 'ingest' ? 'bg-muted font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
          >{t('tabs.ingest')}</button>
        )}
      </div>
      <div className={tab === 'skills' ? '' : 'hidden'}><SkillsView /></div>
      {/* M5 workflow rack + M6 binding UI — keep-mounted-hidden (own fetch/toggle state). */}
      <div className={tab === 'workflows' ? '' : 'hidden'}><WorkflowRackPanel bookId={bookId ?? undefined} /></div>
      <div className={tab === 'bindings' ? '' : 'hidden'}><BindingSettingsPanel bookId={bookId ?? undefined} /></div>
      <div className={tab === 'mcp' ? '' : 'hidden'}><McpServersView /></div>
      <div className={tab === 'commands' ? '' : 'hidden'}><CommandsHooksView /></div>
      <div className={tab === 'subagents' ? '' : 'hidden'}><SubagentsView /></div>
      <div className={tab === 'plugins' ? '' : 'hidden'}><PluginsView /></div>
      {/* keep-mounted — owns the block-a-tool form's draft state. */}
      <div className={tab === 'permissions' ? '' : 'hidden'}><PermissionsView /></div>
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
