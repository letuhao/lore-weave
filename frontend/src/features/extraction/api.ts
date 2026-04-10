import { apiJson } from '../../api';
import type {
  ExtractionProfileResponse,
  ExtractionJobRequest,
  ExtractionJobCreated,
  ExtractionJobStatus,
  CancelJobResponse,
} from './types';

const GLOSSARY = '/v1/glossary';
const EXTRACTION = '/v1/extraction';

export const extractionApi = {
  /** Fetch extraction profile (auto-resolved kinds + attributes by genre). */
  getProfile(bookId: string, token: string): Promise<ExtractionProfileResponse> {
    return apiJson<ExtractionProfileResponse>(
      `${GLOSSARY}/books/${bookId}/extraction-profile`,
      { token },
    );
  },

  /** Create an extraction job. Returns 202 with job_id + cost estimate. */
  startJob(bookId: string, body: ExtractionJobRequest, token: string): Promise<ExtractionJobCreated> {
    return apiJson<ExtractionJobCreated>(
      `${EXTRACTION}/books/${bookId}/extract-glossary`,
      { method: 'POST', body: JSON.stringify(body), token },
    );
  },

  /** Poll job status with chapter-level results. */
  getJobStatus(jobId: string, token: string): Promise<ExtractionJobStatus> {
    return apiJson<ExtractionJobStatus>(
      `${EXTRACTION}/jobs/${jobId}`,
      { token },
    );
  },

  /** Cancel a running or pending extraction job. */
  cancelJob(jobId: string, token: string): Promise<CancelJobResponse> {
    return apiJson<CancelJobResponse>(
      `${EXTRACTION}/jobs/${jobId}/cancel`,
      { method: 'POST', token },
    );
  },
};
