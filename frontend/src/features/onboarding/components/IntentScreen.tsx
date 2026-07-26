import { useTranslation } from 'react-i18next';
import { PenLine, Globe2, Languages, Compass, NotebookPen, type LucideIcon } from 'lucide-react';
import { INTENT_CHOICES } from '../lib/intentRoutes';
import type { IntentId } from '../types';

const ICONS: Record<string, LucideIcon> = { PenLine, Globe2, Languages, Compass, NotebookPen };

// C22 — first-run intent fork view. Renders the BL-15 choices and
// reports the picked intent through onChoose (an EXPLICIT callback — the parent
// hook routes; no useEffect-for-events here). Pure render: no state, no logic.
export function IntentScreen({ onChoose }: { onChoose: (id: IntentId) => void }) {
  const { t } = useTranslation('onboarding');

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-3xl flex-col justify-center px-4 py-10" data-testid="intent-screen">
      <div className="mb-8 text-center">
        <h1 className="font-serif text-2xl font-semibold">
          {t('heading', { defaultValue: 'What do you want to do?' })}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {t('subheading', { defaultValue: 'Pick a starting point — you can switch any time.' })}
        </p>
      </div>

      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2" data-testid="intent-choices">
        {INTENT_CHOICES.map((choice) => {
          const Icon = ICONS[choice.icon];
          return (
            <li key={choice.id}>
              <button
                type="button"
                onClick={() => onChoose(choice.id)}
                className="flex w-full flex-col items-start gap-2 rounded-lg border bg-card p-5 text-left transition-colors hover:border-primary/60 hover:bg-accent/40"
                data-testid={`intent-${choice.id}`}
              >
                <span className="flex items-center gap-2 font-medium">
                  {Icon && <Icon className="h-5 w-5 text-primary" />}
                  {t(choice.titleKey, { defaultValue: choice.id })}
                </span>
                <span className="text-sm text-muted-foreground">
                  {t(choice.descKey, { defaultValue: '' })}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
