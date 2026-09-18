/**
 * Mirror of pipeline/dossier_brief.deterministic_question_check — the same
 * cases as tests/test_dossier_brief.py::TestDeterministicQuestionCheck, so a
 * drift between the two rules shows up on one side or the other.
 */
import { describe, it, expect } from "vitest";
import { questionCheck } from "@/lib/dossierIntake";

const DATACENTER_V1 =
  "The purpose of the dossier is to provide a free sample for the IT Manager of a small " +
  "German technology firm providing IT Infrastructure and software development services in " +
  "their own company group and for related regional partner companies.";

describe("questionCheck", () => {
  it("rejects the datacenter v1 purpose description with a reason", () => {
    const r = questionCheck(DATACENTER_V1);
    expect(r.ok).toBe(false);
    expect(r.reason).toContain("does not ask");
  });

  it("accepts empty (standard question applies)", () => {
    expect(questionCheck("")).toEqual({ ok: true, reason: "" });
    expect(questionCheck(null)).toEqual({ ok: true, reason: "" });
    expect(questionCheck("  \n ")).toEqual({ ok: true, reason: "" });
  });

  it("accepts a question mark anywhere", () => {
    expect(questionCheck("Context first. What moves in LFP cells?").ok).toBe(true);
  });

  it.each([
    "Which stack should we run after the Broadcom change",
    "How mature is sodium-ion for stationary storage",
    "welche Regulierung gilt für Novel Food in der EU",
    "Was bewegt sich bei Perowskit-Tandemzellen",
    '"Should a mid-sized firm adopt Proxmox"',
    "Is the EU Data Act applicable to hosting providers",
  ])("accepts an interrogative opening without '?': %s", (q) => {
    expect(questionCheck(q)).toEqual({ ok: true, reason: "" });
  });

  it.each([
    "The dossier is a free sample for the IT manager.",
    "Overview of virtualization stacks for SMEs.",
    "Ein Überblick über Batterietechnologien für Kunden.",
  ])("rejects a description: %s", (q) => {
    expect(questionCheck(q).ok).toBe(false);
  });
});
