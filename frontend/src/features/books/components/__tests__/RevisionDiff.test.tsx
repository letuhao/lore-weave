import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { RevisionDiff } from '../RevisionDiff';
import type { DiffLine } from '../../types';

const diff: DiffLine[] = [
  { op: 'equal', text: 'intro' },
  { op: 'delete', text: 'old middle' },
  { op: 'insert', text: 'new middle' },
  { op: 'equal', text: 'outro' },
];

describe('RevisionDiff', () => {
  it('inline mode renders git-style ops with op markers', () => {
    const { container } = render(<RevisionDiff diff={diff} mode="inline" />);
    expect(screen.getByTestId('diff-inline')).toBeTruthy();
    expect(container.querySelector('[data-op="insert"]')).toBeTruthy();
    expect(container.querySelector('[data-op="delete"]')).toBeTruthy();
    expect(container.querySelectorAll('[data-op="equal"]').length).toBe(2);
  });

  it('side-by-side mode renders aligned left/right columns with word-level highlight', () => {
    const { container } = render(<RevisionDiff diff={diff} mode="side-by-side" />);
    expect(screen.getByTestId('diff-sxs')).toBeTruthy();
    // a change row word-highlights only the differing words ("old" vs "new"),
    // not the shared "middle".
    const changed = Array.from(container.querySelectorAll('[data-changed="true"]')).map((e) => e.textContent);
    expect(changed).toContain('old');
    expect(changed).toContain('new');
    expect(changed).not.toContain('middle');
  });
});
