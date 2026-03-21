import type { ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { AuthProvider, useAuth } from './auth';
import { RegisterPage } from './pages/RegisterPage';
import { LoginPage } from './pages/LoginPage';
import { ProfilePage } from './pages/ProfilePage';
import { SecurityPage } from './pages/SecurityPage';
import { VerifyPage } from './pages/VerifyPage';
import { ForgotPage } from './pages/ForgotPage';
import { ResetPage } from './pages/ResetPage';

function Home() {
  const { accessToken } = useAuth();
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">LoreWeave — Module 01</h1>
      <p className="mt-4 text-sm text-muted-foreground">
        API base: {import.meta.env.VITE_API_BASE || 'http://localhost:3000'}
      </p>
      <p className="mt-2 text-sm text-muted-foreground">
        {accessToken ? 'You have a session (tokens in localStorage).' : 'Not signed in.'}
      </p>
    </>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { accessToken } = useAuth();
  if (!accessToken) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Home />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/profile"
          element={
            <RequireAuth>
              <ProfilePage />
            </RequireAuth>
          }
        />
        <Route
          path="/security"
          element={
            <RequireAuth>
              <SecurityPage />
            </RequireAuth>
          }
        />
        <Route
          path="/verify"
          element={
            <RequireAuth>
              <VerifyPage />
            </RequireAuth>
          }
        />
        <Route path="/forgot" element={<ForgotPage />} />
        <Route path="/reset" element={<ResetPage />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
