const expected = process.env.PERF_DB;
if (!expected || db.getName() !== expected || !/perf/i.test(expected)) {
  throw new Error("Refusing to run: database must equal PERF_DB and contain 'perf'");
}
const org = "synthetic-perf-a";
const specs = [
  ["vehicles", { org_id: org, status: "active" }, { vehicle_number: 1 }],
  ["trips", { org_id: org, status: "completed" }, { date: -1 }],
  ["expenses", { org_id: org, status: "submitted" }, { date: -1 }],
  ["fuel_entries", { org_id: org }, { date: -1 }],
  ["fastag_transactions", { org_id: org }, { date: -1 }],
  ["repairs", { org_id: org, status: "open" }, { date: -1 }],
  ["downtimes", { org_id: org, status: "open" }, { start_date: -1 }],
  ["documents", { org_id: org }, { expiry_date: 1 }],
];
if (process.env.PERF_INSTALL_INDEXES === "true") {
  const definitions = {
    vehicles: { org_id: 1, status: 1, vehicle_number: 1 },
    trips: { org_id: 1, status: 1, date: -1 },
    expenses: { org_id: 1, status: 1, date: -1 },
    fuel_entries: { org_id: 1, date: -1 },
    fastag_transactions: { org_id: 1, date: -1 },
    repairs: { org_id: 1, status: 1, date: -1 },
    downtimes: { org_id: 1, status: 1, start_date: -1 },
    documents: { org_id: 1, expiry_date: 1 },
  };
  for (const [collection, keys] of Object.entries(definitions)) db[collection].createIndex(keys);
}
const output = {};
for (const [collection, filter, sort] of specs) {
  const timings = [];
  for (let i = 0; i < 30; i++) {
    const start = Date.now();
    db[collection].find(filter).sort(sort).limit(25).toArray();
    timings.push(Date.now() - start);
  }
  timings.sort((a, b) => a - b);
  const explain = db[collection].find(filter).sort(sort).limit(25).explain("executionStats").executionStats;
  output[collection] = {
    median_ms: timings[14],
    p95_ms: timings[28],
    maximum_ms: timings[29],
    winning_stage: explain.executionStages.inputStage?.stage || explain.executionStages.stage,
    examined: explain.totalDocsExamined,
    returned: explain.nReturned,
  };
}
printjson(output);
