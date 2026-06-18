import { describe, it, expect, vi } from 'vitest';
import { type ReactNode } from 'react';
import { render } from '@testing-library/react';

// R3F's <Canvas> creates a real WebGL context (absent in jsdom), so mock the
// three.js layer: Canvas renders its children into a plain div, OrbitControls is
// a no-op, and useGLTF returns a stub scene synchronously (no Suspense). This
// lets us assert the component mounts and threads the `src` into the loader
// without a browser. (Real rendering is covered by typecheck + vite build, and a
// deferred Playwright e2e — D-GLOBE-VIEWER-E2E.)
//
// `vi.hoisted` so the `vi.mock` factory (hoisted above imports) can reference the
// shared `useGLTF` spy.
const { useGLTF } = vi.hoisted(() => ({
  useGLTF: vi.fn(() => ({ scene: { isObject3D: true } })),
}));

vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children, className }: { children: ReactNode; className?: string }) => (
    <div data-testid="r3f-canvas" className={className}>
      {children}
    </div>
  ),
}));
vi.mock('@react-three/drei', () => ({
  OrbitControls: () => null,
  Bounds: ({ children }: { children: ReactNode }) => <>{children}</>,
  useGLTF,
}));

import { GlobeViewer } from '@/components/globe/GlobeViewer';

describe('GlobeViewer', () => {
  it('mounts a canvas and loads the given .glb src', () => {
    const { getByTestId } = render(<GlobeViewer src="/worlds/seed-7-continent.glb" />);
    expect(getByTestId('r3f-canvas')).toBeTruthy();
    expect(useGLTF).toHaveBeenCalledWith('/worlds/seed-7-continent.glb');
  });

  it('forwards className to the canvas wrapper', () => {
    const { getByTestId } = render(
      <GlobeViewer src="/worlds/seed-7-continent.glb" className="absolute inset-0" />,
    );
    expect(getByTestId('r3f-canvas').className).toContain('absolute inset-0');
  });
});
