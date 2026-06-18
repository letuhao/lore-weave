import { Navigate } from 'react-router-dom';
import { useAuth } from '@/auth';

export function HomePage() {
  const { accessToken } = useAuth();

  // Logged in → the first-run intent gate. /onboarding shows the fork once
  // (server-side seen-flag); once seen it falls straight through to /books. So a
  // returning user is never re-onboarded — the gate self-resolves to the workspace.
  if (accessToken) {
    return <Navigate to="/onboarding" replace />;
  }

  // Not logged in → browse (public catalog, no barrier)
  return <Navigate to="/browse" replace />;
}
