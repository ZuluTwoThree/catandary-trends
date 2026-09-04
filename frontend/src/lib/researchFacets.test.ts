import { describe, it, expect } from "vitest";
import {
  parseSourceParam, parseRangeParam, parseSortParam, parseResearchFacets,
  rangeDays, sourceSql, toggleSource, activeFacetCount, kindSql, PAPER_FILTER_SQL,
} from "@/lib/researchFacets";

describe("research facets (URL params)", () => {
  it("whitelists sources, case-insensitive, deduplicated, order kept", () => {
    expect(parseSourceParam("arxiv,OpenAlex,arxiv,bogus")).toEqual(["arxiv", "openalex"]);
    expect(parseSourceParam("")).toEqual([]);
    expect(parseSourceParam(undefined)).toEqual([]);
  });

  it("falls back to all-time on unknown ranges", () => {
    expect(parseRangeParam("30d")).toBe("30d");
    expect(parseRangeParam("2w")).toBe("all");
    expect(parseRangeParam(undefined)).toBe("all");
    expect(rangeDays("90d")).toBe(90);
    expect(rangeDays("all")).toBeNull();
  });

  it("allows relevance only with a text query", () => {
    expect(parseSortParam("relevance", true)).toBe("relevance");
    expect(parseSortParam("relevance", false)).toBe("date");
    expect(parseSortParam(undefined, true)).toBe("relevance");
    expect(parseSortParam(undefined, false)).toBe("date");
    expect(parseSortParam("date", true)).toBe("date");
  });

  it("parses the whole facet set and trims the concept", () => {
    const f = parseResearchFacets(
      { src: "medrxiv", range: "7d", sort: "date", concept: "  Microbiome ", layer: "signals" }, true);
    expect(f).toEqual({ sources: ["medrxiv"], range: "7d", sort: "date", concept: "Microbiome", signalLayer: true, artifacts: false });
    expect(parseResearchFacets({}, false).signalLayer).toBe(false);
    expect(parseResearchFacets({ concept: "" }, false).concept).toBeUndefined();
    expect(activeFacetCount(f)).toBe(3);
    expect(activeFacetCount(parseResearchFacets({}, false))).toBe(0);
  });

  it("hides artifacts by default and counts the toggle as an active facet (#73)", () => {
    expect(parseResearchFacets({}, false).artifacts).toBe(false);
    expect(parseResearchFacets({ artifacts: "1" }, false).artifacts).toBe(true);
    expect(parseResearchFacets({ artifacts: "true" }, false).artifacts).toBe(false);
    expect(activeFacetCount(parseResearchFacets({ artifacts: "1" }, false))).toBe(1);
    // default view filters kind, NULL-safe; the toggle lifts the restriction
    expect(kindSql(false)).toBe(PAPER_FILTER_SQL);
    expect(PAPER_FILTER_SQL).toBe("coalesce(kind, 'unknown') <> 'artifact'");
    expect(kindSql(true)).toBeNull();
    expect(PAPER_FILTER_SQL).not.toMatch(/\$\d/);
  });

  it("builds a constant-only source predicate", () => {
    expect(sourceSql([])).toBeNull();
    expect(sourceSql(["arxiv"])).toBe("(source = 'arXiv Preprints')");
    const sql = sourceSql(["openalex", "journals"]) as string;
    expect(sql).toContain("source LIKE 'OpenAlex%'");
    expect(sql).toContain("source NOT LIKE 'OpenAlex%'");
    expect(sql).not.toMatch(/\$\d/);
  });

  it("toggles a source in the list", () => {
    expect(toggleSource(["arxiv"], "openalex")).toEqual(["arxiv", "openalex"]);
    expect(toggleSource(["arxiv", "openalex"], "arxiv")).toEqual(["openalex"]);
  });
});
