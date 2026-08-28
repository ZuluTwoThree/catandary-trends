import { describe, it, expect } from "vitest";
import {
  parseAnalysisFile,
  buildAnalysisList,
  findAnalysisBySlug,
  formatAnalysisDate,
  analysisImagePath,
  type RawAnalysisFile,
} from "@/lib/analyses";

function file(overrides: Partial<Record<string, string>> = {}, body = "Body text."): RawAnalysisFile {
  const fm = {
    slug: "example-analysis",
    title: "Example Analysis",
    date: "2026-09-14",
    teaser: "One sentence teaser.",
    image: "example.png",
    corpus_asof: "2026-09-12",
    author: "Dirk Herrmann",
    ...overrides,
  };
  const yamlLines = Object.entries(fm)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `${k}: ${/^\d{4}-\d{2}-\d{2}$/.test(String(v)) ? v : JSON.stringify(v)}`);
  return {
    filename: `${fm.slug}.md`,
    raw: `---\n${yamlLines.join("\n")}\n---\n${body}\n`,
  };
}

describe("parseAnalysisFile — frontmatter parsing", () => {
  it("parses a well-formed file into an Analysis", () => {
    const a = parseAnalysisFile(file());
    expect(a).toEqual({
      slug: "example-analysis",
      title: "Example Analysis",
      date: "2026-09-14",
      teaser: "One sentence teaser.",
      image: "example.png",
      corpus_asof: "2026-09-12",
      author: "Dirk Herrmann",
      draft: false,
      body: "Body text.",
    });
  });

  it("defaults draft to false when the field is absent", () => {
    const a = parseAnalysisFile(file());
    expect(a.draft).toBe(false);
  });

  it("reads draft: true", () => {
    const raw: RawAnalysisFile = {
      filename: "draft-one.md",
      raw: "---\nslug: draft-one\ntitle: \"Draft\"\ndate: 2026-01-01\nteaser: \"t\"\nimage: d.png\ncorpus_asof: 2026-01-01\nauthor: A\ndraft: true\n---\nBody\n",
    };
    expect(parseAnalysisFile(raw).draft).toBe(true);
  });

  it("tolerates a trailing YAML comment on a field, as in the #93 frontmatter spec", () => {
    const raw: RawAnalysisFile = {
      filename: "commented.md",
      raw:
        "---\n" +
        "slug: commented\n" +
        'title: "Title"\n' +
        "date: 2026-09-14\n" +
        'teaser: "Teaser"\n' +
        "image: commented.png   # OG-Bild, Pflicht\n" +
        "corpus_asof: 2026-09-12          # Rechenstand, nicht Veröffentlichungsdatum\n" +
        "author: Dirk Herrmann\n" +
        "---\n" +
        "Body\n",
    };
    const a = parseAnalysisFile(raw);
    expect(a.image).toBe("commented.png");
    expect(a.corpus_asof).toBe("2026-09-12");
  });

  it("normalizes an unquoted YAML date scalar to an ISO string", () => {
    // js-yaml parses a bare `2026-09-14` as a JS Date (YAML 1.1 timestamp);
    // toIsoDate() must fold that back to "2026-09-14", not "2026-09-14T00:..." etc.
    const a = parseAnalysisFile(file());
    expect(a.date).toBe("2026-09-14");
    expect(a.corpus_asof).toBe("2026-09-12");
  });

  it("throws when the frontmatter block is missing", () => {
    expect(() => parseAnalysisFile({ filename: "bad.md", raw: "Just a body, no frontmatter.\n" })).toThrow(
      /missing YAML frontmatter/
    );
  });

  it.each(["slug", "title", "teaser", "image", "author"] as const)(
    "throws when required field %s is missing",
    (field) => {
      expect(() => parseAnalysisFile(file({ [field]: undefined }))).toThrow(
        new RegExp(`"${field}"`)
      );
    }
  );

  it("throws when date is not an ISO date string", () => {
    expect(() => parseAnalysisFile(file({ date: "not-a-date" }))).toThrow(/ISO date/);
  });

  it("throws when draft is present but not a boolean", () => {
    const raw: RawAnalysisFile = {
      filename: "bad-draft.md",
      raw: '---\nslug: s\ntitle: "t"\ndate: 2026-01-01\nteaser: "t"\nimage: i.png\ncorpus_asof: 2026-01-01\nauthor: A\ndraft: "yes"\n---\nBody\n',
    };
    expect(() => parseAnalysisFile(raw)).toThrow(/"draft" must be a boolean/);
  });

  it.each(["../secret.png", "sub/dir.png", "back\\slash.png"])(
    "rejects an image value with path segments: %s",
    (image) => {
      expect(() => parseAnalysisFile(file({ image }))).toThrow(/bare filename/);
    }
  );
});

