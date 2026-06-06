import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

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

    if (status === 401 && !isAuthCall) {
      if (!_redirected && typeof window !== "undefined") {
        _redirected = true;
        const here = window.location.pathname + window.location.search;
        if (!here.startsWith("/login")) {
          window.location.href = `/login?next=${encodeURIComponent(here)}`;
        }
      }
      return _foreverPending;
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
