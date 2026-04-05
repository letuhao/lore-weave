import { useRef, useEffect, useState } from 'react';
import type { JSONContent } from '@tiptap/react';

interface ImageBlockProps {
  node: JSONContent;
}

export function ImageBlock({ node }: ImageBlockProps) {
  const src = node.attrs?.src as string | null;
  const alt = (node.attrs?.alt as string) || '';
  const caption = (node.attrs?.caption as string) || '';
  const width = (node.attrs?.width as number) || 100;

  const imgRef = useRef<HTMLImageElement>(null);
  const [loaded, setLoaded] = useState(false);

  // Lazy loading via IntersectionObserver
  useEffect(() => {
    const img = imgRef.current;
    if (!img || !src) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          img.src = src;
          observer.disconnect();
        }
      },
      { rootMargin: '200px' },
    );
    observer.observe(img);
    return () => observer.disconnect();
  }, [src]);

  if (!src) {
    return (
      <figure className="block-image">
        <div className="block-image-empty">
          <svg width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" opacity="0.3">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
          <span>Image not available</span>
        </div>
        {caption && <figcaption>{caption}</figcaption>}
      </figure>
    );
  }

  return (
    <figure className="block-image" style={{ maxWidth: `${width}%` }}>
      <div style={{ position: 'relative' }}>
        <img
          ref={imgRef}
          alt={alt}
          onLoad={() => setLoaded(true)}
          style={{ opacity: loaded ? 1 : 0, transition: 'opacity 200ms' }}
        />
        <div className="zoom-hint">
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
          </svg>
        </div>
      </div>
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  );
}
