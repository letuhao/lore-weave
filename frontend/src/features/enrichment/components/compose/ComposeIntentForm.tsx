import { useTranslation } from 'react-i18next';
import { Wand2, Lightbulb } from 'lucide-react';

interface Props {
  intentText: string;
  onIntentChange: (v: string) => void;
  onResolve: () => void;
  resolving: boolean;
  canResolve: boolean;
  /** The resolver's rationale + technique + suggested dimensions, shown after a resolve. */
  rationale: string;
  resolvedTechnique: string | null;
  dimensions: string[];
}

/** Mode B form — free-text intent → "Resolve" runs the LLM resolver (step 1), which
 *  fills the shared target (existing|new + name + kind) below for the author to edit
 *  and confirm before Run (step 2). 2-step (F5): a mis-resolved target is never
 *  silently enriched. View-only: state lives in ComposePanel. */
export function ComposeIntentForm({
  intentText, onIntentChange, onResolve, resolving, canResolve, rationale, resolvedTechnique, dimensions,
}: Props) {
  const { t } = useTranslation('enrichment');
  return (
    <div className="space-y-3">
      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          {t('compose.intent.label')}
        </label>
        <textarea
          value={intentText}
          onChange={(e) => onIntentChange(e.target.value)}
          rows={3}
          placeholder={t('compose.intent.placeholder')}
          data-testid="compose-intent-text"
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        />
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onResolve}
          disabled={!canResolve || resolving}
          data-testid="compose-intent-resolve"
          className="inline-flex items-center gap-1.5 rounded-md border border-primary/40 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 disabled:opacity-50"
        >
          <Wand2 className="h-3.5 w-3.5" />
          {resolving ? t('compose.intent.resolving') : t('compose.intent.resolve')}
        </button>
        <span className="text-[11px] text-muted-foreground">{t('compose.intent.resolve_hint')}</span>
      </div>
      {rationale && (
        <p
          data-testid="compose-intent-rationale"
          className="flex items-start gap-1.5 rounded-md border bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground"
        >
          <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
          <span>
            {rationale}
            {resolvedTechnique && (
              <span className="ml-1 rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
                {resolvedTechnique}
              </span>
            )}
            {dimensions.length > 0 && (
              <span data-testid="compose-intent-dimensions" className="mt-1 block">
                {dimensions.map((d) => (
                  <span key={d} className="mr-1 inline-block rounded bg-secondary px-1.5 py-0.5 text-[10px]">
                    {d}
                  </span>
                ))}
              </span>
            )}
          </span>
        </p>
      )}
    </div>
  );
}
