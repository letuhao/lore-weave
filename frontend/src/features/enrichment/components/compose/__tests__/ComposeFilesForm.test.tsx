import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ComposeFilesForm } from '../ComposeFilesForm';
import type { UploadItem } from '../../../hooks/useUploads';

const READY: UploadItem = {
  id: 'up-1', filename: '蓬萊.pdf', status: 'ready',
  result: { upload_id: 'up-1', filename: '蓬萊.pdf', status: 'ready', extracted_chars: 1200, ocr_used: true },
};

function renderForm(over: Partial<React.ComponentProps<typeof ComposeFilesForm>> = {}) {
  const props = {
    items: [READY],
    onAddFiles: vi.fn(),
    onRemove: vi.fn(),
    license: 'public_domain' as const,
    onLicenseChange: vi.fn(),
    responsibilityChecked: false,
    onResponsibilityChange: vi.fn(),
    ...over,
  };
  render(<ComposeFilesForm {...props} />);
  return props;
}

describe('ComposeFilesForm', () => {
  it('renders an item with its ready status', () => {
    renderForm();
    expect(screen.getByText('蓬萊.pdf')).toBeInTheDocument();
    expect(screen.getByTestId('compose-files-item-up-1')).toBeInTheDocument();
  });

  it('adding files via the input reports the File list to the parent', () => {
    const props = renderForm({ items: [] });
    const file = new File(['hi'], 'ref.txt', { type: 'text/plain' });
    fireEvent.change(screen.getByTestId('compose-files-input'), { target: { files: [file] } });
    expect(props.onAddFiles).toHaveBeenCalledTimes(1);
    expect(props.onAddFiles.mock.calls[0][0][0].name).toBe('ref.txt');
  });

  it('remove reports the item id', () => {
    const props = renderForm();
    fireEvent.click(screen.getByTestId('compose-files-remove-up-1'));
    expect(props.onRemove).toHaveBeenCalledWith('up-1');
  });

  it('license + responsibility changes report to the parent', () => {
    const props = renderForm();
    fireEvent.change(screen.getByTestId('compose-files-license'), { target: { value: 'owned' } });
    expect(props.onLicenseChange).toHaveBeenCalledWith('owned');
    fireEvent.click(screen.getByTestId('compose-files-responsibility'));
    expect(props.onResponsibilityChange).toHaveBeenCalledWith(true);
  });

  it('shows the copyrighted warning when copyrighted is selected', () => {
    renderForm({ license: 'copyrighted' });
    expect(screen.getByTestId('compose-files-copyright-warning')).toBeInTheDocument();
  });
});
