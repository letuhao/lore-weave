// S-10 O6a — "Save this arc as a template". The arc-agent verb composition_arc_extract_template had
// a REST twin (POST /arcs/{id}/extract-template) but no FE caller; this is the button. Given an
// authored arc node, it opens a tiny inline form (name → auto-derived code + a private/unlisted
// choice) and extracts it into the caller's own arc-template library. Self-contained action widget
// (the ArcMaterializeAction house pattern): its own hook owns the mutation, this renders.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useArcExtractTemplate, slugifyArcCode } from '../hooks/useArcExtractTemplate';

type Props = {
  /** the authored arc's structure_node id */
  nodeId: string;
  /** a sensible default name (the arc's title) */
  defaultName?: string;
  token: string | null;
};

export function ArcExtractTemplateAction({ nodeId, defaultName, token }: Props) {
  const { t } = useTranslation('composition');
  const ex = useArcExtractTemplate(nodeId, token);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(defaultName ?? '');

  const trimmed = name.trim();
  const submit = () => {
    if (!trimmed) return;
    ex.run({ code: slugifyArcCode(trimmed), name: trimmed, visibility: 'private' });
  };

  return (
    <div data-testid="arc-extract-template-action" className="flex flex-col gap-2">
      <p className="text-[11px] text-neutral-500">
        {t('motif.arc.extract.blurb', {
          defaultValue: 'Save this arc’s shape as a reusable template in your library.',
        })}
      </p>

      {!open && !ex.result && (
        <button
          type="button"
          data-testid="arc-extract-open"
          className="self-start rounded border px-2 py-0.5 text-[11px] hover:bg-secondary"
          onClick={() => { setName(defaultName ?? ''); setOpen(true); }}
        >
          {t('motif.arc.extract.open', { defaultValue: 'Save as template…' })}
        </button>
      )}

      {open && !ex.result && (
        <div data-testid="arc-extract-form" className="flex flex-col gap-1.5">
          <input
            data-testid="arc-extract-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('motif.arc.extract.namePlaceholder', { defaultValue: 'Template name' })}
            className="rounded border bg-background px-2 py-1 text-[12px] outline-none focus:border-ring"
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="arc-extract-submit"
              disabled={!trimmed || ex.isPending}
              className="rounded bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              onClick={submit}
            >
              {ex.isPending
                ? t('motif.arc.extract.saving', { defaultValue: 'Saving…' })
                : t('motif.arc.extract.save', { defaultValue: 'Save' })}
            </button>
            <button
              type="button"
              data-testid="arc-extract-cancel"
              className="text-[11px] text-muted-foreground hover:underline"
              onClick={() => { setOpen(false); ex.reset(); }}
            >
              {t('motif.arc.extract.cancel', { defaultValue: 'Cancel' })}
            </button>
          </div>
          {ex.conflict && (
            <p role="alert" data-testid="arc-extract-conflict" className="text-[10px] text-amber-600">
              {t('motif.arc.extract.conflict', { defaultValue: 'You already have a template with that name — rename it.' })}
            </p>
          )}
          {ex.isError && !ex.conflict && (
            <p role="alert" data-testid="arc-extract-error" className="text-[10px] text-destructive">
              {t('motif.arc.extract.error', { defaultValue: 'Could not save this arc as a template.' })}
            </p>
          )}
        </div>
      )}

      {ex.result && (
        <p data-testid="arc-extract-done" className="text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
          {t('motif.arc.extract.done', { name: ex.result.name, defaultValue: 'Saved “{{name}}” to your template library.' })}
        </p>
      )}
    </div>
  );
}
