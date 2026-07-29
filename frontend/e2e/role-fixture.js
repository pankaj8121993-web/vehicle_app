const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const statePath = path.join(__dirname, ".role-matrix-state.json");

function fixtureEnvironment() {
  const runId = process.env.FLEETFLOW_ROLE_E2E_RUN_ID || crypto.randomBytes(6).toString("hex");
  return {
    runId,
    database: `fleetflow_role_e2e_${runId}`,
    mongoUrl: process.env.FLEETFLOW_ROLE_E2E_MONGO_URL || "mongodb://127.0.0.1:27017",
    password: process.env.FLEETFLOW_ROLE_E2E_PASSWORD || crypto.randomBytes(32).toString("base64url"),
    python: process.env.FLEETFLOW_ROLE_E2E_PYTHON || path.resolve(__dirname, "../../.venv/bin/python"),
  };
}

function invoke(action, env) {
  return execFileSync(env.python, [
    path.resolve(__dirname, "../../scripts/role_e2e_fixture.py"), action,
    "--database", env.database, "--mongo-url", env.mongoUrl,
  ], {
    encoding: "utf8",
    env: {
      ...process.env, APP_ENV: "test", FLEETFLOW_ROLE_E2E_RUN_ID: env.runId,
      FLEETFLOW_ROLE_E2E_PASSWORD: env.password, FLEETFLOW_ROLE_E2E_ALLOW: "true",
    },
  });
}

module.exports = { statePath, fixtureEnvironment, invoke };
