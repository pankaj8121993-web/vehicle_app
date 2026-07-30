# Accessibility Evidence (UX-05 — WCAG 2.2 AA)

FleetFlow is audited for accessibility at two levels, both of which run in CI
and block on regressions.

## Automated tooling (pinned)

| Tool | Version | Scope |
| ---- | ------- | ----- |
| `jest-axe` | 8.0.0 | Component/page render in the Jest suite |
| `@axe-core/playwright` | 4.10.1 | Real authenticated pages in the browser |

## Unit-level (jest-axe)

[`frontend/src/a11y.test.jsx`](../../frontend/src/a11y.test.jsx) renders key
surfaces and asserts **no axe violations**:

- Login page
- Permission-denied page
- Not-found page

These run inside `npm run test:ci`, so a missing label, an unnamed control or a
contrast regression fails the build.

## Browser-level (@axe-core/playwright)

[`frontend/e2e/accessibility.spec.js`](../../frontend/e2e/accessibility.spec.js)
logs in with a real session and runs axe with the WCAG 2.0/2.1/2.2 A + AA tag
set against:

- Login (unauthenticated)
- Dashboard (authenticated)
- Vehicles grid (authenticated)

It runs on desktop Chromium and the exact 360×800 mobile Chromium profile and
**fails on any `critical` or `serious` violation**, so CI blocks new critical or
serious accessibility defects.

## Lighthouse accessibility

Lighthouse (see [LIGHTHOUSE_EVIDENCE.md](LIGHTHOUSE_EVIDENCE.md)) scores
**accessibility 100** on every audited page in both desktop and mobile profiles.

## Manual/structural improvements shipped in UX-05

- **Contrast**: muted text raised off `slate-400` to `slate-600/700` across the
  dashboard metrics, exceptions, vehicles filters, login footer and empty
  states so it meets AA contrast.
- **Accessible names**: added `aria-label`s to the mobile navigation trigger,
  the install-prompt dismiss and other icon-only controls.
- **Touch targets**: icon-only buttons (password reveal, dismiss) enlarged to a
  ≥28px hit area laid out on a grid.
- **Status/loading announcements**: dashboard and vehicle-profile loading states
  use `role="status"` with `aria-live="polite"` and an accessible label.
- **Landmarks & headings**: pages retain a single `h1`, landmark regions
  (`complementary` sidebar nav, `main`) and labelled navigation.

## Targets

| Target | Status |
| ------ | ------ |
| WCAG 2.2 AA automated (axe) — no critical/serious | **PASS** (unit + browser) |
| Lighthouse accessibility ≥ 95 | **PASS** (100 all pages) |
| CI blocks new critical/serious axe violations | **PASS** (accessibility.spec.js) |
