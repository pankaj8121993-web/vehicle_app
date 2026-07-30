const fs = require("fs");
const { test, expect } = require("@playwright/test");
const { statePath } = require("./role-fixture");

const state = JSON.parse(fs.readFileSync(statePath, "utf8"));

async function login(page, role) {
  const credential = state.credentials[role];
  await page.goto("/login");
  await page.getByTestId("login-username").fill(credential.username);
  await page.getByTestId("login-password").fill(credential.password);
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("trip completion validates, retains values, locks submission and succeeds", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "Representative domain workflow runs on desktop Chromium");
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page, "org_admin");
  await page.goto("/trips");
  await page.getByTestId(`close-trip-${state.trip_id}`).click();
  const input = page.getByTestId("close-trip-km-input");
  await input.fill("99");
  await page.getByTestId("close-trip-confirm").click();
  await expect(page.getByRole("alert")).toContainText("at least 100");
  await expect(input).toHaveValue("99");
  await input.fill("125");
  const confirm = page.getByTestId("close-trip-confirm");
  await confirm.click();
  await expect(confirm).toBeDisabled();
  await expect(page.getByText("Complete Trip — Enter Closing KM")).toBeHidden();
  expect(errors).toEqual([]);
});

test("expense approval uses the real permission-backed workflow", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "Representative domain workflow runs on desktop Chromium");
  await login(page, "owner");
  await page.goto("/expenses");
  await page.getByRole("tab", { name: "Manual Entries" }).click();
  await page.getByTestId(`approve-expense-${state.expense_id}`).click();
  await expect(page.getByTestId("approve-expense-amount")).toHaveValue("500");
  await page.getByTestId("approve-expense-confirm").click();
  await expect(page.getByText("Approve Expense")).toBeHidden();
  const response = await page.request.get(
    `${process.env.PLAYWRIGHT_API_URL}/api/expenses?search=UX-R1%20approval`,
  );
  expect(response.status()).toBe(200);
  const item = (await response.json()).items.find((row) => row.id === state.expense_id);
  expect(item.approval_status).toBe("approved");
});
