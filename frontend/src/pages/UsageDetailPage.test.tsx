import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { UsageDetailPage } from './UsageDetailPage';

const getUsageLogDetail = vi.fn();

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'token-1' }),
}));

vi.mock('@/features/ai-models/api', () => ({
  aiModelsApi: {
    getUsageLogDetail: (...args: unknown[]) => getUsageLogDetail(...args),
  },
}));

describe('UsageDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  function renderPage() {
    return render(
      <MemoryRouter initialEntries={['/m03/usage/log-1']}>
        <Routes>
          <Route path="/m03/usage/:usageLogId" element={<UsageDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it('renders forbidden error state', async () => {
    getUsageLogDetail.mockRejectedValueOnce(new Error('forbidden'));
    renderPage();
    expect(await screen.findByText('forbidden')).toBeInTheDocument();
  });

  it('renders ciphertext-unavailable secure failure state', async () => {
    getUsageLogDetail.mockRejectedValueOnce(new Error('ciphertext unavailable'));
    renderPage();
    expect(await screen.findByText('ciphertext unavailable')).toBeInTheDocument();
  });

  it('renders decrypted input/output payloads', async () => {
    getUsageLogDetail.mockResolvedValueOnce({
      usage_log: {
        provider_kind: 'openai',
        request_status: 'success',
        total_tokens: 100,
        billing_decision: 'quota',
      },
      input_payload: { prompt: 'hello' },
      output_payload: { result: 'world' },
      viewed_at: '2026-03-22T00:00:00.000Z',
    });
    renderPage();
    expect(await screen.findByText(/Provider:/)).toBeInTheDocument();
    expect(await screen.findByText(/"prompt": "hello"/)).toBeInTheDocument();
    expect(await screen.findByText(/"result": "world"/)).toBeInTheDocument();
  });
});
