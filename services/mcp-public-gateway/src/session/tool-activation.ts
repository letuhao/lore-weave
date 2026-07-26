import { Injectable, Logger } from '@nestjs/common';

import {
  ACTIVATION_TTL_SECONDS,
  InMemoryToolActivationStore,
  type ToolActivationStore,
} from './tool-activation-store.js';

/**
 * The per-session tool-activation state machine. Wraps the store with the edge's fail-soft
 * policy: a store blip must never break a relay — `activated()` degrades to "nothing activated
 * yet" (the session reads as minimal, the agent re-discovers) and `activate()` is best-effort
 * (a missed activation just means the agent re-finds the tool). NEVER throws.
 *
 * Construct with a real store (Redis/in-memory from env) in the module; tests can pass an
 * InMemoryToolActivationStore directly.
 */
@Injectable()
export class ToolActivation {
  private readonly log = new Logger(ToolActivation.name);

  constructor(private readonly store: ToolActivationStore = new InMemoryToolActivationStore()) {}

  /** The session's activated tool names (a Set for O(1) membership in the list collapse).
   * Fail-soft: a store error degrades to ∅ (minimal surface), never throws. */
  async activated(sessionId: string): Promise<Set<string>> {
    try {
      return new Set(await this.store.activated(sessionId, ACTIVATION_TTL_SECONDS));
    } catch (e) {
      this.log.warn(`tool-activation read failed (degrading to minimal surface): ${e}`);
      return new Set();
    }
  }

  /** Activate `names` into the session (best-effort). A missed write just means the agent
   * re-discovers the tool next turn — never fatal to the relay. */
  async activate(sessionId: string, names: string[]): Promise<void> {
    if (names.length === 0) return;
    try {
      await this.store.activate(sessionId, names, ACTIVATION_TTL_SECONDS);
    } catch (e) {
      this.log.warn(`tool-activation write failed (agent will re-discover): ${e}`);
    }
  }
}
