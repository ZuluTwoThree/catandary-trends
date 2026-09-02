// Flat ESLint config (ESLint 9) — replaces the removed `next lint`.
// eslint-config-next@16 exports a flat-config array (Next core-web-vitals +
// TypeScript rules + the @next/next plugin). No blanket rule disables.
import next from "eslint-config-next";

/** @type {import('eslint').Linter.Config[]} */
const config = [
  {
    ignores: [
      ".next/**",
      // alternate dist dirs (NEXT_DIST_DIR=.next-public/.next-check) and the
      // static-export staging/output tree (scripts/build_public_static.sh)
      ".next-*/**",
      ".export/**",
      "out/**",
      "node_modules/**",
      "next-env.d.ts",
    ],
  },
  ...next,
];

export default config;
