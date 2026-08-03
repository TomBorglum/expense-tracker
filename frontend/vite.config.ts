import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
// vitest re-exports vite's defineConfig with the `test` block typed, so one config
// serves both `vite build` and `vitest run`.
import { defineConfig } from "vitest/config";

// The build output goes straight into the Python package so hatchling ships it in
// the wheel and the lean prod pixi environment never needs Node. vite's root is
// this file's directory (frontend/), so the paths below are relative to that.
export default defineConfig({
  // The backend mounts the package's static/ folder at /static/, so emitted asset
  // URLs must carry that prefix.
  base: "/static/",
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // `pnpm dev` serves the page from vite's own port while the API runs on
      // uvicorn's 8000, so the fetch would otherwise be cross-origin. The built bundle
      // is served by FastAPI itself, so this matters only in dev - run `pixi run
      // serve` alongside it.
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "../backend/src/expense_tracker/static",
    // outDir sits outside vite's root, so vite needs explicit permission to clear it.
    emptyOutDir: true,
    assetsDir: "assets",
  },
  test: {
    // Pin vitest to the repo root (the ../ climb out of frontend/), unlike vite's
    // root above. Otherwise lcov records paths like "src/App.tsx", which SonarCloud
    // resolves from the repo root against the Python package instead of the
    // frontend. Everything else in this block is deliberately repo-root relative
    // for the same reason.
    root: fileURLToPath(new URL("../", import.meta.url)),
    environment: "jsdom",
    include: ["frontend/tests/**/*.test.{ts,tsx}"],
    // Starts the MSW server and unmounts React between tests. Repo-root relative like
    // everything else in this block, because test.root is pinned above.
    setupFiles: ["frontend/tests/setup.ts"],
    coverage: {
      provider: "v8",
      // lcov is what SonarCloud ingests; text keeps the summary visible in CI logs.
      reporter: ["text", "lcov"],
      reportsDirectory: "coverage/frontend",
      include: ["frontend/src/**/*.{ts,tsx}"],
      // Bootstrap only: wires React to the DOM and has no logic worth asserting.
      // Also listed in sonar.coverage.exclusions so both tools agree.
      exclude: ["frontend/src/main.tsx"],
    },
  },
});
