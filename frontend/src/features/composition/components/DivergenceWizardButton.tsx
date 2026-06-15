// C24 (dị bản M0) — studio launch affordance for the divergence wizard. Opens the
// 4-step wizard; on a successful derive, forwards the new derivative Work to the
// caller (which routes/opens the dị bản studio). Self-contained: owns its open
// state via an explicit click handler (no useEffect-for-events).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Work } from '../types';
import { DivergenceWizard } from './DivergenceWizard';

type Props = {
  sourceWork: Work;
  token: string | null;
  onDerived?: (derivative: Work) => void;
};

export function DivergenceWizardButton({ sourceWork, token, onDerived }: Props) {
  const { t } = useTranslation('composition');
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        data-testid="divergence-launch"
        className="rounded border border-purple-300 px-2 py-1 text-xs text-purple-700 dark:border-purple-700 dark:text-purple-300"
        onClick={() => setOpen(true)}
        title={t('derive.launchHint', { defaultValue: 'Spawn a what-if branching from this canon' })}
      >
        ⑂ {t('derive.launch', { defaultValue: 'Spawn what-if' })}
      </button>
      {open && (
        <DivergenceWizard
          open={open}
          onOpenChange={setOpen}
          sourceWork={sourceWork}
          token={token}
          onDerived={onDerived}
        />
      )}
    </>
  );
}
