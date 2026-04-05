import type { JSONContent } from '@tiptap/react';

interface VideoBlockProps {
  node: JSONContent;
}

export function VideoBlock({ node }: VideoBlockProps) {
  const src = node.attrs?.src as string | null;
  const caption = (node.attrs?.caption as string) || '';
  const width = (node.attrs?.width as number) || 100;

  if (!src) {
    return (
      <figure className="block-video">
        <div className="video-wrapper block-video-empty">
          <svg width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" opacity="0.3">
            <rect x="2" y="4" width="20" height="16" rx="2" />
            <path d="M8 10l6 4-6 4V10z" />
          </svg>
          <span>Video not available</span>
        </div>
        {caption && <figcaption>{caption}</figcaption>}
      </figure>
    );
  }

  return (
    <figure className="block-video" style={{ maxWidth: `${width}%` }}>
      <div className="video-wrapper">
        <video controls preload="metadata">
          <source src={src} />
        </video>
      </div>
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  );
}
