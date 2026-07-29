import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TripLifecycleActions, ExpenseApprovalActions } from "@/pages/ModulePages";
import api from "@/lib/api";

jest.mock("@/lib/api", () => ({
  get: jest.fn(), post: jest.fn(), patch: jest.fn(), put: jest.fn(), delete: jest.fn(),
}));

describe("high-risk domain action dialogs", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("trip completion enforces odometer order and retains values/dialog after API failure", async () => {
    api.patch.mockRejectedValue({ response: { status: 422, data: { detail: "Closing odometer is invalid" } } });
    const refresh = jest.fn();
    render(TripLifecycleActions({ id: "trip-1", status: "ongoing", opening_km: 100 }, refresh));
    await userEvent.click(screen.getByTestId("close-trip-trip-1"));
    const input = screen.getByTestId("close-trip-km-input");
    await userEvent.type(input, "99");
    await userEvent.click(screen.getByTestId("close-trip-confirm"));
    expect(await screen.findByRole("alert")).toHaveTextContent("at least 100");
    expect(api.patch).not.toHaveBeenCalled();

    await userEvent.clear(input);
    await userEvent.type(input, "125");
    await userEvent.click(screen.getByTestId("close-trip-confirm"));
    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("close-trip-km-input")).toHaveValue(125);
    expect(screen.getByText("Complete Trip — Enter Closing KM")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });

  test("trip completion locks duplicate clicks while the request is pending", async () => {
    let finish;
    api.patch.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    render(TripLifecycleActions({ id: "trip-2", status: "ongoing", opening_km: 1 }, jest.fn()));
    await userEvent.click(screen.getByTestId("close-trip-trip-2"));
    await userEvent.type(screen.getByTestId("close-trip-km-input"), "2");
    const confirm = screen.getByTestId("close-trip-confirm");
    await userEvent.click(confirm);
    expect(confirm).toBeDisabled();
    await userEvent.click(confirm);
    expect(api.patch).toHaveBeenCalledTimes(1);
    await act(async () => finish({ data: {} }));
  });

  test("expense approval retains its dialog on 403 and disables invalid payment amounts", async () => {
    api.patch.mockRejectedValue({ response: { status: 403, data: { detail: "Not permitted" } } });
    const approval = render(ExpenseApprovalActions({ id: "expense-1", amount: 500, approval_status: "submitted" }, jest.fn()));
    await userEvent.click(screen.getByTestId("approve-expense-expense-1"));
    await userEvent.click(screen.getByTestId("approve-expense-confirm"));
    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect(screen.getByText("Approve Expense")).toBeInTheDocument();
    expect(screen.getByTestId("approve-expense-amount")).toHaveValue(500);
    approval.unmount();

    render(ExpenseApprovalActions({
      id: "expense-2", amount: 500, approval_status: "approved",
      approved_amount: 500, paid_amount: 100,
    }, jest.fn()));
    await userEvent.click(screen.getByTestId("pay-expense-expense-2"));
    const pay = screen.getByTestId("pay-expense-amount");
    await userEvent.type(pay, "401");
    expect(screen.getByTestId("pay-expense-confirm")).toBeDisabled();
  });
});
