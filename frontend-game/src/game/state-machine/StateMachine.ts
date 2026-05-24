// Reusable per-entity finite state machine. Per spec §9 pattern #3.
// Each entity (Player, NPC) gets its own instance keyed by state names
// like 'Idle' | 'Walking' | 'Casting' | 'Stunned'. Transitions are
// explicit — the FSM rejects undefined transitions.

export interface State<TContext> {
  name: string;
  enter?: (ctx: TContext) => void;
  update?: (ctx: TContext, delta: number) => void;
  exit?: (ctx: TContext) => void;
}

export class StateMachine<TContext> {
  private current: State<TContext> | null = null;
  private readonly states: Map<string, State<TContext>> = new Map();

  constructor(private readonly ctx: TContext) {}

  add(state: State<TContext>): this {
    this.states.set(state.name, state);
    return this;
  }

  transition(name: string): void {
    const next = this.states.get(name);
    if (!next) {
      throw new Error(`StateMachine: unknown state '${name}'`);
    }
    this.current?.exit?.(this.ctx);
    this.current = next;
    next.enter?.(this.ctx);
  }

  update(delta: number): void {
    this.current?.update?.(this.ctx, delta);
  }

  get currentName(): string | null {
    return this.current?.name ?? null;
  }
}
