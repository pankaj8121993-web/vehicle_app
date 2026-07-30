# Visual Regression Guide (UX-05)

Playwright screenshot baselines guard the key surfaces against unintended
visual change. The suite lives in [`frontend/e2e/visual.spec.js`](../../frontend/e2e/visual.spec.js),
is tagged `@visual`, and is **excluded from the blocking `test:e2e` run** so a
platform rendering difference never blocks an unrelated change.

## Surfaces and profiles

Captured full-page on desktop Chromium and the exact **360×800** mobile Chromium
profile:

- Login
- Dashboard (org name + live exceptions masked)
- Vehicles grid (org name masked)

## Commands

```bash
cd frontend
npm run test:visual          # compare against committed baselines
npm run test:visual:update   # regenerate baselines (after an intended change)
```

## Stability rules

- Animations and the text caret are disabled; web fonts are awaited
  (`document.fonts.ready`) and the network is idle before capture.
- Only genuinely dynamic values are masked — the run-scoped org name, the live
  metrics/exceptions. Comparisons are **not** broadly disabled; the tolerance is
  a small `maxDiffPixelRatio: 0.02`.

## Baselines are platform-specific

Playwright names snapshots per platform (e.g. `login-chromium-linux.png`). Font
rendering differs between operating systems and CPU architectures, so a baseline
captured on one machine will not byte-match another. **Regenerate baselines in
the environment that will compare them** (run `test:visual:update` there and
commit the result). Because of this, CI runs the visual suite as a **reporting,
non-blocking** job that publishes the diff as an artifact; the blocking gates are
the axe accessibility checks, the role matrix, and the unit/e2e suites.

## When a diff is expected

After an intentional UI change, run `npm run test:visual:update`, review the new
PNGs in the diff, and commit them together with the change.
