// View (MVC) — render-only workflow management: list + view-one + enable/disable + delete.
// Mirrors extensions/SkillsView. System-tier rows are read-only (badge, no delete); a
// user may still disable a System workflow FOR THEMSELVES (per-user override, SD-1).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useWorkflowManage } from '../hooks/useWorkflowManage';
import type { WorkflowMeta, WorkflowFull } from '../types';

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
            loadDetail={m.loadDetail}
            onToggle={(enabled) => void m.toggle(wf, enabled)}
            onRemove={() => void m.remove(wf)}
          />
        ))}
      </ul>
    </div>
  );
}

function WorkflowRow({
  wf, loadDetail, onToggle, onRemove,
}: {
  wf: WorkflowMeta;
  loadDetail: (id: string) => Promise<WorkflowFull | null>;
  onToggle: (enabled: boolean) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation('extensions');
  const isSystem = wf.tier === 'system';
  const enabled = wf.enabled !== false;
  const [detail, setDetail] = useState<WorkflowFull | null>(null);
  const [open, setOpen] = useState(false);

  // view-one: lazy-load the full workflow (steps) on first expand; the fetch lives in the
  // hook (loadDetail) so the component stays render-only (MVC: no API calls in components).
  const toggleOpen = () => {
    const next = !open;
    setOpen(next);
    if (next && !detail && wf.workflow_id) void loadDetail(wf.workflow_id).then(setDetail);
  };

  return (
    <li className="rounded-md border p-3" data-testid="workflow-row">
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-medium">{wf.title || wf.slug}</span>
            <span className="rounded border px-1.5 text-[10px] uppercase text-muted-foreground">{wf.tier}</span>
          </div>
          <div className="truncate text-xs text-muted-foreground">{wf.description}</div>
        </div>
        <button
          onClick={toggleOpen}
          data-testid="workflow-view"
          aria-expanded={open}
          className="rounded border px-2 py-1 text-xs text-muted-foreground"
        >
          {open ? t('workflows.hide') : t('workflows.view')}
        </button>
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
      </div>
      {open && detail && (
        <ol className="mt-2 space-y-0.5 rounded bg-muted/40 p-2 text-[11px]" data-testid="workflow-steps">
          {detail.steps.length === 0 && <li className="text-muted-foreground">{t('workflows.noSteps')}</li>}
          {detail.steps.map((s, i) => (
            <li key={s.id || i} className="flex gap-2">
              <span className="text-muted-foreground">{i + 1}.</span>
              <span className="font-mono">{s.tool}</span>
              {s.gate && s.gate !== 'auto' && <span className="rounded border px-1 text-[10px] text-amber-500">{s.gate}</span>}
            </li>
          ))}
        </ol>
      )}
    </li>
  );
}
