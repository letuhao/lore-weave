import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../GenresPanel', () => ({ GenresPanel: () => <div data-testid="panel-genres" /> }));
vi.mock('../KindsPanel', () => ({ KindsPanel: () => <div data-testid="panel-kinds" /> }));
vi.mock('../AttributesPanel', () => ({ AttributesPanel: () => <div data-testid="panel-attributes" /> }));

import { StandardsShell } from '../StandardsShell';

function renderShell(tab: 'genres' | 'kinds' | 'attributes') {
  return render(
    <MemoryRouter>
      <StandardsShell tab={tab} />
    </MemoryRouter>,
  );
}

describe('StandardsShell', () => {
  it('renders all three tab links', () => {
    renderShell('genres');
    expect(screen.getByTestId('standards-tab-genres')).toBeInTheDocument();
    expect(screen.getByTestId('standards-tab-kinds')).toBeInTheDocument();
    expect(screen.getByTestId('standards-tab-attributes')).toBeInTheDocument();
  });

  it('shows the genres panel and marks its tab selected', () => {
    renderShell('genres');
    expect(screen.getByTestId('panel-genres')).toBeInTheDocument();
    expect(screen.queryByTestId('panel-kinds')).not.toBeInTheDocument();
    expect(screen.getByTestId('standards-tab-genres')).toHaveAttribute('aria-selected', 'true');
  });

  it('shows the kinds panel when tab=kinds', () => {
    renderShell('kinds');
    expect(screen.getByTestId('panel-kinds')).toBeInTheDocument();
    expect(screen.queryByTestId('panel-genres')).not.toBeInTheDocument();
  });

  it('shows the attributes panel when tab=attributes', () => {
    renderShell('attributes');
    expect(screen.getByTestId('panel-attributes')).toBeInTheDocument();
  });
});