describe("buildAnalysisList — draft filter + sort", () => {
  it("excludes draft entries", () => {
    const files: RawAnalysisFile[] = [
      file({ slug: "published-a", date: "2026-09-01" }),
      {
        filename: "draft-b.md",
        raw: '---\nslug: draft-b\ntitle: "Draft"\ndate: 2026-09-05\nteaser: "t"\nimage: d.png\ncorpus_asof: 2026-09-01\nauthor: A\ndraft: true\n---\nBody\n',
      },
    ];
    const list = buildAnalysisList(files);
    expect(list.map((a) => a.slug)).toEqual(["published-a"]);
  });

  it("sorts newest date first", () => {
    const files: RawAnalysisFile[] = [
      file({ slug: "oldest", date: "2026-01-01" }),
      file({ slug: "newest", date: "2026-09-14" }),
      file({ slug: "middle", date: "2026-05-01" }),
    ];
    const list = buildAnalysisList(files);
    expect(list.map((a) => a.slug)).toEqual(["newest", "middle", "oldest"]);
  });

  it("throws on a slug collision across two files, naming both filenames", () => {
    const files: RawAnalysisFile[] = [
      { ...file({ slug: "same-slug" }), filename: "a.md" },
      { ...file({ slug: "same-slug" }), filename: "b.md" },
    ];
    expect(() => buildAnalysisList(files)).toThrow(/a\.md.*b\.md|b\.md.*a\.md/);
  });

  it("returns an empty list for an empty input (the pre-launch empty state)", () => {
    expect(buildAnalysisList([])).toEqual([]);
  });
});

describe("findAnalysisBySlug", () => {
  const files: RawAnalysisFile[] = [
    file({ slug: "published-one" }),
    {
      filename: "draft-one.md",
      raw: '---\nslug: draft-one\ntitle: "Draft"\ndate: 2026-01-01\nteaser: "t"\nimage: d.png\ncorpus_asof: 2026-01-01\nauthor: A\ndraft: true\n---\nBody\n',
    },
  ];

  it("finds a published analysis by slug", () => {
    expect(findAnalysisBySlug(files, "published-one")?.slug).toBe("published-one");
  });

  it("returns null for an unknown slug", () => {
    expect(findAnalysisBySlug(files, "nope")).toBeNull();
  });

  it("returns null for a draft slug — a draft 404s exactly like a miss (#93)", () => {
    expect(findAnalysisBySlug(files, "draft-one")).toBeNull();
  });

  it("still enforces slug-collision checking even though the match may be a draft", () => {
    const colliding: RawAnalysisFile[] = [
      { ...file({ slug: "dup" }), filename: "a.md" },
      { ...file({ slug: "dup" }), filename: "b.md" },
    ];
    expect(() => findAnalysisBySlug(colliding, "dup")).toThrow(/Duplicate analysis slug/);
  });
});

describe("formatAnalysisDate", () => {
  it("formats an ISO date as a long English date", () => {
    expect(formatAnalysisDate("2026-09-14")).toBe("September 14, 2026");
  });

  it("is stable regardless of local timezone (parsed as UTC)", () => {
    expect(formatAnalysisDate("2026-01-01")).toBe("January 1, 2026");
    expect(formatAnalysisDate("2026-12-31")).toBe("December 31, 2026");
  });

  it("falls back to the raw string for an unparseable date instead of throwing", () => {
    expect(formatAnalysisDate("not-a-date")).toBe("not-a-date");
  });
});

describe("analysisImagePath", () => {
  it("resolves against the public/analyses convention", () => {
    expect(analysisImagePath("foo.png")).toBe("/analyses/foo.png");
  });
});
