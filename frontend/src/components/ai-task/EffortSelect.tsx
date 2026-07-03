import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Brain, ChevronDown, Sparkles, Zap } from 'lucide-react';
import { EFFORT_LEVELS, type EffortLevel } from './effort';

// AI-Task Standard — the standalone effort/reasoning dropdown (unified 5-level
// vocabulary). The single effort control across the app: the chat composer, the
// generate dialogs, the compose view, the extraction wizards. Reuses the chat
// i18n effort keys (input.effort_{level}[_hint]) — one label set.

const META: Record<EffortLevel, { Icon: typeof Zap; color: string }> = {
  off: { Icon: Zap, color: 'text-accent' },
  low: { Icon: Brain, color: 'text-[#a78bfa]' },
  medium: { Icon: Brain, color: 'text-[#a78bfa]' },
  high: { Icon: Brain, color: 'text-[#a78bfa]' },
  auto: { Icon: Sparkles, color: 'text-amber-400' },
};

interface Props {
  value: EffortLevel;
  onChange: (level: EffortLevel) => void;
  disabled?: boolean;
  /** Smaller trigger for toolbars/config rows. */
  compact?: boolean;
}

export function EffortSelect({ value, onChange, disabled, compact }: Props) {
  const { t } = useTranslation('chat');
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const Active = META[value].Icon;
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        data-testid="effort-select"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={t(`input.effort_${value}_hint`)}
        className={`flex items-center gap-1 rounded-md border font-medium transition-colors disabled:opacity-50 ${
          compact ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-[11px]'
        } ${
          value === 'off'
            ? 'border-accent/30 bg-accent/10 text-accent'
            : value === 'auto'
              ? 'border-amber-400/30 bg-amber-400/10 text-amber-400'
              : 'border-[#3b2d6b] bg-[#1e1633] text-[#a78bfa]'
        }`}
      >
        <Active className="h-2.5 w-2.5" />
        {t(`input.effort_${value}`)}
        <ChevronDown className="h-2.5 w-2.5 opacity-60" />
      </button>
      {open && (
        <div role="menu" data-testid="effort-select-menu"
          className="absolute bottom-full left-0 z-20 mb-1 w-64 rounded-md border border-border bg-card py-1 shadow-lg">
          {EFFORT_LEVELS.map((level) => {
            const { Icon, color } = META[level];
            return (
              <button
                key={level}
                type="button"
                role="menuitemradio"
                aria-checked={value === level}
                data-testid={`effort-select-opt-${level}`}
                onClick={() => { onChange(level); setOpen(false); }}
                className={`flex w-full items-start gap-2 px-3 py-1.5 text-left hover:bg-secondary ${
                  value === level ? 'bg-secondary/60' : ''
                }`}
              >
                <Icon className={`mt-0.5 h-3 w-3 shrink-0 ${color}`} />
                <span className="min-w-0">
                  <span className={`block text-[11px] font-medium ${color}`}>{t(`input.effort_${level}`)}</span>
                  <span className="block text-[10px] leading-snug text-muted-foreground">
                    {t(`input.effort_${level}_hint`)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
