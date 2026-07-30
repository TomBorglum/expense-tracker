import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The frontend sources live in frontend/, but the build output goes straight into
// the Python package so hatchling ships it in the wheel and the lean prod pixi
// environment never needs Node.
export default defineConfig({
  root: "frontend",
  // Flask's built-in static route serves the package's static/ folder at /static/,
  // so emitted asset URLs must carry that prefix.
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
});
