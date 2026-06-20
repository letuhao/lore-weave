import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { StandardFormModal } from '../StandardFormModal';

describe('StandardFormModal', () => {
  it('requires a name', () => {
    const onSubmit = vi.fn();
    render(<StandardFormModal entity="genre" mode="create" onSubmit={onSubmit} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId('std-submit'));
    expect(screen.getByText('stdform.name_required')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('creates a genre with name/icon/color/code and no description', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<StandardFormModal entity="genre" mode="create" onSubmit={onSubmit} onClose={vi.fn()} />);
    fireEvent.change(screen.getByTestId('std-name'), { target: { value: 'Wuxia' } });
    fireEvent.change(screen.getByTestId('std-icon'), { target: { value: '🥋' } });
    fireEvent.change(screen.getByTestId('std-code'), { target: { value: 'wuxia' } });
    fireEvent.click(screen.getByTestId('std-submit'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const vals = onSubmit.mock.calls[0][0];
    expect(vals).toMatchObject({ name: 'Wuxia', icon: '🥋', code: 'wuxia' });
    expect(vals).not.toHaveProperty('description');
  });

  it('creates a kind including a description', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<StandardFormModal entity="kind" mode="create" onSubmit={onSubmit} onClose={vi.fn()} />);
    fireEvent.change(screen.getByTestId('std-name'), { target: { value: 'Faction' } });
    fireEvent.change(screen.getByTestId('std-description'), { target: { value: 'a group' } });
    fireEvent.click(screen.getByTestId('std-submit'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ name: 'Faction', description: 'a group' });
  });

  it('omits code in edit mode', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <StandardFormModal
        entity="genre"
        mode="edit"
        initial={{ name: 'Wuxia', icon: '🥋', color: '#000' }}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('std-code')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('std-submit'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('code');
  });
});
