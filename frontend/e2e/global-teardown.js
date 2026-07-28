const fs = require("fs");
const { statePath, invoke } = require("./role-fixture");

module.exports = async () => {
  if (!fs.existsSync(statePath)) return;
  const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
  try {
    invoke("teardown", state.fixture);
  } finally {
    fs.rmSync(statePath, { force: true });
  }
};
