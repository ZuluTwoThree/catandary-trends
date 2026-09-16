import type { EmergingNest } from "@/lib/emerging";
import Sparkline from "./Sparkline";
import {
  accelText,
  actorText,
  dominantTier,
  leadText,
  TIER_LABEL,
  tierSteps,
  ageIsMeaningful,
  ageText,
  caveats,
  historyTail,
  isYoung,
  nestTitle,
  noveltyText,
} from "@/lib/nestCard";

/**
 * One emerging pocket. The headline number is its AGE, not its size: a pocket
 * whose lookalikes start in 2009 is a subject area, one that starts eleven
 * months ago is a candidate. Weaknesses are printed on the card itself.
 */
export default function NestCard({ nest }: { nest: EmergingNest }) {
  const hist = historyTail(nest);
  const flags = caveats(nest);
  const accel = accelText(nest);
  const title = nestTitle(nest);
  const steps = tierSteps(nest);
  const main = dominantTier(nest);
  const lead = leadText(nest);
  const actors = actorText(nest);

  return (
    <article className="border border-border bg-card/40 p-6 flex flex-col gap-3 hover:border-accent/40 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted flex items-center gap-3 flex-wrap">
          <span>
            <span className="text-paper tabular-nums">{nest.size.toLocaleString("en-US")}</span> docs
          </span>
          <span className="text-border">·</span>
          <span>
            <span className="text-accent tabular-nums">{nest.n_sources}</span> sources
          </span>
          <span className="text-border">·</span>
          <span title="Mean cosine of a member to the pocket centre.">
            density {nest.cohesion.toFixed(2)}
          </span>
          {main && (
            <>
              <span className="text-border">·</span>
              <span
                className="text-accent"
                title="Which of the four conversations this pocket mostly is — research, patents, funding or the market. A science trend is not a market trend even when the topic is the same."
              >
                {TIER_LABEL[main]}
              </span>
            </>
          )}
          {nest.verticals.length > 0 && (
            <>
              <span className="text-border">·</span>
              <span>{nest.verticals.slice(0, 2).join(" / ")}</span>
            </>
          )}
        </div>
        <span
          className="inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] px-2 py-0.5 border shrink-0"
          style={{
            color: isYoung(nest) ? "#d4ff3a" : "#a3a3a3",
            borderColor: (isYoung(nest) ? "#d4ff3a" : "#a3a3a3") + "55",
            backgroundColor: (isYoung(nest) ? "#d4ff3a" : "#a3a3a3") + "10",
          }}
          title="Months since the first month with at least three lookalikes anywhere in the archive."
        >
          {ageText(nest)}
          {!ageIsMeaningful(nest) && " ?"}
        </span>
      </div>

      <div>
        <h2 className="font-display text-[22px] leading-tight text-paper">{title.name}</h2>
        {title.sub && (
          <div
            className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mt-1"
            title="Name written by the local model from the pocket's own titles, checked word by word against them. Underneath: the label derived from its tags."
          >
            tags say: {title.sub}
          </div>
        )}
      </div>

      <p className="font-sans text-sm text-text leading-relaxed">
        {noveltyText(nest)}
        {accel && <span className="text-muted"> {accel}</span>}
      </p>

      {steps.length > 0 && (
        <div className="border-t border-border/60 pt-3">
          <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mb-1.5">
            When each conversation started
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px]">
            {steps.map((st, i) => (
              <span key={st.tier} className="flex items-center gap-2">
                {i > 0 && <span className="text-border">then</span>}
                <span>
                  <span className="text-paper">{st.label}</span>{" "}
                  <span className="text-muted tabular-nums">{st.first_month}</span>
                  <span className="text-muted"> ({Math.round(st.share * 100)} %)</span>
                </span>
              </span>
            ))}
          </div>
          {lead && <div className="font-sans text-xs text-text mt-1.5">{lead}</div>}
          {actors && <div className="font-sans text-xs text-muted mt-1">{actors}</div>}
        </div>
      )}

      {nest.new_terms.length > 0 && (
        <div className="font-mono text-[10px] text-accent">
          new vocabulary: {nest.new_terms.slice(0, 4).join(" · ")}
        </div>
      )}

      {hist.values.length >= 2 && (
        <div>
          <Sparkline
            points={hist.values}
            months={hist.months}
            label={nest.label}
            className="w-full h-12"
            unit="count"
          />
          <div className="flex justify-between font-mono text-[9px] text-muted tabular-nums">
            <span>{hist.months[0]}</span>
            <span>lookalikes per month</span>
            <span>{hist.months[hist.months.length - 1]}</span>
          </div>
        </div>
      )}

      {nest.reps.length > 0 && (
        <div className="border-t border-border/60 pt-3 mt-1">
          <ul className="space-y-1.5">
            {nest.reps.slice(0, 3).map((r) => (
              <li key={r.id} className="text-sm leading-snug">
                {r.date && (
                  <span className="font-mono text-[10px] text-muted tabular-nums mr-2">{r.date}</span>
                )}
                {r.source_url ? (
                  <a
                    href={r.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-text hover:text-accent transition-colors"
                  >
                    {r.title}
                    {r.source_name && <span className="text-muted"> — {r.source_name}</span>}
                  </a>
                ) : (
                  <span className="text-text">{r.title}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {flags.length > 0 && (
        <ul className="border-t border-border/60 pt-3 space-y-1">
          {flags.map((f) => (
            <li key={f.key} className="font-sans text-xs text-muted leading-snug">
              ! {f.text}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
