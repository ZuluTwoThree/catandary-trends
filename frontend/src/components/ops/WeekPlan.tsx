import { fmtDuration, fmtTime, jobColor } from "@/lib/ops";
import type { PlannedBlock } from "@/lib/opsCron";

interface Props {
  weekStart: Date;
  blocks: PlannedBlock[];
  now: Date;
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const W = 960;
const ROW = 26;
const LEFT = 34;
const TOP = 16;
const H = TOP + 7 * ROW + 6;
const PW = W - LEFT - 6;

/**
 * The crontab as a week: one row per day, one block per scheduled run, sized
 * by the job's measured median duration (10 min when there is none yet).
 * Logbook `plan` entries with a day sit in the same grid in accent colour,
 * so a planned manual run shows against what cron will do anyway.
 */
export default function WeekPlan({ weekStart, blocks, now }: Props) {
  const dayOf = (d: Date) => Math.floor((d.getTime() - weekStart.getTime()) / 86_400_000);
  const xOf = (d: Date) => LEFT + ((d.getHours() * 60 + d.getMinutes()) / 1440) * PW;
  const nowDay = dayOf(now);
  return (
    <figure className="border border-border p-3 bg-card overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block min-w-[640px]" role="img" aria-label="Week plan">
        {Array.from({ length: 25 }, (_, h) => (
          <g key={h}>
            <line x1={LEFT + (h / 24) * PW} x2={LEFT + (h / 24) * PW} y1={TOP} y2={TOP + 7 * ROW}
                  stroke="currentColor" className={h % 6 === 0 ? "text-border-strong" : "text-border"} strokeWidth={0.5} />
            {h % 3 === 0 && h < 24 && (
              <text x={LEFT + (h / 24) * PW + 2} y={TOP - 5} fontSize={9} fontFamily="ui-monospace, monospace"
                    fill="currentColor" className="text-muted">{String(h).padStart(2, "0")}</text>
            )}
          </g>
        ))}
        {DAYS.map((d, i) => (
          <g key={d}>
            <line x1={LEFT} x2={LEFT + PW} y1={TOP + i * ROW} y2={TOP + i * ROW} stroke="currentColor" className="text-border" strokeWidth={0.5} />
            <text x={2} y={TOP + i * ROW + ROW / 2 + 3} fontSize={10} fontFamily="ui-monospace, monospace"
                  fill="currentColor" className={i === nowDay ? "text-accent" : "text-muted"}>{d}</text>
          </g>
        ))}
        {blocks.map((b, i) => {
          const day = dayOf(b.start);
          if (day < 0 || day > 6) return null;
          const x0 = xOf(b.start);
          const endSameDay = dayOf(b.end) === day ? b.end : new Date(b.start.getFullYear(), b.start.getMonth(), b.start.getDate(), 23, 59);
          const x1 = Math.max(x0 + 3, xOf(endSameDay));
          const y = TOP + day * ROW + (b.source === "plan" ? 3 : 6);
          const h = b.source === "plan" ? ROW - 6 : ROW - 12;
          const past = b.end.getTime() < now.getTime();
          return (
            <rect key={i} x={x0} y={y} width={x1 - x0} height={h}
                  fill={b.source === "plan" ? "#d4ff3a" : jobColor(b.job)}
                  opacity={b.source === "plan" ? 0.9 : past ? 0.35 : 0.75}
                  stroke={b.source === "plan" ? "#d4ff3a" : "none"} strokeWidth={b.source === "plan" ? 1 : 0}
                  strokeDasharray={b.source === "plan" ? "3 2" : undefined}>
              <title>{`${b.label ?? b.job} · ${DAYS[day]} ${fmtTime(b.start)}–${fmtTime(b.end)} (${fmtDuration(b.end.getTime() - b.start.getTime())})${b.source === "plan" ? " · planned (logbook)" : ""}`}</title>
            </rect>
          );
        })}
        {nowDay >= 0 && nowDay <= 6 && (
          <line x1={xOf(now)} x2={xOf(now)} y1={TOP + nowDay * ROW} y2={TOP + (nowDay + 1) * ROW}
                stroke="#ff6b3a" strokeWidth={1.5} />
        )}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
        {[...new Set(blocks.filter((b) => b.source === "cron").map((b) => b.job))].sort().map((j) => (
          <span key={j} className="inline-flex items-center gap-1">
            <span className="inline-block w-2 h-2" style={{ background: jobColor(j) }} />{j}
          </span>
        ))}
        <span className="inline-flex items-center gap-1">
          <span className="inline-block w-2 h-2 border border-accent border-dashed" />planned (logbook)
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block w-[2px] h-2 bg-warn" />now
        </span>
      </figcaption>
    </figure>
  );
}
