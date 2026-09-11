"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

/**
 * Re-renders the server page every `seconds` (router.refresh keeps scroll
 * position and the URL). Shows the clock of the last refresh so a stalled
 * page is visible as such.
 */
export default function AutoRefresh({ seconds = 60 }: { seconds?: number }) {
  const router = useRouter();
  const [stamp, setStamp] = useState<string>("");
  useEffect(() => {
    const tick = () => setStamp(new Date().toLocaleTimeString("de-DE"));
    tick();
    const id = setInterval(() => {
      router.refresh();
      tick();
    }, seconds * 1000);
    return () => clearInterval(id);
  }, [router, seconds]);
  return (
    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
      auto-refresh {seconds} s{stamp ? ` · ${stamp}` : ""}
    </span>
  );
}
