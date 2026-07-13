/**
 * Register the service worker for offline support + install prompt.
 * Only runs in production builds (skipped in `yarn start` to avoid HMR conflicts).
 *
 * To force-refresh a deployed app, bump VERSION in /public/service-worker.js
 * and postMessage("SKIP_WAITING") from the page.
 */
export function registerServiceWorker() {
  if (typeof window === "undefined") return;
  if (!("serviceWorker" in navigator)) return;
  // Skip in localhost dev (CRA dev-server hot-reload conflicts with SW caching).
  const host = window.location.hostname;
  const isLocalDev = host === "localhost" || host === "127.0.0.1";
  if (isLocalDev && process.env.NODE_ENV !== "production") return;

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/service-worker.js")
      .then((reg) => {
        // Auto-activate any newer SW that finished installing.
        if (reg.waiting) reg.waiting.postMessage("SKIP_WAITING");
        reg.addEventListener("updatefound", () => {
          const sw = reg.installing;
          if (!sw) return;
          sw.addEventListener("statechange", () => {
            if (sw.state === "installed" && navigator.serviceWorker.controller) {
              sw.postMessage("SKIP_WAITING");
            }
          });
        });
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.warn("[sw] registration failed", err);
      });

    // Reload once when a new SW takes control so the user is on fresh assets.
    let reloaded = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (reloaded) return;
      reloaded = true;
      window.location.reload();
    });
  });
}
