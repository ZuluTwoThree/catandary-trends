import type { NextConfig } from "next";

// Baseline security headers (security review 2026-09-02, E-8). Deliberately
// no CSP here — that needs nonce plumbing for Next's inline scripts. On the
// static-export hosting the same three are set via .htaccess
// (frontend/public-export/.htaccess), since `headers()` only applies while a
// Node server answers — and `output: "export"` rejects the option outright.
const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
];

/**
 * STATIC_EXPORT=1 switches this config into the public-site export
 * (design: docs/audits/2026-09-02_static_export_design.md; driver:
 * scripts/build_public_static.sh). Unset, every value below is exactly the
 * workstation instance's config — `npm run build` / `next start` on :3001
 * are unchanged.
 */
const STATIC_EXPORT = process.env.STATIC_EXPORT === "1";

const exportConfig: NextConfig = {
  output: "export",
  // Default kept explicit: /trends/<slug> → out/trends/<slug>.html (+ the
  // <slug>.txt RSC payload). URLs stay byte-identical to the app; Apache
  // maps the extension away (.htaccess). `true` would change every URL to
  // <slug>/ and still not remove the per-page segment directories.
  trailingSlash: false,
  // No next/image in the tree, but the export refuses to build with the
  // default loader on — harmless to state.
  images: { unoptimized: true },
  // Constant build id: Next stamps it into every HTML/RSC payload and the
  // _next/static/<id>/ path — with the random default no two exports were
  // byte-equal (3,080 of 3,150 files differed; spike 2026-09-02).
  generateBuildId: () => "catandary",
  // Prerender workers × pg pool (max 10 in lib/pg.ts) must stay under
  // Postgres max_connections=100. 6 workers ≈ 29 pages/s (spike).
  experimental: { cpus: 6 },
  // The staging tree symlinks node_modules to ../../node_modules. Turbopack
  // refuses symlinks that leave its filesystem root ("points out of the
  // filesystem root"), so the root is lifted to the real frontend dir.
  ...(process.env.STATIC_EXPORT_ROOT
    ? { turbopack: { root: process.env.STATIC_EXPORT_ROOT } }
    : {}),
};

const serverConfig: NextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Build-Verzeichnis per Env übersteuerbar: erlaubt einen ZWEITEN Dev-Server
  // aus demselben Worktree (Next 16 lockt .next/dev pro Verzeichnis). Genutzt
  // für die PUBLIC_MODE-Vorschau: NEXT_DIST_DIR=.next-public → Port 3999,
  // während :3004 normal auf .next läuft. Ohne Env unverändert ".next".
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // NB: no `output: "standalone"` — the deployment runs `next start -p 3001`
  // (deploy/ecosystem.config.js / README / CLAUDE.md), which serves the normal
  // .next build. standalone emits a separate .next/standalone/server.js that
  // `next start` ignores, so it only produced a startup warning + a dead dir.
  // The dev server is reached over Tailscale (100.64.0.0/10 CGNAT range), not
  // localhost. Next 16 blocks its client JS / HMR resources for any non-localhost
  // origin by default, which stops "use client" components from hydrating (the
  // TIR-trajectory "Zeigen" button then never enables). Allow the Tailscale hosts.
  allowedDevOrigins: [
    "100.115.179.37",
    "*.ts.net", // Tailscale MagicDNS names, if reached by hostname
    // Der Platzhalter oben deckt NUR eine Ebene ab — der MagicDNS-Name hat zwei
    // (kiworkstation.<tailnet>.ts.net). Ohne diese Zeilen laedt ueber Tailscale
    // Serve kein Client-JS: schwarze Flaechen, tote Controls (2026-09-05).
    "*.tail678c6e.ts.net",
    "kiworkstation.tail678c6e.ts.net",
    // LAN access to the dev instance on :3004 — without this Next 16 blocks the
    // client JS for non-localhost origins and NOTHING hydrates: the page renders
    // but every "use client" control is dead (radar cells unclickable, 2026-07-30).
    "192.168.178.78",
    "192.168.178.*",
  ],
  // Mirror of the build-mode flag for client components (lib/renderMode.ts):
  // NEXT_PUBLIC_* is inlined into both bundles at build time.
  env: { NEXT_PUBLIC_STATIC_EXPORT: STATIC_EXPORT ? "1" : "0" },
  ...(STATIC_EXPORT ? exportConfig : serverConfig),
};

export default nextConfig;
