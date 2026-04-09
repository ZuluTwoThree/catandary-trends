import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { LocaleProvider } from "@/lib/locale-context";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Catandary Trends — Cross-Industry Trend Intelligence",
  description:
    "Kuratierte Trend-Signale aus acht Industrie-Vertikalen. Powered by Catandary Foresight.",
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
        suppressHydrationWarning
      >
        <LocaleProvider>
          <Header />
          <main>{children}</main>
          <Footer />
        </LocaleProvider>
      </body>
    </html>
  );
}
