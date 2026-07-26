import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { UserModel } from '@/features/ai-models/api';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

// W5 — ComposeConfig renders the shared ModelPicker (gen=chat, embed=embedding)
// which fetches via aiModelsApi (and also imports getUserModelMeta → keep actual).
const listUserModelsMock = vi.fn();
vi.mock('@/features/ai-models/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/ai-models/api')>();
  return {
    ...actual,
    aiModelsApi: {
      listUserModels: (...a: unknown[]) => listUserModelsMock(...a),
      patchFavorite: vi.fn(),
    },
  };
});
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: vi.fn().mockResolvedValue(undefined),
  savePrefToServer: vi.fn().mockResolvedValue(true),
  syncPrefsToServer: vi.fn(),
}));

import { invalidateUserModelsCache } from '@/components/model-picker';
import { ComposeConfig, type ComposeConfigValue } from '../ComposeConfig';

const model = (over: Partial<UserModel> & { user_model_id: string }): UserModel => ({
  provider_credential_id: 'cred-1',
  provider_kind: 'lm_studio',
  provider_model_name: over.user_model_id,
  alias: null,
  is_active: true,
  is_favorite: false,
  capability_flags: {},
  tags: [],
  created_at: '2026-01-01T00:00:00Z',
  ...over,
});

const V: ComposeConfigValue = {
  genModel: '',
  embedModel: '',
  maxSpend: '',
  topK: 5,
  technique: 'retrieval',
  requestedDimensions: null,
};

const DIMS = [
  { id: 'history', label: 'History', required: true },
  { id: 'geography', label: 'Geography', required: false },
];

async function pickModel(pickerLabel: string, optionText: string) {
  fireEvent.click(await screen.findByRole('combobox', { name: pickerLabel }));
  fireEvent.click(await screen.findByText(optionText));
}

beforeEach(() => {
  listUserModelsMock.mockReset();
  listUserModelsMock.mockImplementation((_t: string, opts?: { capability?: string }) =>
    Promise.resolve({
      items:
        opts?.capability === 'embedding'
          ? [model({ user_model_id: 'e1', alias: 'Embed-1', provider_model_name: 'bge-m3' })]
          : [model({ user_model_id: 'g1', alias: 'Gen-1', provider_model_name: 'qwen' })],
    }),
  );
  localStorage.clear();
  invalidateUserModelsCache();
});

describe('ComposeConfig', () => {
  it('renders chat + embedding model pickers and reports a gen-model selection', async () => {
    const onChange = vi.fn();
    render(<ComposeConfig value={V} onChange={onChange} />);
    await pickModel('compose.config.gen_model', 'Gen-1');
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ genModel: 'g1' }));
    // the sibling picker fetched the embedding capability
    fireEvent.click(await screen.findByRole('combobox', { name: 'compose.config.embed_model' }));
    expect(await screen.findByText('Embed-1')).toBeInTheDocument();
    expect(listUserModelsMock).toHaveBeenCalledWith('tok', { include_inactive: false, capability: 'chat' });
    expect(listUserModelsMock).toHaveBeenCalledWith('tok', { include_inactive: false, capability: 'embedding' });
  });

  it('reports an embed-model selection', async () => {
    const onChange = vi.fn();
    render(<ComposeConfig value={V} onChange={onChange} />);
    await pickModel('compose.config.embed_model', 'Embed-1');
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ embedModel: 'e1' }));
  });

  it('reports max-spend + top-k changes', () => {
    const onChange = vi.fn();
    render(<ComposeConfig value={V} onChange={onChange} />);
    fireEvent.change(screen.getByTestId('compose-max-spend'), { target: { value: '0.5' } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ maxSpend: '0.5' }));
    fireEvent.change(screen.getByTestId('compose-top-k'), { target: { value: '8' } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ topK: 8 }));
  });

  it('shows the H0 marker (enriched-stays-a-variant cue)', () => {
    render(<ComposeConfig value={V} onChange={vi.fn()} />);
    expect(screen.getByTestId('enrichment-h0-marker')).toBeInTheDocument();
  });

  // #2 technique selector + #6 eval-gate warning
  it('hides the technique selector unless showTechnique', () => {
    render(<ComposeConfig value={V} onChange={vi.fn()} />);
    expect(screen.queryByTestId('compose-technique')).not.toBeInTheDocument();
  });

  it('shows the technique selector and reports a change when showTechnique', () => {
    const onChange = vi.fn();
    render(<ComposeConfig value={V} onChange={onChange} showTechnique />);
    fireEvent.change(screen.getByTestId('compose-technique'), { target: { value: 'recook' } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ technique: 'recook' }));
  });

  it('warns about the eval-gate only for P2/P3 techniques', () => {
    const { rerender } = render(<ComposeConfig value={V} onChange={vi.fn()} showTechnique />);
    expect(screen.queryByTestId('compose-eval-gate-warning')).not.toBeInTheDocument(); // retrieval=P1
    rerender(<ComposeConfig value={{ ...V, technique: 'fabrication' }} onChange={vi.fn()} showTechnique />);
    expect(screen.getByTestId('compose-eval-gate-warning')).toBeInTheDocument();
  });

  // #1 dimension picker
  it('defaults to auto (no chips) and only shows chips when auto is unchecked', () => {
    const onChange = vi.fn();
    render(<ComposeConfig value={V} onChange={onChange} dimensions={DIMS} />);
    expect(screen.getByTestId('compose-dims-auto')).toBeChecked();
    expect(screen.queryByTestId('compose-dims-picker')).not.toBeInTheDocument();
    // unchecking auto → selects all dim ids (enrich all, explicit)
    fireEvent.click(screen.getByTestId('compose-dims-auto'));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ requestedDimensions: ['history', 'geography'] }),
    );
  });

  it('toggles a single dimension chip off → requestedDimensions excludes it', () => {
    const onChange = vi.fn();
    // start in manual mode with both selected
    render(
      <ComposeConfig
        value={{ ...V, requestedDimensions: ['history', 'geography'] }}
        onChange={onChange}
        dimensions={DIMS}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'History' }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ requestedDimensions: ['geography'] }),
    );
  });

  it('hides the dimension picker when no dimensions are provided', () => {
    render(<ComposeConfig value={V} onChange={vi.fn()} />);
    expect(screen.queryByTestId('compose-dims-auto')).not.toBeInTheDocument();
  });
});
