import { useEffect, useRef } from "react";

/**
 * Background auto-sync: calls `callback` every `interval` ms while the tab is
 * visible. Skips ticks when a dialog is open, the user is typing in a form
 * field, or a previous sync is still in flight (no duplicate API calls, no
 * loss of unsaved form data, no page reset).
 */
export default function useAutoSync(callback, { interval = 3000, enabled = true } = {}) {
  const cbRef = useRef(callback);
  cbRef.current = callback;
  const busyRef = useRef(false);

  useEffect(() => {
    if (!enabled) return undefined;
    const id = setInterval(async () => {
      if (document.visibilityState !== "visible") return;
      if (busyRef.current) return;
      if (document.querySelector('[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]')) return;
      const ae = document.activeElement;
      if (ae && (["INPUT", "TEXTAREA", "SELECT"].includes(ae.tagName) || ae.isContentEditable)) return;
      busyRef.current = true;
      try { await cbRef.current(); } catch { /* silent */ } finally { busyRef.current = false; }
    }, interval);
    return () => clearInterval(id);
  }, [enabled, interval]);
}
