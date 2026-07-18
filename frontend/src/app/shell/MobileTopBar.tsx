import { useLocation, useNavigate } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';

// MobileTopBar — the mobile Back affordance (fixes the "cannot return" dead-end). A PWA in
// standalone display has NO browser back button, so every non-root page needs an in-app Back or the
// user is stranded. Rendered by AppShell in the mobile chrome's leading slot; it self-hides on the
// five bottom-tab ROOT routes (those are reachable via the tab bar, so a Back there would be noise)
// and shows a Back on every nested page. navigate(-1) walks the SPA history; if there's nowhere to
// go back to (a cold deep-link), it falls back to Home so the button is never a no-op dead-end.
const ROOT_ROUTES = new Set(['/home', '/assistant', '/books', '/you', '/onboarding/new']);

export function MobileTopBar() {
  const location = useLocation();
  const navigate = useNavigate();

  if (ROOT_ROUTES.has(location.pathname)) return null;

  const goBack = () => {
    // idx > 0 means there's SPA history to pop; a fresh deep-link (idx 0) has none → go Home.
    const idx = (window.history.state && (window.history.state as { idx?: number }).idx) ?? 0;
    if (idx > 0) navigate(-1);
    else navigate('/home');
  };

  return (
    <div
      className="flex items-center border-b border-border bg-background px-1 py-1"
      data-testid="mobile-top-bar"
    >
      <button
        type="button"
        aria-label="Back"
        data-testid="mobile-back"
        onClick={goBack}
        className="flex min-h-[44px] min-w-[44px] items-center gap-1 rounded-md px-2 text-sm font-medium text-foreground transition-colors hover:bg-secondary"
      >
        <ChevronLeft className="h-5 w-5" aria-hidden="true" />
        Back
      </button>
    </div>
  );
}
