import { describe, it, expect } from 'vitest';
import { sourceJumpUrl } from '../stalenessSource';

describe('sourceJumpUrl', () => {
  it('jumps an entity source to the glossary tab', () => {
    expect(sourceJumpUrl('b1', { source_type: 'entity', source_id: 'e9' })).toBe('/books/b1/glossary');
  });

  it('jumps a block (chapter) source to the chapter reader', () => {
    expect(sourceJumpUrl('b1', { source_type: 'block', source_id: 'ch7' })).toBe('/books/b1/chapters/ch7/read');
  });

  it('returns null for recipe/KG drift (no single viewable source)', () => {
    expect(sourceJumpUrl('b1', { source_type: 'kg', source_id: 'e1' })).toBeNull();
    expect(sourceJumpUrl('b1', { source_type: 'recipe' })).toBeNull();
    expect(sourceJumpUrl('b1', {})).toBeNull();
  });

  it('returns null when the block source has no id, or inputs are missing', () => {
    expect(sourceJumpUrl('b1', { source_type: 'block' })).toBeNull();
    expect(sourceJumpUrl('', { source_type: 'entity', source_id: 'e1' })).toBeNull();
    expect(sourceJumpUrl('b1', null)).toBeNull();
  });

  it('ignores a non-string source_id', () => {
    expect(sourceJumpUrl('b1', { source_type: 'block', source_id: 42 })).toBeNull();
  });
});
