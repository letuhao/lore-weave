import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '@/auth';
import { ModeProvider } from '@/providers/ModeProvider';
import { DashboardLayout } from '@/layouts/DashboardLayout';
import { FullBleedLayout } from '@/layouts/FullBleedLayout';
import { EditorLayout } from '@/layouts/EditorLayout';
import { PlaceholderPage } from '@/pages/PlaceholderPage';

export function App() {
  return (
    <AuthProvider>
    <ModeProvider>
      <BrowserRouter>
        <Routes>
          {/* Auth pages (centered, no sidebar) */}
          <Route element={<FullBleedLayout />}>
            <Route path="/login" element={<PlaceholderPage title="Login" description="Auth pages — coming in P1-10." />} />
            <Route path="/register" element={<PlaceholderPage title="Register" />} />
            <Route path="/forgot" element={<PlaceholderPage title="Forgot Password" />} />
            <Route path="/reset" element={<PlaceholderPage title="Reset Password" />} />
          </Route>

          {/* Editor (collapsed sidebar) */}
          <Route element={<EditorLayout />}>
            <Route path="/books/:bookId/chapters/:chapterId/edit" element={<PlaceholderPage title="Chapter Editor" description="3-panel workbench — coming in P2-05." />} />
          </Route>

          {/* Dashboard pages (full sidebar) */}
          <Route element={<DashboardLayout />}>
            {/* Redirect root to workspace */}
            <Route path="/" element={<Navigate to="/books" replace />} />

            {/* Workspace */}
            <Route path="/books" element={<PlaceholderPage title="Workspace" description="Book list with search, filter, create — coming in P2-02." />} />
            <Route path="/books/trash" element={<PlaceholderPage title="Trash" description="Recycle bin for deleted books." />} />
            <Route path="/books/:bookId" element={<PlaceholderPage title="Book Detail" description="Tabs: Chapters, Translation, Glossary, Sharing, Settings — coming in P2-03." />} />
            <Route path="/books/:bookId/translation" element={<PlaceholderPage title="Translation" />} />
            <Route path="/books/:bookId/glossary" element={<PlaceholderPage title="Glossary" />} />
            <Route path="/books/:bookId/sharing" element={<PlaceholderPage title="Sharing" />} />
            <Route path="/books/:bookId/settings" element={<PlaceholderPage title="Book Settings" />} />
            <Route path="/books/:bookId/wiki" element={<PlaceholderPage title="Wiki" />} />

            {/* Chat */}
            <Route path="/chat" element={<PlaceholderPage title="Chat" description="AI chat with session sidebar — coming in P3-18." />} />

            {/* Browse */}
            <Route path="/browse" element={<PlaceholderPage title="Browse" description="Public book catalog — coming in P4-09." />} />
            <Route path="/browse/:bookId" element={<PlaceholderPage title="Public Book" />} />

            {/* Manage */}
            <Route path="/usage" element={<PlaceholderPage title="Usage" description="AI usage monitor — coming in P4-06." />} />
            <Route path="/usage/:logId" element={<PlaceholderPage title="Usage Detail" />} />
            <Route path="/leaderboard" element={<PlaceholderPage title="Leaderboard" description="Top books, authors, translators — coming in P4-11." />} />

            {/* Settings */}
            <Route path="/settings" element={<Navigate to="/settings/account" replace />} />
            <Route path="/settings/:tab" element={<PlaceholderPage title="Settings" description="Account, Providers, Translation, Reading, Language — coming in P4-01." />} />

            {/* Notifications */}
            <Route path="/notifications" element={<PlaceholderPage title="Notifications" description="Notification center — coming in P2-09." />} />

            {/* Profile */}
            <Route path="/users/:userId" element={<PlaceholderPage title="User Profile" />} />

            {/* 404 */}
            <Route path="*" element={<PlaceholderPage title="404" description="Page not found." />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ModeProvider>
    </AuthProvider>
  );
}
