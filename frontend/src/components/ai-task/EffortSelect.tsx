import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { FocusScope } from '@radix-ui/react-focus-scope';
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
  const menuRef = useRef<HTMLDivElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  // #320 — set only by the close paths that must return focus to the trigger
  // (Escape, picking an option). An outside-click close leaves focus where the
  // user put it; the FocusScope unmount handler reads this flag.
  const restoreFocusRef = useRef(false);
  // #262 — the open menu is a PORTAL at body level with fixed positioning. The old
  // inline `absolute bottom-full z-20` menu stayed inside the control row's stacking
  // context, and in the compose view the what-if promote bar's subtree won the
  // browser's hit test: the menu rendered, but every option click landed on the bar
  // behind it. A body-level portal escapes every ancestor stacking context; the fixed
  // anchor follows the trigger on scroll/resize and flips BELOW the trigger only when
  // there is no viewport room above it (the established upward opening stays the
  // default). z-[60]: above the workspace floats (base 40, capped 49) and the power
  // view (z-50) — a transient menu, not a competing surface.
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const target = e.target as Node;
      // The portal menu is OUTSIDE the trigger's subtree — count it as "inside".
      if (ref.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  useLayoutEffect(() => {
    if (!open) {
      setPos(null);
      return;
    }
    const anchor = () => {
      const trigger = ref.current?.getBoundingClientRect();
      const menu = menuRef.current?.getBoundingClientRect();
      if (!trigger || !menu) return;
      const gap = 4;
      // Prefer the established upward opening; flip below only when the menu does not
      // fit above the trigger.
      const fitsAbove = trigger.top - gap - menu.height >= 0;
      const top = fitsAbove ? trigger.top - gap - menu.height : trigger.bottom + gap;
      setPos({
        left: Math.max(8, Math.min(trigger.left, window.innerWidth - menu.width - 8)),
        top: Math.max(8, top),
      });
    };
    anchor();
    // Reposition (never close) when anything scrolls or the viewport resizes.
    const onMove = () => anchor();
    window.addEventListener('scroll', onMove, true);
    window.addEventListener('resize', onMove);
    return () => {
      window.removeEventListener('scroll', onMove, true);
      window.removeEventListener('resize', onMove);
    };
  }, [open]);

  // #320 — the portal lives at the end of body, so keyboard focus must move into
  // the menu on open: without this, the next Tab from the trigger reaches the
  // control after it (the Diverge checkbox in the compose view), not the menu.
  // The focus move lives in the FocusScope mount handler below, not in a separate
  // effect: the scope pauses an enclosing dialog's trap in its own mount effect,
  // and focusing before that pause lets the trap yank focus back to the trigger.
  // Menu keyboard handling. Capture-phase on the menu element: an
  // enclosing Radix dialog also listens for Escape on document, and the menu
  // must close without dismissing the dialog, so Escape is stopped here before
  // it can bubble to document. Arrows/Home/End move focus between options.
  useEffect(() => {
    if (!open) return;
    const menu = menuRef.current;
    if (!menu) return;
    const onKey = (e: KeyboardEvent) => {
      const options = optionRefs.current.filter((el): el is HTMLButtonElement => el !== null);
      if (e.key === 'Escape') {
        e.stopPropagation();
        setOpen(false);
        restoreFocusRef.current = true;
        buttonRef.current?.focus();
        return;
      }
      if (options.length === 0) return;
      const current = options.indexOf(document.activeElement as HTMLButtonElement);
      let next = -1;
      if (e.key === 'ArrowDown') next = (current + 1) % options.length;
      else if (e.key === 'ArrowUp') next = (current - 1 + options.length) % options.length;
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = options.length - 1;
      else return;
      e.preventDefault();
      options[next]?.focus();
    };
    menu.addEventListener('keydown', onKey, true);
    return () => menu.removeEventListener('keydown', onKey, true);
  }, [open]);

  const Active = META[value].Icon;
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        ref={buttonRef}
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
      {open &&
        createPortal(
          <FocusScope
            // #320 — an untrapped scope: mounting it pauses an enclosing Radix
            // dialog's focus trap (focusScopesStack), so focus moved into this
            // body-level menu is not yanked back into the dialog — without the
            // wrapper, opening the menu inside the extraction/glossary wizards
            // leaves focus on the trigger and the options are keyboard-dead.
            // No `trapped`: Tab must stay native (a trapped scope swallows Tab
            // at the edges). Mount autofocus focuses the selected option (first
            // option when nothing matches) — it runs after the scope pauses an
            // enclosing dialog's trap, so focus is not yanked back to the
            // trigger. Unmount autofocus restores focus to the trigger only
            // for Escape/pick closes (see restoreFocusRef).
            onMountAutoFocus={(e) => {
              e.preventDefault();
              restoreFocusRef.current = false;
              const selected = EFFORT_LEVELS.indexOf(value);
              const target = optionRefs.current[selected] ?? optionRefs.current[0];
              target?.focus();
            }}
            onUnmountAutoFocus={(e) => {
              e.preventDefault();
              if (restoreFocusRef.current) buttonRef.current?.focus();
            }}
          >
            <div
              ref={menuRef}
              role="menu"
              data-testid="effort-select-menu"
            style={{
              position: 'fixed',
              left: pos?.left ?? 0,
              top: pos?.top ?? 0,
              // Hidden until the first measurement lands (layout effect → pre-paint).
              visibility: pos ? 'visible' : 'hidden',
              // #320 — the portal is a direct child of document.body. A modal Radix
              // dialog sets body pointer-events to none and re-enables them only on
              // its own layers, so without this the menu renders above the dialog
              // yet takes no clicks in the extraction/glossary wizards.
              pointerEvents: 'auto',
            }}
            className="z-[60] w-64 rounded-md border border-border bg-card py-1 shadow-lg"
          >
            {EFFORT_LEVELS.map((level, idx) => {
              const { Icon, color } = META[level];
              return (
                <button
                  key={level}
                  type="button"
                  role="menuitemradio"
                  ref={(el) => {
                    optionRefs.current[idx] = el;
                  }}
                  aria-checked={value === level}
                  data-testid={`effort-select-opt-${level}`}
                  onClick={() => {
                    onChange(level);
                    setOpen(false);
                    // #320 — picking closes the menu; focus returns to the trigger.
                    restoreFocusRef.current = true;
                    buttonRef.current?.focus();
                  }}
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
          </FocusScope>,
          document.body,
        )}
    </div>
  );
}
