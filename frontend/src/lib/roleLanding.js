/**
 * Single source of truth for which landing route a given role gets after login.
 * Imported by Login.jsx (post-submit redirect) and Dashboard.jsx (defensive
 * <Navigate> guard for direct /app hits). Add new roles here, never inline.
 */
export function roleLandingPath(role) {
  if (role === "super_admin") return "/app";
  if (role === "vendor") return "/app/vendor-portal";
  // Every other authenticated role lands on the department launcher.
  return "/app/modules";
}
