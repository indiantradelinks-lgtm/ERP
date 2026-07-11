/* eslint-disable no-restricted-globals */
/**
 * WorkSite Command — Service Worker
 *
 * Strategy:
 *  - Pre-cache the app shell (HTML + manifest + favicons) on install.
 *  - For navigations: network-first, fall back to cached shell when offline.
 *  - For static assets (script/style/image/font): stale-while-revalidate.
 *  - For /api/* GET requests: network-only (never serve stale data),
 *    but show an offline JSON if the network fails.
 *  - For /api/* mutations (POST/PUT/DELETE): always network — no caching.
 *
 * Bumping VERSION will purge old caches.
 */
const VERSION = "v1.0.1";
const SHELL_CACHE = `wsc-shell-${VERSION}`;
const ASSET_CACHE = `wsc-assets-${VERSION}`;

const SHELL_URLS = [
  "/",
  "/index.html",
  "/manifest.json",
  "/favicon.ico",
];

const OFFLINE_API_RESPONSE = new Response(
  JSON.stringify({
    detail: "Offline — this request requires a network connection.",
    offline: true,
  }),
  { status: 503, headers: { "Content-Type": "application/json" } }
);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((c) => c.addAll(SHELL_URLS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((k) => k !== SHELL_CACHE && k !== ASSET_CACHE)
          .map((k) => caches.delete(k))
      );
      await self.clients.claim();
    })()
  );
});

function isApiRequest(url) {
  return url.pathname.startsWith("/api/") || url.pathname.startsWith("/api");
}

function isAsset(req) {
  const dest = req.destination;
  return dest === "script" || dest === "style" || dest === "image" || dest === "font";
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") {
    // Mutations always go to network — never cache.
    return;
  }
  const url = new URL(request.url);

  // Cross-origin (e.g. Google Fonts) — let the browser handle it.
  if (url.origin !== self.location.origin) {
    return;
  }

  // 1. API GETs → network-only with offline fallback
  if (isApiRequest(url)) {
    event.respondWith(
      fetch(request).catch(() => OFFLINE_API_RESPONSE.clone())
    );
    return;
  }

  // 2. SPA navigations → network-first, shell fallback when offline
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () => {
        const cached = await caches.match("/index.html");
        return cached || OFFLINE_API_RESPONSE.clone();
      })
    );
    return;
  }

  // 3. Static assets → stale-while-revalidate
  if (isAsset(request)) {
    event.respondWith(
      caches.open(ASSET_CACHE).then(async (cache) => {
        const cached = await cache.match(request);
        const networkFetch = fetch(request)
          .then((resp) => {
            if (resp && resp.status === 200) cache.put(request, resp.clone());
            return resp;
          })
          .catch(() => cached);
        return cached || networkFetch;
      })
    );
    return;
  }
});

// Listen for an explicit message from the app to force-activate a fresh SW.
self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});
