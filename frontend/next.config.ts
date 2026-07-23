import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
  ],
  async redirects() {
    return [
      // Standalone Cross-Industry page removed (owner decision 2026-07-23):
      // it duplicated the main feed — cross-vertical signals are filterable
      // there and every card shows its "Cross:" verticals. Keep old links alive.
      {
        source: "/trends/cross-vertical",
        destination: "/trends",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
