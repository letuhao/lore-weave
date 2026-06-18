// C15 (WG-6) — plain-editor → AI bridge (view).
//
// Plain prose writing works with zero setup, but bridging into the AI co-writer
// previously required finding the Co-write tab manually. This is the visible,
// inline affordance from the editor toolbar: one click opens the (always-mounted)
// Compose panel. Render-only — the handler is owned by the page; clicking calls
// onActivate DIRECTLY (no useEffect-for-events). It is a live action, never a
// dead button.
import { useTranslation } from 'react-i18next';
import { Pen } from 'lucide-react';
import { cn } from '@/lib/utils';

type Props = {
  /** Whether the Compose panel is currently the open right-panel tab. */
  active: boolean;
  /** Direct handler — open the Compose panel. */
  onActivate: () => void;
};

export function CowriteBridgeButton({ active, onActivate }: Props) {
  const { t } = useTranslation('composition');
  return (
    <button
      type="button"
      data-testid="chapter-cowrite-bridge"
      // Plain action button (open the Compose panel), not a toggle: onActivate only
      // ever opens, so `aria-current` (active=this is the open panel) is the honest
      // a11y signal — `aria-pressed` would imply a press/un-press the button can't do.
      aria-current={active ? 'true' : undefined}
      onClick={onActivate}
      title={t('cowriteBridgeHint', {
        defaultValue: 'Hand this draft to the AI co-writer — needs only a chat model; knowledge is optional.',
      })}
      className={cn(
        'flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors',
        active ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      <Pen className="h-3.5 w-3.5" />
      {t('cowriteBridge', { defaultValue: 'Co-write with AI' })}
    </button>
  );
}
