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
import { AssistantPage } from '@/features/assistant/components/AssistantPage';
import { RoleplayPage } from '@/features/roleplay/pages/RoleplayPage';
import { BookDetailPage } from '@/pages/BookDetailPage';
import { ChapterEditorPage } from '@/pages/ChapterEditorPage';
import { WritingStudioPage } from '@/pages/WritingStudioPage';
import { PopoutHost } from '@/features/composition/components/workspace/PopoutHost';
import { StudioPopoutHost } from '@/features/studio/popout/StudioPopoutHost';
import { ChapterComparePage } from '@/pages/ChapterComparePage';
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
import { KnowledgePage } from '@/pages/KnowledgePage';
import { ExtensionsPage } from '@/features/extensions/pages/ExtensionsPage';
import { ProjectDetailShell } from '@/pages/ProjectDetailShell';
import { WorldsPage } from '@/features/world/pages/WorldsPage';
import { WorldWorkspacePage } from '@/features/world/pages/WorldWorkspacePage';
import { CampaignsPage } from '@/features/campaigns/pages/CampaignsPage';
import { CreateCampaignWizardPage } from '@/features/campaigns/pages/CreateCampaignWizardPage';
import { CampaignDetailPage } from '@/features/campaigns/pages/CampaignDetailPage';
import { StandardsPage } from '@/features/standards/pages/StandardsPage';
import { JobsPage } from '@/features/jobs/pages/JobsPage';
import { ContextInspectorPage } from '@/features/chat/inspector/ContextInspectorPage';
import { JobDetailPage } from '@/features/jobs/pages/JobDetailPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { BrowsePage } from '@/pages/BrowsePage';
import { PublicBookDetailPage } from '@/pages/PublicBookDetailPage';
import { SharedBookPage } from '@/pages/SharedBookPage';
import { ChapterTranslationsPage } from '@/pages/ChapterTranslationsPage';
import TranslationReviewPage from '@/pages/TranslationReviewPage';
import ReadingHistoryPage from '@/pages/ReadingHistoryPage';
import { LeaderboardPage } from '@/pages/LeaderboardPage';
import { ProfilePage } from '@/pages/ProfilePage';
import { NotificationsPage } from '@/pages/NotificationsPage';
import { RawSearchPage } from '@/pages/RawSearchPage';
import { OnboardingPage } from '@/features/onboarding/pages/OnboardingPage';
import { OAuthConsentPage } from '@/pages/OAuthConsentPage';

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
            {/* P5 public-MCP OAuth consent — the page handles auth itself (preserves
                the query string across the login round-trip), so it's NOT in RequireAuth. */}
            <Route path="/oauth/consent" element={<OAuthConsentPage />} />
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

          {/* T5.4 M4 — composition panel OS pop-out window (own root, full-screen, auth) */}
          <Route path="/composition/popout" element={<RequireAuth><PopoutHost /></RequireAuth>} />

          {/* #16 2.8 — Studio Compose panel OS pop-out window (own root, full-screen, auth) */}
          <Route path="/studio/popout" element={<RequireAuth><StudioPopoutHost /></RequireAuth>} />

          {/* Translation review — full screen, auth required */}
          <Route path="/books/:bookId/chapters/:chapterId/review/:versionId" element={<RequireAuth><TranslationReviewPage /></RequireAuth>} />

          {/* Writing Studio (v2) — book-level VS Code-style docking workspace (dockview).
              Full screen, auth required — deliberately NOT under EditorLayout: the studio has
              its own Activity Bar chrome, so the app sidebar would be a redundant second rail. */}
          <Route path="/books/:bookId/studio" element={<RequireAuth><WritingStudioPage /></RequireAuth>} />

          {/* Public reader — unlisted/public books readable without login */}
          <Route element={<FullBleedLayout />}>
            <Route path="/s/:accessToken" element={<SharedBookPage />} />
          </Route>

          {/* ── Protected routes (auth required) ── */}

          {/* Editor (collapsed sidebar) */}
          <Route element={<RequireAuth><EditorLayout /></RequireAuth>}>
            <Route path="/books/:bookId/chapters/:chapterId/edit" element={<ChapterEditorPage />} />
            <Route path="/books/:bookId/chapters/:chapterId/compare" element={<ChapterComparePage />} />
            <Route path="/books/:bookId/chapters/:chapterId/translations" element={<ChapterTranslationsPage />} />
            <Route path="/books/:bookId/wiki/:articleId/edit" element={<WikiEditorPage />} />
          </Route>

          {/* Chat (app sidebar + full-bleed content, no padding) */}
          <Route element={<RequireAuth><ChatLayout /></RequireAuth>}>
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:sessionId" element={<ChatPage />} />
            {/* WS-1.10 — the Work Assistant: reuses the chat surface + a home strip,
                bound to the user's private diary book. Same layout chrome as chat. */}
            <Route path="/assistant" element={<AssistantPage />} />
            {/* Roleplay practice — reuses the chat turn loop + voice; scripts +
                start come from roleplay-service (/v1/roleplay). Interview is a
                preset genre. /interview redirects (kept for old links). */}
            <Route path="/roleplay" element={<RoleplayPage />} />
            <Route path="/interview" element={<Navigate to="/roleplay" replace />} />
          </Route>

          {/* Dashboard pages (full sidebar) */}
          <Route element={<RequireAuth><DashboardLayout /></RequireAuth>}>
            {/* C22 — first-run intent fork. /onboarding is the gate (shows the
                fork only on first run, else redirects to /books); /onboarding/new
                is the re-entry "start something new" affordance (always shows). */}
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route path="/onboarding/new" element={<OnboardingPage forceShow />} />

            {/* Mobile bottom-tab targets (M0 placeholders; M2 fills /home, M3 fills /you).
                Real routes on desktop too — harmless, they just show a "coming soon" card. */}
            <Route path="/home" element={<PlaceholderPage title="Home" description="Your platform home — coming soon." />} />
            <Route path="/you" element={<PlaceholderPage title="You" description="Your account & data — coming soon." />} />

            {/* Workspace */}
            <Route path="/books" element={<BooksPage />} />
            <Route path="/trash" element={<TrashPage />} />
            <Route path="/books/:bookId" element={<BookDetailPage />} />
            <Route path="/books/:bookId/translation" element={<BookDetailPage />} />
            <Route path="/books/:bookId/glossary" element={<BookDetailPage />} />
            <Route path="/books/:bookId/kg-ontology" element={<BookDetailPage />} />
            <Route path="/books/:bookId/enrichment" element={<BookDetailPage />} />
            <Route path="/books/:bookId/sharing" element={<BookDetailPage />} />
            <Route path="/books/:bookId/settings" element={<BookDetailPage />} />
            <Route path="/books/:bookId/wiki" element={<BookDetailPage />} />
            <Route path="/books/:bookId/search" element={<RawSearchPage />} />

            {/* Chat — placeholder removed, see FullBleedLayout below */}

            {/* Knowledge Service */}
            <Route path="/knowledge" element={<Navigate to="/knowledge/projects" replace />} />
            {/* C6 (G6) — project-detail shell. The 4-segment nested route is
                more specific than the 2-segment flat-tab route below, so it
                wins; they don't conflict. */}
            <Route
              path="/knowledge/projects/:projectId/:section"
              element={<ProjectDetailShell />}
            />
            <Route path="/knowledge/:tab" element={<KnowledgePage />} />

            {/* C21 — World container (prose-less worldbuilding). HOME browser +
                workspace shell; no manuscript. */}
            <Route path="/worlds" element={<WorldsPage />} />
            <Route path="/worlds/:worldId" element={<WorldWorkspacePage />} />

            {/* Auto-Draft Factory (campaigns) */}
            <Route path="/campaigns" element={<CampaignsPage />} />
            <Route path="/campaigns/new" element={<CreateCampaignWizardPage />} />
            <Route path="/campaigns/:campaignId" element={<CampaignDetailPage />} />

            {/* Unified Jobs control plane (P4) — every background job the user owns. */}
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/jobs/:service/:jobId" element={<JobDetailPage />} />

            {/* Manage */}
            <Route path="/usage" element={<UsagePage />} />

            {/* Context Budget Law §11 — the Context Compiler · Trace Inspector,
                standalone (also a dockable studio panel). */}
            <Route path="/context-inspector" element={<ContextInspectorPage />} />

            {/* Glossary standards library (per-user, tier-scoped) */}
            <Route path="/standards" element={<Navigate to="/standards/genres" replace />} />
            <Route path="/standards/:tab" element={<StandardsPage />} />

            {/* Settings */}
            <Route path="/settings" element={<Navigate to="/settings/account" replace />} />
            <Route path="/settings/:tab" element={<SettingsPage />} />

            {/* Notifications */}
            <Route path="/notifications" element={<NotificationsPage />} />

            {/* Agent Extensibility Registry — plugins/skills/proposals (two-shells
                with the studio ExtensionsPanel) */}
            <Route path="/extensions" element={<ExtensionsPage />} />
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
