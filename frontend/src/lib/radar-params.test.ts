import { describe, expect, it } from "vitest";
import {
  MAX_FIELDS,
  parseRadarParams,
  radarApiQuery,
  radarQueryString,
} from "./radar-params";

describe("parseRadarParams", () => {
  it("keeps a usable query and normalises whitespace", () => {
    expect(parseRadarParams({ q: "  carbon   capture " }).q).toBe("carbon capture");
  });

  it("drops queries below the minimum length instead of half-running them", () => {
    expect(parseRadarParams({ q: "ab" }).q).toBeNull();
    expect(parseRadarParams({ q: "" }).q).toBeNull();
  });

  it("clamps an over-long query rather than rejecting it", () => {
    const p = parseRadarParams({ q: "x".repeat(500) });
    expect(p.q).toHaveLength(120);
  });

  it("lets a query win over a saved radar — they are different objects", () => {
    const p = parseRadarParams({ q: "carbon capture", radar: "alt-protein" });
    expect(p.q).toBe("carbon capture");
    expect(p.radar).toBeNull();
  });

  it("keeps the saved radar when there is no query", () => {
    expect(parseRadarParams({ radar: "alt-protein" }).radar).toBe("alt-protein");
  });

  it("whitelists field slugs and caps the count", () => {
    const many = Array.from({ length: 30 }, (_, i) => `f${i}`).join(",");
    expect(parseRadarParams({ fields: many }).fields).toHaveLength(MAX_FIELDS);
    expect(parseRadarParams({ fields: "ok-1,BAD SLUG,../etc,ok-2" }).fields).toEqual([
      "ok-1",
      "ok-2",
    ]);
  });

  it("rejects an unknown jurisdiction instead of passing it through", () => {
    expect(parseRadarParams({ region: "us" }).region).toBe("US");
    expect(parseRadarParams({ region: "MARS" }).region).toBeNull();
  });

  it("falls back to the strategic dimension set", () => {
    expect(parseRadarParams({ dim: "pestel" }).dim).toBe("pestel");
    expect(parseRadarParams({ dim: "nonsense" }).dim).toBe("strategic");
    expect(parseRadarParams({}).dim).toBe("strategic");
  });

  it("treats regulated as an explicit opt-in", () => {
    expect(parseRadarParams({}).regulated).toBe(false);
    expect(parseRadarParams({ regulated: "1" }).regulated).toBe(true);
    expect(parseRadarParams({ regulated: "true" }).regulated).toBe(false);
  });
});

describe("radarQueryString", () => {
  it("omits everything at its default", () => {
    expect(radarQueryString({ q: "carbon capture" })).toBe("?q=carbon+capture");
    expect(radarQueryString({})).toBe("");
  });

  it("never emits both q and radar", () => {
    const s = radarQueryString({ q: "x-ray optics", radar: "alt-protein" });
    expect(s).toContain("q=");
    expect(s).not.toContain("radar=");
  });

  it("round-trips through the parser", () => {
    const original = {
      q: "solid state battery",
      fields: ["a", "b"],
      field: "a",
      region: "EU" as const,
      dim: "pestel" as const,
      regulated: true,
    };
    const parsed = parseRadarParams(
      Object.fromEntries(new URLSearchParams(radarQueryString(original)))
    );
    expect(parsed.q).toBe(original.q);
    expect(parsed.fields).toEqual(original.fields);
    expect(parsed.field).toBe(original.field);
    expect(parsed.region).toBe(original.region);
    expect(parsed.dim).toBe(original.dim);
    expect(parsed.regulated).toBe(true);
  });
});

describe("radarApiQuery", () => {
  it("omits the default dimension set so the cache key stays stable", () => {
    expect(radarApiQuery({ q: "a b", fields: [], dim: "strategic", regulated: false })).toBe(
      "q=a+b"
    );
  });

  it("passes the lens and the regulated flag through", () => {
    const s = radarApiQuery({ q: "a", fields: ["x"], dim: "pestel", regulated: true });
    expect(s).toContain("dim=pestel");
    expect(s).toContain("regulated=1");
    expect(s).toContain("fields=x");
  });
});
