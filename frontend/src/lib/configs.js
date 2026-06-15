// Module configurations: columns + form fields per module.
// Used by both standalone pages and Vehicle Profile tabs.

export const SERVICE_TYPES = ["Full Service", "Minor Service", "Oil Change", "Brake Service", "Clutch Service", "Battery Service", "Other"];
export const DOC_TYPES = ["RC", "Insurance", "Fitness", "Permit", "PUC", "Road Tax", "Fastag", "Other"];
export const EXPENSE_CATEGORIES = ["Insurance", "Permit", "Road Tax", "Fitness", "Parking", "Driver Allowance", "Fines/Challan", "Washing", "Miscellaneous"];

const sel = (arr) => arr.map((v) => ({ value: v, label: v }));

export const vehicleConfig = {
  title: "Vehicle",
  endpoint: "vehicles",
  columns: [
    { key: "vehicle_number", label: "Vehicle No" },
    { key: "make", label: "Make" },
    { key: "model", label: "Model" },
    { key: "vtype", label: "Type" },
    { key: "fuel_type", label: "Fuel" },
    { key: "status", label: "Status", type: "badge" },
    { key: "current_odometer", label: "Odometer (KM)", type: "number" },
    { key: "fastag_balance", label: "Fastag Bal", type: "currency" },
  ],
  fields: [
    { name: "vehicle_number", label: "Vehicle Number", required: true, placeholder: "MH 12 AB 1234" },
    { name: "make", label: "Make", placeholder: "Tata" },
    { name: "model", label: "Model", placeholder: "Ace Gold" },
    { name: "vtype", label: "Vehicle Type", type: "select", options: sel(["Truck", "Mini Truck", "Pickup", "Van", "Tempo", "Car", "Bike", "Other"]) },
    { name: "fuel_type", label: "Fuel Type", type: "select", options: sel(["Diesel", "Petrol", "CNG", "Electric"]) },
    { name: "chassis_number", label: "Chassis Number" },
    { name: "engine_number", label: "Engine Number" },
    { name: "purchase_date", label: "Purchase Date", type: "date" },
    { name: "purchase_price", label: "Purchase Price", type: "number", suffix: "₹" },
    { name: "current_odometer", label: "Current Odometer", type: "number", suffix: "KM", default: 0 },
    { name: "status", label: "Status", type: "select", options: sel(["active", "under_repair", "idle", "sold", "scrapped"]), default: "active" },
    { name: "fastag_number", label: "Fastag Number" },
    { name: "fastag_bank", label: "Fastag Bank" },
    { name: "fastag_balance", label: "Fastag Balance", type: "number", suffix: "₹", default: 0 },
    { name: "disposal_date", label: "Disposal Date (Sold/Scrapped)", type: "date" },
    { name: "sale_value", label: "Sale Value", type: "number", suffix: "₹" },
    { name: "buyer_name", label: "Buyer Name" },
    { name: "buyer_contact", label: "Buyer Contact" },
    { name: "disposal_remarks", label: "Disposal Remarks", type: "textarea" },
    { name: "notes", label: "Notes", type: "textarea" },
  ],
};

export const driverConfig = {
  title: "Driver",
  endpoint: "drivers",
  columns: [
    { key: "name", label: "Name" },
    { key: "mobile", label: "Mobile" },
    { key: "license_number", label: "License No" },
    { key: "license_expiry", label: "License Expiry", type: "expiry" },
    { key: "assigned_vehicle_number", label: "Assigned Vehicle" },
    { key: "status", label: "Status", type: "badge" },
  ],
  fields: [
    { name: "name", label: "Full Name", required: true },
    { name: "mobile", label: "Mobile Number" },
    { name: "address", label: "Address", type: "textarea" },
    { name: "aadhaar", label: "Aadhaar Number" },
    { name: "license_number", label: "License Number" },
    { name: "license_expiry", label: "License Expiry", type: "date" },
    { name: "assigned_vehicle_id", label: "Assigned Vehicle", type: "vehicle" },
    { name: "status", label: "Status", type: "select", options: sel(["active", "on_leave", "resigned", "terminated"]), default: "active" },
    { name: "exit_date", label: "Exit Date (Resigned/Terminated)", type: "date" },
    { name: "exit_reason", label: "Exit Reason", type: "textarea" },
    { name: "photo_file_id", label: "Photo / License Copy", type: "file" },
  ],
};

