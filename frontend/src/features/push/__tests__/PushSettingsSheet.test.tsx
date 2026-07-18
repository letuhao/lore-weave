// DF5 — the notifications settings sheet: value-first ask when off, per-category toggles when on.
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import type { PushCapability } from '../capability';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }) }));

const sub = {
  capability: { supported: true, iosNeedsInstall: false, permission: 'default', available: true } as PushCapability,
  enabled: false,
  busy: false,
  enable: vi.fn(),
  disable: vi.fn(),
};
const prefs = { topics: {} as Record<string, boolean>, isLoading: false, setTopic: vi.fn() };
vi.mock('../usePushSubscription', () => ({ usePushSubscription: () => sub }));
vi.mock('../usePushPreferences', () => ({ usePushPreferences: () => prefs }));

import { PushSettingsSheet } from '../PushSettingsSheet';

function renderSheet() {
  return render(
    <MemoryRouter initialEntries={['/you?sheet=notifications']}>
      <PushSettingsSheet />
    </MemoryRouter>,
  );
}

describe('PushSettingsSheet (DF5)', () => {
  it('shows the VALUE-FIRST ask when push is off (value points before requesting permission)', () => {
    sub.enabled = false;
    sub.capability = { supported: true, iosNeedsInstall: false, permission: 'default', available: true };
    renderSheet();
    expect(screen.getByTestId('push-value-ask')).toBeTruthy();
    expect(screen.getByText(/Want a nudge/)).toBeTruthy();
    expect(screen.getByText(/never shows your notes/)).toBeTruthy(); // content-free promise
    fireEvent.click(screen.getByTestId('push-turn-on'));
    expect(sub.enable).toHaveBeenCalled();
  });

  it('when denied, shows the settings hint and NO turn-on button (never re-prompts)', () => {
    sub.enabled = false;
    sub.capability = { supported: true, iosNeedsInstall: false, permission: 'denied', available: false };
    renderSheet();
    expect(screen.getByText(/device settings/)).toBeTruthy();
    expect(screen.queryByTestId('push-turn-on')).toBeNull();
  });

  it('shows per-category toggles when push is on, and toggling calls setTopic', () => {
    sub.enabled = true;
    sub.capability = { supported: true, iosNeedsInstall: false, permission: 'granted', available: true };
    prefs.topics = { assistant_weekly: true, social: false };
    renderSheet();
    expect(screen.getByTestId('push-topic-assistant_weekly').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('push-topic-social').getAttribute('aria-checked')).toBe('false');
    fireEvent.click(screen.getByTestId('push-topic-social'));
    expect(prefs.setTopic).toHaveBeenCalledWith('social', true);
    // the content-free guarantee is stated
    expect(screen.getByText(/always content-free/)).toBeTruthy();
  });

  it('hides everything push-y on an unsupported browser', () => {
    sub.enabled = false;
    sub.capability = { supported: false, iosNeedsInstall: false, permission: 'denied', available: false };
    renderSheet();
    expect(screen.getByText(/aren.t available/)).toBeTruthy();
    expect(screen.queryByTestId('push-value-ask')).toBeNull();
  });
});
