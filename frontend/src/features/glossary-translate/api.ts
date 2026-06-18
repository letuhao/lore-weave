import { apiJson } from '../../api';
import type {
  GlossaryTranslateJobRequest,
  GlossaryTranslateJobCreated,
  GlossaryTranslateJobStatus,
  CancelJobResponse,
} from './types';

const BASE = '/v1/glossary-translate';

export const glossaryTranslateApi = {
  startJob(bookId: string, body: GlossaryTranslateJobRequest, token: string): Promise<GlossaryTranslateJobCreated> {
    return apiJson<GlossaryTranslateJobCreated>(
      `${BASE}/books/${bookId}/translate`,
      { method: 'POST', body: JSON.stringify(body), token },
    );
  },

  getJobStatus(jobId: string, token: string): Promise<GlossaryTranslateJobStatus> {
    return apiJson<GlossaryTranslateJobStatus>(`${BASE}/jobs/${jobId}`, { token });
  },

  cancelJob(jobId: string, token: string): Promise<CancelJobResponse> {
    return apiJson<CancelJobResponse>(`${BASE}/jobs/${jobId}/cancel`, { method: 'POST', token });
  },
};
