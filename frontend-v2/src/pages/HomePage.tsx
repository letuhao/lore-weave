import { Navigate } from 'react-router-dom';
import { useAuth } from '@/auth';

export function HomePage() {
  const { accessToken } = useAuth();

  // Logged in → workspace
  if (accessToken) {
    return <Navigate to="/books" replace />;
  }

  // Not logged in → browse (public catalog, no barrier)
  return <Navigate to="/browse" replace />;
}
