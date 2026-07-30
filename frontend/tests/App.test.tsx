import greeting from "@data/greeting.json";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import App from "../src/App";

// RTL's automatic cleanup only registers itself when vitest globals are enabled;
// they are not, so unmount explicitly between tests.
afterEach(cleanup);

test("renders the greeting from greeting.json", () => {
  render(<App />);
  // The Python side asserts the same file reaches the served page (see
  // tests/test_app.py). Together they pin both ends of the single source of truth.
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(greeting.greeting);
});
