/**
 * Resolve a tone (success | info | warning | danger | primary | neutral) from a
 * lookup table — used by status/severity/stage badges across pages so we can
 * avoid nested ternary chains like
 *   tone: r.status === "approved" ? "success" : r.status === "rejected" ? "danger" : "warning"
 *
 * Usage:
 *   const PO_TONE = { approved: "success", rejected: "danger", received: "info" };
 *   tone: toneFor(PO_TONE, r.status, "warning")
 *
 * @param {Record<string, string>} map     lookup of value -> tone
 * @param {string|undefined|null} value    the discriminating value
 * @param {string} fallback                tone returned when value is missing/unknown
 * @returns {string}
 */
export function toneFor(map, value, fallback = "neutral") {
  if (value == null) return fallback;
  return map[value] || fallback;
}
