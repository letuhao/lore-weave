import type { JSONContent } from '@tiptap/react';

interface AudioBlockProps {
  node: JSONContent;
}

function formatDuration(ms: number): string {
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function AudioBlock({ node }: AudioBlockProps) {
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
          <span>Audio not available</span>
        </div>
      </figure>
    );
  }

  return (
    <figure className="block-audio">
      <div className="audio-player">
        <audio controls preload="metadata" src={src}>
          Your browser does not support the audio element.
        </audio>
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
