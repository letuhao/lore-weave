import { Sparkles, Copy, Check, Wand2, Loader2 } from 'lucide-react';
import { useState, useCallback, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { ModelPicker } from '@/components/model-picker';

interface MediaPromptProps {
  prompt: string;
  onChange: (prompt: string) => void;
  onRegenerate?: () => void;
  regenerateDisabled?: boolean;
  regenerateLabel?: string;
  /** Capability filter for the model picker (e.g. 'image_gen', 'video_gen').
   *  Omit to render the prompt editor without a model picker. */
  modelCapability?: string;
  /** Selected user_model_id for this block's AI generation, or null when unset. */
  modelId?: string | null;
  onModelChange?: (userModelId: string | null) => void;
}

/**
 * Collapsible AI prompt editor for media blocks (image, video).
 * Stores the prompt text for AI generation / re-generation, plus an explicit
 * model picker so generation never falls back to a silently-chosen model
 * (D-MEDIA-MODEL-PICKER — the block persists its own ai_model_id attribute).
 */
export function MediaPrompt({
  prompt,
  onChange,
  onRegenerate,
  regenerateDisabled = true,
  regenerateLabel,
  modelCapability,
  modelId,
  onModelChange,
}: MediaPromptProps) {
  const { t } = useTranslation('editor');
  const label = regenerateLabel ?? t('media.regenerate');
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const hasPrompt = prompt.trim().length > 0;

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el && open) {
      el.style.height = 'auto';
      el.style.height = `${el.scrollHeight}px`;
    }
  }, [prompt, open]);

  const handleCopy = useCallback(() => {
    if (!hasPrompt) return;
    navigator.clipboard.writeText(prompt).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => {},
    );
  }, [prompt, hasPrompt]);

  return (
    <div className="border-t" contentEditable={false}>
      {/* Toggle header */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-1.5 px-3 py-1 text-[10px] text-muted-foreground transition-colors hover:text-foreground"
        aria-expanded={open}
      >
        <Sparkles className="h-3 w-3" />
        <span>{t('media.ai_prompt')}</span>
        {hasPrompt ? (
          <span className="rounded bg-info/10 px-1 text-[8px] font-semibold text-info">{t('media.saved')}</span>
        ) : (
          <span className="rounded bg-secondary px-1 text-[8px] text-muted-foreground/60">{t('media.empty')}</span>
        )}
        <span className="ml-auto text-[9px]">{open ? '▾' : '▸'}</span>
      </button>

      {/* Expanded content */}
      {open && (
        <div className="border-t px-3 py-2">
          <textarea
            ref={textareaRef}
            value={prompt}
            onChange={(e) => onChange(e.target.value)}
            placeholder={t('media.placeholder')}
            className="w-full resize-none rounded-md border bg-input px-2.5 py-2 text-[11px] leading-relaxed text-foreground outline-none transition-colors placeholder:text-muted-foreground/35 focus:border-ring focus:ring-1 focus:ring-ring/20"
            rows={2}
          />
          <p className="mt-1 text-[9px] text-muted-foreground/60">
            {t('media.stored_note')}
          </p>
          {modelCapability && (
            <div className="mt-2 flex items-center gap-2">
              <span className="shrink-0 text-[10px] text-muted-foreground">
                {t('media.model_label')}
              </span>
              <ModelPicker
                capability={modelCapability}
                value={modelId ?? null}
                onChange={onModelChange ?? (() => {})}
                compact
                ariaLabel={t('media.model_label')}
                className="max-w-[220px]"
              />
            </div>
          )}
          <div className="mt-2 flex items-center gap-2">
            {onRegenerate !== undefined && (
              <button
                type="button"
                onClick={onRegenerate}
                disabled={regenerateDisabled}
                className={cn(
                  'flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-medium transition-colors',
                  regenerateDisabled
                    ? 'cursor-not-allowed border-border/50 text-muted-foreground/40'
                    : 'border-accent/30 bg-accent-muted text-accent-foreground hover:bg-accent hover:text-white',
                )}
              >
                {regenerateDisabled && label.includes('...') ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Wand2 className="h-3 w-3" />
                )}
                {label}
              </button>
            )}
            <button
              type="button"
              onClick={handleCopy}
              disabled={!hasPrompt}
              className={cn(
                'flex items-center gap-1 rounded px-2 py-0.5 text-[10px] transition-colors',
                copied
                  ? 'text-success'
                  : hasPrompt
                    ? 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                    : 'cursor-not-allowed text-muted-foreground/30',
              )}
            >
              {copied ? (
                <><Check className="h-3 w-3" /> {t('media.copied')}</>
              ) : (
                <><Copy className="h-3 w-3" /> {t('media.copy_prompt')}</>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
