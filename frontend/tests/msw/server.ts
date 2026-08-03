import { setupServer } from "msw/node";

import { handlers } from "./handlers";

// msw/node rather than the browser worker: vitest runs on Node, so there is no service
// worker to register and nothing for msw's install script to copy (see
// ../../pnpm-workspace.yaml).
export const server = setupServer(...handlers);
