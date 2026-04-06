import { useEffect } from 'react';
import { useTTSState } from './useTTS';

/**
 * Auto-scrolls the active block into view during TTS playback.
 * Attaches to a scroll container ref.
 */
export function useBlockScroll(containerRef: React.RefObject<HTMLElement | null>) {
  const { activeBlockId, status } = useTTSState();

  useEffect(() => {
    if (!activeBlockId || status === 'idle') return;

    const container = containerRef.current;
    if (!container) return;

    const blockEl = container.querySelector(`[data-block-id="${activeBlockId}"]`);
    if (!blockEl) return;

    blockEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [activeBlockId, status, containerRef]);
}
