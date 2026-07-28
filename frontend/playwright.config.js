const { defineConfig, devices } = require("@playwright/test");
const crypto = require("crypto");

// One id is shared by global setup and both web servers. It is generated at
// runtime and never committed.
process.env.FLEETFLOW_ROLE_E2E_RUN_ID ||= crypto.randomBytes(6).toString("hex");
process.env.FLEETFLOW_ROLE_E2E_MONGO_URL ||= "mongodb://127.0.0.1:27017";
process.env.PLAYWRIGHT_API_URL ||= "http://127.0.0.1:8101";

module.exports = defineConfig({
  testDir: "./e2e",
  workers: 1,
  globalSetup: require.resolve("./e2e/global-setup"),
  globalTeardown: require.resolve("./e2e/global-teardown"),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3101",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "cd ../backend && APP_ENV=test FLEETFLOW_CROSS_SITE_COOKIES=false MONGO_URL=${FLEETFLOW_ROLE_E2E_MONGO_URL:-mongodb://127.0.0.1:27017} DB_NAME=fleetflow_role_e2e_${FLEETFLOW_ROLE_E2E_RUN_ID} CORS_ORIGINS=http://127.0.0.1:3101 ../.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8101",
      url: "http://127.0.0.1:8101/api/",
      reuseExistingServer: false,
      timeout: 120000,
    },
    {
      command: "REACT_APP_BACKEND_URL=http://127.0.0.1:8101 npm run build && ../.venv/bin/python ../scripts/serve_spa.py build --port 3101",
      url: "http://127.0.0.1:3101",
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
  ],
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 5"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
  ],
});
