// Minimal service worker: makes the app installable. Always goes to the network –
// rules and status must never be served stale from a cache.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
