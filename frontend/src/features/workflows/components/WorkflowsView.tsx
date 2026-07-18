// View (MVC) — render-only workflow management: list + enable/disable + delete.
// Mirrors extensions/SkillsView. System-tier rows are read-only (badge, no delete); a
// user may still disable a System workflow FOR THEMSELVES (per-user override, SD-1).
import { useTranslation } from 'react-i18next';
import { useWorkflowManage } from '../hooks/useWorkflowManage';
import type { WorkflowMeta } from '../types';

export function WorkflowsView({ bookId }: { bookId?: string }) {
  const { t } = useTranslation('extensions');
  const m = useWorkflowManage(bookId);
  return (
    <div className="space-y-3" data-testid="workflows-view">
      <span className="text-xs text-muted-foreground">{t('workflows.total', { count: m.workflows.length })}</span>
      {m.error && <div className="rounded-md border border-red-400 bg-red-500/10 px-3 py-2 text-xs text-red-400">{m.error}</div>}
      {!m.loading && m.workflows.length === 0 && !m.error && (
        <div className="rounded-md border border-dashed px-6 py-8 text-center text-xs text-muted-foreground" data-testid="workflows-empty">
          {t('workflows.empty')}
        </div>
      )}
      <ul className="space-y-2">
        {m.workflows.map((wf) => (
          <WorkflowRow
            key={wf.workflow_id ?? wf.slug}
            wf={wf}
            onToggle={(enabled) => void m.toggle(wf, enabled)}
            onRemove={() => void m.remove(wf)}
          />
        ))}
      </ul>
    </div>
  );
}

function WorkflowRow({ wf, onToggle, onRemove }: { wf: WorkflowMeta; onToggle: (enabled: boolean) => void; onRemove: () => void }) {
  const { t } = useTranslation('extensions');
  const isSystem = wf.tier === 'system';
  const enabled = wf.enabled !== false;
  return (
    <li className="flex items-center gap-2 rounded-md border p-3" data-testid="workflow-row">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium">{wf.title || wf.slug}</span>
          <span className="rounded border px-1.5 text-[10px] uppercase text-muted-foreground">{wf.tier}</span>
        </div>
        <div className="truncate text-xs text-muted-foreground">{wf.description}</div>
      </div>
      <button
        role="switch"
        aria-checked={enabled}
        data-testid="workflow-toggle"
        onClick={() => onToggle(!enabled)}
        className={`rounded border px-2 py-1 text-xs ${enabled ? 'border-green-400/60 text-green-400' : 'border-muted text-muted-foreground'}`}
      >
        {enabled ? t('workflows.enabled') : t('workflows.disabled')}
      </button>
      {!isSystem && (
        <button
          onClick={onRemove}
          data-testid="workflow-delete"
          className="rounded border border-red-400/60 px-2 py-1 text-xs text-red-400"
        >
          {t('workflows.delete')}
        </button>
      )}
    </li>
  );
}