export const documentConfig = {
  title: "Document",
  endpoint: "documents",
  columns: [
    { key: "vehicle_number", label: "Vehicle" },
    { key: "doc_type", label: "Document" },
    { key: "doc_number", label: "Number" },
    { key: "issue_date", label: "Issued", type: "date" },
    { key: "expiry_date", label: "Expiry", type: "expiry" },
    { key: "file_id", label: "File", type: "file" },
  ],
  fields: [
    { name: "vehicle_id", label: "Vehicle", type: "vehicle", required: true },
    { name: "doc_type", label: "Document Type", type: "select", options: sel(DOC_TYPES), required: true },
    { name: "doc_number", label: "Document Number" },
    { name: "issue_date", label: "Issue Date", type: "date" },
    { name: "expiry_date", label: "Expiry Date", type: "date" },
    { name: "file_id", label: "Upload Document", type: "file" },
    { name: "notes", label: "Notes", type: "textarea" },
  ],
};

export const tripConfig = {
  title: "Trip",
  endpoint: "trips",
  columns: [
    { key: "date", label: "Date", type: "date" },
    { key: "vehicle_number", label: "Vehicle" },
    { key: "driver_name", label: "Driver" },
    { key: "origin", label: "Origin" },
    { key: "destination", label: "Destination" },
    { key: "opening_km", label: "Opening KM", type: "number" },
    { key: "closing_km", label: "Closing KM", type: "number" },
    { key: "distance", label: "Distance (KM)", type: "number" },
    { key: "status", label: "Status", type: "badge" },
    { key: "file_id", label: "POD", type: "file" },
  ],
  fields: [
    { name: "date", label: "Trip Date", type: "date", required: true },
    { name: "vehicle_id", label: "Vehicle", type: "vehicle", required: true },
    { name: "driver_id", label: "Driver", type: "driver" },
    { name: "origin", label: "Origin" },
    { name: "destination", label: "Destination" },
    { name: "purpose", label: "Purpose" },
    { name: "opening_km", label: "Opening KM", type: "number", required: true, suffix: "KM" },
    { name: "closing_km", label: "Closing KM (leave blank if ongoing)", type: "number", suffix: "KM" },
    { name: "toll_expense", label: "Toll Expense", type: "number", suffix: "₹", default: 0 },
    { name: "parking_expense", label: "Parking Expense", type: "number", suffix: "₹", default: 0 },
    { name: "misc_expense", label: "Misc Expense", type: "number", suffix: "₹", default: 0 },
    { name: "file_id", label: "POD / Challan / E-way Bill", type: "file" },
    { name: "notes", label: "Notes", type: "textarea" },
  ],
};

export const fuelConfig = {
  title: "Fuel Entry",
  endpoint: "fuel",
  columns: [
    { key: "date", label: "Date", type: "date" },
    { key: "vehicle_number", label: "Vehicle" },
    { key: "driver_name", label: "Driver" },
    { key: "odometer", label: "Odometer", type: "number" },
    { key: "quantity", label: "Litres", type: "number" },
    { key: "amount", label: "Amount", type: "currency" },
    { key: "mileage", label: "Mileage (KM/L)", type: "number" },
    { key: "station", label: "Station" },
    { key: "file_id", label: "Invoice", type: "file" },
  ],
  fields: [
    { name: "date", label: "Date", type: "date", required: true },
    { name: "vehicle_id", label: "Vehicle", type: "vehicle", required: true },
    { name: "driver_id", label: "Driver", type: "driver" },
    { name: "odometer", label: "Odometer Reading", type: "number", required: true, suffix: "KM" },
    { name: "quantity", label: "Fuel Quantity", type: "number", required: true, suffix: "L" },
    { name: "amount", label: "Fuel Amount", type: "number", required: true, suffix: "₹" },
    { name: "station", label: "Fuel Station" },
    { name: "file_id", label: "Invoice Upload", type: "file" },
    { name: "notes", label: "Notes", type: "textarea" },
  ],
};

