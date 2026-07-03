import { describe, it, expect, vi, beforeEach } from 'vitest';

// W3 — chatApi.compactSession wire mapping (URL, method, body shape).

const apiJsonMock = vi.fn();
vi.mock('@/api', () => ({
  apiJson: (...a: unknown[]) => apiJsonMock(...a),
  apiBase: () => '',
}));

import { chatApi } from '../api';

describe('chatApi.compactSession', () => {
  beforeEach(() => apiJsonMock.mockReset());

  it('POSTs instructions + keep_recent to the compact route', async () => {
    apiJsonMock.mockResolvedValue({ compacted_before_seq: 5 });
    await chatApi.compactSession('tok', 's-1', { instructions: 'keep names', keep_recent: 4 });
    expect(apiJsonMock).toHaveBeenCalledWith('/v1/chat/sessions/s-1/compact', {
      method: 'POST',
      token: 'tok',
      body: JSON.stringify({ instructions: 'keep names', keep_recent: 4 }),
    });
  });

  it('defaults to an empty body (server picks keep_recent default)', async () => {
    apiJsonMock.mockResolvedValue({});
    await chatApi.compactSession('tok', 's-1');
    expect(apiJsonMock).toHaveBeenCalledWith('/v1/chat/sessions/s-1/compact', {
      method: 'POST',
      token: 'tok',
      body: '{}',
    });
  });
});
