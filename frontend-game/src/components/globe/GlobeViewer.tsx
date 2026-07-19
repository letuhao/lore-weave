import { Suspense } from 'react';
import { Canvas } from '@react-three/fiber';
import { Bounds, OrbitControls, useGLTF } from '@react-three/drei';
import type { JSX } from 'react';

// Reusable 3D globe viewer — renders a `world-gen` `.glb` displaced-sphere mesh
// (real bathymetry + hypsometric/biome texture) with orbit controls. Pure view:
// it takes a `src` URL and is delivery-agnostic (static asset now, a
// world-gen-service blob URL later) so it can be dropped into any route/feature
// (world-preview, world-select, future creator tools).
//
// Sizing: the <Canvas> fills its parent, so the consumer must give the wrapper a
// height (e.g. a flex-1 container or a fixed h-*).

export interface GlobeViewerProps {
  /** URL of the `.glb` globe mesh (see `worlds.ts` for the static catalog). */
  src: string;
  /** Extra classes for the Canvas wrapper. */
  className?: string;
  /** Slowly spin the globe (default on). */
  autoRotate?: boolean;
}

/** The loaded globe mesh. Suspends (via `useGLTF`) until the `.glb` is fetched. */
function GlobeModel({ src }: { src: string }): JSX.Element {
  const { scene } = useGLTF(src);
  return <primitive object={scene} />;
}

export function GlobeViewer({ src, className, autoRotate = true }: GlobeViewerProps): JSX.Element {
  return (
    <Canvas
      className={className}
      // R3F sets the container to `position:relative; height:100%` inline, which
      // (a) defeats an `absolute inset-0` *class* and (b) collapses to ~0 height
      // when the parent is a flex item (percentage height has no definite base).
      // User `style` merges last in R3F, so absolutely position the canvas here —
      // it then fills the relative parent with a definite size. The parent must
      // be positioned + sized (the route's `<main className="flex-1 relative">`).
      style={{ position: 'absolute', inset: 0 }}
      camera={{ position: [0, 0, 3], fov: 45 }}
      dpr={[1, 2]}
    >
      {/* Soft key + fill so the textured terrain reads in 3D. */}
      <ambientLight intensity={0.7} />
      <directionalLight position={[5, 3, 5]} intensity={1.3} />
      <directionalLight position={[-4, -2, -3]} intensity={0.3} />
      <Suspense fallback={null}>
        {/* Auto-frame the globe to fill the viewport (any model size / aspect),
            re-fitting on load + resize — avoids a tiny globe in a wide canvas. */}
        <Bounds fit clip observe margin={1.1}>
          <GlobeModel src={src} />
        </Bounds>
      </Suspense>
      <OrbitControls
        makeDefault
        enablePan={false}
        autoRotate={autoRotate}
        autoRotateSpeed={0.5}
        minDistance={1.2}
        maxDistance={8}
      />
    </Canvas>
  );
}
