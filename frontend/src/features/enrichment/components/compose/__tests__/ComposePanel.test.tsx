import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

vi.mock('@/features/settings/api', () => ({
  providerApi: {
    listUserModels: (_t: string, opts?: { capability?: string }) =>
      Promise.resolve({
        items:
          opts?.capability === 'embedding'
            ? [{ user_model_id: 'e1', alias: 'Embed-1', provider_model_name: 'bge-m3' }]
            : [{ user_model_id: 'g1', alias: 'Gen-1', provider_model_name: 'qwen' }],
      }),
  },
}));

const composeMock = vi.fn().mockResolvedValue({ job_id: 'j1' });
vi.mock('../../../hooks/useCompose', () => ({
  useCompose: () => ({ compose: composeMock, composing: false }),
}));

const uploadsMock = vi.hoisted(() => ({
  items: [] as Array<{ id: string; filename: string; status: string }>,
  upload: vi.fn(),
  remove: vi.fn(),
  readyIds: [] as string[],
}));
vi.mock('../../../hooks/useUploads', () => ({ useUploads: () => uploadsMock }));

// existing-target autocomplete reads the book's glossary entity names (best-effort).
vi.mock('@/features/glossary/api', () => ({
  glossaryApi: { listEntityNames: () => Promise.resolve([]) },
}));

import { ComposePanel } from '../ComposePanel';
import { EnrichmentProvider } from '../../../context/EnrichmentContext';

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <EnrichmentProvider bookId="book-1">{children}</EnrichmentProvider>
    </QueryClientProvider>
  );
  return render(<ComposePanel />, { wrapper: Wrapper });
}

async function fillGen() {
  await waitFor(() => expect(screen.getByRole('option', { name: 'Gen-1' })).toBeInTheDocument());
  fireEvent.change(screen.getByTestId('compose-gen-model'), { target: { value: 'g1' } });
}
async function fillModels() {
  await fillGen();
  fireEvent.change(screen.getByTestId('compose-embed-model'), { target: { value: 'e1' } });
}

beforeEach(() => {
  composeMock.mockClear();
  uploadsMock.items = [];
  uploadsMock.readyIds = [];
  uploadsMock.upload.mockClear();
  uploadsMock.remove.mockClear();
});

describe('ComposePanel (mode D)', () => {
  it('Run is disabled until a draft, a target name, and the GEN model are set (embed optional)', async () => {
    renderPanel();
    expect(screen.getByTestId('compose-run')).toBeDisabled();
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '碧遊宮' } });
    fireEvent.change(screen.getByTestId('compose-draft-text'), { target: { value: '通天教主道場。' } });
    await fillGen(); // gen only — no embed model picked
    expect(screen.getByTestId('compose-run')).not.toBeDisabled();
  });

  it('draft without an embed model omits embedding_model_ref (D-COMPOSE-S1-EMBED-REF)', async () => {
    renderPanel();
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '碧遊宮' } });
    fireEvent.change(screen.getByTestId('compose-draft-text'), { target: { value: '道場。' } });
    await fillGen();
    fireEvent.click(screen.getByTestId('compose-run'));
    const body = composeMock.mock.calls[0][0];
    expect(body.embedding_model_ref).toBeUndefined();
    expect(body.generation_model_ref).toBe('g1');
  });

  it('Run composes a draft body for an EXISTING target (target_ref = name)', async () => {
    renderPanel();
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '碧遊宮' } });
    fireEvent.change(screen.getByTestId('compose-draft-text'), { target: { value: '通天教主道場。' } });
    await fillModels();
    fireEvent.click(screen.getByTestId('compose-run'));

    expect(composeMock).toHaveBeenCalledTimes(1);
    const body = composeMock.mock.calls[0][0];
    expect(body).toMatchObject({
      input_source: 'draft',
      draft_text: '通天教主道場。',
      expand_mode: 'rewrite',
      generation_model_ref: 'g1',
      embedding_model_ref: 'e1',
      max_spend_usd: null,
      top_k: 5,
    });
    expect(body.target).toMatchObject({
      mode: 'existing',
      canonical_name: '碧遊宮',
      target_ref: '碧遊宮',
    });
  });

  it('a NEW target composes with target_ref=null (anchor minted at promote)', async () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('compose-target-mode-new'));
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '新天地' } });
    fireEvent.change(screen.getByTestId('compose-target-kind'), { target: { value: 'generic' } });
    fireEvent.change(screen.getByTestId('compose-draft-text'), { target: { value: '星際殖民地。' } });
    await fillModels();
    fireEvent.click(screen.getByTestId('compose-run'));

    const body = composeMock.mock.calls[0][0];
    expect(body.target).toMatchObject({
      mode: 'new',
      canonical_name: '新天地',
      entity_kind: 'generic',
      target_ref: null,
    });
  });

  it('clamps a cleared Top-K to a valid value and passes a real spend through', async () => {
    renderPanel();
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '碧遊宮' } });
    fireEvent.change(screen.getByTestId('compose-draft-text'), { target: { value: '道場。' } });
    await fillModels();
    // clear top-k (Number('')→0) and set a valid spend
    fireEvent.change(screen.getByTestId('compose-top-k'), { target: { value: '' } });
    fireEvent.change(screen.getByTestId('compose-max-spend'), { target: { value: '0.25' } });
    fireEvent.click(screen.getByTestId('compose-run'));
    const body = composeMock.mock.calls[0][0];
    expect(body.top_k).toBeGreaterThanOrEqual(1);
    expect(body.top_k).toBeLessThanOrEqual(20);
    expect(body.max_spend_usd).toBe(0.25);
  });

  it('add_only expand mode flows into the body', async () => {
    renderPanel();
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '碧遊宮' } });
    fireEvent.change(screen.getByTestId('compose-draft-text'), { target: { value: '道場。' } });
    fireEvent.click(screen.getByTestId('compose-expand-add_only'));
    await fillModels();
    fireEvent.click(screen.getByTestId('compose-run'));
    expect(composeMock.mock.calls[0][0].expand_mode).toBe('add_only');
  });
});

