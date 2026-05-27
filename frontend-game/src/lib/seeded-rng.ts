// Deterministic pseudo-random generator. Mulberry32 — small, fast,
// statistically OK for game placement / decoration. NOT cryptographic.
//
// Useful when the client needs to reproduce server-decided placement
// (e.g. drop particle pattern) given a seed sent over the wire.

export class SeededRng {
  private state: number;

  constructor(seed: number) {
    this.state = seed >>> 0;
  }

  next(): number {
    this.state = (this.state + 0x6d2b79f5) >>> 0;
    let t = this.state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  // Inclusive low, exclusive high.
  nextInt(low: number, high: number): number {
    return Math.floor(this.next() * (high - low)) + low;
  }
}
