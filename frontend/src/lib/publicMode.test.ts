/**
 * Public-mode gate (issue #93, Etappe 1). PUBLIC_MODE=1 hides the Foresight
 * tool suite and the two internal review pages on the public deployment;
 * unset/0 must change nothing on the workstation instance.
 */
import { describe, it, expect, afterEach } from "vitest";
import { isPublicMode, isBlockedInPublicMode } from "@/lib/publicMode";

afterEach(() => {
  delete process.env.PUBLIC_MODE;
});

describe("isPublicMode", () => {
  it("is off when unset — the workstation instance today", () => {
    delete process.env.PUBLIC_MODE;
    expect(isPublicMode()).toBe(false);
  });

  it("is off for any value other than '1'", () => {
    for (const v of ["0", "true", "yes", ""]) {
      process.env.PUBLIC_MODE = v;
      expect(isPublicMode()).toBe(false);
    }
  });

  it("is on only for '1'", () => {
    process.env.PUBLIC_MODE = "1";
    expect(isPublicMode()).toBe(true);
  });
});

describe("isBlockedInPublicMode", () => {
  const blocked = [
    "/trends/foresight",
    "/trends/foresight/clusters",
    "/trends/foresight/technology",
    "/trends/foresight/lead-time",
    "/trends/foresight/evolution",
    "/trends/foresight/research",
    "/trends/foresight/research/paper/W123",
    "/trends/foresight/research/export",
    "/trends/foresight/research/suggest",
    "/trends/foresight/patents",
    "/trends/foresight/ventures",
    "/trends/foresight/ventures/company/5",
    "/trends/review",
    "/trends/dossiers",
    "/trends/dossiers/solid-state-batteries",
    "/api/foresight/analyze",
    "/api/foresight/clusters",
    "/api/foresight/lineage",
    "/api/foresight/query",
    "/api/foresight/query/evidence",
    "/api/foresight/technology",
    "/api/foresight/tir",
    "/api/foresight/trajectory",
  ];

  it.each(blocked)("blocks %s", (path) => {
    expect(isBlockedInPublicMode(path)).toBe(true);
  });

  const allowed = [
    "/",
    "/trends",
    "/trends/some-example-slug",
    "/trends/mega",
    "/trends/mega/personalized-nutrition",
    "/trends/methodology",
    "/trends/newsletter",
    "/trends/newsletter/unsubscribe",
    "/imprint",
    "/privacy",
    // #93 Etappe 2 — the analysis + enquiry routes are the new public lead-gen
    // surface and must stay reachable in both PUBLIC_MODE states.
    "/analysis",
    "/analysis/some-analysis-slug",
    "/enquiry",
    // gone for good since 2026-09-03 (#93 physical removal) — not blocked,
    // simply nonexistent; Next's own 404 answers them.
    "/account",
    "/trends/pricing",
    "/api/auth/request",
  ];

  it.each(allowed)("does not block %s", (path) => {
    expect(isBlockedInPublicMode(path)).toBe(false);
  });

  it("does not block a sibling path that merely starts with a blocked prefix", () => {
    // Guards against a naive startsWith() on the raw prefix string.
    expect(isBlockedInPublicMode("/trends/foresights")).toBe(false);
    expect(isBlockedInPublicMode("/trends/reviewer")).toBe(false);
    expect(isBlockedInPublicMode("/trends/dossiersx")).toBe(false);
    expect(isBlockedInPublicMode("/api/foresighter")).toBe(false);
  });
});
