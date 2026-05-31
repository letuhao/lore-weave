import { AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { PROMPT_OPS, PROMPT_MAX_LEN, type PromptOp } from '../types';

// B2-C — guarded raw per-op system-prompt editor (advanced). Renders one
// textarea per wired op with a live length counter against the BE 16 kB cap.
// An empty box means "use the default prompt for that op". The "affects
// quality" warning is deliberately prominent — a bad custom prompt degrades
// the user's own extraction (the BE keeps the JSON output-contract regardless).

interface Props {
  prompts: Record<PromptOp, string>;
  promptLengths: Record<PromptOp, number>;
  onChange: (op: PromptOp, system: string) => void;
  disabled?: boolean;
}

export function RawPromptEditor({ prompts, promptLengths, onChange, disabled }: Props) {
  const { t } = useTranslation('knowledge');
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-2.5 text-[11px] text-amber-700 dark:text-amber-400">
        <AlertTriangle className="h-4 w-4 flex-shrink-0" />
        <span>{t('projects.extractionTuning.promptWarning')}</span>
      </div>
      {PROMPT_OPS.map((op) => {
        const len = promptLengths[op];
        const over = len > PROMPT_MAX_LEN;
        return (
          <label key={op} className="flex flex-col gap-1">
            <span className="flex items-center justify-between text-[12px] font-medium">
              <span>{t(`projects.extractionTuning.prompt.${op}`)}</span>
              <span className={over ? 'text-destructive' : 'text-muted-foreground'}>
                {len}/{PROMPT_MAX_LEN}
              </span>
            </span>
            <textarea
              value={prompts[op]}
              onChange={(e) => onChange(op, e.target.value)}
              disabled={disabled}
              rows={3}
              placeholder={t('projects.extractionTuning.promptPlaceholder')}
              className={`w-full resize-y rounded-md border bg-background px-2 py-1.5 font-mono text-[11px] leading-relaxed disabled:opacity-60 ${
                over ? 'border-destructive' : ''
              }`}
            />
          </label>
        );
      })}
    </div>
  );
}
