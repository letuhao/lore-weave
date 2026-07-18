// The ledger proves composition_publish MATCHES this handler; this proves it invalidates the RIGHT
// key so an agent publish refreshes the flywheel (its poll then catches the async extraction delta).
import { describe, it, expect, vi } from 'vitest';
import { flywheelPublishEffect } from '../flywheelEffects';
import type { EffectContext } from '../../effectRegistry';

describe('flywheelPublishEffect', () => {
  it('invalidates the composition flywheel query on publish', () => {
    const invalidateQueries = vi.fn();
    flywheelPublishEffect({ queryClient: { invalidateQueries } } as unknown as EffectContext);
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['composition', 'flywheel'] });
  });
});