describe('ComposePanel (mode C — context)', () => {
  const toContext = () => fireEvent.click(screen.getByTestId('compose-mode-context'));

  it('Run requires text + target + gen + EMBED model (embed required for context)', async () => {
    renderPanel();
    toContext();
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '蓬萊' } });
    fireEvent.change(screen.getByTestId('compose-context-text'), { target: { value: '東海仙山。' } });
    await fillGen(); // gen only — embed still missing → blocked
    expect(screen.getByTestId('compose-run')).toBeDisabled();
    fireEvent.change(screen.getByTestId('compose-embed-model'), { target: { value: 'e1' } });
    expect(screen.getByTestId('compose-run')).not.toBeDisabled();
  });

  it('composes a context body (input_source context + license + embed + existing target)', async () => {
    renderPanel();
    toContext();
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '蓬萊' } });
    fireEvent.change(screen.getByTestId('compose-context-text'), { target: { value: '東海仙山。' } });
    await fillModels();
    fireEvent.click(screen.getByTestId('compose-run'));

    expect(composeMock).toHaveBeenCalledTimes(1);
    const body = composeMock.mock.calls[0][0];
    expect(body).toMatchObject({
      input_source: 'context',
      context_text: '東海仙山。',
      context_license: 'public_domain',
      generation_model_ref: 'g1',
      embedding_model_ref: 'e1',
    });
    expect(body.draft_text).toBeUndefined();
    expect(body.target).toMatchObject({ mode: 'existing', canonical_name: '蓬萊', target_ref: '蓬萊' });
  });

  it('a copyrighted license disables Run (default-deny in the UI)', async () => {
    renderPanel();
    toContext();
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '蓬萊' } });
    fireEvent.change(screen.getByTestId('compose-context-text'), { target: { value: '東海仙山。' } });
    await fillModels();
    expect(screen.getByTestId('compose-run')).not.toBeDisabled();
    fireEvent.change(screen.getByTestId('compose-context-license'), { target: { value: 'copyrighted' } });
    expect(screen.getByTestId('compose-run')).toBeDisabled();
    expect(screen.getByTestId('compose-context-copyright-warning')).toBeInTheDocument();
  });
});

describe('ComposePanel (mode F — files)', () => {
  const toFiles = () => fireEvent.click(screen.getByTestId('compose-mode-files'));

  it('Run needs ≥1 ready upload + target + gen + embed + responsibility checked', async () => {
    uploadsMock.readyIds = ['up-1'];
    uploadsMock.items = [{ id: 'up-1', filename: 'a.pdf', status: 'ready' }];
    renderPanel();
    toFiles();
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '蓬萊' } });
    await fillModels(); // gen + embed
    // still blocked until the responsibility box is ticked
    expect(screen.getByTestId('compose-run')).toBeDisabled();
    fireEvent.click(screen.getByTestId('compose-files-responsibility'));
    expect(screen.getByTestId('compose-run')).not.toBeDisabled();
  });

  it('composes a files body (input_source files + upload_ids from the ready uploads)', async () => {
    uploadsMock.readyIds = ['up-1', 'up-2'];
    uploadsMock.items = [
      { id: 'up-1', filename: 'a.pdf', status: 'ready' },
      { id: 'up-2', filename: 'b.docx', status: 'ready' },
    ];
    renderPanel();
    toFiles();
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '蓬萊' } });
    await fillModels();
    fireEvent.click(screen.getByTestId('compose-files-responsibility'));
    fireEvent.click(screen.getByTestId('compose-run'));

    const body = composeMock.mock.calls[0][0];
    expect(body).toMatchObject({
      input_source: 'files',
      upload_ids: ['up-1', 'up-2'],
      generation_model_ref: 'g1',
      embedding_model_ref: 'e1',
    });
    expect(body.target).toMatchObject({ canonical_name: '蓬萊' });
  });

  it('Run stays disabled with no ready uploads', async () => {
    uploadsMock.readyIds = [];
    renderPanel();
    toFiles();
    fireEvent.change(screen.getByTestId('compose-target-name'), { target: { value: '蓬萊' } });
    await fillModels();
    fireEvent.click(screen.getByTestId('compose-files-responsibility'));
    expect(screen.getByTestId('compose-run')).toBeDisabled();
  });
});
