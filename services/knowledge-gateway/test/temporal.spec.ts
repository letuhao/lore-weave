import { knowledge } from '../src/kal/downstream.js';
import { temporalCapability, __resetTemporalCapabilityCache } from '../src/kal/temporal.js';

/**
 * The RULE ("can the KG honour as_of?") moved to knowledge-service in T26 — its tests moved
 * with it, to `tests/unit/test_kal_temporal.py`. Duplicating them here would recreate
 * exactly the problem T26 fixed: two processes holding independent opinions about one
 * substrate, agreeing right up until a deploy makes them disagree.
 *
 * What is left for the gateway to be tested on is FORWARDING: does it report what the owner
 * said, and what does it claim when it cannot ask?
 */
describe('temporal capability is forwarded, not decided (T26)', () => {
  const orig = knowledge.get;
  afterEach(() => {
    knowledge.get = orig;
    __resetTemporalCapabilityCache();
  });

  it('reports whatever the owning service reports', async () => {
    knowledge.get = async () => ({ glossary: 'ordinal_valid_time', kg: 'ordinal_valid_time' });
    expect(await temporalCapability()).toEqual({
      glossary: 'ordinal_valid_time',
      kg: 'ordinal_valid_time',
    });

    __resetTemporalCapabilityCache();
    knowledge.get = async () => ({ glossary: 'ordinal_valid_time', kg: 'temporal_unsupported' });
    expect((await temporalCapability()).kg).toBe('temporal_unsupported');
  });

  it('forwards a value it has never heard of rather than normalising it away', async () => {
    // The gateway is not the authority on this vocabulary. If the service starts reporting
    // `from_order_only`, passing it through is correct; coercing it to a value this file
    // recognises would put the gateway back in the business of deciding.
    knowledge.get = async () => ({ glossary: 'current_only', kg: 'from_order_only' });
    expect(await temporalCapability()).toEqual({ glossary: 'current_only', kg: 'from_order_only' });
  });

  it('claims the LEAST when it cannot ask', async () => {
    // Not a re-implementation of the rule: "we do not know" written as the value that
    // claims the least. Advertising ordinal_valid_time on a failed lookup would be the
    // original T26 bug with extra steps — a guarantee nobody verified.
    knowledge.get = async () => {
      throw new Error('ECONNREFUSED');
    };
    expect(await temporalCapability()).toEqual({
      glossary: 'ordinal_valid_time',
      kg: 'temporal_unsupported',
    });
  });

  it('does not cache a failure', async () => {
    knowledge.get = async () => {
      throw new Error('down');
    };
    expect((await temporalCapability()).kg).toBe('temporal_unsupported');

    // A cached failure would keep under-reporting for the whole TTL after recovery — the
    // migration would look unfinished for 30s every time the service blipped.
    knowledge.get = async () => ({ glossary: 'ordinal_valid_time', kg: 'ordinal_valid_time' });
    expect((await temporalCapability()).kg).toBe('ordinal_valid_time');
  });

  it('caches a success, so a read does not add a round trip', async () => {
    let calls = 0;
    knowledge.get = async () => {
      calls += 1;
      return { glossary: 'ordinal_valid_time', kg: 'ordinal_valid_time' };
    };
    await temporalCapability();
    await temporalCapability();
    expect(calls).toBe(1);
  });
});
