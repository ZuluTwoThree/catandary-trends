/**
 * The Field Watch gate on the public article page (owner 2026-10-04, launch
 * evening). Everything below the generated article — signal details, tags,
 * same-story reports, related signals — is blurred on the public site; a hover
 * (or, on touch devices, always) shows who gets to see it and how to ask.
 *
 * Plain words, one address. The source link is NOT behind the gate: source
 * attribution is mandatory and the AI disclosure promises "the single source
 * linked below".
 */
export const CONTACT_EMAIL = "contact@catandary.de";

export const FIELD_WATCH_GATE_LABEL = "Field Watch clients only";

export const FIELD_WATCH_GATE_TEXT =
  "Signal details, tags, other reports of the same story and related signals are " +
  "part of Field Watch — our monitored-field service for clients. The article and " +
  "its source above are free for everyone.";

export const FIELD_WATCH_GATE_CTA = "Ask about Field Watch:";

export const FIELD_WATCH_MAILTO =
  `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("Field Watch")}`;
