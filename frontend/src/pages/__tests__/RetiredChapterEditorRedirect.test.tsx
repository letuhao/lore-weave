import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { RetiredChapterEditorRedirect } from '../RetiredChapterEditorRedirect';

// The legacy chapter editor is RETIRED (PO, 2026-09-18): the Writing Studio is the only writing
// surface. Its route survives only as a redirect, and nothing in the app may link to it again.

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname + loc.search}</div>;
}

describe('the retired chapter editor route', () => {
  it('sends /books/:bookId/chapters/:chapterId/edit to the same chapter in the Writing Studio', () => {
    render(
      <MemoryRouter initialEntries={['/books/b-1/chapters/c-9/edit']}>
        <Routes>
          <Route path="/books/:bookId/chapters/:chapterId/edit" element={<RetiredChapterEditorRedirect />} />
          <Route path="/books/:bookId/studio" element={<Where />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('where').textContent).toBe('/books/b-1/studio?chapter=c-9');
  });

  it('no source file builds a link to the retired editor path', () => {
    const root = join(__dirname, '..', '..');
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name);
        if (statSync(p).isDirectory()) {
          if (name !== '__tests__' && name !== 'node_modules') walk(p);
        } else if (/\.(tsx?|jsx?)$/.test(name)) {
          const src = readFileSync(p, 'utf8');
          // a navigation target: `/books/${...}/chapters/${...}/edit` in a template literal
          if (/\/books\/\$\{[^}]+\}\/chapters\/\$\{[^}]+\}\/edit/.test(src)) offenders.push(p);
        }
      }
    };
    walk(root);
    expect(offenders, 'these still link into the retired chapter editor — use studioChapterPath').toEqual([]);
  });
});
