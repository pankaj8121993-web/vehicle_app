import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CrudModule } from "@/components/CrudModule";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

jest.mock("@/lib/api", () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() }));
jest.mock("@/context/AuthContext", () => ({ useAuth: jest.fn() }));

const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};
const response = (label, total = 1) => ({
  data: { items: total ? [{ id: label, name: label }] : [], total, page: 1, page_size: 25, total_pages: total ? 1 : 0 },
});

describe("CrudModule server query behavior", () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ user: { role: "viewer" } });
    api.get.mockReset();
  });

  test("debounces search, ignores stale responses, clears search and keeps filters when sorting", async () => {
    const initial = deferred();
    const alpha = deferred();
    const beta = deferred();
    const cleared = deferred();
    const sorted = deferred();
    api.get
      .mockReturnValueOnce(initial.promise)
      .mockReturnValueOnce(alpha.promise)
      .mockReturnValueOnce(beta.promise)
      .mockReturnValueOnce(cleared.promise)
      .mockReturnValueOnce(sorted.promise);

    render(
      <CrudModule
        title="Records" endpoint="records" testIdPrefix="records"
        columns={[{ key: "name", label: "Name" }]} fields={[]}
        fixedFilters={{ status: "active" }} readOnly
      />,
    );
    initial.resolve(response("initial"));
    expect(await screen.findByText("initial")).toBeInTheDocument();

    const search = screen.getByTestId("records-search-input");
    await userEvent.type(search, "alpha");
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2), { timeout: 1000 });
    await userEvent.clear(search);
    await userEvent.type(search, "beta");
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(3), { timeout: 1000 });
    beta.resolve(response("beta-result"));
    expect(await screen.findByText("beta-result")).toBeInTheDocument();
    alpha.resolve(response("alpha-stale"));
    await waitFor(() => expect(screen.queryByText("alpha-stale")).not.toBeInTheDocument());

    await userEvent.clear(search);
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(4), { timeout: 1000 });
    cleared.resolve(response("cleared-result"));
    expect(await screen.findByText("cleared-result")).toBeInTheDocument();
    expect(api.get.mock.calls[3][1].params.search).toBeUndefined();

    await userEvent.click(screen.getByTestId("records-sort-name"));
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(5));
    expect(api.get.mock.calls[4][1].params).toMatchObject({
      status: "active", sort_by: "name", sort_dir: "asc", page: 1,
    });
    sorted.resolve(response("sorted-result"));
    expect(await screen.findByText("sorted-result")).toBeInTheDocument();
  });

  test("shows an explicit no-results state", async () => {
    api.get.mockResolvedValue(response("none", 0));
    render(
      <CrudModule title="Records" endpoint="records" testIdPrefix="records"
        columns={[{ key: "name", label: "Name" }]} fields={[]} readOnly />,
    );
    expect(await screen.findByTestId("records-empty-state")).toHaveTextContent("No records records yet.");
  });
});
