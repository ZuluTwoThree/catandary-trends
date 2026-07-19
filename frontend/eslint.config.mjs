// Flat ESLint config (ESLint 9) — replaces the removed `next lint`.
// eslint-config-next@16 exports a flat-config array (Next core-web-vitals +
// TypeScript rules + the @next/next plugin). No blanket rule disables.
import next from "eslint-config-next";

/** @type {import('eslint').Linter.Config[]} */
const config = [
  {
    ignores: [
      ".next/**",
      "out/**",
      "node_modules/**",
      "next-env.d.ts",
    ],
  },
  ...next,
];

export default config;
