import { Navigate } from 'react-router-dom';
import { useOnboarding } from '../hooks/useOnboarding';
import { IntentScreen } from '../components/IntentScreen';

// C22 — onboarding route container. Two entry modes:
//   - first-run gate (forceShow=false): show the fork only when the server-side
//     seen-flag is unset; once seen, fall through to the workspace.
//   - re-entry (forceShow=true): the "start something new" affordance — always
//     renders the fork without consulting the flag.
export function OnboardingPage({ forceShow = false }: { forceShow?: boolean }) {
  const { isLoading, shouldShow, chooseIntent } = useOnboarding({ forceShow });

  if (isLoading) return null; // avoid a flash of the fork before the flag loads
  if (!shouldShow) return <Navigate to="/books" replace />;

  return <IntentScreen onChoose={chooseIntent} />;
}
