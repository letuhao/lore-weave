import { Navigate, Route, Routes } from 'react-router-dom';
import { RequireAuth } from './auth';
import { LoginPage } from './pages/LoginPage';
import { CmsShell } from './components/CmsShell';
import { GenresAdminPanel } from './features/standards-admin/GenresAdminPanel';
import { KindsAdminPanel } from './features/standards-admin/KindsAdminPanel';
import { AttributesAdminPanel } from './features/standards-admin/AttributesAdminPanel';
import { AdminChatPanel } from './features/admin-chat/AdminChatPanel';

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <CmsShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="genres" replace />} />
        <Route path="genres" element={<GenresAdminPanel />} />
        <Route path="kinds" element={<KindsAdminPanel />} />
        <Route path="attributes" element={<AttributesAdminPanel />} />
        <Route path="chat" element={<AdminChatPanel />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
