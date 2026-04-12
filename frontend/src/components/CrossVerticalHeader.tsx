import Link from "next/link";

export default function CrossVerticalHeader({ count }: { count: number }) {
  return (
    <>
      <nav className="flex items-center gap-2 text-sm text-muted mb-6">
        <Link
          href="/trends"
          className="hover:text-foreground transition-colors"
        >
          Trends
        </Link>
        <span>/</span>
        <span className="text-foreground">Cross-Industry Trends</span>
      </nav>

      <div className="mb-10">
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
          Cross-Industry Trends
        </h1>
        <p className="text-muted text-lg max-w-2xl">
          Trend signals affecting multiple industries simultaneously — early
          indicators of systemic change.
        </p>
        <p className="text-sm text-muted mt-2">{count} Trend signals</p>
      </div>
    </>
  );
}
