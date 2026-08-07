import { afterEach, expect, test, vi } from "vitest";

import { apiUrl } from "@/api/greeting";

// apiUrl reads import.meta.env at call time rather than closing over it, which is what
// lets these stub a base URL per test. GREETING_URL is resolved at module load from the
// real frontend/.env and is unaffected by any of this.
afterEach(() => {
  vi.unstubAllEnvs();
});

test("resolves a path against a bare origin", () => {
  vi.stubEnv("VITE_API_BASE_URL", "http://localhost:8000");
  expect(apiUrl("/api/greeting")).toBe("http://localhost:8000/api/greeting");
});

test("keeps a path prefix on the base", () => {
  // The case a bare `new URL("/api/greeting", base)` gets wrong: it resolves the
  // leading slash against the origin and drops the /v1 without complaining.
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.com/v1");
  expect(apiUrl("/api/greeting")).toBe("https://api.example.com/v1/api/greeting");
});

test("accepts a path that is already relative", () => {
  // Every caller passes a rooted path today, because that is the form the backend route
  // is written in. Taking both keeps the slash handling in one place rather than at the
  // call sites.
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.com/v1");
  expect(apiUrl("api/greeting")).toBe("https://api.example.com/v1/api/greeting");
});

test("does not double the separator when the base already ends in a slash", () => {
  vi.stubEnv("VITE_API_BASE_URL", "https://api.example.com/v1/");
  expect(apiUrl("/api/greeting")).toBe("https://api.example.com/v1/api/greeting");
});

test("names the missing variable instead of throwing an opaque TypeError", () => {
  // An unset value is a misconfigured build, and vite inlines it, so there is nothing
  // to recover from - only something to say clearly. Left to `new URL(path, "")` this
  // is a bare "Invalid URL" from module scope, which reaches the page as a blank
  // screen.
  vi.stubEnv("VITE_API_BASE_URL", "");
  expect(() => apiUrl("/api/greeting")).toThrow("VITE_API_BASE_URL is not set");
});
