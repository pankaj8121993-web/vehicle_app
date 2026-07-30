// UX-05 visual regression baselines (@visual).
//
// Captures stable, full-page screenshots of the key surfaces on desktop and the
// exact 360x800 mobile profile. Truly dynamic values (the run-scoped org name,
// live counts, dates) are masked; nothing else is disabled. Animations and the
// text caret are turned off and web fonts are awaited so renders are stable.
//
// Baselines are platform-specific. Regenerate them in the target environment
// with `npm run test:visual:update` (see VISUAL_REGRESSION_GUIDE.md). This
// suite is tagged @visual and excluded from the blocking `test:e2e` run.
const fs = require("fs");
const { test, expect } = require("@playwright/test");
const { statePath } = require("./role-fixture");

const state = JSON.parse(fs.readFileSync(statePath, "utf8"));

const SHOT = {
  fullPage: true,
  animations: "disabled",
  caret: "hide",
  maxDiffPixelRatio: 0.02,
};

async function settle(page) {
  await page.evaluate(() => document.fonts && document.fonts.ready);
  await page.waitForLoadState("networkidle");
}

async function login(page) {
  const cred = state.credentials.org_admin;
  await page.goto("/login");
  await page.getByTestId("login-username").fill(cred.username);
  await page.getByTestId("login-password").fill(cred.password);
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test.describe("@visual visual regression", () => {
  test.skip(({ browserName }) => browserName === "firefox", "Baselines captured on Chromium profiles");

  test("login", async ({ page }, testInfo) => {
    await page.goto("/login");
    await expect(page.getByTestId("login-submit")).toBeVisible();
    await settle(page);
    await expect(page).toHaveScreenshot(`login-${testInfo.project.name}.png`, SHOT);
  });

  test("dashboard", async ({ page }, testInfo) => {
    await login(page);
    await expect(page.getByTestId("dashboard-page")).toBeVisible();
    await settle(page);
    await expect(page).toHaveScreenshot(`dashboard-${testInfo.project.name}.png`, {
      ...SHOT,
      // The org name carries a run id and the metrics/exceptions are live.
      mask: [page.getByTestId("sidebar-org-name"), page.getByTestId("exceptions-panel")],
    });
  });

  test("vehicles", async ({ page }, testInfo) => {
    await login(page);
    await page.goto("/vehicles");
    await expect(page.getByTestId("vehicles-page")).toBeVisible();
    await settle(page);
    await expect(page).toHaveScreenshot(`vehicles-${testInfo.project.name}.png`, {
      ...SHOT,
      mask: [page.getByTestId("sidebar-org-name")],
    });
  });
});
