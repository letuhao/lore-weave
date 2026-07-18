// §2#6 loop-connect — the conformance trace must not be an island: a scene row + the empty-state
// CTA deep-link to the scene surface (proven by effect — onOpenScene fires with the right ids).
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConformanceSceneRow } from '../components/ConformanceSceneRow';
import type { SceneConformance } from '../types';

const scene = {
  outline_node_id: 'node-7',
  beat_role: 'reversal',
  planned: { beat_key: 'reversal', tension: 4 },
  realized: { has_prose: true },
  conformance: { beat_realized: false, tension_band_match: false, calibrated: true, error: null },
} as unknown as SceneConformance;

describe('conformance → scene deep-link', () => {
  it('a scene row opens the scene when onOpenScene is provided', () => {
    const onOpenScene = vi.fn();
    render(<ConformanceSceneRow scene={scene} onRegenerate={() => {}} onOpenScene={onOpenScene} />);
    fireEvent.click(screen.getByTestId('conformance-open-scene-node-7'));
    expect(onOpenScene).toHaveBeenCalledWith('node-7');
  });

  it('renders a plain (non-link) beat label when no deep-link handler is given (legacy mount)', () => {
    render(<ConformanceSceneRow scene={scene} onRegenerate={() => {}} />);
    expect(screen.queryByTestId('conformance-open-scene-node-7')).not.toBeInTheDocument();
  });
});
