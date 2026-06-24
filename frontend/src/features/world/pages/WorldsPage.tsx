import { WorldsBrowser } from '../components/WorldsBrowser';

// C21 — /worlds HOME. Thin page wrapper; the browser owns the list + create.
export function WorldsPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <WorldsBrowser />
    </div>
  );
}
