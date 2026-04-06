import { useState, useRef, useCallback } from 'react';
import type { JSONContent } from '@tiptap/react';
import './reader.css';
import { ParagraphBlock } from './blocks/ParagraphBlock';
import { HeadingBlock } from './blocks/HeadingBlock';
import { ImageBlock } from './blocks/ImageBlock';
import { VideoBlock } from './blocks/VideoBlock';
import { AudioBlock } from './blocks/AudioBlock';
import { CodeBlock } from './blocks/CodeBlock';
import { CalloutBlock } from './blocks/CalloutBlock';
import { BlockquoteBlock } from './blocks/BlockquoteBlock';
import { ListBlock } from './blocks/ListBlock';
import { HorizontalRuleBlock } from './blocks/HorizontalRuleBlock';
import { cn } from '@/lib/utils';

const TEXT_BLOCK_TYPES = new Set(['paragraph', 'heading', 'blockquote', 'callout']);

interface ContentRendererProps {
  /** doc.content array from Tiptap JSON */
  blocks: JSONContent[];
  /** 'full' for reader page, 'compact' for panels/embeds */
  mode?: 'full' | 'compact';
  /** Block id to highlight (TTS sync — gold left border) */
  ttsActiveBlock?: string;
  /** Show block index numbers (translator mode) */
  showIndices?: boolean;
  /** Limit number of blocks shown (embedded preview) */
  maxBlocks?: number;
  /** Click handler for block selection (TTS jump, etc.) */
  onBlockClick?: (blockId: string) => void;
  className?: string;
}

/** Recursively extract plain text from Tiptap JSON content */
function extractPlainText(content?: JSONContent[]): string {
  if (!content) return '';
  return content.map((n) => {
    if (n.type === 'text') return n.text || '';
    if (n.type === 'hardBreak') return '\n';
    return extractPlainText(n.content);
  }).join('');
}

function normalize(s: string): string {
  return s.replace(/\s+/g, ' ').trim().toLowerCase();
}

/** Render the inner content for a single block based on its type. */
function renderBlockContent(node: JSONContent) {
  switch (node.type) {
    case 'paragraph':
      return <ParagraphBlock node={node} />;
    case 'heading':
      return <HeadingBlock node={node} />;
    case 'imageBlock':
      return <ImageBlock node={node} />;
    case 'videoBlock':
      return <VideoBlock node={node} />;
    case 'audioBlock':
      return <AudioBlock node={node} />;
    case 'codeBlock':
      return <CodeBlock node={node} />;
    case 'callout':
      return <CalloutBlock node={node} />;
    case 'blockquote':
      return <BlockquoteBlock node={node} />;
    case 'bulletList':
    case 'orderedList':
      return <ListBlock node={node} />;
    case 'horizontalRule':
      return <HorizontalRuleBlock />;
    default:
      return (
        <pre className="block-unknown">
          {JSON.stringify(node, null, 2)}
        </pre>
      );
  }
}

/** Inline play button for text blocks with attached audio */
function AudioIndicator({ audioUrl, audioSource, audioSubtitle, blockText }: {
  audioUrl: string;
  audioSource: string | null;
  audioSubtitle: string | null;
  blockText: string;
}) {
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const hasMismatch = audioSubtitle != null && audioSubtitle.trim() !== '' &&
    blockText.trim() !== '' && normalize(blockText) !== normalize(audioSubtitle);

  const toggle = useCallback(() => {
    if (!audioRef.current) {
      audioRef.current = new Audio(audioUrl);
      audioRef.current.addEventListener('ended', () => setPlaying(false));
    }
    if (playing) {
      audioRef.current.pause();
      setPlaying(false);
    } else {
      audioRef.current.play();
      setPlaying(true);
    }
  }, [audioUrl, playing]);

  const sourceLabel = audioSource || 'audio';

  return (
    <span className="reader-audio-indicator" onClick={(e) => { e.stopPropagation(); toggle(); }}>
      <button
        type="button"
        className={cn('reader-inline-play', playing && 'playing')}
        title={playing ? 'Pause' : 'Play attached audio'}
      >
        {playing ? '⏸' : '▶'}
      </button>
      <span className={cn('reader-audio-badge', audioSource || 'uploaded')}>
        {sourceLabel}
      </span>
      {hasMismatch && (
        <span className="reader-audio-mismatch" title="Audio subtitle differs from block text">⚠</span>
      )}
    </span>
  );
}

/**
 * Renders Tiptap JSON blocks as pure React components.
 * No Tiptap editor instance created — lightweight display-only.
 *
 * Used by: ReaderPage, RevisionHistory, TranslationReview, BookDetailPage excerpts.
 */
export function ContentRenderer({
  blocks,
  mode = 'full',
  ttsActiveBlock,
  showIndices = false,
  maxBlocks,
  onBlockClick,
  className,
}: ContentRendererProps) {
  const visibleBlocks = maxBlocks != null ? blocks.slice(0, maxBlocks) : blocks;
  const isTruncated = maxBlocks != null && blocks.length > maxBlocks;

  return (
    <div
      className={cn(
        mode === 'full' ? 'content-renderer' : 'content-renderer-compact',
        showIndices && 'show-indices',
        className,
      )}
    >
      {visibleBlocks.map((node, i) => {
        const blockId = `block-${i}`;
        const isActive = ttsActiveBlock === blockId;
        const audioUrl = node.attrs?.audio_url as string | null;
        const hasAudio = !!audioUrl && TEXT_BLOCK_TYPES.has(node.type || '');

        return (
          <div
            key={blockId}
            data-block-id={blockId}
            className={cn(
              'content-block',
              isActive && 'tts-active',
              onBlockClick && 'tts-clickable',
              hasAudio && 'has-audio',
            )}
            onClick={onBlockClick ? () => onBlockClick(blockId) : undefined}
          >
            {showIndices && <span className="block-index">{i}</span>}
            {renderBlockContent(node)}
            {hasAudio && (
              <AudioIndicator
                audioUrl={audioUrl!}
                audioSource={node.attrs?.audio_source as string | null}
                audioSubtitle={node.attrs?.audio_subtitle as string | null}
                blockText={extractPlainText(node.content)}
              />
            )}
          </div>
        );
      })}

      {isTruncated && (
        <div className="content-renderer-fade" />
      )}
    </div>
  );
}
