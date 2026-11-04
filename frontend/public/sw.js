/* RouteProof service worker: app-shell caching so the driver capture screens open offline.
 * API traffic is never cached (images/CSV are private). Uploads are retried by the page (foreground sync);
 * Background Sync, when available, only wakes open pages because the auth token lives in the page, not here. */
const VERSION = "rp-v1";
const SHELL = ["/", "/driver", "/login", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL).catch(() => {})));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return; // never touch cross-origin API calls
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req).then((r) => { const copy = r.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); return r; })
        .catch(() => caches.match(req).then((m) => m || caches.match("/driver") || caches.match("/"))),
    );
    return;
  }
  if (url.pathname.startsWith("/_next/static/") || /\.(?:svg|png|webmanifest|woff2?)$/.test(url.pathname)) {
    e.respondWith(caches.match(req).then((m) => m || fetch(req).then((r) => { const copy = r.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); return r; })));
  }
});

self.addEventListener("sync", (e) => {
  if (e.tag === "rp-upload") {
    e.waitUntil(self.clients.matchAll().then((cs) => cs.forEach((c) => c.postMessage("rp-sync"))));
  }
});
