import type { JSONContent } from '@tiptap/react';
import { ParagraphBlock } from './blocks/ParagraphBlock';
import { HeadingBlock } from './blocks/HeadingBlock';
import { ImageBlock } from './blocks/ImageBlock';
import { VideoBlock } from './blocks/VideoBlock';
import { CodeBlock } from './blocks/CodeBlock';
import { CalloutBlock } from './blocks/CalloutBlock';
import { BlockquoteBlock } from './blocks/BlockquoteBlock';
import { ListBlock } from './blocks/ListBlock';
import { HorizontalRuleBlock } from './blocks/HorizontalRuleBlock';
import { cn } from '@/lib/utils';

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
      // Debug fallback — shows unknown block type in development
      return (
        <pre className="block-unknown">
          {JSON.stringify(node, null, 2)}
        </pre>
      );
  }
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

        return (
          <div
            key={blockId}
            data-block-id={blockId}
            className={cn(
              'content-block',
              isActive && 'tts-active',
              onBlockClick && 'tts-clickable',
            )}
            onClick={onBlockClick ? () => onBlockClick(blockId) : undefined}
          >
            {showIndices && <span className="block-index">{i}</span>}
            {renderBlockContent(node)}
          </div>
        );
      })}

      {isTruncated && (
        <div className="content-renderer-fade" />
      )}
    </div>
  );
}
