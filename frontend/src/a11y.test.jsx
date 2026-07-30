/**
 * UX-05 accessibility unit checks (jest-axe / WCAG 2.2 AA).
 *
 * Renders key UI surfaces in isolation and asserts axe finds no violations.
 * This runs in the normal Jest suite (and therefore CI), so a regression that
 * introduces a missing label, a contrast problem or an unnamed control fails
 * the build.
 */
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { axe } from "jest-axe";
import Login from "@/pages/Login";
import PermissionDenied from "@/pages/PermissionDenied";
import NotFound from "@/pages/NotFound";
import { useAuth } from "@/context/AuthContext";

jest.mock("@/context/AuthContext", () => ({ useAuth: jest.fn() }));

const renderWithRouter = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("accessibility (jest-axe)", () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ login: jest.fn(), user: null, loading: false });
  });

  test("login page has no axe violations", async () => {
    const { container } = renderWithRouter(<Login />);
    expect(await axe(container)).toHaveNoViolations();
  });

  test("permission-denied page has no axe violations", async () => {
    const { container } = renderWithRouter(<PermissionDenied />);
    expect(await axe(container)).toHaveNoViolations();
  });

  test("not-found page has no axe violations", async () => {
    const { container } = renderWithRouter(<NotFound />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
