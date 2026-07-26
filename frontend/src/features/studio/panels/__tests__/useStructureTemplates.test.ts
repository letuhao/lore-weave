// S-01b · unit tests for the structure-templates hook's pure helpers.
// The mutation wiring is covered by the panel test + the live smoke; here we lock the
// error CLASSIFIER (C3) so an OCC conflict never again surfaces as a raw "…status 412".
import { describe, it, expect } from 'vitest';
import { classifyStructTplError } from '../useStructureTemplates';

describe('classifyStructTplError', () => {
  it('maps OCC / missing-If-Match to conflict', () => {
    expect(classifyStructTplError({ status: 412 })).toBe('conflict');
    expect(classifyStructTplError({ status: 428 })).toBe('conflict');
  });
  it('maps a name UNIQUE collision to duplicate', () => {
    expect(classifyStructTplError({ status: 409 })).toBe('duplicate');
  });
  it('maps a rejected blank name to blank', () => {
    expect(classifyStructTplError({ status: 422 })).toBe('blank');
  });
  it('falls back to unknown for anything else / no status', () => {
    expect(classifyStructTplError({ status: 500 })).toBe('unknown');
    expect(classifyStructTplError(new Error('network'))).toBe('unknown');
    expect(classifyStructTplError(null)).toBe('unknown');
  });
});
