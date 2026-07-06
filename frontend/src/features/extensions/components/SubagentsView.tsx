// View (MVC) — the Subagent-persona authoring GUI (REG-P5-01). Create a named
// persona (system_prompt + a tool_scope subset + optional model_ref); the runtime
// `run_subagent` resolves + runs these. Render-only; logic in useSubagents.
import { useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { useSubagents } from '../hooks/useSubagents';
import type { Subagent } from '../types';

const inputCls = 'w-full rounded-md border bg-background px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring';

// "glossary_*, kg_*" → ["glossary_*","kg_*"] (empty = a pure-reasoning subagent).
function parseScope(raw: string): string[] {
  return raw.split(',').map((s) => s.trim()).filter(Boolean);
}

export function SubagentsView() {
  const { t } = useTranslation('extensions');
  const sa = useSubagents();
  const [name, setName] = useState('');
  const [modelRef, setModelRef] = useState('');
  const [scope, setScope] = useState('');
  const [prompt, setPrompt] = useState('');
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null);
    const e = await sa.create({
      name: name.trim(),
      system_prompt: prompt.trim(),
      tool_scope: parseScope(scope),
      model_ref: modelRef.trim() || undefined,
    });
    if (e) { setErr(e); return; } // surface the backend error verbatim — no silent no-op
    setName(''); setModelRef(''); setScope(''); setPrompt('');
  };

  const canSubmit = !!name.trim() && !!prompt.trim();

  return (
    <section className="space-y-2" data-testid="subagents-view">
      <h3 className="text-sm font-semibold">{t('subagents.title')}</h3>
      <p className="text-xs text-muted-foreground">
        <Trans i18nKey="subagents.description" ns="extensions" components={{ code: <code /> }} />
      </p>
      <div className="space-y-2 rounded-md border p-3">
        <div className="flex flex-wrap items-start gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('subagents.namePlaceholder')} data-testid="sa-name" className={`${inputCls} max-w-[180px]`} />
          <input value={scope} onChange={(e) => setScope(e.target.value)} placeholder={t('subagents.scopePlaceholder')} data-testid="sa-scope" className={`${inputCls} min-w-[200px] flex-1`} />
          <input value={modelRef} onChange={(e) => setModelRef(e.target.value)} placeholder={t('subagents.modelPlaceholder')} data-testid="sa-model" className={`${inputCls} max-w-[220px]`} />
        </div>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder={t('subagents.promptPlaceholder')} data-testid="sa-prompt" rows={3} className={inputCls} />
        <div className="flex justify-end">
          <button onClick={() => void submit()} disabled={!canSubmit} data-testid="sa-create" className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-40">{t('subagents.create')}</button>
        </div>
      </div>
      {err && <div className="rounded-md border border-red-400 bg-red-500/10 px-3 py-1.5 text-xs text-red-400" data-testid="sa-error">{err}</div>}
      {sa.error && <div className="text-xs text-red-400">{sa.error}</div>}
      <ul className="divide-y rounded-md border">
        {sa.subagents.length === 0 && !sa.loading && <li className="px-3 py-4 text-center text-xs text-muted-foreground">{t('subagents.empty')}</li>}
        {sa.subagents.map((s) => <SubagentRow key={s.subagent_id} sub={s} onToggle={(en) => void sa.toggle(s, en)} onRemove={() => void sa.remove(s)} />)}
      </ul>
    </section>
  );
}

function SubagentRow({ sub, onToggle, onRemove }: { sub: Subagent; onToggle: (e: boolean) => void; onRemove: () => void }) {
  const { t } = useTranslation('extensions');
  const scope = Array.isArray(sub.tool_scope) ? sub.tool_scope : [];
  return (
    <li className="flex items-start gap-3 px-3 py-2" data-testid="sa-row">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs">{sub.name}</span>
          {sub.tier === 'system' && <span className="text-[10px] uppercase text-indigo-400">{t('common.system')}</span>}
          {sub.tier === 'book' && <span className="text-[10px] uppercase text-amber-400">{t('common.book')}</span>}
        </div>
        {sub.description && <div className="truncate text-xs text-muted-foreground">{sub.description}</div>}
        <div className="mt-1 flex flex-wrap gap-1">
          {scope.length === 0
            ? <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{t('subagents.reasoningOnly')}</span>
            : scope.map((g) => <span key={g} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]" data-testid="sa-scope-chip">{g}</span>)}
          {sub.model_ref && <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{t('subagents.modelPinned')}</span>}
        </div>
      </div>
      <input type="checkbox" role="switch" defaultChecked={sub.enabled} onChange={(e) => onToggle(e.target.checked)} data-testid="sa-toggle" />
      {sub.tier !== 'system' && <button onClick={onRemove} data-testid="sa-delete" className="rounded border border-red-400/50 px-2 py-0.5 text-[11px] text-red-400">{t('common.delete')}</button>}
    </li>
  );
}
