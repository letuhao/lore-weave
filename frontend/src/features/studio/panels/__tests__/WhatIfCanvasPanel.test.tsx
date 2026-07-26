/**
 * O-11 — the what-if branch-preview producer, mounted in the Studio.
 * The panel is a thin wrapper: it resolves the book's composition Work, then mounts the EXISTING
 * SceneGraphCanvas producer (the 449-LOC what-if canvas stays in composition, reused as-is — the
 * GroundingPanel precedent). So the what-if capability survives Wave 6 retiring the legacy page,
 * and PromoteWhatIfButton (already ported to divergence) has a producer again.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../host/StudioHostProvider', () => ({ useStudioHost: () => ({ bookId: 'book-1' }) }));
vi.mock('../useStudioPanel', () => ({ useStudioPanel: () => undefined }));
vi.mock('@/features/composition/components/SceneGraphCanvas', () => ({
  SceneGraphCanvas: ({ bookId }: { bookId: string }) => (
    <div data-testid="scene-graph-canvas">{bookId}</div>
  ),
}));

// useWorkResolution resolves to the ENVELOPE `WorkResolution {status, work, candidates}` — NOT a bare
// Work. The panel must dig out `.work`; mocking a bare object here is what hid the shape mismatch that
// crashed SceneGraphCanvas live (it reads `work.settings`). So the mock returns the real envelope shape.
let resolution: unknown = null;
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: () => ({ data: resolution }),
}));

import { WhatIfCanvasPanel } from '../WhatIfCanvasPanel';

const props = { api: {} } as never;

describe('WhatIfCanvasPanel (close-21-28 O-11)', () => {
  it('shows a calm no-plan-yet state when the book has no composition Work', () => {
    resolution = { status: 'not_found', work: null };
    render(<WhatIfCanvasPanel {...props} />);
    expect(screen.getByTestId('whatif-canvas-nowork')).toBeInTheDocument();
    expect(screen.queryByTestId('scene-graph-canvas')).not.toBeInTheDocument();
  });

  it('mounts the SceneGraphCanvas producer once a Work exists — the capability survives the port', () => {
    // The real envelope: status:'found' wrapping the inner Work. The panel must pass res.work (WITH its
    // settings), not the envelope — else SceneGraphCanvas crashes on `work.settings.scene_graph`.
    resolution = { status: 'found', work: { id: 'w1', project_id: 'p1', settings: {} } };
    render(<WhatIfCanvasPanel {...props} />);
    expect(screen.getByTestId('whatif-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('scene-graph-canvas')).toHaveTextContent('book-1');
  });

  it('handles the candidates envelope (a book with unresolved candidate Works) by mounting the first', () => {
    resolution = { status: 'candidates', work: null, candidates: [{ id: 'c1', project_id: 'p2', settings: {} }] };
    render(<WhatIfCanvasPanel {...props} />);
    expect(screen.getByTestId('whatif-canvas')).toBeInTheDocument();
  });
});
