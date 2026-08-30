/**
 * Human-behaviour simulation — the persona contract.
 *
 * WHY THIS EXISTS, AND WHAT IT IS NOT
 * ───────────────────────────────────
 * A simulated user that reports impressions ("the search felt slow") is noise: nobody can
 * act on it and nothing can go red. What makes a simulated journey worth running is that it
 * ends in a claim that can be FALSE. So a persona is not a character sketch — it is a
 * starting state, an intent, and an assertion.
 *
 * THE CALIBRATION CASE, AND THE REASON `scale` IS A FIRST-CLASS FIELD
 * ──────────────────────────────────────────────────────────────────
 * On 2026-08-30 this repo fixed a defect where a user with 83 books searched their library
 * by title and got nothing. The page loaded 20 rows (the endpoint's default), displayed the
 * true total of 83, and filtered those 20 in the browser. The book sat at rank 32.
 *
 * It had been recorded for six days as "book search is broken for Vietnamese diacritics",
 * because the queries that happened to work were for recently-created books and the one that
 * failed was older. The encoding was never involved.
 *
 * **Below 21 books the defect does not exist.** A simulated user on a fresh account — which
 * is what a persona suite naturally reaches for — would have walked that journey, found its
 * book, and reported success forever. That is why `scale` is declared and ENFORCED here
 * rather than left to whatever the test account happens to hold: a persona that does not
 * pin the size of its world is testing a world it did not choose.
 */

/** What the account must look like BEFORE the journey runs. */
export interface PersonaState {
  /**
   * How many books this persona owns, at minimum. The harness seeds up to this
   * number and FAILS rather than proceeding if it cannot — a journey that
   * silently ran at the wrong scale is worse than one that did not run, because
   * it reports a pass for a case it never entered.
   */
  minBooks: number;
  /** True for a first-session user: no books, no history, onboarding unseen. */
  fresh?: boolean;
}

/**
 * One falsifiable claim about the end of a journey.
 *
 * `describe` is written as the USER's expectation, in their words, because that
 * is what makes a failure legible to someone who did not write the test:
 * "the book I searched for is in the results" beats "expect(rows).toHaveLength(1)".
 */
export interface Expectation {
  describe: string;
  /**
   * Why this is the user's expectation and not merely the implementation's
   * current behaviour. Required: an assertion nobody can justify is how a suite
   * ends up pinning a bug in place.
   */
  because: string;
}

export interface Journey {
  /** Stable id, kebab-case — appears in the trace and in findings. */
  id: string;
  /** What the persona is trying to accomplish, in one line, from their side. */
  intent: string;
  expects: Expectation[];
}

export interface Persona {
  /** Stable id, kebab-case. */
  id: string;
  /** One line: who this is and what they already know. */
  who: string;
  state: PersonaState;
  journeys: Journey[];
}

/**
 * `newcomer` and `frequent` are the two the product actually has to serve, and
 * they fail differently: a newcomer hits empty states, unexplained vocabulary
 * and dead ends; a frequent user hits SCALE — pagination, truncation, search
 * that only sees the first page. Nearly every defect this repo has recorded in
 * the second class was invisible to a fresh account.
 */
export const PERSONAS: Persona[] = [
  {
    id: 'newcomer',
    who: 'First session. No books, no vocabulary for the product, has not seen onboarding.',
    state: { minBooks: 0, fresh: true },
    journeys: [
      {
        id: 'find-where-to-start',
        intent: 'Work out what to do first on an account with nothing in it.',
        expects: [
          {
            describe: 'the empty library offers a way to create a book, not just a blank page',
            because:
              'An empty state with no next action is the most common place a first session ends. ' +
              'The account genuinely has nothing, so the page cannot rely on content to guide them.',
          },
        ],
      },
    ],
  },
  {
    id: 'frequent',
    who: 'Returning author with a large library. Knows what they want and navigates by name.',
    // 25 > the books endpoint's default page of 20 — deliberately. At 20 or
    // fewer, a client-side filter over the first page is indistinguishable from
    // a correct search, and the journey below cannot fail.
    state: { minBooks: 25 },
    journeys: [
      {
        id: 'open-a-book-by-name',
        intent: 'Find one specific book by typing part of its title.',
        expects: [
          {
            describe: 'a book they own is found by name even when it is not among the newest',
            because:
              'This is how a returning user navigates a library they cannot see all of. ' +
              'It is also the exact journey that was broken for six days while every ' +
              'fresh-account test passed: the search only ever saw the first 20 rows.',
          },
          {
            describe: 'the count shown describes what was searched, not the whole library',
            because:
              'Showing "83" beside a search that read 20 rows tells the user their book ' +
              'does not exist. A wrong count is not cosmetic — it is the thing that makes ' +
              'a missing result look like an answer.',
          },
        ],
      },
    ],
  },
];
