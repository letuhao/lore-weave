import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import { createLowlight } from 'lowlight';

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

/**
 * CodeBlock extension with lowlight syntax highlighting.
 *
 * No custom NodeView — uses Tiptap's built-in <pre><code> rendering.
 * This avoids all React/ProseMirror DOM conflicts (focus, whitespace, paste).
 *
 * The header bar (language selector, copy button) is styled via CSS
 * using the `language-*` class that CodeBlockLowlight adds to <code>.
 * A floating toolbar can be added later via a separate Tiptap plugin.
 */
export const CodeBlockExtension = CodeBlockLowlight.configure({
  lowlight,
  defaultLanguage: 'plaintext',
});
