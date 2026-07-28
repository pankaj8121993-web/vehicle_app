const { test, expect } = require("@playwright/test");

test.beforeEach(async ({ page }) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Not authenticated" }) })
  );
});

test("anonymous public routes remain available", async ({ page }) => {
  await page.goto("/demo");
  await expect(page.getByRole("heading", { name: /explore fleetflow/i })).toBeVisible();
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: /sign in to fleetflow/i })).toBeVisible();
});

test("protected routes preserve a safe login destination", async ({ page }) => {
  await page.goto("/vehicles?status=active");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
});

test("unknown routes render a useful fallback", async ({ page }) => {
  await page.goto("/missing-route");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
});
