/* Service worker : met en cache l'interface pour un démarrage instantané.
   Les données (API) ne sont jamais mises en cache : elles viennent toujours du serveur. */
const CACHE = "wgm-mobile-v1";
const FICHIERS = ["./", "index.html", "app.css", "app.js", "jsQR.js", "manifest.webmanifest",
  "icone-180.png", "icone-192.png", "icone-512.png", "icone-maskable-512.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(FICHIERS))); self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(k => Promise.all(k.filter(n => n !== CACHE).map(n => caches.delete(n)))));
  self.clients.claim();
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.includes("/api/")) return;
  // Réseau d'abord (mises à jour), cache en secours.
  e.respondWith(fetch(e.request).then(r => {
    const copie = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copie)); return r;
  }).catch(() => caches.match(e.request).then(r => r || caches.match("index.html"))));
});
