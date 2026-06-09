import type { JSONContent } from '@tiptap/react';
import { useTranslation } from 'react-i18next';
import { AuthenticatedMediaAudio } from '@/components/media/AuthenticatedMedia';

interface AudioBlockProps {
  node: JSONContent;
  accessToken?: string | null;
}

function formatDuration(ms: number): string {
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function AudioBlock({ node, accessToken }: AudioBlockProps) {
  const { t } = useTranslation('reader');
  const src = node.attrs?.src as string | null;
  const subtitle = (node.attrs?.subtitle as string) || '';
  const title = (node.attrs?.title as string) || '';
  const durationMs = node.attrs?.duration_ms as number | null;

  if (!src) {
    return (
      <figure className="block-audio">
        <div className="audio-empty">
          <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" opacity="0.3">
            <path d="M9 18V5l12-2v13" />
            <circle cx="6" cy="18" r="3" />
            <circle cx="18" cy="16" r="3" />
          </svg>
          <span>{t('block.audio_unavailable')}</span>
        </div>
      </figure>
    );
  }

  return (
    <figure className="block-audio">
      <div className="audio-player">
        <AuthenticatedMediaAudio url={src} accessToken={accessToken} preload="metadata" />
        {(durationMs != null || title) && (
          <div className="audio-meta">
            {durationMs != null && <span>{formatDuration(durationMs)}</span>}
            {title && <span className="audio-title">{title}</span>}
          </div>
        )}
      </div>
      {subtitle && <figcaption>{subtitle}</figcaption>}
    </figure>
  );
}
