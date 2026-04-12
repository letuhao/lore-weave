import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, RequireAuth } from '@/auth';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000, // 30s — data considered fresh for 30s
      gcTime: 5 * 60 * 1000, // 5min — garbage collect after 5min
      refetchOnWindowFocus: true, // refetch when user returns to tab
      retry: 1,
    },
  },
});
import { DashboardLayout } from '@/layouts/DashboardLayout';
import { FullBleedLayout } from '@/layouts/FullBleedLayout';
import { EditorLayout } from '@/layouts/EditorLayout';
import { ChatLayout } from '@/layouts/ChatLayout';
import { PlaceholderPage } from '@/pages/PlaceholderPage';
import { BooksPage } from '@/pages/BooksPage';
import { TrashPage } from '@/pages/TrashPage';
import { ChatPage } from '@/pages/ChatPage';
import { BookDetailPage } from '@/pages/BookDetailPage';
import { ChapterEditorPage } from '@/pages/ChapterEditorPage';
import { WikiEditorPage } from '@/pages/WikiEditorPage';
import { ReaderPage } from '@/pages/ReaderPage';
import { ThemeProvider } from '@/providers/ThemeProvider';
import { useAuth } from '@/auth';
import { SidebarProvider } from '@/providers/SidebarProvider';
import { LoginPage } from '@/pages/auth/LoginPage';
import { RegisterPage } from '@/pages/auth/RegisterPage';
import { ForgotPage } from '@/pages/auth/ForgotPage';
import { ResetPage } from '@/pages/auth/ResetPage';
import { HomePage } from '@/pages/HomePage';
import { UsagePage } from '@/pages/UsagePage';
import { SettingsPage } from '@/pages/SettingsPage';
import { BrowsePage } from '@/pages/BrowsePage';
import { PublicBookDetailPage } from '@/pages/PublicBookDetailPage';
import { SharedBookPage } from '@/pages/SharedBookPage';
import { ChapterTranslationsPage } from '@/pages/ChapterTranslationsPage';
import TranslationReviewPage from '@/pages/TranslationReviewPage';
import ReadingHistoryPage from '@/pages/ReadingHistoryPage';
import { LeaderboardPage } from '@/pages/LeaderboardPage';
import { ProfilePage } from '@/pages/ProfilePage';

function AuthenticatedThemeProvider({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuth();
  return <ThemeProvider accessToken={accessToken}>{children}</ThemeProvider>;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
    <AuthProvider>
    <AuthenticatedThemeProvider>
    <SidebarProvider>
      <BrowserRouter>
        <Toaster position="bottom-right" richColors closeButton />
        <Routes>
          {/* ── Public routes (no auth required) ── */}

          {/* Landing / home */}
          <Route path="/" element={<HomePage />} />

          {/* Auth pages (centered, no sidebar) */}
          <Route element={<FullBleedLayout />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot" element={<ForgotPage />} />
            <Route path="/reset" element={<ResetPage />} />
          </Route>

          {/* Public pages with sidebar — no auth required */}
          <Route element={<DashboardLayout />}>
            <Route path="/browse" element={<BrowsePage />} />
            <Route path="/browse/:bookId" element={<PublicBookDetailPage />} />
            <Route path="/reading-history" element={<ReadingHistoryPage />} />
            <Route path="/leaderboard" element={<LeaderboardPage />} />
            <Route path="/users/:userId" element={<ProfilePage />} />
          </Route>

          {/* Reader — full screen, no sidebar */}
          <Route path="/books/:bookId/chapters/:chapterId/read" element={<ReaderPage />} />

          {/* Translation review — full screen, auth required */}
          <Route path="/books/:bookId/chapters/:chapterId/review/:versionId" element={<RequireAuth><TranslationReviewPage /></RequireAuth>} />

          {/* Public reader — unlisted/public books readable without login */}
          <Route element={<FullBleedLayout />}>
            <Route path="/s/:accessToken" element={<SharedBookPage />} />
          </Route>

          {/* ── Protected routes (auth required) ── */}

          {/* Editor (collapsed sidebar) */}
          <Route element={<RequireAuth><EditorLayout /></RequireAuth>}>
            <Route path="/books/:bookId/chapters/:chapterId/edit" element={<ChapterEditorPage />} />
            <Route path="/books/:bookId/chapters/:chapterId/translations" element={<ChapterTranslationsPage />} />
            <Route path="/books/:bookId/wiki/:articleId/edit" element={<WikiEditorPage />} />
          </Route>

          {/* Chat (app sidebar + full-bleed content, no padding) */}
          <Route element={<RequireAuth><ChatLayout /></RequireAuth>}>
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:sessionId" element={<ChatPage />} />
          </Route>

          {/* Dashboard pages (full sidebar) */}
          <Route element={<RequireAuth><DashboardLayout /></RequireAuth>}>
            {/* Workspace */}
            <Route path="/books" element={<BooksPage />} />
            <Route path="/trash" element={<TrashPage />} />
            <Route path="/books/:bookId" element={<BookDetailPage />} />
            <Route path="/books/:bookId/translation" element={<BookDetailPage />} />
            <Route path="/books/:bookId/glossary" element={<BookDetailPage />} />
            <Route path="/books/:bookId/sharing" element={<BookDetailPage />} />
            <Route path="/books/:bookId/settings" element={<BookDetailPage />} />
            <Route path="/books/:bookId/wiki" element={<BookDetailPage />} />

            {/* Chat — placeholder removed, see FullBleedLayout below */}

            {/* Manage */}
            <Route path="/usage" element={<UsagePage />} />

            {/* Settings */}
            <Route path="/settings" element={<Navigate to="/settings/account" replace />} />
            <Route path="/settings/:tab" element={<SettingsPage />} />

            {/* Notifications */}
            <Route path="/notifications" element={<PlaceholderPage title="Notifications" description="Notification center — coming in P2-09." />} />
          </Route>

          {/* 404 */}
          <Route path="*" element={<FullBleedLayout />}>
            <Route path="*" element={<PlaceholderPage title="404" description="Page not found." />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </SidebarProvider>
    </AuthenticatedThemeProvider>
    </AuthProvider>
    </QueryClientProvider>
  );
}
