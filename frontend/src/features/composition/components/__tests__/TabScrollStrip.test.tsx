import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TabScrollStrip } from '../TabScrollStrip';

// D-080 — the scroll-aware edge fade. jsdom does no layout, so we drive the
// scroll geometry by defining scrollLeft/scrollWidth/clientWidth on the
// scroller, then fire `scroll` and assert which fade overlay renders.
function setGeometry(el: HTMLElement, { scrollLeft, scrollWidth, clientWidth }: { scrollLeft: number; scrollWidth: number; clientWidth: number }) {
  Object.defineProperty(el, 'scrollLeft', { value: scrollLeft, configurable: true });
  Object.defineProperty(el, 'scrollWidth', { value: scrollWidth, configurable: true });
  Object.defineProperty(el, 'clientWidth', { value: clientWidth, configurable: true });
}

function renderStrip() {
  render(
    <TabScrollStrip testid="strip" className="overflow-x-auto">
      <button>a</button><button>b</button>
    </TabScrollStrip>,
  );
  return screen.getByTestId('strip');
}

describe('TabScrollStrip (D-080)', () => {
  it('keeps the caller testid + className on the inner scroller', () => {
    const strip = renderStrip();
    expect(strip).toHaveClass('overflow-x-auto');
    expect(strip).toHaveTextContent('ab');
  });

  it('shows ONLY the right fade when scrolled to the start (more to the right)', () => {
    const strip = renderStrip();
    setGeometry(strip, { scrollLeft: 0, scrollWidth: 300, clientWidth: 100 });
    fireEvent.scroll(strip);
    expect(screen.getByTestId('tab-fade-right')).toBeInTheDocument();
    expect(screen.queryByTestId('tab-fade-left')).toBeNull();
  });

  it('shows BOTH fades when scrolled to the middle', () => {
    const strip = renderStrip();
    setGeometry(strip, { scrollLeft: 100, scrollWidth: 300, clientWidth: 100 });
    fireEvent.scroll(strip);
    expect(screen.getByTestId('tab-fade-left')).toBeInTheDocument();
    expect(screen.getByTestId('tab-fade-right')).toBeInTheDocument();
  });

  it('shows ONLY the left fade at the end, and NO fade when it all fits', () => {
    const strip = renderStrip();
    setGeometry(strip, { scrollLeft: 200, scrollWidth: 300, clientWidth: 100 });
    fireEvent.scroll(strip);
    expect(screen.getByTestId('tab-fade-left')).toBeInTheDocument();
    expect(screen.queryByTestId('tab-fade-right')).toBeNull();

    // content narrower than the viewport → no fade either side.
    setGeometry(strip, { scrollLeft: 0, scrollWidth: 80, clientWidth: 100 });
    fireEvent.scroll(strip);
    expect(screen.queryByTestId('tab-fade-left')).toBeNull();
    expect(screen.queryByTestId('tab-fade-right')).toBeNull();
  });
});
