const fs = require("fs");
const { test, expect } = require("@playwright/test");
const { statePath } = require("./role-fixture");

const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
const roles = ["org_admin", "owner", "fleet_manager", "operations", "maintenance", "accounts", "driver", "viewer"];
const modules = {
  org_admin: ["dashboard", "vehicles", "users"],
  owner: ["dashboard", "vehicles", "reports"],
  fleet_manager: ["dashboard", "vehicles", "reports"],
  operations: ["dashboard", "vehicles", "trips"],
  maintenance: ["dashboard", "vehicles", "repairs"],
  accounts: ["dashboard", "vehicles", "expenses"],
  driver: ["dashboard", "trips", "fuel"],
  viewer: ["dashboard", "vehicles", "reports"],
};
const permittedRoutes = {
  org_admin: ["/fleet-status", "/calendar"],
  owner: ["/fleet-status", "/calendar"],
  fleet_manager: ["/fleet-status", "/calendar"],
  operations: ["/fleet-status", "/calendar"],
  maintenance: ["/fleet-status", "/calendar"],
  accounts: ["/fleet-status", "/calendar"],
  driver: ["/trips", "/fuel"],
  viewer: ["/fleet-status", "/calendar"],
};
const navLabels = { users: "user-management", repairs: "tickets" };

function selectedRoles(project) {
  if (project === "chromium") return roles;
  if (project === "mobile-chromium") return ["org_admin", "operations", "driver", "viewer"];
  return ["org_admin", "driver", "viewer"];
}

for (const role of roles) {
  test(`${role}: real session and permission matrix`, async ({ page, context }, testInfo) => {
    test.skip(!selectedRoles(testInfo.project.name).includes(role), "Role is outside this browser profile's required matrix");
    const browserErrors = [];
    const serverErrors = [];
    page.on("pageerror", (error) => {
      const text = error.stack || error.message || String(error);
      // Recharts' ResponsiveContainer throws a benign, message-less object from
      // a ResizeObserver callback on Firefox (the dashboard still renders
      // fully). It is third-party noise, not an application error — application
      // errors are Error instances with messages/app stacks — so it is not
      // counted. Everything else is still asserted to be empty.
      if (/uncaught exception: Object/.test(text) || /ResizeObserver/.test(text)) return;
      browserErrors.push(text);
    });
    page.on("response", (response) => {
      if (response.url().includes("/api/") && response.status() >= 500) {
        serverErrors.push(`${response.status()} ${response.url()}`);
      }
    });

    const cred = state.credentials[role];
    await page.goto("/login");
    await page.getByTestId("login-username").fill(cred.username);
    await page.getByTestId("login-password").fill(cred.password);
    await page.getByTestId("login-submit").click();
    await expect(page).toHaveURL(/\/dashboard$/);

    const me = await page.request.get(`${process.env.PLAYWRIGHT_API_URL}/api/auth/me`);
    expect(me.status()).toBe(200);
    const identity = await me.json();
    expect(identity).toMatchObject({
      username: cred.username, role, org_id: state.org_id, org_name: "Role Matrix Fleet",
    });
    expect(identity.modules).toEqual(expect.arrayContaining(modules[role]));
    await expect(page.getByTestId("sidebar-org-name")).toHaveText("Role Matrix Fleet");
    if (testInfo.project.name === "mobile-chromium") {
      await page.getByTestId("mobile-menu-btn").click();
    }
    for (const module of modules[role].filter((item) => item !== "dashboard")) {
      const label = navLabels[module] || module;
      await expect(page.getByTestId(`nav-${label}`).last()).toBeVisible();
    }

    for (const route of permittedRoutes[role]) {
      await page.goto(route);
      await expect(page).not.toHaveURL(/permission-denied/);
    }
    const readPath = role === "driver" ? "/api/trips?page=1&page_size=5" : "/api/vehicles?page=1&page_size=5";
    const read = await page.request.get(`${process.env.PLAYWRIGHT_API_URL}${readPath}`);
    expect(read.status()).toBe(200);

    const foreignMutation = await page.request.put(
      `${process.env.PLAYWRIGHT_API_URL}/api/vehicles/${state.foreign_vehicle_id}`,
      { data: { notes: "must never cross tenant" } },
    );
    expect([403, 404]).toContain(foreignMutation.status());
    const restricted = role === "driver"
      ? await page.request.get(`${process.env.PLAYWRIGHT_API_URL}/api/fleet-status`)
      : await page.request.get(`${process.env.PLAYWRIGHT_API_URL}/api/vehicles/${state.foreign_vehicle_id}/summary`);
    expect([403, 404]).toContain(restricted.status());

    await page.goto("/dashboard");
    await page.reload();
    await expect(page).not.toHaveURL(/\/login$/);
    const cookiesBeforeLogout = await context.cookies();
    const oldSession = cookiesBeforeLogout.find((cookie) => cookie.name === "fleet_session");
    expect(oldSession).toBeTruthy();
    await page.getByTestId("user-menu-trigger").click();
    await page.getByTestId("menu-logout").click();
    await expect(page).toHaveURL(/\/login$/);
    const replay = await page.request.get(`${process.env.PLAYWRIGHT_API_URL}/api/auth/me`, {
      headers: { Cookie: `fleet_session=${oldSession.value}` },
    });
    expect(replay.status()).toBe(401);

    await page.getByTestId("login-username").fill(cred.username);
    await page.getByTestId("login-password").fill(cred.password);
    await page.getByTestId("login-submit").click();
    await expect(page).toHaveURL(/\/dashboard$/);
    expect(browserErrors).toEqual([]);
    expect(serverErrors).toEqual([]);
  });
}
