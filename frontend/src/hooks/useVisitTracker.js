/**
 * useVisitTracker — fires a fire-and-forget /telemetry/module-visit ping
 * on every meaningful route change inside /app/*. Powers the personalised
 * Quick Actions on Department Workspace pages.
 *
 * Design notes
 * ------------
 *  - Skips landing pages (/app, /app/, /app/modules, /app/modules/:dept)
 *    because visiting the workspace itself isn't a "shortcut usage".
 *  - Skips profile / email settings — noise.
 *  - Uses findDepartmentForRoute() from menuConfig so we don't duplicate
 *    the pathname→department mapping.
 *  - Uses `keepalive` semantics via axios (fire-and-forget) — we never
 *    await the response nor surface errors. Backend errors are silent.
 */
import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { findDepartmentForRoute } from "@/config/menuConfig";

const SKIP_EXACT = new Set(["/app", "/app/", "/app/modules", "/app/profile", "/app/me/email"]);

export default function useVisitTracker(isAuthed) {
  const { pathname } = useLocation();

  useEffect(() => {
    if (!isAuthed) return;
    if (!pathname || !pathname.startsWith("/app/") && pathname !== "/app") return;
    if (SKIP_EXACT.has(pathname)) return;
    // Department workspace landing pages themselves are not shortcuts.
    if (pathname.startsWith("/app/modules/")) return;

    const dept = findDepartmentForRoute(pathname) || undefined;
    // Fire-and-forget; ignore all errors so this never disrupts UX.
    api.post("/telemetry/module-visit", { path: pathname, dept }).catch(() => {});
  }, [pathname, isAuthed]);
}
