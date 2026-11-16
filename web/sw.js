// Uygulama kabuğunu önbelleğe alır (çevrimdışı açılsın), API'ye dokunmaz; bildirimleri gösterir.
const ONBELLEK = "kalori-v1";
const KABUK = ["/", "/yemekler.js", "/ikon-192.png", "/ikon-512.png", "/apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(ONBELLEK).then((c) => c.addAll(KABUK)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((adlar) => Promise.all(adlar.filter((a) => a !== ONBELLEK).map((a) => caches.delete(a)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/") || url.pathname === "/manifest.webmanifest") return;
  e.respondWith(
    fetch(e.request)
      .then((y) => { const k = y.clone(); caches.open(ONBELLEK).then((c) => c.put(e.request, k)); return y; })
      .catch(() => caches.match(e.request, { ignoreSearch: true }))
  );
});

self.addEventListener("push", (e) => {
  let v = { baslik: "Zayıflama", govde: "" };
  try { v = e.data.json(); } catch {}
  e.waitUntil(self.registration.showNotification(v.baslik, { body: v.govde, icon: "/ikon-192.png", badge: "/ikon-192.png" }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: "window" }).then((l) => (l.length ? l[0].focus() : self.clients.openWindow("/"))));
});
