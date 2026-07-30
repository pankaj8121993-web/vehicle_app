const POSITIVE_NAMES = new Set(["quantity", "litres"]);
const DATE_PAIRS = [
  ["issue_date", "expiry_date"],
  ["start_date", "end_date"],
  ["purchase_date", "disposal_date"],
];

export const validateCrudForm = (fields, values) => {
  const errors = {};
  for (const field of fields) {
    const value = values[field.name];
    if (field.required && (value === undefined || value === null || String(value).trim() === "")) {
      errors[field.name] = `${field.label} is required`;
      continue;
    }
    if (field.type === "number" && value !== "" && value !== null && value !== undefined) {
      const number = Number(value);
      if (!Number.isFinite(number)) errors[field.name] = `${field.label} must be a valid number`;
      else if (POSITIVE_NAMES.has(field.name) && number <= 0) errors[field.name] = `${field.label} must be greater than zero`;
      else if (number < 0) errors[field.name] = `${field.label} cannot be negative`;
    }
  }
  for (const [start, end] of DATE_PAIRS) {
    if (values[start] && values[end] && values[end] < values[start]) {
      const label = fields.find((field) => field.name === end)?.label || end;
      errors[end] = `${label} cannot be before ${fields.find((field) => field.name === start)?.label || start}`;
    }
  }
  if (values.opening_km !== undefined && values.closing_km !== undefined && values.closing_km !== "" && Number(values.closing_km) < Number(values.opening_km)) {
    errors.closing_km = "Closing kilometre cannot be less than opening kilometre";
  }
  return errors;
};

export const explainApiError = (error, fallback = "The action could not be completed.") => {
  const status = error?.response?.status;
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg).filter(Boolean).join(". ") || fallback;
  }
  if (typeof detail === "string" && detail.length <= 300) return detail;
  if (status === 403) return "You do not have permission to perform this action.";
  if (status === 409) return "This record conflicts with an existing record or has changed. Review it and try again.";
  if (status === 422) return "Some fields are invalid. Review the highlighted values and try again.";
  if (!error?.response) return "The network is unavailable. Check your connection and try again.";
  return fallback;
};

export const recordLabel = (record = {}) => {
  const value = record || {};
  return value.vehicle_number || value.name || value.title || value.employee_number ||
    value.doc_number || value.id || "selected record";
};
