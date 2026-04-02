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

// --- Tiptap extension with native DOM NodeView (not React) ---
// Using native NodeView preserves <pre><code> structure which is essential
// for whitespace handling, paste behavior, and lowlight decorations.
export const CodeBlockExtension = CodeBlockLowlight.extend({
  addNodeView() {
    return ({ node, getPos, editor }) => {
      // Outer wrapper
      const wrapper = document.createElement('div');
      wrapper.classList.add('code-block-wrapper');

      // Header bar (non-editable)
      const header = document.createElement('div');
      header.classList.add('code-block-header');
      header.contentEditable = 'false';

      // Language selector
      const select = document.createElement('select');
      select.classList.add('code-block-lang');
      select.setAttribute('aria-label', 'Code language');
      CODE_LANGUAGES.forEach((lang) => {
        const opt = document.createElement('option');
        opt.value = lang.value;
        opt.textContent = lang.label;
        select.appendChild(opt);
      });
      select.value = node.attrs.language || 'plaintext';
      select.addEventListener('change', () => {
        if (typeof getPos === 'function') {
          const pos = getPos();
          if (pos != null) {
            editor.chain().focus().command(({ tr }) => {
              tr.setNodeMarkup(pos, undefined, { ...node.attrs, language: select.value });
              return true;
            }).run();
          }
        }
      });

      // Copy button
      const copyBtn = document.createElement('button');
      copyBtn.type = 'button';
      copyBtn.classList.add('code-block-copy');
      copyBtn.title = 'Copy code';
      copyBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg> Copy';
      copyBtn.addEventListener('click', () => {
        const text = contentEl.textContent || '';
        navigator.clipboard.writeText(text).then(() => {
          copyBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Copied';
          setTimeout(() => {
            copyBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg> Copy';
          }, 1500);
        }, () => {});
      });

      header.appendChild(select);
      header.appendChild(copyBtn);

      // Content: <pre><code> — this is where ProseMirror puts the text
      const pre = document.createElement('pre');
      pre.classList.add('code-block-pre');
      const contentEl = document.createElement('code');
      contentEl.classList.add('code-block-code');
      pre.appendChild(contentEl);

      // Classic mode placeholder (hidden by default)
      const classicPlaceholder = document.createElement('div');
      classicPlaceholder.classList.add('code-block-classic');
      classicPlaceholder.innerHTML = `<span class="code-block-classic-icon">&lt;/&gt;</span><span class="code-block-classic-label">Code Block</span><span class="code-block-classic-lang"></span><span class="code-block-classic-lock">🔒 AI mode</span>`;
      classicPlaceholder.style.display = 'none';

      wrapper.appendChild(header);
      wrapper.appendChild(pre);
      wrapper.appendChild(classicPlaceholder);

      const syncMode = () => {
        const mode = (editor.storage as any).mediaGuard?.editorMode || 'ai';
        const isClassic = mode === 'classic';
        header.style.display = isClassic ? 'none' : '';
        pre.style.display = isClassic ? 'none' : '';
        classicPlaceholder.style.display = isClassic ? '' : 'none';
        wrapper.classList.toggle('code-block-wrapper--classic', isClassic);
        const langEl = classicPlaceholder.querySelector('.code-block-classic-lang');
        if (langEl) langEl.textContent = select.value;
      };
      syncMode();

      return {
        dom: wrapper,
        contentDOM: contentEl,
        update(updatedNode) {
          if (updatedNode.type.name !== 'codeBlock') return false;
          select.value = updatedNode.attrs.language || 'plaintext';
          syncMode();
          return true;
        },
      };
    };
  },
}).configure({
  lowlight,
  defaultLanguage: 'plaintext',
});
