/**
 * RouteGuard · auto-checks route permission from the central menuConfig.
 *
 * Wrap any route element with <RouteGuard>{<Page/>}</RouteGuard> OR rely on
 * the Layout-level guard which inspects the URL and consults menuConfig.
 *
 * Resolution order:
 *   1. If the route path is found in MENU_ITEMS with a `perm`, check
 *      `can(perm, "read")`.
 *   2. If item is `superAdminOnly`, require role==super_admin.
 *   3. If item is `vendorOnly`, require role==vendor.
 *   4. If item has `allowedRoles`, require role in list.
 *   5. No matching entry → allow (assumes the route is intentionally
 *      public-after-auth, e.g. /app/profile).
 */
import { useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { MENU_ITEMS } from "@/config/menuConfig";
import AccessDenied from "@/pages/AccessDenied";

function findItem(pathname) {
  // Exact match first
  for (const it of MENU_ITEMS) {
    if (it.to === pathname) return it;
  }
  // Longest matching prefix (skip comingSoon)
  let best = null;
  let bestLen = 0;
  for (const it of MENU_ITEMS) {
    if (!it.to || it.comingSoon) continue;
    if (pathname.startsWith(it.to + "/") && it.to.length > bestLen) {
      best = it;
      bestLen = it.to.length;
    }
  }
  return best;
}

export default function RouteGuard({ children }) {
  const { user, can } = useAuth();
  const location = useLocation();
  if (!user) return children;  // ProtectedRoute already gates auth

  const item = findItem(location.pathname);
  if (!item) return children;  // route not in menu config → no guard

  if (item.superAdminOnly && user.role !== "super_admin") {
    return <AccessDenied reason="This page is restricted to super admin only." />;
  }
  if (item.hideForRoles && item.hideForRoles.includes(user.role)) {
    return <AccessDenied reason="This page is not available for your role." />;
  }
  if (item.vendorOnly && user.role !== "vendor") {
    return <AccessDenied reason="This page is restricted to vendor users only." />;
  }
  if (item.allowedRoles && Array.isArray(item.allowedRoles)
      && !item.allowedRoles.includes(user.role) && user.role !== "super_admin") {
    return <AccessDenied reason={`This page requires one of these roles: ${item.allowedRoles.join(", ")}.`} />;
  }
  if (item.perm && !can(item.perm, "read")) {
    return <AccessDenied reason={`You don't have '${item.perm}' read permission.`} />;
  }
  return children;
}
