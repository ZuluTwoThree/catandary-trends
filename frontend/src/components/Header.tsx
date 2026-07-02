export default function Header() {
  return (
    <header className="border-b border-border">
      <div className="mx-auto max-w-7xl px-6 md:px-12 h-16 flex items-center justify-between">
        <a href="/trends" className="group">
          <span className="font-display text-[22px] font-normal tracking-tight text-paper">
            Catandary<span className="text-accent">.</span>
          </span>
        </a>
        <nav className="flex items-center gap-1">
          {[
            { href: "/trends", label: "Trends" },
            { href: "/trends/mega", label: "Mega Trends" },
            { href: "/trends/cross-vertical", label: "Cross-Industry" },
            { href: "/trends/foresight", label: "Foresight" },
            { href: "/trends/foresight/clusters", label: "Clusters" },
            { href: "https://catandary.de", label: "Catandary", external: true },
          ].map((item) => (
            <a
              key={item.href}
              href={item.href}
              {...(item.external
                ? { target: "_blank", rel: "noopener noreferrer" }
                : {})}
              className="hidden md:inline font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-paper px-3 py-1.5 transition-colors"
            >
              {item.label}
            </a>
          ))}
          <a
            href="/trends/newsletter"
            className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent px-3 py-1.5 border border-accent bg-accent/5 hover:bg-accent/15 transition-colors"
          >
            Newsletter
          </a>
        </nav>
      </div>
    </header>
  );
}
