import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, RequireAuth } from '@/auth';
import { ModeProvider } from '@/providers/ModeProvider';
import { DashboardLayout } from '@/layouts/DashboardLayout';
import { FullBleedLayout } from '@/layouts/FullBleedLayout';
import { EditorLayout } from '@/layouts/EditorLayout';
import { PlaceholderPage } from '@/pages/PlaceholderPage';
import { BooksPage } from '@/pages/BooksPage';
import { BookDetailPage } from '@/pages/BookDetailPage';
import { ChapterEditorPage } from '@/pages/ChapterEditorPage';
import { ReaderPage } from '@/pages/ReaderPage';
import { ReaderThemeProvider } from '@/providers/ReaderThemeProvider';
import { LoginPage } from '@/pages/auth/LoginPage';
import { RegisterPage } from '@/pages/auth/RegisterPage';
import { ForgotPage } from '@/pages/auth/ForgotPage';
import { ResetPage } from '@/pages/auth/ResetPage';
import { HomePage } from '@/pages/HomePage';

export function App() {
  return (
    <AuthProvider>
    <ModeProvider>
    <ReaderThemeProvider>
      <BrowserRouter>
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
            <Route path="/browse" element={<PlaceholderPage title="Browse" description="Discover stories across languages and genres." />} />
            <Route path="/browse/:bookId" element={<PlaceholderPage title="Public Book" />} />
            <Route path="/leaderboard" element={<PlaceholderPage title="Leaderboard" description="Top books, authors, and translators." />} />
            <Route path="/users/:userId" element={<PlaceholderPage title="User Profile" />} />
          </Route>

          {/* Reader — full screen, no sidebar */}
          <Route path="/books/:bookId/chapters/:chapterId/read" element={<ReaderPage />} />

          {/* Public reader — unlisted/public books readable without login */}
          <Route element={<FullBleedLayout />}>
            <Route path="/s/:accessToken" element={<PlaceholderPage title="Shared Book" description="Unlisted access — coming in P4." />} />
          </Route>

          {/* ── Protected routes (auth required) ── */}

          {/* Editor (collapsed sidebar) */}
          <Route element={<RequireAuth><EditorLayout /></RequireAuth>}>
            <Route path="/books/:bookId/chapters/:chapterId/edit" element={<ChapterEditorPage />} />
          </Route>

          {/* Dashboard pages (full sidebar) */}
          <Route element={<RequireAuth><DashboardLayout /></RequireAuth>}>
            {/* Workspace */}
            <Route path="/books" element={<BooksPage />} />
            <Route path="/books/trash" element={<PlaceholderPage title="Trash" description="Recycle bin for deleted books." />} />
            <Route path="/books/:bookId" element={<BookDetailPage />} />
            <Route path="/books/:bookId/translation" element={<BookDetailPage />} />
            <Route path="/books/:bookId/glossary" element={<BookDetailPage />} />
            <Route path="/books/:bookId/sharing" element={<BookDetailPage />} />
            <Route path="/books/:bookId/settings" element={<BookDetailPage />} />
            <Route path="/books/:bookId/wiki" element={<BookDetailPage />} />

            {/* Chat */}
            <Route path="/chat" element={<PlaceholderPage title="Chat" description="AI chat with session sidebar — coming in P3-18." />} />

            {/* Manage */}
            <Route path="/usage" element={<PlaceholderPage title="Usage" description="AI usage monitor — coming in P4-06." />} />
            <Route path="/usage/:logId" element={<PlaceholderPage title="Usage Detail" />} />

            {/* Settings */}
            <Route path="/settings" element={<Navigate to="/settings/account" replace />} />
            <Route path="/settings/:tab" element={<PlaceholderPage title="Settings" description="Account, Providers, Translation, Reading, Language — coming in P4-01." />} />

            {/* Notifications */}
            <Route path="/notifications" element={<PlaceholderPage title="Notifications" description="Notification center — coming in P2-09." />} />
          </Route>

          {/* 404 */}
          <Route path="*" element={<FullBleedLayout />}>
            <Route path="*" element={<PlaceholderPage title="404" description="Page not found." />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ReaderThemeProvider>
    </ModeProvider>
    </AuthProvider>
  );
}