export const serviceConfig = {
  title: "Service",
  endpoint: "services",
  columns: [
    { key: "date", label: "Date", type: "date" },
    { key: "vehicle_number", label: "Vehicle" },
    { key: "service_type", label: "Service Type" },
    { key: "odometer", label: "Odometer", type: "number" },
    { key: "vendor", label: "Vendor" },
    { key: "cost", label: "Cost", type: "currency" },
    { key: "next_due_date", label: "Next Due", type: "expiry" },
    { key: "next_due_km", label: "Next Due KM", type: "number" },
    { key: "file_id", label: "Invoice", type: "file" },
  ],
  fields: [
    { name: "vehicle_id", label: "Vehicle", type: "vehicle", required: true },
    { name: "service_type", label: "Service Type", type: "select", options: sel(SERVICE_TYPES), required: true },
    { name: "date", label: "Service Date", type: "date", required: true },
    { name: "odometer", label: "Odometer", type: "number", suffix: "KM" },
    { name: "vendor", label: "Vendor / Workshop" },
    { name: "responsible_person", label: "Person Responsible" },
    { name: "cost", label: "Cost", type: "number", suffix: "₹", default: 0 },
    { name: "next_due_date", label: "Next Due Date", type: "date" },
    { name: "next_due_km", label: "Next Due KM", type: "number", suffix: "KM" },
    { name: "file_id", label: "Invoice Upload", type: "file" },
    { name: "notes", label: "Notes", type: "textarea" },
  ],
};

export const repairConfig = {
  title: "Repair",
  endpoint: "repairs",
  columns: [
    { key: "date", label: "Date", type: "date" },
    { key: "vehicle_number", label: "Vehicle" },
    { key: "repair_type", label: "Type", type: "badge" },
    { key: "issue", label: "Issue" },
    { key: "vendor", label: "Vendor" },
    { key: "cost", label: "Cost", type: "currency" },
    { key: "downtime_days", label: "Downtime (D)", type: "number" },
    { key: "status", label: "Status", type: "badge" },
  ],
  fields: [
    { name: "vehicle_id", label: "Vehicle", type: "vehicle", required: true },
    { name: "repair_type", label: "Repair Type", type: "select", options: [{ value: "minor", label: "Minor (direct entry)" }, { value: "major", label: "Major (approval workflow)" }], required: true },
    { name: "issue", label: "Issue / Breakdown", required: true },
    { name: "date", label: "Date", type: "date", required: true },
    { name: "vendor", label: "Vendor" },
    { name: "cost", label: "Repair Cost", type: "number", suffix: "₹", default: 0 },
    { name: "downtime_days", label: "Downtime Days", type: "number", default: 0 },
    { name: "root_cause", label: "Root Cause" },
    { name: "file_id", label: "Invoice Upload", type: "file" },
    { name: "notes", label: "Notes", type: "textarea" },
  ],
};

export const tyreConfig = {
  title: "Tyre",
  endpoint: "tyres",
  columns: [
    { key: "tyre_number", label: "Tyre No" },
    { key: "vehicle_number", label: "Vehicle" },
    { key: "brand", label: "Brand" },
    { key: "size", label: "Size" },
    { key: "position", label: "Position" },
    { key: "installation_date", label: "Installed", type: "date" },
    { key: "installation_km", label: "Install KM", type: "number" },
    { key: "cost", label: "Cost", type: "currency" },
    { key: "status", label: "Status", type: "badge" },
  ],
  fields: [
    { name: "vehicle_id", label: "Vehicle", type: "vehicle", required: true },
    { name: "tyre_number", label: "Tyre Number", required: true },
    { name: "brand", label: "Brand" },
    { name: "size", label: "Size" },
    { name: "position", label: "Position", type: "select", options: sel(["Front Left", "Front Right", "Rear Left", "Rear Right", "Rear Left Inner", "Rear Right Inner", "Stepney"]) },
    { name: "installation_date", label: "Installation Date", type: "date" },
    { name: "installation_km", label: "Installation KM", type: "number", suffix: "KM" },
    { name: "cost", label: "Cost", type: "number", suffix: "₹", default: 0 },
    { name: "notes", label: "Notes", type: "textarea" },
  ],
};

export const tyreEventConfig = {
  title: "Tyre Event",
  endpoint: "tyre-events",
  columns: [
    { key: "date", label: "Date", type: "date" },
    { key: "event_type", label: "Event", type: "badge" },
    { key: "vehicle_number", label: "Vehicle" },
    { key: "odometer", label: "Odometer", type: "number" },
    { key: "cost", label: "Cost", type: "currency" },
    { key: "notes", label: "Notes" },
  ],
  fields: [
    { name: "tyre_id", label: "Tyre", type: "tyre", required: true },
    { name: "event_type", label: "Event Type", type: "select", options: sel(["puncture", "rotation", "retreading", "replacement"]), required: true },
    { name: "date", label: "Date", type: "date", required: true },
    { name: "odometer", label: "Odometer", type: "number", suffix: "KM" },
    { name: "cost", label: "Cost", type: "number", suffix: "₹", default: 0 },
    { name: "notes", label: "Notes", type: "textarea" },
  ],
};

