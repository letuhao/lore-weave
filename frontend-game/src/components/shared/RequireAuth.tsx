// Route guard. Redirects to /login when there is no session.
//
// It reads `isAuthenticated` from SessionProvider, which hydrates from storage
// SYNCHRONOUSLY. That matters here specifically: were hydration deferred to an
// effect, the first render of an already-signed-in user would see
// `isAuthenticated === false` and this component would redirect them to the
// login screen before the session arrived — losing the destination on the way.

import { Navigate, useLocation } from 'react-router-dom';
import { useSession } from '@/store/session-context';
import type { ReactNode, JSX } from 'react';

export function RequireAuth({ children }: { children: ReactNode }): JSX.Element {
  const { isAuthenticated } = useSession();
  const location = useLocation();

  if (!isAuthenticated) {
    // Carry the full destination (path + query + hash) so the login round-trip
    // returns the user where they were headed.
    const from = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to="/login" state={{ from }} replace />;
  }
  return <>{children}</>;
}
