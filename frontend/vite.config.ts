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
  resolve: {
    alias: {
      // greeting.json is owned by the Python package; alias it so the import path
      // does not have to climb out of frontend/.
      "@data": fileURLToPath(
        new URL("../backend/src/expense_tracker", import.meta.url),
      ),
    },
  },
  server: {
    fs: {
      // vite derives its serving allow-list from the nearest package.json, which is
      // now frontend/ - so greeting.json over in the Python package would be denied.
      // Only the dev server and vitest enforce this; `vite build` does not, so
      // without this line the build passes and only `pixi run web-test` fails.
      allow: [fileURLToPath(new URL("../", import.meta.url))],
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
