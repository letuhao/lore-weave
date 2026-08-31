// The browser half of `picker-search-live-smoke.sh`. Run it through that script; it
// supplies BASE / JWT / USER_ID / BOOK_ID from the RUNNING stack.
//
// WHAT IT ASSERTS, AND WHY IT IS THE REQUEST AND NOT THE RENDER
// ------------------------------------------------------------
// Typing "StepA Smoke" and seeing one row is what a CLIENT-SIDE filter does too — it is
// what the picker did before, over one clamped page, which is the whole defect. So this
// listens on the network and requires the typed term to appear in an outgoing
// `/v1/worlds` request. A render assertion would pass on the bug.
//
// It also pins the request COUNT: the box is debounced, and a picker that fires one
// request per keystroke is a different defect wearing the same green.
import { chromium } from 'playwright';

const BASE = process.env.BASE;
const JWT = process.env.JWT;
const USER_ID = process.env.USER_ID;
const BOOK_ID = process.env.BOOK_ID;
const TERM = process.env.TERM_TO_TYPE ?? 'StepA Smoke';
for (const [k, v] of Object.entries({ BASE, JWT, USER_ID, BOOK_ID })) {
  if (!v) {
    console.log('REFUSED: ' + k + ' is empty. Run this through picker-search-live-smoke.sh.');
    process.exit(2);
  }
}

const browser = await chromium.launch();
const page = await (await browser.newContext()).newPage();
const seen = [];
page.on('request', (r) => {
  if (r.url().includes('/v1/worlds')) seen.push(r.url());
});

let failures = 0;
const check = (ok, label) => {
  console.log((ok ? '  ok   ' : '  FAIL ') + label);
  if (!ok) failures++;
};

try {
  // The session is SEEDED rather than typed. The iso account's password is not recorded
  // in the repo, and a smoke that cannot run is worth less than one that skips the login
  // form — everything after this line is the real UI on the real build.
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await page.evaluate(([jwt, uid]) => {
    localStorage.setItem('lw_auth', JSON.stringify({ accessToken: jwt, refreshToken: jwt }));
    localStorage.setItem('lw_user', JSON.stringify({ user_id: uid }));
  }, [JWT, USER_ID]);

  // Let the app's own post-auth redirect (`/` -> `/browse`) finish first. Navigating
  // straight after seeding raced it and Playwright aborted the second goto — a failure
  // about the harness, not about the picker, which is the worst kind to leave in a smoke.
  await page.waitForTimeout(2000);

  // A book with NO world attached, so the picker renders its combobox rather than the
  // selected-world chip. The caller picks it; this only reports what it got.
  await page.goto(BASE + '/books/' + BOOK_ID + '/settings', { waitUntil: 'domcontentloaded' });
  const picker = page.getByTestId('world-picker-input');
  await picker.waitFor({ timeout: 25000 });
  console.log('  --   WorldPicker combobox is on the page');

  seen.length = 0;
  await picker.click();
  await picker.fill(TERM);
  await page.waitForTimeout(1800); // past the 180ms debounce plus a round trip

  seen.forEach((u) => console.log('  --   ' + u.replace(/^https?:\/\/[^/]+/, '')));
  const encoded = encodeURIComponent(TERM).replace(/%20/g, '+');
  const carried = seen.filter((u) => u.includes('q=' + encoded) || u.includes('q=' + encodeURIComponent(TERM)));

  check(carried.length > 0,
    'the typed term reached the SERVER (a client-side filter renders the same)');
  check(seen.length > 0 && seen.length <= 3,
    'the box is debounced — ' + seen.length + ' request(s), not one per keystroke');

  const rows = await page.locator('#world-picker-list li').allTextContents();
  console.log('  --   rendered: ' + JSON.stringify(rows.slice(0, 5)));
  check(rows.length > 0, "the server's result actually rendered");
  check(rows.every((r) => r.toLowerCase().includes(TERM.toLowerCase().split(' ')[0])),
    'every rendered row matches the term');
} catch (e) {
  console.log('  FAIL ' + String(e.message).split('\n')[0]);
  failures++;
} finally {
  await browser.close();
}

console.log(failures ? '\npicker-search-live-smoke: FAILED (' + failures + ')'
                     : '\npicker-search-live-smoke: OK');
process.exitCode = failures ? 1 : 0;
