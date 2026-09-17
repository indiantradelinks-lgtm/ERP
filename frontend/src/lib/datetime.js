/**
 * Single source of truth for date/time display across every ERP module.
 *
 * The backend stores everything in UTC (`2026-09-14T09:01:54+00:00`). Printing
 * that raw (or letting each device apply its own timezone) made the same action
 * read differently on different screens. Everything below renders in IST
 * (Asia/Kolkata) — the company's operating timezone — e.g. "14 Sep 2026, 2:31 PM IST".
 */
const TZ = "Asia/Kolkata";

/** Parse an ISO string / Date. Strings with no timezone are treated as UTC (backend default). */
export function toDate(value) {
  if (!value) return null;
  if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
  let s = String(value).trim();
  if (!s) return null;
  const hasTime = s.includes("T") || /\d{2}:\d{2}/.test(s);
  const hasTz = /(Z|[+-]\d{2}:?\d{2})$/.test(s);
  const hasSeconds = /\d{2}:\d{2}:\d{2}/.test(s);
  // Backend timestamps are full ISO with seconds → UTC. Values typed into a
  // datetime-local input ("2026-09-14T10:30") are local wall time → leave as-is.
  if (hasTime && !hasTz && hasSeconds) s = `${s.replace(" ", "T")}Z`;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

/** True for plain calendar dates like "2026-09-14" — these must not be timezone-shifted. */
function isDateOnly(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value.trim());
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parts(d) {
  const f = new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ, day: "2-digit", month: "2-digit", year: "numeric",
    hour: "numeric", minute: "2-digit", hour12: true,
  }).formatToParts(d);
  const get = (t) => (f.find((p) => p.type === t) || {}).value || "";
  return {
    day: get("day"), month: MONTHS[Number(get("month")) - 1] || get("month"), year: get("year"),
    hour: get("hour"), minute: get("minute"),
    dayPeriod: (get("dayPeriod") || "").toUpperCase().replace(/\./g, ""),
  };
}

/** "14 Sep 2026, 2:31 PM IST" */
export function fmtDT(value, { withTz = true, fallback = "—" } = {}) {
  if (isDateOnly(value)) return fmtD(value, { fallback });
  const d = toDate(value);
  if (!d) return fallback;
  const p = parts(d);
  return `${p.day} ${p.month} ${p.year}, ${p.hour}:${p.minute} ${p.dayPeriod}${withTz ? " IST" : ""}`;
}

/** "14 Sep 2026" */
export function fmtD(value, { fallback = "—" } = {}) {
  if (isDateOnly(value)) {
    const [y, m, dd] = value.trim().split("-");
    return `${dd} ${MONTHS[Number(m) - 1]} ${y}`;
  }
  const d = toDate(value);
  if (!d) return fallback;
  const p = parts(d);
  return `${p.day} ${p.month} ${p.year}`;
}

/** "2:31 PM" */
export function fmtT(value, { withTz = false, fallback = "—" } = {}) {
  const d = toDate(value);
  if (!d) return fallback;
  const p = parts(d);
  return `${p.hour}:${p.minute} ${p.dayPeriod}${withTz ? " IST" : ""}`;
}

/** "just now" · "5 min ago" · "3 h ago" · "2 d ago" · then the absolute date */
export function fmtRel(value, { fallback = "—" } = {}) {
  const d = toDate(value);
  if (!d) return fallback;
  const secs = Math.round((Date.now() - d.getTime()) / 1000);
  const abs = Math.abs(secs);
  if (abs < 45) return "just now";
  if (abs < 3600) return `${Math.round(abs / 60)} min ${secs < 0 ? "from now" : "ago"}`;
  if (abs < 86400) return `${Math.round(abs / 3600)} h ${secs < 0 ? "from now" : "ago"}`;
  if (abs < 7 * 86400) return `${Math.round(abs / 86400)} d ${secs < 0 ? "from now" : "ago"}`;
  return fmtD(d);
}

/** "14 Sep 2026, 2:31 PM IST · 5 min ago" — for request/approval timelines */
export function fmtDTRel(value, { fallback = "—" } = {}) {
  const d = toDate(value);
  if (!d) return fallback;
  return `${fmtDT(d)} · ${fmtRel(d)}`;
}

/** Today in IST as YYYY-MM-DD — for date inputs and "as on" defaults. */
export function todayIST() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date());
}
