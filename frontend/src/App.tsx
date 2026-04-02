import type { ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Toaster } from 'sonner';
import { AppLayout } from '@/components/layout/AppLayout';
import { AuthProvider, useAuth } from './auth';
import { RegisterPage } from './pages/RegisterPage';
import { LoginPage } from './pages/LoginPage';
import { ForgotPage } from './pages/ForgotPage';
import { ResetPage } from './pages/ResetPage';
import {
  BooksPageV2 as BooksPage,
  BookDetailPageV2 as BookDetailPage,
  ChapterEditorPageV2 as ChapterEditorPage,
} from '@/pages/v2-drafts';
import { RecycleBinPage } from './pages/RecycleBinPage';
import { SharingPage } from './pages/SharingPage';
import { BrowsePage } from './pages/BrowsePage';
import { UnlistedPage } from './pages/UnlistedPage';
import { PublicBookPage } from './pages/PublicBookPage';
import { PlatformModelsPage } from './pages/PlatformModelsPage';
import { UsageLogsPage } from './pages/UsageLogsPage';
import { UsageDetailPage } from './pages/UsageDetailPage';
import { UserSettingsPage } from './pages/UserSettingsPage';
import BookTranslationPage from './pages/BookTranslationPage';
import { GlossaryPage } from './pages/GlossaryPage';
import { GlossaryTrashPage } from './pages/GlossaryTrashPage';
import ChatPageV2 from './pages/ChatPageV2';

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
      {/* Full-bleed routes (outside AppLayout) */}
      <Route
        path="/chat"
        element={
          <RequireAuth>
            <ChatPageV2 />
          </RequireAuth>
        }
      />

      <Route element={<AppLayout />}>
        <Route path="/" element={<Home />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/login" element={<LoginPage />} />
        {/* Settings — unified user settings page */}
        <Route path="/settings" element={<Navigate to="/settings/account" replace />} />
        <Route
          path="/settings/:tab"
          element={
            <RequireAuth>
              <UserSettingsPage />
            </RequireAuth>
          }
        />
        {/* Compat redirects for old URLs */}
        <Route path="/profile" element={<Navigate to="/settings/account" replace />} />
        <Route path="/security" element={<Navigate to="/settings/account" replace />} />
        <Route path="/verify" element={<Navigate to="/settings/account" replace />} />
        <Route path="/m03/models" element={<Navigate to="/settings/providers" replace />} />
        <Route path="/translation/settings" element={<Navigate to="/settings/translation" replace />} />
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
        <Route path="/m03/providers" element={<Navigate to="/settings/providers" replace />} />
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
          path="/books/:bookId/translation"
          element={
            <RequireAuth>
              <BookTranslationPage />
            </RequireAuth>
          }
        />
        <Route
          path="/books/:bookId/chapters/:chapterId/translations"
          element={
            <RequireAuth>
              <ChapterEditorPage />
            </RequireAuth>
          }
        />
        <Route
          path="/books/:bookId/glossary"
          element={
            <RequireAuth>
              <GlossaryPage />
            </RequireAuth>
          }
        />
        <Route
          path="/books/:bookId/glossary/trash"
          element={
            <RequireAuth>
              <GlossaryTrashPage />
            </RequireAuth>
          }
        />
        {/* /chat moved outside AppLayout for full-bleed layout */}
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <AuthProvider>
      <AppRoutes />
      <Toaster richColors position="bottom-right" />
    </AuthProvider>
  );
}
