import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listModelsMock = vi.fn();
vi.mock('@/features/settings/api', () => ({
  providerApi: { listUserModels: (...a: unknown[]) => listModelsMock(...a) },
}));

import { ProfileForm } from '../ProfileForm';
import type { BookProfile, SuggestedProfile } from '../../types';

const P = (over: Partial<BookProfile> = {}): BookProfile => ({
  book_id: 'book-1',
  worldview: '商周·封神演义',
  language: 'zh',
  era_policy: '商周',
  voice: '文言',
  anachronism_markers: [{ term: '火车', reason: 'modern' }],
  anachronism_enabled: true,
  dimension_overrides: {},
  profile_source: 'seed',
  ...over,
});

function renderForm(profile: BookProfile, onSave = vi.fn(), onSuggest = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  render(
    <Wrapper>
      <ProfileForm profile={profile} onSave={onSave} onSuggest={onSuggest} saving={false} suggesting={false} />
    </Wrapper>,
  );
  return { onSave, onSuggest };
}

beforeEach(() => {
  listModelsMock.mockReset();
  listModelsMock.mockResolvedValue({
    items: [{ user_model_id: 'm1', alias: 'qwen', provider_model_name: 'qwen' }],
  });
});

describe('ProfileForm', () => {
  it('seeds the fields from the profile', () => {
    renderForm(P());
    expect((screen.getByTestId('profile-worldview') as HTMLTextAreaElement).value).toBe('商周·封神演义');
    expect((screen.getByTestId('profile-language') as HTMLInputElement).value).toBe('zh');
  });

  it('save sends the FULL profile — editing worldview round-trips the seeded markers (review #3)', () => {
    const { onSave } = renderForm(P());
    fireEvent.change(screen.getByTestId('profile-worldview'), { target: { value: 'new worldview' } });
    fireEvent.click(screen.getByTestId('profile-save'));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        worldview: 'new worldview',
        language: 'zh',
        era_policy: '商周',
        anachronism_markers: [{ term: '火车', reason: 'modern' }], // NOT wiped
      }),
    );
  });

  it('drops blank-id add rows + trims ids on save (review #1 — avoids a 400)', () => {
    const { onSave } = renderForm(
      P({
        dimension_overrides: {
          character: { add: [{ id: '', label: 'blank' }, { id: '  cult  ', label: 'Cultivation' }], remove: ['history'] },
          item: { add: [{ id: '', label: 'all-blank' }] },
        },
      }),
    );
    fireEvent.click(screen.getByTestId('profile-save'));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        dimension_overrides: {
          // blank-id dropped, id trimmed, sibling `remove` preserved
          character: { add: [{ id: 'cult', label: 'Cultivation' }], remove: ['history'] },
          // item had ONLY a blank-id add → kind dropped entirely
        },
      }),
    );
  });

  it('parses the multi-line markers textarea (term | reason) on save', () => {
    const { onSave } = renderForm(P({ anachronism_markers: [] }));
    fireEvent.change(screen.getByLabelText('settings.markers'), {
      target: { value: '火车 | modern\n飞机\n  \n股票 | finance | extra' },
    });
    fireEvent.click(screen.getByTestId('profile-save'));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        anachronism_markers: [
          { term: '火车', reason: 'modern' },
          { term: '飞机', reason: '' }, // no pipe → empty reason
          { term: '股票', reason: 'finance | extra' }, // reason keeps later pipes
        ],
      }),
    );
  });

  it('empty era/voice serialize to null (not empty string)', () => {
    const { onSave } = renderForm(P({ era_policy: null, voice: null }));
    fireEvent.click(screen.getByTestId('profile-save'));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ era_policy: null, voice: null }),
    );
  });

  it('suggest is disabled until a model is picked', () => {
    renderForm(P());
    expect(screen.getByTestId('profile-suggest')).toBeDisabled();
  });

  it('picking a model + suggesting applies the draft to the fields', async () => {
    const draft: SuggestedProfile = {
      worldview: 'cyberpunk Saigon',
      language: 'vi',
      era_policy: 'no pre-2040 tech',
      voice: 'noir',
      dimension_overrides: { character: { add: [{ id: 'implants', label: 'Implants' }] } },
      profile_source: 'ai_suggested',
    };
    const onSuggest = vi.fn().mockResolvedValue(draft);
    renderForm(P(), vi.fn(), onSuggest);
    await waitFor(() => expect(screen.getByRole('option', { name: 'qwen' })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('settings.suggest_model'), { target: { value: 'm1' } });
    fireEvent.click(screen.getByTestId('profile-suggest'));
    expect(onSuggest).toHaveBeenCalledWith('m1');
    await waitFor(() =>
      expect((screen.getByTestId('profile-worldview') as HTMLTextAreaElement).value).toBe('cyberpunk Saigon'),
    );
    expect((screen.getByTestId('profile-language') as HTMLInputElement).value).toBe('vi');
  });
});
