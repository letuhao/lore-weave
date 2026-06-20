import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AttributeFormModal } from '../AttributeFormModal';

describe('AttributeFormModal', () => {
  it('requires a name before submit', async () => {
    const onSubmit = vi.fn();
    render(<AttributeFormModal mode="create" onSubmit={onSubmit} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId('attr-submit'));
    expect(screen.getByText('attrform.name_required')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits name, code, field_type and required; no options for a text field', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<AttributeFormModal mode="create" onSubmit={onSubmit} onClose={vi.fn()} />);
    fireEvent.change(screen.getByTestId('attr-name'), { target: { value: 'Rank' } });
    fireEvent.change(screen.getByTestId('attr-code'), { target: { value: 'rank' } });
    fireEvent.click(screen.getByTestId('attr-required'));
    fireEvent.click(screen.getByTestId('attr-submit'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Rank', code: 'rank', field_type: 'text', is_required: true, options: [],
    });
  });

  it('parses options (one per line) only for select/tags', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<AttributeFormModal mode="create" onSubmit={onSubmit} onClose={vi.fn()} />);
    fireEvent.change(screen.getByTestId('attr-name'), { target: { value: 'Tier' } });
    fireEvent.change(screen.getByTestId('attr-field-type'), { target: { value: 'select' } });
    fireEvent.change(screen.getByTestId('attr-options'), { target: { value: 'gold\nsilver\n\n bronze ' } });
    fireEvent.click(screen.getByTestId('attr-submit'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      field_type: 'select', options: ['gold', 'silver', 'bronze'],
    });
  });

  it('omits code in edit mode (code is immutable post-create)', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <AttributeFormModal
        mode="edit"
        initial={{ name: 'Rank', code: 'rank', field_type: 'text', is_required: false, options: [] }}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('attr-code')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('attr-submit'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('code');
  });
});
