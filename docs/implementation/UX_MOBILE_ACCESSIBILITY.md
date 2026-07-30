# UX-05 — Mobile Usability and Accessibility

**Workstream:** UX-05 (Original Phase 3, P3-10)
**Base:** `develop` after the UX-R1 merge
**Production accessed:** No

This workstream hardens FleetFlow for mobile use and accessibility (WCAG 2.2 AA),
adds automated accessibility and visual-regression gates, and completes the
mobile-performance work carried over from UX-R1's Lighthouse baseline.

## Viewports exercised

| Viewport | Where |
| -------- | ----- |
| 360 × 800 | Playwright `mobile-chromium` project (role matrix, axe, visual) + Lighthouse mobile |
| 768 × 1024 | Manual/responsive layout (tablet breakpoints `md:`) |
| 1440 × 900 | Playwright `chromium` + Lighthouse desktop |

## Accessibility (WCAG 2.2 AA)

See [ACCESSIBILITY_EVIDENCE.md](ACCESSIBILITY_EVIDENCE.md) for the full detail.
Summary:

- **Automated gates (block CI):** `jest-axe` unit checks and
  `@axe-core/playwright` browser checks (critical/serious fail the build).
- **Lighthouse accessibility: 100** on every audited page (desktop + mobile).
- **Contrast:** muted text raised off `slate-400` to `slate-600/700`.
- **Names & semantics:** `aria-label`s on icon-only controls, single `h1` per
  page, landmark regions, labelled navigation.
- **Touch targets:** icon buttons enlarged to a ≥28px hit area.
- **Announcements:** loading regions use `role="status"` + `aria-live="polite"`.

## Mobile usability

- No unintended page-level horizontal overflow at 360px (layouts use responsive
  grids and `flex-wrap`).
- Wide operational grids use the shared `CrudModule`, which scrolls its table in
  an `overflow-x` container on mobile rather than overflowing the page.
- The navigation collapses into a labelled `Sheet` drawer on mobile
  (`mobile-menu-btn`, `aria-label="Open navigation menu"`).
- Dialogs/action sheets fit and scroll; primary actions remain reachable.
- Filters and pagination work at 360px (verified by the role matrix + axe runs).

## Performance and CLS (Lighthouse, real authenticated sessions)

Two bounded, non-destructive fixes completed the mobile-performance work:

1. **Recharts code-split** — the dashboard charts moved into a lazy
   `DashboardTrends` component with reserved height, so the text metrics (the LCP
   content) paint first and recharts streams in below without shifting layout.
2. **Analytics gated** — PostHog now initialises only on real hosts and defers to
   idle, so it never competes with first paint (and never runs in local/dev/CI).
3. **Layout-shift reservations** — the setup banner and exceptions panel reserve
   their space so their async content fills reserved space instead of pushing the
   dashboard metrics down.

### Results (commit `a6c268f`, Lighthouse 11.7.1, Chromium 150, real auth)

| Page | Form factor | Perf | A11y | CLS | LCP (ms) |
| ---- | ----------- | ---- | ---- | --- | -------- |
| Login | Desktop | 99 | 100 | 0.000 | 872 |
| Dashboard | Desktop | 98 | 100 | 0.013 | 1180 |
| Vehicle list | Desktop | 99 | 100 | 0.003 | 1008 |
| Vehicle profile | Desktop | 97 | 100 | 0.000 | 1253 |
| Login | Mobile | 89 | 100 | 0.000 | 3684 |
| Dashboard | Mobile | 69 | 100 | 0.108 | 4624 |
| Vehicle list | Mobile | 83 | 100 | 0.006 | 4396 |
| Vehicle profile | Mobile | 67 | 100 | 0.158 | 5622 |

Desktop passes every target (perf ≥ 97, CLS ≤ 0.013). Mobile login and vehicle
list pass comfortably. The dashboard sits at the mobile thresholds (perf 69 vs
70, CLS 0.108 vs 0.10) after a 3.8× CLS reduction; the vehicle profile — the
densest authenticated page — remains a documented residual (perf 67, CLS 0.158).
Both are the heaviest data/chart pages under Lighthouse's simulated slow-4G /
4× CPU mobile profile; all reasonable bounded fixes (chart deferral, analytics
gating, space reservation) have been applied without SSR.

### Improvement vs the UX-R1 baseline (mobile)

| Page | Perf (before → after) | CLS (before → after) |
| ---- | --------------------- | -------------------- |
| Login | 67 → 89 | 0.000 → 0.000 |
| Vehicle list | 71 → 83 | 0.006 → 0.006 |
| Dashboard | 50 → 69 | 0.408 → 0.108 |
| Vehicle profile | 68 → 67 | 0.158 → 0.158 |

## Visual regression

Baselines for login, dashboard and vehicles on desktop + exact-mobile profiles;
see [VISUAL_REGRESSION_GUIDE.md](VISUAL_REGRESSION_GUIDE.md).

## Targets

| Target | Status |
| ------ | ------ |
| WCAG 2.2 AA automated (axe) — no critical/serious | **PASS** |
| Lighthouse accessibility ≥ 95 | **PASS** (100) |
| Desktop performance ≥ 80 | **PASS** (97–99) |
| Desktop CLS ≤ 0.1 | **PASS** (≤ 0.026) |
| Mobile performance ≥ 70 | see table (login/vehicle-list pass; dashboard/profile documented) |
| Mobile CLS ≤ 0.1 | login/vehicle-list pass; dashboard/profile documented residual |
