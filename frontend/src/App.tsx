import { Link, Navigate, Route, Routes } from 'react-router-dom';
import { apiJson } from './api';
import { AuthProvider, useAuth } from './auth';
import { RegisterPage } from './pages/RegisterPage';
import { LoginPage } from './pages/LoginPage';
import { ProfilePage } from './pages/ProfilePage';
import { SecurityPage } from './pages/SecurityPage';
import { VerifyPage } from './pages/VerifyPage';
import { ForgotPage } from './pages/ForgotPage';
import { ResetPage } from './pages/ResetPage';

function Nav() {
  const { accessToken, refreshToken, logoutLocal } = useAuth();
  const serverLogout = async () => {
    if (!accessToken) return;
    try {
      await apiJson('/v1/auth/logout', { method: 'POST', token: accessToken });
    } catch {
      /* still clear local */
    }
    logoutLocal();
  };
  return (
    <nav>
      <Link to="/">Home</Link>
      {!accessToken && <Link to="/register">Register</Link>}
      {!accessToken && <Link to="/login">Login</Link>}
      {accessToken && <Link to="/profile">Profile</Link>}
      {accessToken && <Link to="/security">Security</Link>}
      {accessToken && <Link to="/verify">Verify email</Link>}
      {!accessToken && <Link to="/forgot">Forgot password</Link>}
      {!accessToken && <Link to="/reset">Reset password</Link>}
      {accessToken && (
        <button type="button" onClick={() => void serverLogout()} style={{ marginLeft: 8 }}>
          Log out
        </button>
      )}
      {refreshToken && !accessToken && (
        <span style={{ marginLeft: 8, fontSize: 12 }}>Has refresh token only</span>
      )}
    </nav>
  );
}

function Home() {
  const { accessToken } = useAuth();
  return (
    <div className="layout">
      <Nav />
      <h1>LoreWeave — Module 01</h1>
      <p>API base: {import.meta.env.VITE_API_BASE || 'http://localhost:3000'}</p>
      <p>{accessToken ? 'You have a session (tokens in localStorage).' : 'Not signed in.'}</p>
    </div>
  );
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuth();
  if (!accessToken) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
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
