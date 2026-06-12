import { useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { enrichmentApi } from '../api';
import type { ContextLicense, UploadResult, UploadStatus } from '../types';

/** One file in the dropzone: starts `processing`, polled to `ready`/`failed`. */
export interface UploadItem {
  id: string; // temp id until the server upload_id arrives, then the upload_id
  filename: string;
  status: UploadStatus;
  result?: UploadResult;
  error?: string;
}

const POLL_INTERVAL_MS = 1500;
const POLL_MAX = 60; // ~90s — a large scan's OCR can be slow (F10)
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Mode-F uploads controller: upload each file (multipart) then poll its extraction
 *  to ready/failed. Exposes the items (for status badges) + the ready upload_ids the
 *  compose run consumes. The license is asserted per upload (default-deny on the BE).
 */
export function useUploads(bookId: string) {
  const { accessToken } = useAuth();
  const [items, setItems] = useState<UploadItem[]>([]);
  const seq = useRef(0);

  const upload = async (file: File, license: ContextLicense) => {
    const tmpId = `tmp-${seq.current++}`;
    setItems((prev) => [...prev, { id: tmpId, filename: file.name, status: 'processing' }]);
    try {
      const created = await enrichmentApi.uploadFile(bookId, file, license, accessToken!);
      // adopt the server upload_id, then poll until extraction settles.
      setItems((prev) => prev.map((it) => (it.id === tmpId ? { ...it, id: created.upload_id } : it)));
      let latest = created;
      for (let i = 0; i < POLL_MAX && latest.status === 'processing'; i++) {
        await sleep(POLL_INTERVAL_MS);
        latest = await enrichmentApi.getUpload(created.upload_id, accessToken!);
      }
      setItems((prev) =>
        prev.map((it) =>
          it.id === created.upload_id
            ? { id: created.upload_id, filename: file.name, status: latest.status, result: latest, error: latest.error ?? undefined }
            : it,
        ),
      );
    } catch (e) {
      setItems((prev) =>
        prev.map((it) => (it.id === tmpId ? { ...it, status: 'failed' as UploadStatus, error: (e as Error).message } : it)),
      );
    }
  };

  const remove = (id: string) => setItems((prev) => prev.filter((it) => it.id !== id));
  // Only ready uploads with extractable text count toward a run — a ready-but-empty
  // file (e.g. a blank scan, OCR off) grounds nothing and the BE would 422 on it
  // (review-impl #3). The form still shows it (flagged), it just can't enable Run.
  const readyIds = items
    .filter((it) => it.status === 'ready' && (it.result?.extracted_chars ?? 0) > 0)
    .map((it) => it.id);

  return { items, upload, remove, readyIds };
}
