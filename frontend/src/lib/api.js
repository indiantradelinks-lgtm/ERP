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
  (r) => r,
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
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
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
