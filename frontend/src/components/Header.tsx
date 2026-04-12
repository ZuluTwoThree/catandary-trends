export default function Header() {
  return (
    <header className="border-b border-border">
      <div className="mx-auto max-w-7xl px-4 py-4 flex items-center justify-between">
        <a href="/trends" className="flex items-center gap-2">
          <span className="text-xl font-bold tracking-tight">
            Catandary <span className="text-accent">Trends</span>
          </span>
        </a>
        <nav className="flex items-center gap-4 text-sm text-muted">
          <a
            href="/trends"
            className="hover:text-foreground transition-colors"
          >
            Trends
          </a>
          <a
            href="/trends/mega"
            className="hover:text-foreground transition-colors hidden sm:inline"
          >
            Mega Trends
          </a>
          <a
            href="/trends/cross-vertical"
            className="hover:text-foreground transition-colors hidden md:inline"
          >
            Cross-Industry
          </a>
          <a
            href="/trends/foresight"
            className="hover:text-foreground transition-colors hidden md:inline"
          >
            Foresight
          </a>
          <a
            href="https://catandary.de"
            className="hover:text-foreground transition-colors hidden sm:inline"
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
  );
}
