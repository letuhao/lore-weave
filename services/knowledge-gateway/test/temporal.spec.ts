import { resetConfigForTest } from '../src/config/config.js';
import { temporalCapability, kgAsOfOrDrop } from '../src/kal/temporal.js';

describe('per-substrate temporal capability (§12.5.1 / A5)', () => {
  const origEnv = process.env.KG_TEMPORAL_ENABLED;
  afterEach(() => {
    if (origEnv === undefined) delete process.env.KG_TEMPORAL_ENABLED;
    else process.env.KG_TEMPORAL_ENABLED = origEnv;
    resetConfigForTest();
  });

  it('glossary is always ordinal_valid_time; KG honors as_of when enabled', () => {
    process.env.KG_TEMPORAL_ENABLED = 'true';
    resetConfigForTest();
    expect(temporalCapability()).toEqual({ glossary: 'ordinal_valid_time', kg: 'ordinal_valid_time' });
    // as_of forwarded unchanged when the KG can honor it
    expect(kgAsOfOrDrop(500)).toBe(500);
    expect(kgAsOfOrDrop(undefined)).toBeUndefined();
  });

  it('KG reports temporal_unsupported and DROPS as_of when disabled (degrade-safe, no spoiler leak)', () => {
    process.env.KG_TEMPORAL_ENABLED = 'false';
    resetConfigForTest();
    expect(temporalCapability()).toEqual({ glossary: 'ordinal_valid_time', kg: 'temporal_unsupported' });
    // as_of is DROPPED rather than forwarded as a transaction-time-contaminated query
    expect(kgAsOfOrDrop(500)).toBeUndefined();
  });
});
