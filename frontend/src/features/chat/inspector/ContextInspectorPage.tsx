import { ContextInspectorView } from './ContextInspectorView';

// Standalone route for the Context Compiler · Trace Inspector (spec §11 — "also
// remains reachable standalone"). Renders the SAME shared view the studio dock
// panel uses (DOCK-2). Self-contained: it lists the user's sessions and picks one.
export function ContextInspectorPage() {
  return (
    <div className="h-[calc(100vh-4rem)] min-h-0">
      <ContextInspectorView />
    </div>
  );
}
