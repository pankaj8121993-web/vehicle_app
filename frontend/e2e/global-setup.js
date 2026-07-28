const fs = require("fs");
const { statePath, fixtureEnvironment, invoke } = require("./role-fixture");

module.exports = async () => {
  const env = fixtureEnvironment();
  const state = JSON.parse(invoke("seed", env));
  fs.writeFileSync(statePath, JSON.stringify({ ...state, fixture: env }), { mode: 0o600 });
};
