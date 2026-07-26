import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LanguagePicker } from '../LanguagePicker';

describe('LanguagePicker', () => {
  it('renders the canonical language list as "Name (code)" options', () => {
    render(<LanguagePicker value="" onChange={() => {}} />);
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    const opts = Array.from(select.options).map((o) => o.textContent);
    expect(opts).toContain('日本語 (ja)');
    expect(opts).toContain('English (en)');
    expect(opts).toContain('繁體中文 (zh-TW)');
  });

  it('shows a leading empty option only when placeholder is provided', () => {
    const { rerender } = render(<LanguagePicker value="" onChange={() => {}} />);
    expect(
      Array.from((screen.getByRole('combobox') as HTMLSelectElement).options).some((o) => o.value === ''),
    ).toBe(false);

    rerender(<LanguagePicker value="" onChange={() => {}} placeholder="Select language…" />);
    const empty = Array.from((screen.getByRole('combobox') as HTMLSelectElement).options).find(
      (o) => o.value === '',
    );
    expect(empty?.textContent).toBe('Select language…');
  });

  it('reports the picked code via onChange', () => {
    const onChange = vi.fn();
    render(<LanguagePicker value="" onChange={onChange} placeholder="x" />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'vi' } });
    expect(onChange).toHaveBeenCalledWith('vi');
  });

  it('omits excluded codes from the list', () => {
    render(<LanguagePicker value="" onChange={() => {}} exclude={['en', 'ja']} />);
    const codes = Array.from((screen.getByRole('combobox') as HTMLSelectElement).options).map((o) => o.value);
    expect(codes).not.toContain('en');
    expect(codes).not.toContain('ja');
    expect(codes).toContain('vi');
  });

  it('preserves an unrecognised current value as a selectable option (no silent drop)', () => {
    render(<LanguagePicker value="it" onChange={() => {}} />);
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.value).toBe('it');
    expect(Array.from(select.options).map((o) => o.value)).toContain('it');
  });

  it('preserves a known code that is excluded so editing keeps it visible', () => {
    render(<LanguagePicker value="en" onChange={() => {}} exclude={['en']} />);
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.value).toBe('en');
    // rendered via the orphan branch as "English (en)"
    const selected = Array.from(select.options).find((o) => o.value === 'en');
    expect(selected?.textContent).toBe('English (en)');
  });
});
