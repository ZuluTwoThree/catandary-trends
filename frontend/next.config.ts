import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // The dev server is reached over Tailscale (100.64.0.0/10 CGNAT range), not
  // localhost. Next 16 blocks its client JS / HMR resources for any non-localhost
  // origin by default, which stops "use client" components from hydrating (the
  // TIR-trajectory "Zeigen" button then never enables). Allow the Tailscale hosts.
  allowedDevOrigins: [
    "100.115.179.37",
    "*.ts.net", // Tailscale MagicDNS names, if reached by hostname
  ],
};

export default nextConfig;
