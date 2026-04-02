import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  NodeViewContent,
  type NodeViewProps,
} from '@tiptap/react';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import { createLowlight } from 'lowlight';
import { useState, useCallback } from 'react';
import { cn } from '@/lib/utils';

// --- Language imports (tree-shakeable, not `common`) ---
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import python from 'highlight.js/lib/languages/python';
import go from 'highlight.js/lib/languages/go';
import rust from 'highlight.js/lib/languages/rust';
import jsonLang from 'highlight.js/lib/languages/json';
import yaml from 'highlight.js/lib/languages/yaml';
import markdown from 'highlight.js/lib/languages/markdown';
import xml from 'highlight.js/lib/languages/xml'; // covers HTML
import css from 'highlight.js/lib/languages/css';
import sql from 'highlight.js/lib/languages/sql';
import bash from 'highlight.js/lib/languages/bash';

// --- Lowlight instance ---
const lowlight = createLowlight();
lowlight.register('javascript', javascript);
lowlight.register('typescript', typescript);
lowlight.register('python', python);
lowlight.register('go', go);
lowlight.register('rust', rust);
lowlight.register('json', jsonLang);
lowlight.register('yaml', yaml);
lowlight.register('markdown', markdown);
lowlight.register('html', xml);
lowlight.register('css', css);
lowlight.register('sql', sql);
lowlight.register('bash', bash);

export { lowlight };

// --- Language list for the selector ---
export const CODE_LANGUAGES = [
  { value: 'plaintext', label: 'Plain Text' },
  { value: 'javascript', label: 'JavaScript' },
  { value: 'typescript', label: 'TypeScript' },
  { value: 'python', label: 'Python' },
  { value: 'go', label: 'Go' },
  { value: 'rust', label: 'Rust' },
  { value: 'json', label: 'JSON' },
  { value: 'yaml', label: 'YAML' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'html', label: 'HTML' },
  { value: 'css', label: 'CSS' },
  { value: 'sql', label: 'SQL' },
  { value: 'bash', label: 'Bash' },
] as const;

// --- NodeView component ---
// Key: NodeViewContent MUST render as <pre> to preserve whitespace on paste.
// The type says as="div" only but runtime accepts any string tag.
function CodeBlockNodeView({ node, updateAttributes, editor }: NodeViewProps) {
  const editorMode = ((editor.storage as any).mediaGuard?.editorMode as string) || 'ai';
  const isClassic = editorMode === 'classic';
  const language = (node.attrs.language as string) || 'plaintext';
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(node.textContent).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => {},
    );
  }, [node.textContent]);

  const handleLanguageChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      updateAttributes({ language: e.target.value });
    },
    [updateAttributes],
  );

  // --- Classic mode: compact locked placeholder ---
  if (isClassic) {
    return (
      <NodeViewWrapper className="code-block-wrapper code-block-wrapper--classic">
        <div className="code-block-classic">
          <span className="code-block-classic-icon">&lt;/&gt;</span>
          <span className="code-block-classic-label">Code Block</span>
          <span className="code-block-classic-lang">{language}</span>
          <span className="code-block-classic-lock">🔒 AI mode</span>
        </div>
        {/* Hidden but preserved content — NodeViewContent must always be in DOM */}
        <NodeViewContent style={{ display: 'none' }} />
      </NodeViewWrapper>
    );
  }

  return (
    <NodeViewWrapper className="code-block-wrapper">
      {/* Header bar — not editable */}
      <div className="code-block-header" contentEditable={false}>
        <select
          value={language}
          onChange={handleLanguageChange}
          aria-label="Code language"
          className="code-block-lang"
        >
          {CODE_LANGUAGES.map((lang) => (
            <option key={lang.value} value={lang.value}>
              {lang.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={handleCopy}
          className={cn('code-block-copy', copied && 'code-block-copy--copied')}
          title="Copy code"
        >
          {copied ? '✓ Copied' : '⧉ Copy'}
        </button>
      </div>

      {/* Code content — contentDOMElementTag='pre' in ReactNodeViewRenderer
          makes ProseMirror use a real <pre> as contentDOM */}
      <NodeViewContent className="code-block-pre" />
    </NodeViewWrapper>
  );
}

// --- Tiptap extension ---
export const CodeBlockExtension = CodeBlockLowlight.extend({
  addNodeView() {
    return ReactNodeViewRenderer(CodeBlockNodeView, {
      contentDOMElementTag: 'pre',
    });
  },
}).configure({
  lowlight,
  defaultLanguage: 'plaintext',
});
