/* Foxy Study service worker: lets the app install on the phone and open fast. API calls are never cached. */
const V = "foxy-v6";
const SHELL = ["/", "/static/style.css", "/static/app.js", "/static/app2.js", "/static/app3.js", "/static/i18n.js", "/static/i18n2.js", "/static/sfx.js", "/static/mascots.js", "/static/badges.js", "/static/favicon.svg"];
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => Promise.allSettled(SHELL.map(u => c.add(u)))).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/")) return;   // never touch the API
  e.respondWith(fetch(e.request).then(r => { if (r.ok) { const cp = r.clone(); caches.open(V).then(c => c.put(e.request, cp)); } return r; }).catch(() => caches.match(e.request).then(m => m || caches.match("/"))));
});
