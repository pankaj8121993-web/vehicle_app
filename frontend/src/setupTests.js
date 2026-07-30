import "@testing-library/jest-dom";
import { toHaveNoViolations } from "jest-axe";
import { TextDecoder, TextEncoder } from "util";

// jest-axe: assert rendered UI has no WCAG violations (UX-05).
expect.extend(toHaveNoViolations);

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;
