import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRouter } from "@/App";
import { useAuth } from "@/context/AuthContext";

jest.mock("@/context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("@/lib/api", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("@/components/Layout", () => ({ Layout: ({ children }) => <div data-testid="layout">{children}</div> }));
jest.mock("@/pages/Landing", () => () => <div>Landing page</div>);
jest.mock("@/pages/Onboarding", () => () => <div>Get started page</div>);
jest.mock("@/pages/DemoEntry", () => () => <div>Demo entry page</div>);
jest.mock("@/pages/Login", () => () => <div>Login page</div>);
jest.mock("@/pages/Dashboard", () => () => <div>Dashboard page</div>);
jest.mock("@/pages/DriverHome", () => () => <div>Driver home</div>);
jest.mock("@/pages/Vehicles", () => () => <div>Vehicles page</div>);

const renderRoute = (path, auth) => {
  useAuth.mockReturnValue(auth);
  return render(<MemoryRouter initialEntries={[path]}><AppRouter /></MemoryRouter>);
};

describe("route guards", () => {
  test.each([
    ["/", "Landing page"],
    ["/get-started", "Get started page"],
    ["/demo", "Demo entry page"],
    ["/login", "Login page"],
  ])("keeps public/guest route %s stable after anonymous hydration", async (path, label) => {
    renderRoute(path, { user: null, loading: false });
    // Guest/marketing pages are code-split, so they resolve through Suspense.
    expect(await screen.findByText(label)).toBeInTheDocument();
  });

  test("waits for authentication hydration without flashing a page", () => {
    renderRoute("/dashboard", { user: null, loading: true });
    expect(screen.getByLabelText("Checking your session")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard page")).not.toBeInTheDocument();
  });

  test("redirects an anonymous protected route to login", async () => {
    renderRoute("/vehicles", { user: null, loading: false });
    expect(await screen.findByText("Login page")).toBeInTheDocument();
  });

  test("renders permission denied instead of silently redirecting", () => {
    renderRoute("/vehicles", { user: { role: "viewer", modules: ["dashboard"] }, loading: false });
    expect(screen.getByText("You don’t have access")).toBeInTheDocument();
    expect(screen.getByText("This module is not available for your account.")).toBeInTheDocument();
  });

  test("routes an authenticated user away from guest-only login", async () => {
    renderRoute("/login", { user: { role: "viewer", modules: ["dashboard"] }, loading: false });
    expect(await screen.findByText("Dashboard page")).toBeInTheDocument();
  });

  test("shows a useful broken-route fallback", () => {
    renderRoute("/definitely-missing", { user: null, loading: false });
    expect(screen.getByText("Page not found")).toBeInTheDocument();
  });
});
