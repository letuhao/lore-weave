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
 * Uses a pure ProseMirror NodeView (no React) to avoid focus/whitespace issues.
 * The header bar (language selector + copy button) is injected as DOM above the
 * native <pre><code> content area.
 */
export const CodeBlockExtension = CodeBlockLowlight.extend({
  addNodeView() {
    return ({ node, getPos, editor }) => {
      const wrapper = document.createElement('div');
      wrapper.classList.add('code-block-wrapper');

      // --- Header bar ---
      const header = document.createElement('div');
      header.classList.add('code-block-header');
      header.contentEditable = 'false';

      const select = document.createElement('select');
      select.classList.add('code-block-lang');
      select.setAttribute('aria-label', 'Code language');
      for (const lang of CODE_LANGUAGES) {
        const opt = document.createElement('option');
        opt.value = lang.value;
        opt.textContent = lang.label;
        select.appendChild(opt);
      }
      select.value = node.attrs.language || 'plaintext';
      select.addEventListener('change', () => {
        if (typeof getPos !== 'function') return;
        const pos = getPos();
        if (pos == null) return;
        editor.view.dispatch(
          editor.state.tr.setNodeMarkup(pos, undefined, {
            ...node.attrs,
            language: select.value,
          }),
        );
      });
      // Prevent ProseMirror from handling select interactions
      select.addEventListener('mousedown', (e) => e.stopPropagation());

      const copyBtn = document.createElement('button');
      copyBtn.type = 'button';
      copyBtn.classList.add('code-block-copy');
      copyBtn.title = 'Copy code';
      copyBtn.textContent = '⧉ Copy';
      copyBtn.addEventListener('mousedown', (e) => e.preventDefault()); // prevent focus steal
      copyBtn.addEventListener('click', () => {
        const text = codeEl.textContent || '';
        navigator.clipboard.writeText(text).then(() => {
          copyBtn.textContent = '✓ Copied';
          copyBtn.classList.add('code-block-copy--copied');
          setTimeout(() => {
            copyBtn.textContent = '⧉ Copy';
            copyBtn.classList.remove('code-block-copy--copied');
          }, 1500);
        }, () => {});
      });

      header.appendChild(select);
      header.appendChild(copyBtn);

      // --- Code area: <pre><code> — this is ProseMirror's contentDOM ---
      const pre = document.createElement('pre');
      pre.classList.add('code-block-pre');
      const codeEl = document.createElement('code');
      pre.appendChild(codeEl);

      // --- Classic placeholder (hidden by default) ---
      const classicEl = document.createElement('div');
      classicEl.classList.add('code-block-classic');
      classicEl.style.display = 'none';
      classicEl.innerHTML = '<span class="code-block-classic-icon">&lt;/&gt;</span>'
        + '<span class="code-block-classic-label">Code Block</span>'
        + '<span class="code-block-classic-lang"></span>'
        + '<span class="code-block-classic-lock">🔒 AI mode</span>';

      wrapper.appendChild(header);
      wrapper.appendChild(pre);
      wrapper.appendChild(classicEl);

      const syncMode = () => {
        const mode = (editor.storage as any).mediaGuard?.editorMode || 'ai';
        const isClassic = mode === 'classic';
        header.style.display = isClassic ? 'none' : '';
        pre.style.display = isClassic ? 'none' : '';
        classicEl.style.display = isClassic ? '' : 'none';
        wrapper.classList.toggle('code-block-wrapper--classic', isClassic);
        const langSpan = classicEl.querySelector('.code-block-classic-lang');
        if (langSpan) langSpan.textContent = node.attrs.language || 'plaintext';
      };
      syncMode();

      return {
        dom: wrapper,
        contentDOM: codeEl, // ProseMirror puts text content here
        update(updatedNode) {
          if (updatedNode.type.name !== 'codeBlock') return false;
          // Keep reference to latest node attrs for the select change handler
          node = updatedNode;
          select.value = updatedNode.attrs.language || 'plaintext';
          syncMode();
          return true;
        },
        selectNode() {
          wrapper.classList.add('code-block-wrapper--selected');
        },
        deselectNode() {
          wrapper.classList.remove('code-block-wrapper--selected');
        },
        destroy() {
          // cleanup
        },
      };
    };
  },
}).configure({
  lowlight,
  defaultLanguage: 'plaintext',
});
