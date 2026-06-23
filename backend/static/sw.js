const CACHE_NAME = "stocktake-v41";
const APP_SHELL = [
  "/",
  "/index.html",
  "/mapping.html",
  "/styles.css?v=scanner-recovery-4",
  "/app.js?v=scanner-recovery-4",
  "/mapping.js?v=scanner-recovery-4",
  "/frontend-utils.js?v=scanner-recovery-4",
  "/manifest.webmanifest",
  "/vendor/zxing-library.min.js?v=scanner-recovery-4"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  const isApiLike = [
    "/catalog",
    "/sync/",
    "/sessions",
    "/products/",
    "/pre-export/",
    "/export/",
    "/admin",
    "/admin/api/",
    "/mapping",
    "/product-images/"
  ].some((path) => url.pathname.startsWith(path));
  if (isApiLike) {
    event.respondWith(fetch(event.request));
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (!response || !response.ok || response.type === "opaque") return response;
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request).then((cached) => {
        if (cached) return cached;
        if (event.request.mode === "navigate") return caches.match("/");
        return new Response("Offline asset unavailable", {
          status: 503,
          statusText: "Service Unavailable",
          headers: { "Content-Type": "text/plain" }
        });
      }))
  );
});
