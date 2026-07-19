import { defineConfig } from "vitest/config";
import path from "node:path";

// Node-environment unit tests for the API/lib hardening (rate limit, auth, stripe).
// The `@/…` alias mirrors tsconfig paths so tests import the same modules the app does.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
});
