import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { QuickCreateModal } from '../QuickCreateModal';

describe('QuickCreateModal', () => {
  it('Create calls onCreate with just the name when optionals are blank', async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(<QuickCreateModal kind="genre" onCreate={onCreate} onClose={onClose} />);

    fireEvent.change(screen.getByPlaceholderText('quickcreate.name_placeholder'), {
      target: { value: '  Cultivation  ' },
    });
    fireEvent.click(screen.getByText('quickcreate.create'));

    await vi.waitFor(() => expect(onCreate).toHaveBeenCalledWith({ name: 'Cultivation' }));
  });

  it('passes optional icon and code through, trimmed', async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(<QuickCreateModal kind="kind" onCreate={onCreate} onClose={vi.fn()} />);

    const inputs = screen.getAllByRole('textbox');
    fireEvent.change(inputs[0], { target: { value: 'Sect' } });
    fireEvent.change(inputs[1], { target: { value: ' ⚔️ ' } });
    fireEvent.change(inputs[2], { target: { value: ' sect ' } });
    fireEvent.click(screen.getByText('quickcreate.create'));

    await vi.waitFor(() =>
      expect(onCreate).toHaveBeenCalledWith({ name: 'Sect', icon: '⚔️', code: 'sect' }),
    );
  });

  it('blocks submit on empty name and shows the required error', () => {
    const onCreate = vi.fn();
    render(<QuickCreateModal kind="genre" onCreate={onCreate} onClose={vi.fn()} />);

    fireEvent.click(screen.getByText('quickcreate.create'));
    expect(onCreate).not.toHaveBeenCalled();
    expect(screen.getByText('quickcreate.name_required')).toBeInTheDocument();
  });

  it('closes on Escape when idle', () => {
    const onClose = vi.fn();
    render(<QuickCreateModal kind="genre" onCreate={vi.fn()} onClose={onClose} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('does NOT close on Escape while submitting', () => {
    const onClose = vi.fn();
    // never-resolving promise holds the modal in the submitting state
    const onCreate = vi.fn(() => new Promise<void>(() => {}));
    render(<QuickCreateModal kind="genre" onCreate={onCreate} onClose={onClose} />);

    fireEvent.change(screen.getByPlaceholderText('quickcreate.name_placeholder'), {
      target: { value: 'Genre' },
    });
    fireEvent.click(screen.getByText('quickcreate.create'));
    // now in the submitting state (button label flips to "creating")
    expect(screen.getByText('quickcreate.creating')).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });
});
