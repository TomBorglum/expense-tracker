import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
// vitest re-exports vite's defineConfig with the `test` block typed, so one config
// serves both `vite build` and `vitest run`.
import { defineConfig } from "vitest/config";

// The frontend sources live in frontend/, but the build output goes straight into
// the Python package so hatchling ships it in the wheel and the lean prod pixi
// environment never needs Node.
export default defineConfig({
  root: "frontend",
  // The backend mounts the package's static/ folder at /static/, so emitted asset
  // URLs must carry that prefix.
  base: "/static/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // greeting.json is owned by the Python package; alias it so the import path
      // does not have to climb out of frontend/.
      "@data": fileURLToPath(new URL("./src/expense_tracker", import.meta.url)),
    },
  },
  build: {
    outDir: "../src/expense_tracker/static",
    // outDir sits outside vite's root, so vite needs explicit permission to clear it.
    emptyOutDir: true,
    assetsDir: "assets",
  },
  test: {
    // Pin vitest to the repo root even though vite's root is frontend/. Otherwise
    // lcov records paths like "src/App.tsx", which SonarCloud resolves from the
    // repo root against the Python package instead of the frontend.
    root: fileURLToPath(new URL(".", import.meta.url)),
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
