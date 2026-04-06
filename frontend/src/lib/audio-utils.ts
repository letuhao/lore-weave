import type { JSONContent } from '@tiptap/react';

export type AudioSource = 'attached' | 'ai' | 'browser' | 'inline';

export interface SpeakableBlock {
  blockId: string;
  index: number;
  /** 'text' for paragraph/heading/etc, 'audio' for audioBlock */
  type: 'text' | 'audio';
  /** Plain text for TTS (empty for audioBlock) */
  text: string;
  /** Attached audio URL (from block attrs) */
  audioUrl: string | null;
  /** Audio source type from block attrs */
  audioSource: string | null;
  /** Subtitle for audioBlock */
  subtitle: string | null;
}

const TEXT_BLOCK_TYPES = new Set(['paragraph', 'heading', 'blockquote', 'callout']);
const SKIP_BLOCK_TYPES = new Set(['imageBlock', 'videoBlock', 'horizontalRule']);

/** Recursively extract plain text from Tiptap JSON content */
function extractPlainText(content?: JSONContent[]): string {
  if (!content) return '';
  return content.map((n) => {
    if (n.type === 'text') return n.text || '';
    if (n.type === 'hardBreak') return '\n';
    return extractPlainText(n.content);
  }).join('');
}

/**
 * Extract ordered list of speakable blocks for the playback engine.
 * Skips image, video, and horizontal rule blocks.
 * audioBlocks are returned with type 'audio' for inline playback.
 */
export function extractSpeakableBlocks(blocks: JSONContent[]): SpeakableBlock[] {
  const result: SpeakableBlock[] = [];

  for (let i = 0; i < blocks.length; i++) {
    const node = blocks[i];
    const blockId = `block-${i}`;

    if (!node.type || SKIP_BLOCK_TYPES.has(node.type)) continue;

    if (node.type === 'audioBlock') {
      result.push({
        blockId,
        index: i,
        type: 'audio',
        text: '',
        audioUrl: (node.attrs?.src as string) || null,
        audioSource: 'inline',
        subtitle: (node.attrs?.subtitle as string) || null,
      });
      continue;
    }

    if (TEXT_BLOCK_TYPES.has(node.type)) {
      const text = extractPlainText(node.content).trim();
      if (!text) continue; // skip empty paragraphs

      result.push({
        blockId,
        index: i,
        type: 'text',
        text,
        audioUrl: (node.attrs?.audio_url as string) || null,
        audioSource: (node.attrs?.audio_source as string) || null,
        subtitle: (node.attrs?.audio_subtitle as string) || null,
      });
      continue;
    }

    // Lists — extract all text as one block
    if (node.type === 'bulletList' || node.type === 'orderedList') {
      const text = extractPlainText(node.content).trim();
      if (!text) continue;
      result.push({
        blockId,
        index: i,
        type: 'text',
        text,
        audioUrl: null,
        audioSource: null,
        subtitle: null,
      });
      continue;
    }

    // codeBlock — extract as text (may be spoken in full)
    if (node.type === 'codeBlock') {
      const text = extractPlainText(node.content).trim();
      if (!text) continue;
      result.push({
        blockId,
        index: i,
        type: 'text',
        text,
        audioUrl: null,
        audioSource: null,
        subtitle: null,
      });
    }
  }

  return result;
}

/**
 * Resolve the audio source for a speakable block.
 * Priority: 1. Attached audio → 2. AI TTS segments → 3. Browser TTS → 4. Skip
 */
export function resolveAudioSource(
  block: SpeakableBlock,
  aiSegments?: Map<number, string>, // block_index → audio URL
): { source: AudioSource; url: string | null } {
  // audioBlock plays inline
  if (block.type === 'audio') {
    return { source: 'inline', url: block.audioUrl };
  }

  // 1. Attached audio on text block
  if (block.audioUrl) {
    return { source: 'attached', url: block.audioUrl };
  }

  // 2. AI TTS segment
  const aiUrl = aiSegments?.get(block.index);
  if (aiUrl) {
    return { source: 'ai', url: aiUrl };
  }

  // 3. Browser TTS fallback (no URL — engine uses text directly)
  if (block.text) {
    return { source: 'browser', url: null };
  }

  // 4. Nothing to play
  return { source: 'browser', url: null };
}
