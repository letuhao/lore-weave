// #19 G10c — the spotlight overlay itself. Renders exactly ONE step at a time (the parent hook,
// useStudioTour, fully owns sequencing — see its header comment for why joyride's own internal
// Back/Next/target-search state machine is deliberately bypassed).
import { useTranslation } from 'react-i18next';
import { Joyride, type Step, type TooltipRenderProps } from 'react-joyride';
import type { useStudioTour } from './useStudioTour';
import { StudioTourTooltip } from './StudioTourTooltip';

// Above dockview's --dv-overlay-z-index:999 and the studio palette's z-[60] (docs/standards/
// dockable-gui.md DOCK-9 documents this exact conflict zone) — an active tour is a modal-like
// focused state and should win over both.
const TOUR_Z_INDEX = 1100;

export function StudioGuidedTour({ tour }: { tour: ReturnType<typeof useStudioTour> }) {
  const { t } = useTranslation('studio');

  if (!tour.active || !tour.currentDef) return null;

  const step: Step = {
    target: tour.currentDef.target,
    title: t(tour.currentDef.titleKey, { defaultValue: '' }),
    content: t(tour.currentDef.bodyKey, { defaultValue: '' }),
    skipBeacon: true,
    placement: 'auto',
    zIndex: TOUR_Z_INDEX, // Options is per-step in v3, not a top-level `styles.options` prop
  };

  const renderTooltip = (props: TooltipRenderProps) => (
    <StudioTourTooltip
      {...props}
      stepIndex={tour.stepIndex}
      stepCount={tour.stepCount}
      onNext={tour.next}
      onPrev={tour.prev}
      onSkip={tour.stop}
    />
  );

  return (
    <Joyride
      key={`${tour.stepIndex}-${tour.currentDef.target}`}
      steps={[step]}
      run
      continuous={false}
      tooltipComponent={renderTooltip}
    />
  );
}
