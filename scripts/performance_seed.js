// Run only against an isolated database:
// PERF_DB=fleetflow_performance mongosh mongodb://127.0.0.1:27017/fleetflow_performance scripts/performance_seed.js
const expected = process.env.PERF_DB;
if (!expected || db.getName() !== expected || !/perf/i.test(expected)) {
  throw new Error("Refusing to run: database must equal PERF_DB and contain 'perf'");
}

const prefix = "synthetic-perf-";
const orgs = ["a", "b"].map((suffix) => `${prefix}${suffix}`);
const collections = ["organizations", "vehicles", "drivers", "trips", "expenses", "expense_payments", "advances", "fuel_entries", "fastag_transactions", "repairs", "downtimes", "documents", "tyres", "accidents", "exception_acks", "users", "user_sessions"];

for (const name of collections) db[name].deleteMany({ performance_fixture: true });
if (process.env.PERF_TEARDOWN === "true") {
  printjson({ action: "teardown", database: db.getName() });
  quit(0);
}

function insertBatches(collection, total, factory) {
  for (let start = 0; start < total; start += 1000) {
    const docs = [];
    for (let i = start; i < Math.min(start + 1000, total); i++) docs.push(factory(i));
    db[collection].insertMany(docs, { ordered: false });
  }
}

for (const orgId of orgs) {
  const suffix = orgId.endsWith("-a") ? "a" : "b";
  db.organizations.insertOne({ id: orgId, legal_name: `Synthetic Performance ${suffix.toUpperCase()}`, trade_name: `Synthetic Performance ${suffix.toUpperCase()}`, is_demo: false, performance_fixture: true });
  insertBatches("vehicles", 250, (i) => ({ id: `${orgId}-v-${i}`, org_id: orgId, vehicle_number: `PERF-${suffix}-${String(i).padStart(4, "0")}`, make: "Synthetic", model: "Load", status: "active", current_odometer: i * 100, performance_fixture: true }));
  insertBatches("drivers", 250, (i) => ({ id: `${orgId}-d-${i}`, org_id: orgId, name: `Synthetic Driver ${suffix}-${i}`, employee_number: `EMP-${suffix}-${i}`, status: "active", performance_fixture: true }));
  insertBatches("trips", 10000, (i) => ({ id: `${orgId}-t-${i}`, org_id: orgId, vehicle_id: `${orgId}-v-${i % 250}`, driver_id: `${orgId}-d-${i % 250}`, date: `2026-06-${String((i % 28) + 1).padStart(2, "0")}`, status: i % 5 ? "completed" : "ongoing", from_location: "Synthetic Origin", to_location: `Synthetic Destination ${i}`, performance_fixture: true }));
  insertBatches("expenses", 20000, (i) => ({ id: `${orgId}-e-${i}`, org_id: orgId, vehicle_id: `${orgId}-v-${i % 250}`, date: `2026-06-${String((i % 28) + 1).padStart(2, "0")}`, category: i % 2 ? "Fuel" : "Maintenance", amount: (i % 5000) + 1, status: "submitted", performance_fixture: true }));
  insertBatches("expense_payments", 10000, (i) => ({ id: `${orgId}-p-${i}`, org_id: orgId, expense_id: `${orgId}-e-${i}`, amount: (i % 500) + 1, status: "paid", paid_at: "2026-06-20", performance_fixture: true }));
  insertBatches("advances", 10000, (i) => ({ id: `${orgId}-a-${i}`, org_id: orgId, driver_id: `${orgId}-d-${i % 250}`, amount: (i % 1000) + 1, status: "open", date: "2026-06-10", performance_fixture: true }));
  insertBatches("fuel_entries", 10000, (i) => ({ id: `${orgId}-f-${i}`, org_id: orgId, vehicle_id: `${orgId}-v-${i % 250}`, date: `2026-06-${String((i % 28) + 1).padStart(2, "0")}`, quantity: (i % 100) + 1, amount: (i % 7000) + 1, performance_fixture: true }));
  insertBatches("fastag_transactions", 10000, (i) => ({ id: `${orgId}-g-${i}`, org_id: orgId, vehicle_id: `${orgId}-v-${i % 250}`, date: `2026-06-${String((i % 28) + 1).padStart(2, "0")}`, txn_type: "toll", plaza_name: `Synthetic Plaza ${i % 50}`, amount: (i % 500) + 1, performance_fixture: true }));
  insertBatches("repairs", 1250, (i) => ({ id: `${orgId}-r-${i}`, org_id: orgId, vehicle_id: `${orgId}-v-${i % 250}`, date: "2026-06-15", status: "open", description: `Synthetic repair ${i}`, performance_fixture: true }));
  insertBatches("downtimes", 1250, (i) => ({ id: `${orgId}-down-${i}`, org_id: orgId, vehicle_id: `${orgId}-v-${i % 250}`, start_date: "2026-06-15", status: "open", reason: `Synthetic downtime ${i}`, performance_fixture: true }));
  insertBatches("documents", 2500, (i) => ({ id: `${orgId}-doc-${i}`, org_id: orgId, vehicle_id: `${orgId}-v-${i % 250}`, doc_type: "Insurance", doc_number: `DOC-${suffix}-${i}`, expiry_date: "2027-06-15", performance_fixture: true }));
  insertBatches("tyres", 250, (i) => ({ id: `${orgId}-tyre-${i}`, org_id: orgId, vehicle_id: `${orgId}-v-${i}`, serial_number: `PERF-TYRE-${suffix}-${i}`, status: "fitted", performance_fixture: true }));
  insertBatches("accidents", 100, (i) => ({ id: `${orgId}-acc-${i}`, org_id: orgId, vehicle_id: `${orgId}-v-${i % 250}`, date: "2026-06-12", status: "reported", claim_status: "submitted", performance_fixture: true }));
  insertBatches("exception_acks", 100, (i) => ({ id: `${orgId}-exception-${i}`, org_id: orgId, exception_id: `${orgId}-exception-${i}`, status: "open", performance_fixture: true }));
}
printjson({ database: db.getName(), organisations: 2, vehicles: 500, drivers: 500, trips: 20000, expenses_payments_advances: 80000, fuel: 20000, fastag: 20000, repairs_and_downtime: 5000, documents: 5000 });
