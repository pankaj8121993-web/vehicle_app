const fs = require("fs");
const { statePath, fixtureEnvironment, invoke } = require("./role-fixture");

module.exports = async () => {
  const env = fixtureEnvironment();
  const state = JSON.parse(invoke("seed", env));
  for (const credential of Object.values(state.credentials)) {
    credential.password = env.password;
  }
  fs.writeFileSync(statePath, JSON.stringify({ ...state, fixture: env }), { mode: 0o600 });
};
