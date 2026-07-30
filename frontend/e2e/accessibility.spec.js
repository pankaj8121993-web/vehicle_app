// UX-05 accessibility E2E (@axe-core/playwright, WCAG 2.2 AA).
//
// Runs axe against real, authenticated pages in the browser and fails on any
// new critical or serious violation. Runs on desktop Chromium and the exact
// 360x800 mobile Chromium profile so mobile-specific issues are caught too.
const fs = require("fs");
const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
const { statePath } = require("./role-fixture");

const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const BLOCKING = new Set(["critical", "serious"]);

async function scan(page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  const blocking = results.violations.filter((v) => BLOCKING.has(v.impact));
  return blocking.map((v) => `${v.impact}: ${v.id} — ${v.nodes.length} node(s)`);
}

async function login(page) {
  const cred = state.credentials.org_admin;
  await page.goto("/login");
  await page.getByTestId("login-username").fill(cred.username);
  await page.getByTestId("login-password").fill(cred.password);
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test.describe("accessibility (axe, WCAG 2.2 AA)", () => {
  test.skip(({ browserName }) => browserName === "firefox", "axe runs on Chromium profiles");

  test("login page has no critical/serious violations", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByTestId("login-submit")).toBeVisible();
    expect(await scan(page)).toEqual([]);
  });

  test("dashboard has no critical/serious violations", async ({ page }) => {
    await login(page);
    await expect(page.getByTestId("sidebar-org-name")).toBeVisible();
    expect(await scan(page)).toEqual([]);
  });

  test("vehicles grid has no critical/serious violations", async ({ page }, testInfo) => {
    await login(page);
    await page.goto("/vehicles");
    // The grid renders its heading once the first page loads.
    await expect(page.getByRole("heading", { name: /vehicles/i }).first()).toBeVisible();
    expect(await scan(page)).toEqual([]);
  });
});
