import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./msw/server";

beforeAll(() => {
  // "error" turns a request nobody stubbed into a failing test rather than a silent
  // attempt to reach the real network.
  server.listen({ onUnhandledRequest: "error" });
});

afterEach(() => {
  // Drops any per-test override added with server.use(), so one test's failure stub
  // cannot leak into the next.
  server.resetHandlers();
  // RTL's automatic cleanup only registers itself when vitest globals are enabled;
  // they are not, so unmount explicitly between tests.
  cleanup();
});

afterAll(() => {
  server.close();
});
