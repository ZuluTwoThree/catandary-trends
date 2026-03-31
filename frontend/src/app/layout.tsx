import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Catandary Trends — Cross-Industry Trend Intelligence",
  description:
    "Kuratierte Trend-Signale aus 10 Industrie-Vertikalen. Powered by Catandary Foresight.",
  openGraph: {
    title: "Catandary Trends",
    description: "Cross-Industry Trend Intelligence",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="de" className="dark">
      <body
        className={`${inter.className} bg-background text-foreground min-h-screen antialiased`}
      >
        <header className="border-b border-border">
          <div className="mx-auto max-w-7xl px-4 py-4 flex items-center justify-between">
            <a href="/trends" className="flex items-center gap-2">
              <span className="text-xl font-bold tracking-tight">
                Catandary{" "}
                <span className="text-accent">Trends</span>
              </span>
            </a>
            <nav className="flex items-center gap-6 text-sm text-muted">
              <a href="/trends" className="hover:text-foreground transition-colors">
                Trends
              </a>
              <a
                href="https://catandary.de"
                className="hover:text-foreground transition-colors"
                target="_blank"
                rel="noopener noreferrer"
              >
                Catandary
              </a>
              <a
                href="/trends/newsletter"
                className="bg-accent/10 text-accent px-3 py-1.5 rounded-md hover:bg-accent/20 transition-colors"
              >
                Newsletter
              </a>
            </nav>
          </div>
        </header>
        <main>{children}</main>
        <footer className="border-t border-border mt-20">
          <div className="mx-auto max-w-7xl px-4 py-8 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted">
            <p>&copy; {new Date().getFullYear()} Catandary. All rights reserved.</p>
            <div className="flex items-center gap-4">
              <span>
                Powered by{" "}
                <a
                  href="https://catandary.de"
                  className="text-accent hover:underline"
                >
                  Catandary Foresight
                </a>
              </span>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
