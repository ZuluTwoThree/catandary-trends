import { describe, it, expect } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import FieldWatchGate from "@/components/FieldWatchGate";
import {
  CONTACT_EMAIL,
  FIELD_WATCH_GATE_LABEL,
  FIELD_WATCH_GATE_TEXT,
  FIELD_WATCH_MAILTO,
} from "@/lib/fieldWatchGate";

const child = createElement("section", { id: "below" }, "signal details");

describe("FieldWatchGate", () => {
  it("renders the children untouched on the owner instance", () => {
    const html = renderToStaticMarkup(createElement(FieldWatchGate, { active: false, children: child }));
    expect(html).toBe('<section id="below">signal details</section>');
  });

  it("blurs the children and explains the gate on the public site", () => {
    const html = renderToStaticMarkup(createElement(FieldWatchGate, { active: true, children: child }));
    expect(html).toContain('data-testid="field-watch-gate"');
    expect(html).toMatch(/aria-hidden="true"[^>]*blur-\[6px\]/);
    expect(html).toContain('<section id="below">signal details</section>');
    expect(html).toContain(FIELD_WATCH_GATE_LABEL);
    expect(html).toContain(FIELD_WATCH_GATE_TEXT);
    expect(html).toContain(`href="${FIELD_WATCH_MAILTO.replace(/&/g, "&amp;")}"`);
    expect(html).toContain(CONTACT_EMAIL);
    // CSS-only hover: no handlers, no script
    expect(html).not.toMatch(/onClick|<script/);
  });

  it("speaks plainly and names one address", () => {
    expect(CONTACT_EMAIL).toBe("contact@catandary.de");
    expect(FIELD_WATCH_GATE_TEXT).toMatch(/Field Watch/);
    expect(FIELD_WATCH_GATE_TEXT).toMatch(/free for everyone/);
    expect(FIELD_WATCH_GATE_TEXT).not.toMatch(/tier|premium|unlock|paywall|subscription/i);
    expect(FIELD_WATCH_MAILTO).toMatch(/^mailto:contact@catandary\.de\?subject=/);
  });
});
