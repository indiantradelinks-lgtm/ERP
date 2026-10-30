import axios from "axios";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

// ─── Duplicate submission guard (layer 1) ───────────────────────────────
// Two identical POSTs fired before the first one answers (double click, Enter
// twice, an impatient retry) share ONE network call — the second caller gets
// the same response instead of creating a second record. The backend holds the
// same guard for resubmits that arrive after the response.
const _inflight = new Map();
const _baseAdapter = axios.getAdapter(api.defaults.adapter);
api.defaults.adapter = (config) => {
  const method = (config.method || "").toLowerCase();
  const isFormData = typeof FormData !== "undefined" && config.data instanceof FormData;
  if (method !== "post" || isFormData) return _baseAdapter(config);
  const key = `${config.url}|${typeof config.data === "string" ? config.data : JSON.stringify(config.data ?? "")}`;
  if (_inflight.has(key)) return _inflight.get(key);
  const pending = _baseAdapter(config).finally(() => _inflight.delete(key));
  _inflight.set(key, pending);
  return pending;
};

// ─── Global 401 handler ─────────────────────────────────────────────────
// When the session cookie expires or is invalid, every background poll
// (NotificationBell, ApprovalsDashboard auto-refresh, etc.) starts firing
// 401s. Without this interceptor each rejection surfaces as a webpack
// "Uncaught runtime error" overlay in dev. Strategy:
//   1. On the very first 401, redirect the user to /login (one-shot).
//   2. Return a forever-pending promise — caller's `.then` never fires
//      so it doesn't try to read `.data` on a null response and crash.
//   3. Auth endpoints (`/auth/login`, `/auth/register`) are exempt so the
//      login form can still show "Invalid credentials" toasts.
let _redirected = false;
const _foreverPending = new Promise(() => {});  // never resolves, never rejects
api.interceptors.response.use(
  (r) => {
    // A repeat submission the backend answered from its cache — tell the user
    // nothing new was saved, otherwise the page shows a misleading "created".
    if (r?.headers?.["x-duplicate-submission"] === "replayed") {
      const ref = r.headers["x-duplicate-record"];
      toast.warning("Already submitted — not saved again", {
        description: ref ? `This entry was already saved as ${ref}.` : "The original entry was returned instead of creating a second record.",
        id: `dup-replay-${ref || r.config?.url}`, duration: 8000,
      });
    }
    return r;
  },
  (error) => {
    const status = error?.response?.status;
    const url = error?.config?.url || "";
    const isAuthCall = url.includes("/auth/login") || url.includes("/auth/register");
    const isMeCall = url.includes("/auth/me");

    if (status === 401 && !isAuthCall) {
      if (!_redirected && typeof window !== "undefined") {
        const here = window.location.pathname + window.location.search;
        // Public token pages (e.g. vendor PO acknowledgement) must never bounce to /login.
        const isPublicPage = here.startsWith("/login") || here.startsWith("/po-ack");
        if (!isPublicPage) {
          _redirected = true;
          window.location.href = `/login?next=${encodeURIComponent(here)}`;
        }
      }
      // /auth/me must reject so AuthContext can finish its initial session check.
      if (isMeCall) return Promise.reject(error);
      return _foreverPending;
    }
    // Friendly full-screen notice when a project-scoped user follows a link
    // to a project that is not assigned to them.
    // FastAPI 422s return `detail` as an ARRAY of validation objects. Callers
    // toast `detail` directly, and React cannot render an object — that used to
    // unmount the whole app (white screen). Normalise it to text once, here, so
    // no caller can ever hand an object to a toast.
    if (error?.response?.data && error.response.data.detail != null
        && typeof error.response.data.detail !== "string") {
      error.response.data.detail_raw = error.response.data.detail;
      error.response.data.detail = formatApiErrorDetail(error.response.data.detail);
    }
    const detail = error?.response?.data?.detail;
    // Duplicate blocked by the ERP-wide guard — always surface a clear warning.
    if (status === 409 && error?.response?.data?.duplicate) {
      const msg = formatApiErrorDetail(detail);
      toast.warning("Duplicate detected — not saved", { description: msg, id: `dup-${msg}`, duration: 8000 });
    }
    if (status === 403 && typeof detail === "string" && detail.toLowerCase().includes("access to this project")) {
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("project-access-denied"));
      }
    }
    return Promise.reject(error);
  }
);

export function formatApiErrorDetail(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => {
      if (!e || typeof e !== "object") return String(e ?? "");
      const where = Array.isArray(e.loc)
        ? e.loc.filter((p) => p !== "body").join(" → ")
        : "";
      const msg = typeof e.msg === "string" ? e.msg : JSON.stringify(e);
      return where ? `${where}: ${msg}` : msg;
    }).filter(Boolean).join(" · ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  if (typeof detail === "object") { try { return JSON.stringify(detail); } catch { return "Request failed"; } }
  return String(detail);
}

export function apiErrorMessage(err, fallback = "Request failed") {
  return formatApiErrorDetail(err?.response?.data?.detail) || fallback;
}

export function stripEmpty(obj) {
  // Drop "", null, undefined values from a plain object so backend optional
  // validators (EmailStr etc.) don't reject empty strings.
  const out = {};
  for (const [k, v] of Object.entries(obj || {})) {
    if (v === "" || v === null || v === undefined) continue;
    out[k] = v;
  }
  return out;
}
