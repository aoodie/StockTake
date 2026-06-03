const CACHE_NAME = "stocktake-v8";
const APP_SHELL = [
  "/",
  "/index.html",
  "/mapping",
  "/mapping.html",
  "/styles.css",
  "/app.js?v=pw-fast-1",
  "/mapping.js?v=phone-mapping-3",
  "/frontend-utils.js?v=pw-fast-1",
  "/frontend-utils.js?v=phone-mapping-3",
  "/manifest.webmanifest",
  "/vendor/zxing-library.min.js"
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
    "/product-images/"
  ].some((path) => url.pathname.startsWith(path));
  if (isApiLike) {
    event.respondWith(fetch(event.request));
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request).then((cached) => cached || caches.match("/")))
  );
});
