// View (MVC) — the Commands & Hooks builder (REG-P4-02/04). Two sections: slash
// commands (name + template) and declarative hooks (event → match → action). Render-only.
import { useState } from 'react';
import { useCommands, useHooks } from '../hooks/useCommandsHooks';
import type { SlashCommand, Hook, HookEvent, HookActionKind } from '../types';

export function CommandsHooksView() {
  return (
    <div className="space-y-6" data-testid="commands-hooks-view">
      <CommandsSection />
      <HooksSection />
    </div>
  );
}

const inputCls = 'w-full rounded-md border bg-background px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring';

function CommandsSection() {
  const c = useCommands();
  const [name, setName] = useState('');
  const [template, setTemplate] = useState('');
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null);
    const e = await c.create({ name: name.trim(), template_md: template });
    if (e) { setErr(e); return; }
    setName(''); setTemplate('');
  };

  return (
    <section className="space-y-2" data-testid="commands-section">
      <h3 className="text-sm font-semibold">Slash commands</h3>
      <p className="text-xs text-muted-foreground">Type <code>/name</code> in chat to expand a template. Use <code>{'{{args}}'}</code> or <code>{'{{key}}'}</code> for arguments.</p>
      <div className="flex flex-wrap items-start gap-2">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="name (e.g. plan-scene)" data-testid="cmd-name" className={`${inputCls} max-w-[180px]`} />
        <input value={template} onChange={(e) => setTemplate(e.target.value)} placeholder="Template: Plan a scene about {{topic}}…" data-testid="cmd-template" className={`${inputCls} min-w-[240px] flex-1`} />
        <button onClick={() => void submit()} disabled={!name.trim() || !template.trim()} data-testid="cmd-create" className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-40">Add</button>
      </div>
      {err && <div className="rounded-md border border-red-400 bg-red-500/10 px-3 py-1.5 text-xs text-red-400" data-testid="cmd-error">{err}</div>}
      {c.error && <div className="text-xs text-red-400">{c.error}</div>}
      <ul className="divide-y rounded-md border">
        {c.commands.length === 0 && !c.loading && <li className="px-3 py-4 text-center text-xs text-muted-foreground">No commands yet.</li>}
        {c.commands.map((cmd) => <CommandRow key={cmd.command_id} cmd={cmd} onToggle={(en) => void c.toggle(cmd, en)} onRemove={() => void c.remove(cmd)} />)}
      </ul>
    </section>
  );
}

function CommandRow({ cmd, onToggle, onRemove }: { cmd: SlashCommand; onToggle: (e: boolean) => void; onRemove: () => void }) {
  return (
    <li className="flex items-center gap-3 px-3 py-2" data-testid="cmd-row">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2"><span className="font-mono text-xs">/{cmd.name}</span>{cmd.tier === 'system' && <span className="text-[10px] uppercase text-indigo-400">system</span>}</div>
        <div className="truncate text-xs text-muted-foreground">{cmd.template_md}</div>
      </div>
      <input type="checkbox" role="switch" defaultChecked={cmd.enabled} onChange={(e) => onToggle(e.target.checked)} data-testid="cmd-toggle" />
      {cmd.tier !== 'system' && <button onClick={onRemove} data-testid="cmd-delete" className="rounded border border-red-400/50 px-2 py-0.5 text-[11px] text-red-400">Delete</button>}
    </li>
  );
}

const EVENTS: HookEvent[] = ['pre_tool_call', 'post_tool_call', 'pre_turn', 'post_turn'];
const ACTION_KINDS: HookActionKind[] = ['deny', 'require_approval', 'annotate', 'inject_text'];

function HooksSection() {
  const hk = useHooks();
  const [onEvent, setOnEvent] = useState<HookEvent>('pre_tool_call');
  const [kind, setKind] = useState<HookActionKind>('deny');
  const [toolPattern, setToolPattern] = useState('');
  const [text, setText] = useState('');
  const [err, setErr] = useState<string | null>(null);

  const needsText = kind === 'inject_text' || kind === 'annotate';
  const showMatch = onEvent === 'pre_tool_call' || onEvent === 'post_tool_call';

  const submit = async () => {
    setErr(null);
    const action = needsText ? { kind, text } : { kind };
    const match = showMatch && toolPattern.trim() ? { tool_pattern: toolPattern.trim() } : {};
    const e = await hk.create({ on_event: onEvent, action, match });
    if (e) { setErr(e); return; }
    setToolPattern(''); setText('');
  };

  return (
    <section className="space-y-2" data-testid="hooks-section">
      <h3 className="text-sm font-semibold">Hooks</h3>
      <p className="text-xs text-muted-foreground">Declarative rules that fire at agent-loop seams. No code — just an event, an optional tool match, and an action.</p>
      <div className="flex flex-wrap items-center gap-2">
        <select value={onEvent} onChange={(e) => setOnEvent(e.target.value as HookEvent)} data-testid="hook-event" className={`${inputCls} max-w-[160px]`}>
          {EVENTS.map((ev) => <option key={ev} value={ev}>{ev}</option>)}
        </select>
        <select value={kind} onChange={(e) => setKind(e.target.value as HookActionKind)} data-testid="hook-action" className={`${inputCls} max-w-[150px]`}>
          {ACTION_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
        {showMatch && <input value={toolPattern} onChange={(e) => setToolPattern(e.target.value)} placeholder="tool match (e.g. glossary_delete_*)" data-testid="hook-match" className={`${inputCls} max-w-[220px]`} />}
        {needsText && <input value={text} onChange={(e) => setText(e.target.value)} placeholder="text to inject / annotate" data-testid="hook-text" className={`${inputCls} min-w-[200px] flex-1`} />}
        <button onClick={() => void submit()} disabled={needsText && !text.trim()} data-testid="hook-create" className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-40">Add</button>
      </div>
      {err && <div className="rounded-md border border-red-400 bg-red-500/10 px-3 py-1.5 text-xs text-red-400" data-testid="hook-error">{err}</div>}
      {hk.error && <div className="text-xs text-red-400">{hk.error}</div>}
      <ul className="divide-y rounded-md border">
        {hk.hooks.length === 0 && !hk.loading && <li className="px-3 py-4 text-center text-xs text-muted-foreground">No hooks yet.</li>}
        {hk.hooks.map((h) => <HookRow key={h.hook_id} hook={h} onToggle={(en) => void hk.toggle(h, en)} onRemove={() => void hk.remove(h)} />)}
      </ul>
    </section>
  );
}

function HookRow({ hook, onToggle, onRemove }: { hook: Hook; onToggle: (e: boolean) => void; onRemove: () => void }) {
  const m = (hook.match as { tool_pattern?: string })?.tool_pattern;
  return (
    <li className="flex items-center gap-3 px-3 py-2" data-testid="hook-row">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs">
          <span className="font-mono">{hook.on_event}</span>
          <span className="rounded bg-muted px-1.5 py-0.5 font-semibold">{hook.action.kind}</span>
          {m && <span className="text-muted-foreground">· {m}</span>}
        </div>
        {(hook.action.text || hook.action.message) && <div className="truncate text-xs text-muted-foreground">{hook.action.text || hook.action.message}</div>}
      </div>
      <input type="checkbox" role="switch" defaultChecked={hook.enabled} onChange={(e) => onToggle(e.target.checked)} data-testid="hook-toggle" />
      {hook.tier !== 'system' && <button onClick={onRemove} data-testid="hook-delete" className="rounded border border-red-400/50 px-2 py-0.5 text-[11px] text-red-400">Delete</button>}
    </li>
  );
}
