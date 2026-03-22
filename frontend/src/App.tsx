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
import { BooksPage } from './pages/BooksPage';
import { BookDetailPage } from './pages/BookDetailPage';
import { ChapterEditorPage } from './pages/ChapterEditorPage';
import { RecycleBinPage } from './pages/RecycleBinPage';
import { SharingPage } from './pages/SharingPage';
import { BrowsePage } from './pages/BrowsePage';
import { UnlistedPage } from './pages/UnlistedPage';
import { PublicBookPage } from './pages/PublicBookPage';
import { UserModelsPage } from './pages/UserModelsPage';
import { PlatformModelsPage } from './pages/PlatformModelsPage';
import { UsageLogsPage } from './pages/UsageLogsPage';
import { UsageDetailPage } from './pages/UsageDetailPage';
import TranslationSettingsPage from './pages/TranslationSettingsPage';
import BookTranslationPage from './pages/BookTranslationPage';

function Home() {
  const { accessToken } = useAuth();
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">LoreWeave Workspace</h1>
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
        <Route
          path="/books"
          element={
            <RequireAuth>
              <BooksPage />
            </RequireAuth>
          }
        />
        <Route
          path="/books/trash"
          element={
            <RequireAuth>
              <RecycleBinPage />
            </RequireAuth>
          }
        />
        <Route
          path="/books/:bookId"
          element={
            <RequireAuth>
              <BookDetailPage />
            </RequireAuth>
          }
        />
        <Route
          path="/books/:bookId/sharing"
          element={
            <RequireAuth>
              <SharingPage />
            </RequireAuth>
          }
        />
        <Route
          path="/books/:bookId/chapters/:chapterId/edit"
          element={
            <RequireAuth>
              <ChapterEditorPage />
            </RequireAuth>
          }
        />
        <Route path="/browse" element={<BrowsePage />} />
        <Route path="/browse/:bookId" element={<PublicBookPage />} />
        <Route path="/s/:accessToken" element={<UnlistedPage />} />
        <Route path="/m03/providers" element={<Navigate to="/m03/models" replace />} />
        <Route
          path="/m03/models"
          element={
            <RequireAuth>
              <UserModelsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/m03/platform-models"
          element={
            <RequireAuth>
              <PlatformModelsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/m03/usage"
          element={
            <RequireAuth>
              <UsageLogsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/m03/usage/:usageLogId"
          element={
            <RequireAuth>
              <UsageDetailPage />
            </RequireAuth>
          }
        />
        <Route
          path="/translation/settings"
          element={
            <RequireAuth>
              <TranslationSettingsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/books/:bookId/translation"
          element={
            <RequireAuth>
              <BookTranslationPage />
            </RequireAuth>
          }
        />
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
