import Link from "next/link";
import { getVerticalInfo, getMegaTrendInfo } from "@/lib/types";
import type { Vertical } from "@/lib/types";

export default function MegaTrendHeader({
  megaTrend,
  count,
  verticals,
}: {
  megaTrend: string;
  count: number;
  verticals: string[];
}) {
  const info = getMegaTrendInfo(megaTrend);
  const displayName = info ? info.name_en : megaTrend;
  const description = info ? info.description_en : null;

  return (
    <>
      <nav className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-8">
        <Link href="/trends" className="hover:text-paper transition-colors">
          Trends
        </Link>
        <span className="text-border">/</span>
        <Link
          href="/trends/mega"
          className="hover:text-paper transition-colors"
        >
          Mega Trends
        </Link>
        <span className="text-border">/</span>
        <span className="text-paper">{displayName}</span>
      </nav>

      <div className="mb-10">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Mega Trend
        </div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-5">
          {displayName}
        </h1>
        {description && (
          <p className="font-sans text-text text-lg leading-relaxed max-w-2xl mb-6">
            {description}
          </p>
        )}
        <div className="flex items-center gap-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-6 pb-6 border-b border-border">
          <span>
            <span className="text-paper">{count}</span>
            <span className="text-muted/70"> / Signals</span>
          </span>
          <span className="text-border">——</span>
          <span>
            <span className="text-paper">{verticals.length}</span>
            <span className="text-muted/70"> / Verticals</span>
          </span>
        </div>
        <div className="flex flex-wrap gap-2 mb-6">
          {verticals.map((v) => {
            const vInfo = getVerticalInfo(v as Vertical);
            return (
              <Link
                key={v}
                href={`/trends?vertical=${v}`}
                className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] border px-2.5 py-1 transition-colors hover:opacity-80"
                style={{
                  color: vInfo.color,
                  borderColor: `${vInfo.color}55`,
                  backgroundColor: `${vInfo.color}10`,
                }}
              >
                <span
                  className="inline-block w-2 h-[3px]"
                  style={{ backgroundColor: vInfo.color }}
                  aria-hidden="true"
                />
                <span>{vInfo.code}</span>
                <span className="text-muted/70 font-sans normal-case tracking-normal">
                  {vInfo.label}
                </span>
              </Link>
            );
          })}
        </div>
        <div className="border-l-[3px] border-accent pl-5 py-2">
          <p className="font-sans text-sm text-paper">
            Want the full mega-trend forecast?{" "}
            <span className="text-accent">Discover Catandary Foresight →</span>
          </p>
        </div>
      </div>
    </>
  );
}