export const accidentConfig = {
  title: "Accident",
  endpoint: "accidents",
  columns: [
    { key: "date", label: "Date", type: "date" },
    { key: "vehicle_number", label: "Vehicle" },
    { key: "driver_name", label: "Driver" },
    { key: "location", label: "Location" },
    { key: "fir_number", label: "FIR No" },
    { key: "repair_cost", label: "Repair Cost", type: "currency" },
    { key: "claim_amount", label: "Claim", type: "currency" },
    { key: "claim_status", label: "Claim Status" },
    { key: "file_id", label: "Photos/Docs", type: "file" },
  ],
  fields: [
    { name: "vehicle_id", label: "Vehicle", type: "vehicle", required: true },
    { name: "driver_id", label: "Driver", type: "driver" },
    { name: "date", label: "Date", type: "date", required: true },
    { name: "time", label: "Time", placeholder: "14:30" },
    { name: "location", label: "Location" },
    { name: "description", label: "Description", type: "textarea" },
    { name: "fir_number", label: "FIR Number" },
    { name: "insurance_claim_number", label: "Insurance Claim Number" },
    { name: "claim_status", label: "Claim Status", type: "select", options: sel(["Not Filed", "Filed", "Approved", "Rejected", "Settled"]) },
    { name: "repair_cost", label: "Repair Cost", type: "number", suffix: "₹", default: 0 },
    { name: "claim_amount", label: "Claim Amount", type: "number", suffix: "₹", default: 0 },
    { name: "settlement_amount", label: "Settlement Amount", type: "number", suffix: "₹", default: 0 },
    { name: "file_id", label: "Photos / FIR Copy", type: "file" },
  ],
};

export const fastagConfig = {
  title: "Fastag Transaction",
  endpoint: "fastag",
  columns: [
    { key: "date", label: "Date", type: "date" },
    { key: "vehicle_number", label: "Vehicle" },
    { key: "txn_type", label: "Type", type: "badge" },
    { key: "toll_plaza", label: "Toll Plaza" },
    { key: "amount", label: "Amount", type: "currency" },
  ],
  fields: [
    { name: "vehicle_id", label: "Vehicle", type: "vehicle", required: true },
    { name: "txn_type", label: "Transaction Type", type: "select", options: [{ value: "toll", label: "Toll Deduction" }, { value: "recharge", label: "Recharge" }], required: true },
    { name: "date", label: "Date", type: "date", required: true },
    { name: "toll_plaza", label: "Toll Plaza (for toll)" },
    { name: "amount", label: "Amount", type: "number", required: true, suffix: "₹" },
    { name: "notes", label: "Notes", type: "textarea" },
  ],
};

export const downtimeConfig = {
  title: "Downtime",
  endpoint: "downtime",
  columns: [
    { key: "vehicle_number", label: "Vehicle" },
    { key: "reason", label: "Reason", type: "badge" },
    { key: "start_date", label: "Start", type: "date" },
    { key: "end_date", label: "End", type: "date" },
    { key: "days", label: "Days", type: "number" },
    { key: "status", label: "Status", type: "badge" },
  ],
  fields: [
    { name: "vehicle_id", label: "Vehicle", type: "vehicle", required: true },
    { name: "reason", label: "Reason", type: "select", options: sel(["service", "breakdown", "accident", "compliance", "other"]), required: true },
    { name: "start_date", label: "Start Date", type: "date", required: true },
    { name: "end_date", label: "End Date (blank if ongoing)", type: "date" },
    { name: "notes", label: "Notes", type: "textarea" },
  ],
};

export const expenseConfig = {
  title: "Expense",
  endpoint: "expenses",
  columns: [
    { key: "date", label: "Date", type: "date" },
    { key: "vehicle_number", label: "Vehicle" },
    { key: "category", label: "Category" },
    { key: "description", label: "Description" },
    { key: "amount", label: "Amount", type: "currency" },
    { key: "file_id", label: "Invoice", type: "file" },
  ],
  fields: [
    { name: "vehicle_id", label: "Vehicle", type: "vehicle", required: true },
    { name: "category", label: "Category", type: "select", options: sel(EXPENSE_CATEGORIES), required: true },
    { name: "date", label: "Date", type: "date", required: true },
    { name: "amount", label: "Amount", type: "number", required: true, suffix: "₹" },
    { name: "description", label: "Description" },
    { name: "file_id", label: "Invoice Upload", type: "file" },
  ],
};
