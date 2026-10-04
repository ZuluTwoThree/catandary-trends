/**
 * The Field Watch gate on the public article page (owner 2026-10-04, launch
 * evening). Everything below the generated article — signal details, tags,
 * same-story reports, related signals — is blurred on the public site; a hover
 * (or, on touch devices, always) shows who gets to see it and how to ask.
 *
 * Plain words, one address. Since the launch evening the source link sits
 * behind the gate too (owner): the attribution stays in the markup and in the
 * JSON-LD, but is not readable for visitors without Field Watch.
 */
export const CONTACT_EMAIL = "contact@catandary.de";

export const FIELD_WATCH_GATE_LABEL = "Field Watch clients only";

export const FIELD_WATCH_GATE_TEXT =
  "The source link, signal details, tags, other reports of the same story and " +
  "related signals are part of Field Watch — our monitored-field service for " +
  "clients. The article itself is free for everyone.";

export const FIELD_WATCH_GATE_CTA = "Ask about Field Watch:";

export const FIELD_WATCH_MAILTO =
  `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("Field Watch")}`;
