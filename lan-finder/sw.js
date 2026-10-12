/* LAN Finder offline shell - v2.4.0 */
const CACHE_NAME = "lan-finder-shell-v2.4.0";
const PAGE_URL = new URL("./index.html", self.registration.scope).href;
const SCOPE_PATH = new URL(self.registration.scope).pathname;

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.add(new Request(PAGE_URL, { cache: "reload" }));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k.startsWith("lan-finder-shell-") && k !== CACHE_NAME).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.mode !== "navigate") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || (url.pathname !== SCOPE_PATH && url.pathname !== SCOPE_PATH + "index.html")) return;
  event.respondWith((async () => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 4500);
    try {
      const response = await fetch(request, { signal: controller.signal });
      if (response.ok) {
        try {
          const cache = await caches.open(CACHE_NAME);
          await cache.put(PAGE_URL, response.clone());
        } catch (_) { /* Storage may be unavailable; still display the live page. */ }
      }
      return response;
    } catch (error) {
      const cache = await caches.open(CACHE_NAME);
      return (await cache.match(PAGE_URL)) || Response.error();
    } finally {
      clearTimeout(timer);
    }
  })());
});
