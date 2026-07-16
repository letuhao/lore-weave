// 34 §4.3 拆文 (Import & Deconstruct) — the SECTION inside arc-templates. Import a reference story,
// then deconstruct it into a reusable arc template (PRICED — the generic cost-gate: mint → confirm
// → poll). Render-only; logic in useDeconstruct. AT-8: an explicit BYOK model is REQUIRED (no silent
// platform-fallback payer). Copyright/B-3 stated in the UI, not buried.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { CostConfirmCard } from '../motif/components/CostConfirmCard';
import { ModelRolePicker } from '../../campaigns/components/ModelRolePicker';
import { useDeconstruct, IMPORT_SOURCE_MAX } from './useDeconstruct';

export function ImportDeconstructSection({ token }: { token: string | null }) {
  const { t } = useTranslation('composition');
  const d = useDeconstruct(token);
  const [model, setModel] = useState<string | null>(null);
  const busy = d.mint.isPending || d.confirm.isPending;
  const err = (d.error as Error | null)?.message;

  return (
    <div data-testid="import-deconstruct-section" className="flex flex-col gap-3 p-2 text-[11px]">
      <p data-testid="deconstruct-copyright" className="rounded bg-muted/50 p-2 text-[10px] text-muted-foreground">
        {t('motif.arc.import.privacy', {
          defaultValue: 'The raw text stays private to you and is never shared. Only the derived abstract structure can be published — and publishing strips the source reference.',
        })}
      </p>

      {/* ── 1. Sources ─────────────────────────────────────────────── */}
      <section className="flex flex-col gap-1.5">
        <h4 className="font-medium text-foreground/80">{t('motif.arc.import.sources', { defaultValue: 'Reference sources' })}</h4>
        {d.sourcesLoading ? (
          <p className="text-muted-foreground">Loading…</p>
        ) : d.sources.length === 0 ? (
          <p data-testid="deconstruct-no-sources" className="italic text-muted-foreground">No sources yet — paste one below.</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {d.sources.map((s) => (
              <li key={s.id} className="flex items-center gap-2">
                <button type="button" data-testid={`source-${s.id}`}
                  className={`min-w-0 flex-1 truncate text-left ${d.selectedSourceId === s.id ? 'font-medium text-primary' : ''}`}
                  onClick={() => d.setSelectedSourceId(s.id)}>{s.title || '(untitled)'}</button>
                <button type="button" data-testid={`source-del-${s.id}`} className="text-muted-foreground hover:text-destructive"
                  onClick={() => d.deleteSource.mutate(s.id)} title="Delete (no restore)">✕</button>
              </li>
            ))}
          </ul>
        )}
        <PasteBox onCreate={(body) => d.createSource.mutate(body)} busy={d.createSource.isPending} />
      </section>

      {/* ── 2. Configure + 3. Cost gate ─────────────────────────────── */}
      {d.estimate ? (
        <CostConfirmCard
          estimate={d.estimate}
          whatItDoes={t('motif.arc.import.what', { defaultValue: 'Deconstruct the reference into a reusable arc template (LLM-metered).' })}
          confirming={d.confirm.isPending}
          onConfirm={() => d.confirm.mutate()}
          onCancel={() => d.cancel()}
        />
      ) : (
        <section className="flex flex-col gap-1.5">
          <label className="flex flex-col gap-0.5">
            <span className="text-muted-foreground">{t('motif.arc.import.hint', { defaultValue: 'Arc hint (optional)' })}</span>
            <input data-testid="deconstruct-hint" className="rounded border bg-background px-2 py-1" value={d.arcHint}
              disabled={busy} onChange={(e) => d.setArcHint(e.target.value)} />
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" data-testid="deconstruct-useweb" checked={d.useWeb} disabled={busy} onChange={(e) => d.setUseWeb(e.target.checked)} />
            <span className="text-muted-foreground">{t('motif.arc.import.useWeb', { defaultValue: 'Allow web lookup' })}</span>
          </label>
          {/* AT-8: model REQUIRED — no silent platform payer. */}
          <ModelRolePicker capability="chat" label={t('motif.arc.import.model', { defaultValue: 'Deconstruct model' })} value={model} onChange={setModel} disabled={busy} />

          <button type="button" data-testid="deconstruct-run"
            className="self-start rounded border border-primary px-2 py-0.5 font-medium text-primary hover:bg-primary/10 disabled:opacity-50"
            disabled={!d.selectedSourceId || !model || !token || busy}
            onClick={() => model && d.mint.mutate(model)}>
            {d.mint.isPending ? t('motif.arc.import.estimating', { defaultValue: 'Estimating…' })
              : d.confirm.isPending ? t('motif.arc.import.running', { defaultValue: 'Deconstructing…' })
                : t('motif.arc.import.run', { defaultValue: 'Deconstruct' })}
          </button>
          {!d.selectedSourceId && <p className="text-[10px] text-muted-foreground">Select a source above first.</p>}

          {err && <p data-testid="deconstruct-error" role="alert" className="text-destructive">{err}</p>}
        </section>
      )}

      {d.result && (
        <div data-testid="deconstruct-result" className="rounded border p-2 text-primary">
          {t('motif.arc.import.done', { defaultValue: 'A new arc template was created — find it in the Library.' })}
        </div>
      )}
    </div>
  );
}

function PasteBox({ onCreate, busy }: { onCreate: (b: { content: string; title: string }) => void; busy: boolean }) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const over = content.length > IMPORT_SOURCE_MAX;
  return (
    <div className="flex flex-col gap-1 rounded border bg-muted/30 p-2">
      <input data-testid="paste-title" className="rounded border bg-background px-2 py-1" placeholder="title" value={title} onChange={(e) => setTitle(e.target.value)} />
      <textarea data-testid="paste-content" className="min-h-[60px] resize-y rounded border bg-background px-2 py-1" placeholder="paste reference text…" value={content} onChange={(e) => setContent(e.target.value)} />
      <div className="flex items-center gap-2">
        <span data-testid="paste-count" className={`text-[10px] ${over ? 'text-destructive' : 'text-muted-foreground'}`}>{content.length} / {IMPORT_SOURCE_MAX}</span>
        {over && <span data-testid="paste-over" className="text-[10px] text-destructive">Too long — trim before importing.</span>}
        <button type="button" data-testid="paste-submit" className="ml-auto rounded bg-primary px-2 py-0.5 font-medium text-primary-fg disabled:opacity-50"
          disabled={busy || over || !content.trim() || !title.trim()}
          onClick={() => { onCreate({ title: title.trim(), content }); setTitle(''); setContent(''); }}>Add source</button>
      </div>
    </div>
  );
}
