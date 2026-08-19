import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
// vitest re-exports vite's defineConfig with the `test` block typed, so one config
// serves both `vite build` and `vitest run`.
import { defineConfig } from "vitest/config";

// A standalone SPA: it builds to frontend/dist/ (vite's default, gitignored) and
// knows nothing about the backend beyond VITE_API_BASE_URL, which src/api/expenses.ts
// reads. vite's root is this file's directory (frontend/), so the paths below are
// relative to that -- except inside the `test` block, which is pinned to the repo
// root for the reason given there.
export default defineConfig({
  // Pinned to this directory rather than left to default. envDir defaults to the
  // config's `root`, and the `test` block below moves that to the repo root - which
  // would send vitest looking for .env one level up and leave VITE_API_BASE_URL
  // undefined in the suite. `vite build` is unaffected either way; this is what keeps
  // the two agreeing.
  envDir: fileURLToPath(new URL("./", import.meta.url)),
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // Lets tests reach into src/ without climbing (../../src/api/expenses). Declared
      // again as "paths" in tsconfig.app.json for the type checker - vite does not read
      // tsconfig paths, so the two must be changed together.
      //
      // A bare "@" key is safe next to scoped packages: vite matches an alias only on
      // an exact hit or the key followed by "/", so "@/api/expenses" rewrites and
      // "@tanstack/react-query" does not.
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  // No `server.proxy` and no `build.outDir` on purpose. A proxy would hardcode the
  // backend's port here and hide the fact that the call is cross-origin; the API
  // origin belongs in .env instead, where it is configurable and the browser really
  // does perform a CORS request against it. The build output is vite's default dist/.
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
      exclude: [
        // Bootstrap only: wires React to the DOM and has no logic worth asserting.
        // Also listed in sonar.coverage.exclusions so both tools agree.
        "frontend/src/main.tsx",
        // Type declarations erase to nothing, so they would report as covered files
        // with no executable lines and pad the lcov Sonar reads.
        "frontend/src/**/*.d.ts",
      ],
    },
  },
});
