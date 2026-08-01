import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { LoginRoute } from '@/routes/login';
import { WorldSelectRoute } from '@/routes/world-select';
import { PlayRoute } from '@/routes/play';
import { ResetRoute } from '@/routes/reset';
import { ErrorBoundary } from '@/components/shared/ErrorBoundary';
import { RequireAuth } from '@/components/shared/RequireAuth';
import { useLanguagePreference } from '@/hooks/use-language-preference';
import type { JSX } from 'react';

// App router shell. Per spec §3, three routes:
//   /login         → LoginRoute (Session E wires real auth)
//   /world-select  → WorldSelectRoute (Session E wires character list)
//   /play          → PlayRoute (PhaserGame + HUD overlay, Session D wires real demo)
//   /world-preview → WorldPreviewRoute (3D globe of a generated world-gen .glb)
//
// WorldPreviewRoute is **lazy-loaded**: it pulls in three.js / react-three-fiber
// (~740 KB gzip), which must NOT ship in the initial game-client bundle (AC-FG-15
// budget). Code-splitting keeps it in a separate chunk fetched only when a user
// actually opens /world-preview.
const WorldPreviewRoute = lazy(() =>
  import('@/routes/world-preview').then((m) => ({ default: m.WorldPreviewRoute })),
);

export default function App(): JSX.Element {
  // Mounted at the router root ON PURPOSE. This hook pulls the server-side
  // `ui_language` preference once per session, and it first lived inside
  // <LanguageSwitcher>, which only ever renders on /login — so a returning user
  // with a live session landing straight on /play never had their stored
  // language applied. The write-through worked; the read-back was unreachable.
  useLanguagePreference();

  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/reset" element={<ResetRoute />} />
      <Route
        path="/world-select"
        element={
          <RequireAuth>
            <WorldSelectRoute />
          </RequireAuth>
        }
      />
      <Route
        path="/play"
        element={
          <RequireAuth>
            <PlayRoute />
          </RequireAuth>
        }
      />
      <Route
        path="/world-preview"
        element={
          // ErrorBoundary backstops a failed lazy-chunk fetch (network) — the
          // route module never loads, so the route's own inner boundary can't
          // exist yet. Without this, a chunk-load error white-screens the app.
          <ErrorBoundary
            fallback={
              <div className="min-h-screen flex flex-col items-center justify-center gap-2 bg-slate-950 text-slate-400">
                <p>Could not load the 3D viewer.</p>
                <p className="text-xs text-slate-500">Check your connection and reload.</p>
              </div>
            }
          >
            <Suspense
              fallback={
                <div className="min-h-screen flex items-center justify-center bg-slate-950 text-slate-400">
                  Loading 3D viewer…
                </div>
              }
            >
              <WorldPreviewRoute />
            </Suspense>
          </ErrorBoundary>
        }
      />
      <Route path="*" element={<Navigate to="/play" replace />} />
    </Routes>
  );
}
