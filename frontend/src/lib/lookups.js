import { api } from "@/lib/api";

// Short-lived cache + in-flight dedupe for dropdown/lookup GETs that many
// screens request at the same time (projects, clients, vendors, employees…).
const TTL_MS = 60_000;
const cache = new Map();   // url -> { at, data }
const inflight = new Map(); // url -> Promise

export function lookupGet(url, { ttl = TTL_MS } = {}) {
  const hit = cache.get(url);
  if (hit && Date.now() - hit.at < ttl) return Promise.resolve({ data: hit.data });
  if (inflight.has(url)) return inflight.get(url);
  const p = api.get(url)
    .then((res) => { cache.set(url, { at: Date.now(), data: res.data }); return res; })
    .finally(() => inflight.delete(url));
  inflight.set(url, p);
  return p;
}

export function invalidateLookup(prefix = "") {
  [...cache.keys()].forEach((k) => { if (k.startsWith(prefix)) cache.delete(k); });
}

// Any write anywhere invalidates lookups so freshly created masters appear immediately.
api.interceptors.request.use((config) => {
  const m = (config.method || "get").toLowerCase();
  if (m !== "get" && m !== "head" && m !== "options") cache.clear();
  return config;
});
