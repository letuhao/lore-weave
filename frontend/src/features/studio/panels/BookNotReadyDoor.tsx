// Onboarding-door track (Part A) — the ONE empty-state a gated Studio surface renders when the book
// isn't set up yet. Replaces the four ad-hoc patterns that existed before (inline WorkSetupCta,
// redirect-to-Compose, open-plan-hub, and bare dead text) with a single component: guided copy + the
// right create door for the surface's own prerequisite.
//
// HOST-AGNOSTIC by design. Dock panels have `useStudioHost`; render-only components (PlanNavigatorRail,
// DivergenceManagerView) do NOT — so the plan door is taken as an `onPlan` CALLBACK the caller wires,
// never reached for here. That's the only way one component can serve both kinds of surface.
//
// Two prerequisites today (they collapse to one after the C-merge structure unification):
//   • need="work" → mounts the existing idempotent WorkSetupCta (creates the composition Work).
//   • need="plan" → a "Plan this book" button firing onPlan (opens the plan-hub origin flow).
import { useTranslation } from 'react-i18next';
import { WorkSetupCta } from './WorkSetupCta';

interface WorkDoorProps {
  need: 'work';
  bookId: string;
  token: string | null;
}
interface PlanDoorProps {
  need: 'plan';
  /** The caller wires this to its open-plan action (dock panel: host.openPanel('plan-hub'); rail: its
   *  onOpenPlan prop). Absent ⇒ copy-only, never a broken button. */
  onPlan?: () => void;
}
type Props = { message: string; testId?: string; className?: string } & (WorkDoorProps | PlanDoorProps);

export function BookNotReadyDoor(props: Props) {
  const { t } = useTranslation('studio');
  const { message, testId, className } = props;

  return (
    <div
      data-testid={testId ?? 'book-not-ready'}
      className={
        className ??
        'flex h-full flex-col items-center justify-center gap-3 p-6 text-center text-sm text-muted-foreground'
      }
    >
      <p className="max-w-xs">{message}</p>
      {props.need === 'work' ? (
        <WorkSetupCta bookId={props.bookId} token={props.token} />
      ) : (
        props.onPlan && (
          <button
            type="button"
            data-testid="book-plan-cta"
            onClick={props.onPlan}
            className="rounded border border-border bg-background px-3 py-1 text-xs font-semibold hover:border-ring"
          >
            {t('planNav.planCta', { defaultValue: 'Plan this book' })}
          </button>
        )
      )}
    </div>
  );
}
