import type { CSSProperties, MouseEvent, RefObject, ReactNode } from 'react';
import { useMediaAuthUrl } from '@/hooks/useMediaAuthUrl';

type AuthMediaProps = {
  url: string | null | undefined;
  accessToken: string | null | undefined;
};

export function AuthenticatedMediaImg({
  url,
  accessToken,
  alt,
  className,
  onLoad,
  imgRef,
  style,
}: AuthMediaProps & {
  alt: string;
  className?: string;
  onLoad?: () => void;
  imgRef?: RefObject<HTMLImageElement | null>;
  style?: CSSProperties;
}) {
  const src = useMediaAuthUrl(url, accessToken);
  if (!src) return null;
  return (
    <img
      ref={imgRef}
      src={src}
      alt={alt}
      className={className}
      onLoad={onLoad}
      style={style}
    />
  );
}

export function AuthenticatedMediaAudio({
  url,
  accessToken,
  audioRef,
  onEnded,
  preload,
  className,
}: AuthMediaProps & {
  audioRef?: RefObject<HTMLAudioElement | null>;
  onEnded?: () => void;
  preload?: 'none' | 'metadata' | 'auto';
  className?: string;
}) {
  const src = useMediaAuthUrl(url, accessToken);
  if (!src) return null;
  return (
    <audio
      ref={audioRef}
      src={src}
      preload={preload}
      className={className}
      onEnded={onEnded}
    />
  );
}

export function AuthenticatedMediaLink({
  url,
  accessToken,
  children,
  className,
  download,
  onClick,
}: AuthMediaProps & {
  children: ReactNode;
  className?: string;
  download?: boolean;
  onClick?: (e: MouseEvent) => void;
}) {
  const href = useMediaAuthUrl(url, accessToken);
  if (!href) return null;
  return (
    <a href={href} className={className} download={download} onClick={onClick}>
      {children}
    </a>
  );
}
