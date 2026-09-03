import { describe, expect, it } from "vitest";
import { sourceLicenseNotice } from "./sourceLicense";

describe("sourceLicenseNotice", () => {
  it("returns the CC BY notice for OpenAIRE and CORDIS", () => {
    expect(sourceLicenseNotice("OpenAIRE Projects (EU + National Funders)")?.licenseName).toBe("CC BY 4.0");
    expect(sourceLicenseNotice("CORDIS EU Research Projects (SME Participations)")?.text).toContain("CORDIS");
  });
  it("returns OGL for UKRI", () => {
    expect(sourceLicenseNotice("UKRI Gateway to Research (UK)")?.licenseName).toBe("Open Government Licence v3.0");
  });
  it("returns null for trade media, public-domain and empty names", () => {
    for (const n of ["TechCrunch", "NSF Awards (US Federal Research Funding)", "", null, undefined]) {
      expect(sourceLicenseNotice(n)).toBeNull();
    }
  });
});
