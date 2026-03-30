import { Navigate, Link } from 'react-router-dom';
import { useAuth } from '@/auth';
import { useMode } from '@/providers/ModeProvider';
import { BookOpen, LogIn, UserPlus } from 'lucide-react';

/**
 * Home page logic:
 *
 * Workbench mode:
 *   Logged in  → redirect to /books (workspace)
 *   Not logged → redirect to /login
 *
 * Platform mode:
 *   Logged in  → redirect to /books (workspace)
 *   Not logged → show landing page with "Browse" + "Sign in"
 */
export function HomePage() {
  const { accessToken } = useAuth();
  const { isWorkbench } = useMode();

  // Logged in → workspace
  if (accessToken) {
    return <Navigate to="/books" replace />;
  }

  // Workbench mode, not logged in → login
  if (isWorkbench) {
    return <Navigate to="/login" replace />;
  }

  // Platform mode, not logged in → landing page
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
      <div className="space-y-6 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-xl bg-primary text-lg font-bold text-primary-foreground">
          L
        </div>
        <div className="space-y-2">
          <h1 className="font-serif text-3xl font-semibold">LoreWeave</h1>
          <p className="mx-auto max-w-md text-sm text-muted-foreground">
            A multilingual novel platform for writing, translating, and building story worlds with AI assistance.
          </p>
        </div>

        <div className="flex items-center justify-center gap-3">
          <Link
            to="/browse"
            className="inline-flex items-center gap-2 rounded-md border border-border px-5 py-2.5 text-sm font-medium transition-colors hover:bg-secondary"
          >
            <BookOpen className="h-4 w-4" />
            Browse Stories
          </Link>
          <Link
            to="/login"
            className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <LogIn className="h-4 w-4" />
            Sign In
          </Link>
          <Link
            to="/register"
            className="inline-flex items-center gap-2 rounded-md border border-primary/30 px-5 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-primary/10"
          >
            <UserPlus className="h-4 w-4" />
            Sign Up
          </Link>
        </div>
      </div>
    </div>
  );
}
