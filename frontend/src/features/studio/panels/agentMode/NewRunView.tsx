// #20_agent_mode.md §2 (New run config) — render-only view; all logic lives in
// useNewRunForm. Chapter reordering uses real move-up/down controls (not a DnD
// library) — a functional substitute for the mockup's cosmetic drag handle,
// documented here rather than left silently unimplemented.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUp, ArrowDown, X } from 'lucide-react';
import { useNewRunForm } from './useNewRunForm';
import { GateChecklist } from './GateChecklist';

interface Props {
  bookId: string;
  onCreated: (runId: string) => void;
  onCancel: () => void;
}

export function NewRunView({ bookId, onCreated, onCancel }: Props) {
  const { t } = useTranslation('composition');
  const f = useNewRunForm(bookId);
  const [newTool, setNewTool] = useState('');

  const submit = async () => {
    try {
      const runId = await f.runGateCheck();
      onCreated(runId);
    } catch {
      // f.error already holds the message; stay on this view so the user can fix it.
    }
  };

  return (
    <div className="space-y-4 p-3" data-testid="agent-mode-new-run">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {t('authoringRun.newRun.title', { defaultValue: 'New run — configure' })}
      </h2>

      <div>
        <label className="mb-1 block text-[10.5px] uppercase tracking-wide text-muted-foreground">
          {t('authoringRun.newRun.planLabel', {
            defaultValue: "Plan (required — a run drafts an already-approved plan's beats)",
          })}
        </label>
        {f.approvedPlans.length === 0 ? (
          <p data-testid="agent-mode-plan-empty" className="text-xs text-muted-foreground">
            {t('authoringRun.newRun.planEmpty', { defaultValue: 'No approved plan runs yet for this book.' })}
          </p>
        ) : (
          <select
            data-testid="agent-mode-plan-select"
            value={f.planRunId}
            onChange={(e) => f.setPlanRunId(e.target.value)}
            className="w-full rounded-md border bg-background px-2 py-1.5 text-xs"
          >
            {f.approvedPlans.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id.slice(0, 8)}… · {p.status}
              </option>
            ))}
          </select>
        )}
      </div>

      <div>
        <label className="mb-1 block text-[10.5px] uppercase tracking-wide text-muted-foreground">
          {t('authoringRun.newRun.chaptersLabel', { defaultValue: 'Chapters to include (book TOC)' })}
        </label>
        <div className="max-h-48 overflow-y-auto rounded-md border">
          {f.chapters.map((c) => (
            <label key={c.chapter_id} className="flex items-center gap-2 border-b px-2 py-1.5 text-xs last:border-b-0">
              <input
                type="checkbox"
                data-testid={`agent-mode-chapter-check-${c.chapter_id}`}
                checked={f.scopeIds.includes(c.chapter_id)}
                onChange={() => f.toggleChapter(c.chapter_id)}
              />
              {c.title || c.original_filename}
            </label>
          ))}
        </div>
        <p className="mt-1 text-[10.5px] text-muted-foreground">
          {t('authoringRun.newRun.chaptersHint', {
            total: f.chapters.length, selected: f.scopeIds.length,
            defaultValue: '{{total}} chapters in book · {{selected}} selected',
          })}
        </p>
      </div>

      <div>
        <label className="mb-1 block text-[10.5px] uppercase tracking-wide text-muted-foreground">
          {t('authoringRun.newRun.orderLabel', { defaultValue: 'Run order' })}
        </label>
        <div className="rounded-md border" data-testid="agent-mode-run-order">
          {f.scopeIds.map((id, idx) => {
            const chapter = f.chapters.find((c) => c.chapter_id === id);
            return (
              <div key={id} className="flex items-center gap-2 border-b px-2 py-1.5 text-xs last:border-b-0">
                <span className="w-5 font-mono text-muted-foreground">{idx + 1}</span>
                <span className="flex-1 truncate">{chapter?.title || chapter?.original_filename || id.slice(0, 8)}</span>
                <button
                  type="button"
                  aria-label="Move up"
                  data-testid={`agent-mode-move-up-${id}`}
                  disabled={idx === 0}
                  onClick={() => f.moveChapter(idx, -1)}
                  className="rounded p-0.5 hover:bg-secondary disabled:opacity-30"
                >
                  <ArrowUp className="h-3 w-3" />
                </button>
                <button
                  type="button"
                  aria-label="Move down"
                  data-testid={`agent-mode-move-down-${id}`}
                  disabled={idx === f.scopeIds.length - 1}
                  onClick={() => f.moveChapter(idx, 1)}
                  className="rounded p-0.5 hover:bg-secondary disabled:opacity-30"
                >
                  <ArrowDown className="h-3 w-3" />
                </button>
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex gap-3">
        <div className="flex-1">
          <label className="mb-1 block text-[10.5px] uppercase tracking-wide text-muted-foreground">
            {t('authoringRun.newRun.budgetLabel', { defaultValue: 'Budget (USD)' })}
          </label>
          <input
            data-testid="agent-mode-budget-input"
            type="number"
            min="0"
            step="0.01"
            value={f.budgetUsd}
            onChange={(e) => f.setBudgetUsd(e.target.value)}
            className="w-full rounded-md border bg-background px-2 py-1.5 text-xs"
          />
        </div>
        <div className="flex-1">
          <label className="mb-1 block text-[10.5px] uppercase tracking-wide text-muted-foreground">
            {t('authoringRun.newRun.levelLabel', { defaultValue: 'Level' })}
          </label>
          <select
            data-testid="agent-mode-level-select"
            value={f.level}
            onChange={(e) => f.setLevel(Number(e.target.value) as 3 | 4)}
            className="w-full rounded-md border bg-background px-2 py-1.5 text-xs"
          >
            <option value={3}>{t('authoringRun.newRun.level3', { defaultValue: 'Level 3 — revise' })}</option>
            <option value={4}>{t('authoringRun.newRun.level4', { defaultValue: 'Level 4 — draft' })}</option>
          </select>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-[10.5px] uppercase tracking-wide text-muted-foreground">
          {t('authoringRun.newRun.allowlistLabel', { defaultValue: 'Tool allowlist' })}
        </label>
        <div className="flex flex-wrap gap-1.5" data-testid="agent-mode-allowlist-chips">
          {f.toolAllowlist.map((tool) => (
            <span key={tool} className="inline-flex items-center gap-1 rounded-full border bg-secondary px-2 py-0.5 text-[10.5px]">
              {tool}
              <button type="button" aria-label={`remove ${tool}`} onClick={() => f.removeAllowlistTool(tool)}>
                <X className="h-2.5 w-2.5" />
              </button>
            </span>
          ))}
        </div>
        <div className="mt-1.5 flex gap-1.5">
          <input
            data-testid="agent-mode-allowlist-input"
            value={newTool}
            onChange={(e) => setNewTool(e.target.value)}
            placeholder={t('authoringRun.newRun.allowlistAdd', { defaultValue: 'Add tool…' })}
            className="flex-1 rounded-md border bg-background px-2 py-1 text-xs"
          />
          <button
            type="button"
            data-testid="agent-mode-allowlist-add"
            onClick={() => { f.addAllowlistTool(newTool); setNewTool(''); }}
            className="rounded-md border px-2 py-1 text-xs hover:bg-secondary"
          >
            +
          </button>
        </div>
      </div>

      <label className="flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          data-testid="agent-mode-pause-toggle"
          checked={f.pauseAfterEachUnit}
          onChange={(e) => f.setPauseAfterEachUnit(e.target.checked)}
        />
        {t('authoringRun.header.pausePolicyLabel', { defaultValue: 'Auto-pause after each unit' })}
      </label>

      <div>
        <h3 className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('authoringRun.gate.title', { defaultValue: 'Gate check' })}
        </h3>
        <GateChecklist items={f.gateChecks} />
      </div>

      {f.error && (
        <p data-testid="agent-mode-gate-error" className="text-xs text-destructive">{f.error}</p>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          data-testid="agent-mode-run-gate-check"
          disabled={!f.canRunGateCheck}
          onClick={() => void submit()}
          className="rounded-md border border-primary bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {f.busy
            ? t('authoringRun.newRun.gating', { defaultValue: 'Checking…' })
            : t('authoringRun.newRun.runGateCheck', { defaultValue: 'Run gate check →' })}
        </button>
        <button type="button" onClick={onCancel} className="rounded-md border px-3 py-1.5 text-xs hover:bg-secondary">
          {t('authoringRun.newRun.cancel', { defaultValue: 'Cancel' })}
        </button>
      </div>
    </div>
  );
}
