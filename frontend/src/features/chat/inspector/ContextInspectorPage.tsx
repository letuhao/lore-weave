import { useSearchParams } from 'react-router-dom';
import { ContextInspectorView } from './ContextInspectorView';

// Standalone route for the Context Compiler · Trace Inspector (spec §11 — "also
// remains reachable standalone"). Renders the SAME shared view the studio dock
// panel uses (DOCK-2). Self-contained: it lists the user's sessions and picks one.
// The chat header's inspector icon deep-links here with ?session=<id> so the view
// opens focused on that conversation (initialSessionId); absent the param it falls
// back to the most-recent session.
export function ContextInspectorPage() {
  const [params] = useSearchParams();
  const initialSessionId = params.get('session');
  return (
    <div className="h-[calc(100vh-4rem)] min-h-0">
      <ContextInspectorView initialSessionId={initialSessionId} />
    </div>
  );
}
