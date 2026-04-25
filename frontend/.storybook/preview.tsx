import type { Preview, Decorator } from '@storybook/react-vite';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { initialize, mswLoader } from 'msw-storybook-addon';
import { MockAuthProvider } from './MockAuthProvider';

// Tailwind base styles + project css (needed so state cards render
// with their variant borders, padding, colors).
import '../src/index.css';
// i18n init side-effect — gives every story a usable `useTranslation`
// without having to wrap individually.
import '../src/i18n';

// C13 — bootstrap MSW once at Storybook preview-iframe load. Stories
// that need network mocks supply `parameters.msw.handlers` and the
// addon's loader wires them before the story renders. `onUnhandledRequest`
// set to 'warn' (not 'error') so stories that accidentally let an
// unmocked call slip through get a console warning in devtools instead
// of a thrown fetch — less noisy while we're adding coverage story by
// story.
initialize({ onUnhandledRequest: 'warn' });

// K19a.8 — One global decorator to wrap every story in the providers
// components expect:
//   - `MockAuthProvider` — stub for `useAuth()` (see MockAuthProvider.tsx)
//   - `QueryClientProvider` — fresh client per render; `retry: false` +
//     `staleTime: Infinity` keeps stories deterministic (no background
//     refetches polluting the preview panel)
//   - `MemoryRouter` — components using `useLocation`/`<Link>` would
//     otherwise throw
//
// Stories that need network-mocked APIs should use a local msw handler
// via a story-level decorator (deferred to D-K19a.8-01 — we scoped to
// presentational cards in this cycle).
const withProviders: Decorator = (Story) => {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  return (
    <MockAuthProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/']}>
          <div className="min-h-screen bg-background p-6 text-foreground">
            <Story />
          </div>
        </MemoryRouter>
      </QueryClientProvider>
    </MockAuthProvider>
  );
};

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    a11y: {
      // 'todo' — show a11y violations in the test UI but don't fail
      // the story. Upgrade to 'error' when we wire a CI pipeline.
      test: 'todo',
    },
    backgrounds: {
      default: 'app',
      values: [
        { name: 'app', value: '#0a0a0a' },
        { name: 'light', value: '#ffffff' },
      ],
    },
  },
  decorators: [withProviders],
  loaders: [mswLoader],
};

export default preview;
