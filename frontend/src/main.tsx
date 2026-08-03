import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles/app.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Root element #root not found in index.html");
}

// Built here rather than in a module of its own: main.tsx is the one file excluded from
// coverage (in vite.config.ts and sonar-project.properties, which must agree), so
// bootstrap wiring that lives here needs no test and opens no gap. The tests build
// their own client.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The greeting only changes when a new wheel is deployed, and this is a single
      // screen -- there is nothing worth refetching when the tab regains focus.
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
