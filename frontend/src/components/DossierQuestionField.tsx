"use client";

import { useState } from "react";
import { questionCheck } from "@/lib/dossierIntake";

/**
 * Custom-question textarea of the dossier order form with the deterministic
 * intake check (stage 1, 2026-09-19): a text that is not a question blocks the
 * submit with the same reason the server action and the worker would give.
 * The server action re-checks — this is convenience, not the gate.
 */
export function DossierQuestionField({ className }: { className: string }) {
  const [reason, setReason] = useState("");
  return (
    <>
      <textarea
        name="question"
        rows={2}
        maxLength={2000}
        className={className}
        onChange={(e) => {
          const r = questionCheck(e.currentTarget.value);
          e.currentTarget.setCustomValidity(r.ok ? "" : r.reason);
          setReason(r.ok ? "" : r.reason);
        }}
      />
      {reason && <p className="mt-1 font-mono text-[11px] text-warn">{reason}</p>}
    </>
  );
}
