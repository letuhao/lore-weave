import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../ManageWorkspace', () => ({ ManageWorkspace: () => <div data-testid="screen-manage" /> }));
vi.mock('../MatrixScreen', () => ({ MatrixScreen: () => <div data-testid="screen-matrix" /> }));
vi.mock('../SyncScreen', () => ({ SyncScreen: () => <div data-testid="screen-sync" /> }));

import { OntologyShell } from '../OntologyShell';

describe('OntologyShell', () => {
  it('shows the Manage screen by default', () => {
    render(<OntologyShell bookId="book-1" onClose={vi.fn()} />);
    expect(screen.getByTestId('screen-manage')).toBeInTheDocument();
    expect(screen.queryByTestId('screen-matrix')).not.toBeInTheDocument();
  });

  it('switches to the Matrix and Sync tabs', () => {
    render(<OntologyShell bookId="book-1" onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId('ontology-tab-matrix'));
    expect(screen.getByTestId('screen-matrix')).toBeInTheDocument();
    expect(screen.queryByTestId('screen-manage')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('ontology-tab-sync'));
    expect(screen.getByTestId('screen-sync')).toBeInTheDocument();
  });

  it('calls onClose from the back-to-entities link', () => {
    const onClose = vi.fn();
    render(<OntologyShell bookId="book-1" onClose={onClose} />);
    fireEvent.click(screen.getByText('shell.back_to_entities'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
