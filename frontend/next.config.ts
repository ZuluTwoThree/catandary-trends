import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
    // LAN access to the dev instance on :3004 — without this Next 16 blocks the
    // client JS for non-localhost origins and NOTHING hydrates: the page renders
    // but every "use client" control is dead (radar cells unclickable, 2026-07-30).
    "192.168.178.78",
    "192.168.178.*",
  ],
};

export default nextConfig;
