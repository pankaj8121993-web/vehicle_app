import { explainApiError, recordLabel, validateCrudForm } from "@/lib/formSafety";

const fields = [
  { name: "name", label: "Name", required: true },
  { name: "quantity", label: "Quantity", type: "number" },
  { name: "amount", label: "Amount", type: "number" },
  { name: "issue_date", label: "Issue date", type: "date" },
  { name: "expiry_date", label: "Expiry date", type: "date" },
  { name: "opening_km", label: "Opening kilometre", type: "number" },
  { name: "closing_km", label: "Closing kilometre", type: "number" },
];

describe("form safety", () => {
  test("associates required errors with their field", () => {
    expect(validateCrudForm(fields, {}).name).toBe("Name is required");
  });

  test("requires positive quantities", () => {
    expect(validateCrudForm(fields, { name: "Fuel", quantity: 0 }).quantity).toMatch(/greater than zero/);
  });

  test("rejects negative money and odometer values", () => {
    const errors = validateCrudForm(fields, { name: "Fuel", amount: -1, opening_km: -2 });
    expect(errors.amount).toMatch(/cannot be negative/);
    expect(errors.opening_km).toMatch(/cannot be negative/);
  });

  test("rejects reversed date ranges", () => {
    expect(validateCrudForm(fields, { name: "Policy", issue_date: "2026-07-02", expiry_date: "2026-07-01" }).expiry_date).toMatch(/cannot be before/);
  });

  test("rejects closing kilometre below opening kilometre", () => {
    expect(validateCrudForm(fields, { name: "Trip", opening_km: 100, closing_km: 99 }).closing_km).toMatch(/cannot be less/);
  });

  test("explains common backend status responses", () => {
    expect(explainApiError({ response: { status: 403 } })).toMatch(/permission/);
    expect(explainApiError({ response: { status: 409 } })).toMatch(/conflicts/);
    expect(explainApiError({ response: { status: 422 } })).toMatch(/invalid/);
  });

  test("does not expose oversized raw backend exceptions", () => {
    expect(explainApiError({ response: { status: 500, data: { detail: "x".repeat(500) } } }, "Safe message")).toBe("Safe message");
  });

  test("identifies destructive-action records", () => {
    expect(recordLabel({ vehicle_number: "MH12AB1234", id: "secret-id" })).toBe("MH12AB1234");
  });
});
