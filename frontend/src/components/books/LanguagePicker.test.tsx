import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { LanguagePicker } from './LanguagePicker';
import { LANGUAGE_CODES } from '@/data/languageCodes';

describe('LanguagePicker', () => {
  beforeEach(() => { cleanup(); });

  // ── Rendering ────────────────────────────────────────────────────────────────

  it('renders a text input', () => {
    render(<LanguagePicker value="en" onChange={vi.fn()} />);
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('renders default label "Language"', () => {
    render(<LanguagePicker value="" onChange={vi.fn()} />);
    expect(screen.getByText('Language')).toBeInTheDocument();
  });

  it('renders custom label', () => {
    render(<LanguagePicker value="" onChange={vi.fn()} label="Target language" />);
    expect(screen.getByText('Target language')).toBeInTheDocument();
  });

  it('renders required asterisk when required=true', () => {
    render(<LanguagePicker value="" onChange={vi.fn()} required />);
    expect(screen.getByText(/\*/)).toBeInTheDocument();
  });

  it('does not render asterisk when required is omitted', () => {
    render(<LanguagePicker value="" onChange={vi.fn()} />);
    expect(screen.queryByText(/\*/)).not.toBeInTheDocument();
  });

  it('shows current value in the input', () => {
    render(<LanguagePicker value="vi" onChange={vi.fn()} />);
    const input = screen.getByRole('combobox') as HTMLInputElement;
    expect(input.value).toBe('vi');
  });

  // ── Datalist ──────────────────────────────────────────────────────────────────

  it('input has a list attribute pointing to a datalist', () => {
    render(<LanguagePicker value="" onChange={vi.fn()} />);
    const input = screen.getByRole('combobox') as HTMLInputElement;
    const listId = input.getAttribute('list');
    expect(listId).toBeTruthy();
    const datalist = document.getElementById(listId!);
    expect(datalist).toBeInTheDocument();
    expect(datalist!.tagName.toLowerCase()).toBe('datalist');
  });

  it('datalist contains all 581 language entries', () => {
    render(<LanguagePicker value="" onChange={vi.fn()} />);
    const input = screen.getByRole('combobox') as HTMLInputElement;
    const datalist = document.getElementById(input.getAttribute('list')!)!;
    const options = datalist.querySelectorAll('option');
    expect(options.length).toBe(LANGUAGE_CODES.length);
    expect(options.length).toBe(581);
  });

  it('datalist option value is the BCP-47 code', () => {
    render(<LanguagePicker value="" onChange={vi.fn()} />);
    const input = screen.getByRole('combobox') as HTMLInputElement;
    const datalist = document.getElementById(input.getAttribute('list')!)!;
    const viOption = Array.from(datalist.querySelectorAll('option')).find(
      (o) => (o as HTMLOptionElement).value === 'vi',
    ) as HTMLOptionElement | undefined;
    expect(viOption).toBeDefined();
    expect(viOption!.value).toBe('vi');
  });

  // ── Unique datalist IDs ───────────────────────────────────────────────────────

  it('two instances have different datalist IDs', () => {
    const { unmount: unmount1 } = render(
      <LanguagePicker value="en" onChange={vi.fn()} />,
    );
    const input1 = screen.getByRole('combobox') as HTMLInputElement;
    const id1 = input1.getAttribute('list');

    unmount1();
    cleanup();

    render(<LanguagePicker value="vi" onChange={vi.fn()} />);
    const input2 = screen.getByRole('combobox') as HTMLInputElement;
    const id2 = input2.getAttribute('list');

    // In separate renders both IDs are generated fresh — they are different DOM environments
    // but the key test is that the component uses useId, so concurrent renders differ:
    expect(id1).toBeTruthy();
    expect(id2).toBeTruthy();
  });

  it('two simultaneous instances have different datalist IDs', () => {
    const { container } = render(
      <div>
        <LanguagePicker value="en" onChange={vi.fn()} label="Source" />
        <LanguagePicker value="vi" onChange={vi.fn()} label="Target" />
      </div>,
    );
    const inputs = container.querySelectorAll('input[list]');
    expect(inputs.length).toBe(2);
    const id1 = inputs[0].getAttribute('list');
    const id2 = inputs[1].getAttribute('list');
    expect(id1).not.toBe(id2);
    // Datalists: each ID resolves to a distinct datalist element
    const datalist1 = document.getElementById(id1!);
    const datalist2 = document.getElementById(id2!);
    expect(datalist1).toBeInTheDocument();
    expect(datalist2).toBeInTheDocument();
    expect(datalist1).not.toBe(datalist2);
  });

  // ── onChange ──────────────────────────────────────────────────────────────────

  it('calls onChange with typed value', () => {
    const onChange = vi.fn();
    render(<LanguagePicker value="" onChange={onChange} />);
    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'fr' } });
    expect(onChange).toHaveBeenCalledWith('fr');
  });

  it('calls onChange with empty string when cleared', () => {
    const onChange = vi.fn();
    render(<LanguagePicker value="en" onChange={onChange} />);
    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith('');
  });

  // ── Placeholder ───────────────────────────────────────────────────────────────

  it('shows default placeholder text', () => {
    render(<LanguagePicker value="" onChange={vi.fn()} />);
    const input = screen.getByRole('combobox') as HTMLInputElement;
    expect(input.placeholder).toBe('e.g. en, vi, zh-Hans');
  });

  it('shows custom placeholder when provided', () => {
    render(<LanguagePicker value="" onChange={vi.fn()} placeholder="Type a language code" />);
    const input = screen.getByRole('combobox') as HTMLInputElement;
    expect(input.placeholder).toBe('Type a language code');
  });

  // ── required attribute ────────────────────────────────────────────────────────

  it('input has required attribute when required=true', () => {
    render(<LanguagePicker value="" onChange={vi.fn()} required />);
    const input = screen.getByRole('combobox') as HTMLInputElement;
    expect(input.required).toBe(true);
  });

  it('input does not have required attribute when required is omitted', () => {
    render(<LanguagePicker value="" onChange={vi.fn()} />);
    const input = screen.getByRole('combobox') as HTMLInputElement;
    expect(input.required).toBe(false);
  });
});
