import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TimezoneConfirm } from '../TimezoneConfirm';

// F2 — the tz-confirm banner: pure view. "Use this" confirms the detected zone; "Pick another"
// reveals a select and "Save" confirms the chosen zone.

describe('TimezoneConfirm', () => {
  it('confirms the detected zone on "Use this"', () => {
    const onConfirm = vi.fn();
    render(<TimezoneConfirm detected="Asia/Ho_Chi_Minh" saving={false} onConfirm={onConfirm} />);
    // The banner names the detected zone. Under the key-returning i18n mock the
    // interpolated value is not observable (the key carries no {{zone}} literal), so
    // assert the sentence renders and pin the zone through the action it feeds —
    // which is the behaviour that actually matters if the detection is wrong.
    expect(screen.getByTestId('tz-detected')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('tz-use-detected'));
    expect(onConfirm).toHaveBeenCalledWith('Asia/Ho_Chi_Minh');
  });

  it('lets the user pick a different zone and saves it', () => {
    const onConfirm = vi.fn();
    render(<TimezoneConfirm detected="UTC" saving={false} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByTestId('tz-pick-another'));
    fireEvent.change(screen.getByTestId('tz-select'), { target: { value: 'Europe/Berlin' } });
    fireEvent.click(screen.getByTestId('tz-save-choice'));
    expect(onConfirm).toHaveBeenCalledWith('Europe/Berlin');
  });

  it('injects a detected zone not in the common list so it is always selectable', () => {
    render(<TimezoneConfirm detected="Pacific/Chatham" saving={false} onConfirm={vi.fn()} />);
    fireEvent.click(screen.getByTestId('tz-pick-another'));
    const opts = Array.from(screen.getByTestId('tz-select').querySelectorAll('option')).map((o) => o.value);
    expect(opts).toContain('Pacific/Chatham');
  });

  it('disables the buttons while saving', () => {
    render(<TimezoneConfirm detected="UTC" saving onConfirm={vi.fn()} />);
    expect(screen.getByTestId('tz-use-detected')).toBeDisabled();
  });
});
