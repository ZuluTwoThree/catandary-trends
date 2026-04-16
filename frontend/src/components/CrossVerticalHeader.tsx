import Link from "next/link";

export default function CrossVerticalHeader({ count }: { count: number }) {
  return (
    <>
      <nav className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-8">
        <Link href="/trends" className="hover:text-paper transition-colors">
          Trends
        </Link>
        <span className="text-border">/</span>
        <span className="text-paper">Cross-Industry</span>
      </nav>

      <div className="mb-12">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Multi-Industry Impact
        </div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
          Cross-Industry <span className="italic">Trends</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl mb-5">
          Trend signals affecting multiple industries simultaneously — early
          indicators of systemic change.
        </p>
        <div className="inline-flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted pt-4 border-t border-border">
          <span className="text-paper">{count}</span>
          <span>Trend signals</span>
        </div>
      </div>
    </>
  );
}
