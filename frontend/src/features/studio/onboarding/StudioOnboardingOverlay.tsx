// #19 G7 — the Studio role-picker overlay. Lives OUTSIDE features/studio/panels/** (it is not
// a dock tab, so DOCK-1..11 don't apply), and — on principle, not just where the mechanical
// DOCK-9 gate scans — reuses the existing shared FormDialog rather than a hand-rolled
// `fixed inset-0` overlay. A single-step design (pick a role → immediately dismiss) fits
// FormDialog's title+body+footer template natively, so no custom Dialog.* chrome is needed.
import { useTranslation } from 'react-i18next';
import { PenLine, Globe2, Languages, Sparkles, Share2, type LucideIcon } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import type { StudioRole } from './types';

const ROLES: { id: StudioRole; icon: LucideIcon }[] = [
  { id: 'writer', icon: PenLine },
  { id: 'worldbuilder', icon: Globe2 },
  { id: 'translator', icon: Languages },
  { id: 'enricher', icon: Sparkles },
  { id: 'manager', icon: Share2 },
];

interface Props {
  open: boolean;
  onChooseRole: (role: StudioRole) => void;
  onSkip: () => void;
}

export function StudioOnboardingOverlay({ open, onChooseRole, onSkip }: Props) {
  const { t } = useTranslation('studio');

  return (
    <FormDialog
      open={open}
      // Any dismiss path (backdrop click, Esc, the X button) counts as skip — this can
      // never trap the user, on the first showing or any re-trigger.
      onOpenChange={(next) => { if (!next) onSkip(); }}
      title={t('intro.title', { defaultValue: 'Welcome to Writing Studio' })}
      description={t('intro.subtitle', {
        defaultValue: "What are you here to do? This tailors your Welcome panel and quick tour — change it anytime from the Command Palette.",
      })}
      size="lg"
      footer={
        <button
          type="button"
          data-testid="studio-onboarding-skip"
          onClick={onSkip}
          className="text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          {t('intro.skip', { defaultValue: "Skip, I'll explore" })}
        </button>
      }
    >
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" data-testid="studio-onboarding-overlay">
        {ROLES.map(({ id, icon: Icon }) => (
          <button
            key={id}
            type="button"
            data-testid={`studio-onboarding-role-${id}`}
            onClick={() => onChooseRole(id)}
            className="flex items-start gap-3 rounded-lg border p-3 text-left transition-colors hover:border-primary hover:bg-secondary"
          >
            <Icon className="mt-0.5 h-5 w-5 flex-shrink-0 text-muted-foreground" />
            <div>
              <div className="text-sm font-medium text-foreground">
                {t(`intro.roles.${id}.title`)}
              </div>
              <div className="text-xs text-muted-foreground">{t(`intro.roles.${id}.desc`)}</div>
            </div>
          </button>
        ))}
      </div>
    </FormDialog>
  );
}
