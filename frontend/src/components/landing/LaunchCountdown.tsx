"use client";

import { useEffect, useState } from "react";

// Public launch moment shown on the landing hub (catandary.de): 01 Sep 2026, 09:00 CEST.
const LAUNCH_AT = Date.parse("2026-09-01T09:00:00+02:00");

function remaining(now: number) {
  const diff = Math.max(0, LAUNCH_AT - now);
  return {
    d: Math.floor(diff / 86_400_000),
    h: Math.floor(diff / 3_600_000) % 24,
    m: Math.floor(diff / 60_000) % 60,
    s: Math.floor(diff / 1_000) % 60,
    live: diff === 0,
  };
}

const pad = (n: number) => String(n).padStart(2, "0");

export default function LaunchCountdown() {
  // Render placeholders on the server / first paint so hydration stays stable.
  const [t, setT] = useState<ReturnType<typeof remaining> | null>(null);

  useEffect(() => {
    const tick = () => setT(remaining(Date.now()));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <section className="lp-cd" aria-label="Countdown to public launch">
      <div className="lp-wrap lp-cd-inner">
        <span className="lp-eyebrow">Public launch</span>
        {t?.live ? (
          <span className="lp-cd-live">We are live</span>
        ) : (
          <div className="lp-cd-units" role="timer" aria-label="Time remaining until launch">
            <div className="lp-cd-unit">
              <span className="lp-cd-n">{t ? t.d : "-"}</span>
              <span className="lp-cd-l">Days</span>
            </div>
            <span className="lp-cd-sep" aria-hidden="true">:</span>
            <div className="lp-cd-unit">
              <span className="lp-cd-n">{t ? pad(t.h) : "-"}</span>
              <span className="lp-cd-l">Hrs</span>
            </div>
            <span className="lp-cd-sep" aria-hidden="true">:</span>
            <div className="lp-cd-unit">
              <span className="lp-cd-n">{t ? pad(t.m) : "-"}</span>
              <span className="lp-cd-l">Min</span>
            </div>
            <span className="lp-cd-sep" aria-hidden="true">:</span>
            <div className="lp-cd-unit">
              <span className="lp-cd-n">{t ? pad(t.s) : "-"}</span>
              <span className="lp-cd-l">Sec</span>
            </div>
          </div>
        )}
        <span className="lp-cd-date">01 Sep 2026 &middot; 09:00 CEST</span>
      </div>
    </section>
  );
}
