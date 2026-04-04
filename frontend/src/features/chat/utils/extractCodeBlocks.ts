import type { ChatOutput } from '../types';

const CODE_BLOCK_RE = /```(\w*)\n([\s\S]*?)```/g;

/**
 * Extract fenced code blocks from assistant markdown text
 * and return them as ChatOutput-shaped objects for OutputCard rendering.
 */
export function extractCodeBlocks(text: string, messageId: string): ChatOutput[] {
  const results: ChatOutput[] = [];
  let match: RegExpExecArray | null;
  let idx = 0;

  while ((match = CODE_BLOCK_RE.exec(text)) !== null) {
    const lang = match[1] || null;
    const code = match[2];
    results.push({
      output_id: `${messageId}-code-${idx}`,
      message_id: messageId,
      session_id: '',
      owner_user_id: '',
      output_type: 'code',
      title: lang ? `Code (${lang})` : 'Code block',
      content_text: code,
      language: lang,
      storage_key: null,
      mime_type: null,
      file_name: null,
      file_size_bytes: null,
      metadata: null,
      created_at: '',
    });
    idx++;
  }

  return results;
}
