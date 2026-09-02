/**
 * JSON-LD embedding must survive hostile strings from feeds / LLM output
 * (security review 2026-09-02, F-2). Both the serialiser and the rendered
 * component are checked — the component is what the page actually emits.
 */
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { serializeJsonLd } from "./jsonld";
import { TrendArticleJsonLd } from "@/components/JsonLd";
import type { Trend } from "./types";

const HOSTILE = '</script><script>alert(1)</script>';

describe("serializeJsonLd", () => {
  it("never emits a raw < > or & (so a </script> in data cannot close the tag)", () => {
    const out = serializeJsonLd({ headline: HOSTILE, x: "a&b <c>" });
    expect(out).not.toMatch(/[<>&]/);
    expect(out).not.toContain("</script>");
  });

  it("stays valid JSON and round-trips the original string", () => {
    const out = serializeJsonLd({ headline: HOSTILE, amp: "R&D", u: "x\u2028y" });
    const back = JSON.parse(out);
    expect(back.headline).toBe(HOSTILE);
    expect(back.amp).toBe("R&D");
    expect(back.u).toBe("x\u2028y");
    expect(out).not.toContain("\u2028");
  });

  it("leaves ordinary payloads readable", () => {
    expect(serializeJsonLd({ "@type": "Article", headline: "Plain title" })).toBe(
      '{"@type":"Article","headline":"Plain title"}'
    );
  });
});

describe("TrendArticleJsonLd", () => {
  const trend = {
    id: 1,
    slug: "hostile",
    title_en: HOSTILE,
    summary_en: "summary with </script> inside & <b>",
    tags: ["<img src=x onerror=alert(1)>", "ok"],
    primary_vertical: "TECH",
    published_at: "2026-09-01",
    created_at: "2026-09-01",
  } as unknown as Trend;

  it("renders one ld+json script whose body contains no </script>", () => {
    const html = renderToStaticMarkup(createElement(TrendArticleJsonLd, { trend }));
    // exactly one opening and one closing script tag — the injected one did not escape
    expect(html.match(/<script/g)?.length).toBe(1);
    expect(html.match(/<\/script>/g)?.length).toBe(1);
    expect(html).toContain('type="application/ld+json"');
    const body = html.replace(/^.*?>/, "").replace(/<\/script>$/, "");
    expect(body).not.toMatch(/[<>&]/);
    expect(JSON.parse(body).headline).toBe(HOSTILE);
  });
});
