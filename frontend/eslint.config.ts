import eslintReact from "@eslint-react/eslint-plugin";
import js from "@eslint/js";
import vitest from "@vitest/eslint-plugin";
// The /flat entrypoint is the same rule set as the bare import, plus a config `name`,
// so it shows up identifiably in `eslint --inspect-config` instead of as an anonymous
// block.
import prettier from "eslint-config-prettier/flat";
import perfectionist from "eslint-plugin-perfectionist";
import reactHooks from "eslint-plugin-react-hooks";
import { reactRefresh } from "eslint-plugin-react-refresh";
import { defineConfig, globalIgnores } from "eslint/config";
import tseslint from "typescript-eslint";

// Authored as .ts (loaded through the pinned jiti) and listed in tsconfig.node.json,
// so `pnpm run check` type-checks this file like any other. Zed reads it too: its
// built-in eslint language server is pointed at frontend/node_modules by
// .zed/settings.json, so the editor reports exactly what `pnpm run lint` enforces.
export default defineConfig(
  // eslint only ignores node_modules by default, so the vite build output has to be
  // named. Not cosmetic: dist/ holds emitted JS that no tsconfig includes, and the
  // type-aware config below fails outright on a file it cannot get a program for.
  globalIgnores(["dist"]),

  // Type-aware base for every TS/TSX file. projectService lets the TypeScript project
  // service pick the right tsconfig per file - tsconfig.app.json for src/ and tests/,
  // tsconfig.node.json for vite.config.ts and this file - so the solution-style split
  // in tsconfig.json needs no second declaration here.
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.strictTypeChecked,
      tseslint.configs.stylisticTypeChecked,
    ],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
  },

  // React correctness. ESLint React and eslint-plugin-react-hooks overlap on the
  // hooks rules, so the disable-conflict preset follows them and turns off the
  // duplicated half - a violation is then reported once, not twice.
  {
    files: ["src/**/*.tsx", "tests/**/*.tsx"],
    extends: [
      eslintReact.configs["strict-type-checked"],
      reactHooks.configs.flat["recommended-latest"],
      eslintReact.configs["disable-conflict-eslint-plugin-react-hooks"],
    ],
  },

  // Fast-refresh boundaries only matter for the app itself, not the test tree. The
  // vite preset allows constant exports, which the React plugin in vite.config.ts
  // supports.
  {
    files: ["src/**/*.tsx"],
    extends: [reactRefresh.configs.vite()],
  },

  // vitest rules for the test tree. No languageOptions.globals on purpose: globals
  // are disabled in this repo, so the tests import test/expect/afterEach explicitly.
  {
    files: ["tests/**/*.{ts,tsx}"],
    plugins: { vitest },
    rules: { ...vitest.configs.recommended.rules },
  },

  // Import order. Prettier does not sort imports, so this is the only gate on it.
  // Just the two import rules, not a perfectionist preset - the presets also sort
  // object keys, union members and JSX props, which is churn with no correctness
  // payoff.
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { perfectionist },
    rules: {
      "perfectionist/sort-imports": [
        "error",
        {
          newlinesBetween: 1,
          // internalPattern is left at its default, which already covers the `@`
          // alias (`['^~/.+', '^@/.+', '^#.+']`), so `@/api/greeting` groups as
          // internal without this file having to name the alias.
          //
          // The one deviation from perfectionist's default groups is using bare
          // selectors: they match an import whatever its modifiers, so `import type`
          // sits beside the value import from the same origin instead of being
          // hoisted into a leading type-only block. With verbatimModuleSyntax on,
          // keeping the two adjacent reads better than separating them.
          //
          // That grouping is what makes this fallbackSort necessary. Imports sort by
          // path, so `import type { X } from "m"` and `import { y } from "m"` tie,
          // and perfectionist's default fallback ("unsorted") resolves a tie by
          // keeping whatever order was typed - two files could then disagree and the
          // rule would flag neither. The stock groups never hit this because they
          // split type and value into separate groups. Type import first, always.
          fallbackSort: { type: "type-import-first" },
          //
          // Side-effect selectors are absent because sortSideEffects defaults to
          // false, which keeps `import "./styles/app.css"` pinned where it is
          // (reordering side effects can change behaviour); perfectionist rejects
          // mixing them into a group with sortable ones.
          groups: [
            "builtin",
            "external",
            "internal",
            ["parent", "sibling", "index", "style"],
            "unknown",
          ],
        },
      ],
      "perfectionist/sort-named-imports": "error",
    },
  },

  // Last, so it wins: drop every rule prettier already decides. Formatting is
  // prettier's job here (printWidth 88), the linter's job is correctness.
  prettier,
);
