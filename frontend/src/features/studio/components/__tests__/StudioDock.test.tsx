import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// dockview-react is heavy + canvas/DOM-measuring; stub it to a marker that exposes the
// component registry + theme it was handed. The layout hook is unit-tested separately.
vi.mock('dockview-react', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  DockviewReact: (props: any) => (
    <div
      data-testid="dockview"
      data-components={Object.keys(props.components).join(',')}
      data-themed={props.theme ? 'yes' : 'no'}
    />
  ),
  themeAbyss: { name: 'abyss' },
}));

import { StudioDock } from '../StudioDock';

describe('StudioDock', () => {
  it('mounts dockview with the Welcome panel registered and a theme', () => {
    render(<StudioDock bookId="b1" />);
    const dv = screen.getByTestId('dockview');
    expect(dv.getAttribute('data-components')).toContain('welcome');
    expect(dv.getAttribute('data-themed')).toBe('yes');
  });
});
