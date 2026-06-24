/* The Morning Commute — service worker: offline shell + runtime cache for episodes/audio. */
const SHELL = 'commute-shell-v2';
const RUNTIME = 'commute-runtime-v2';
const SHELL_FILES = [
  './', 'index.html', 'styles.css', 'app.js', 'manifest.webmanifest',
  'icon-192.png', 'icon-512.png', 'apple-touch-icon.png',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== SHELL && k !== RUNTIME).map(k => caches.delete(k)))
  ).then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // audio: cache-first regardless of origin — episodes now stream from a bucket/CDN
  // (R2), a different origin than the app shell. Range requests (206) can't be cached,
  // so offline coverage is best-effort: full (200) fetches are stored, range plays
  // fall through to the network. Needs CORS on the bucket (see README).
  if (req.destination === 'audio' || /\.mp3($|\?)/i.test(url.pathname)) {
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(res => {
      if (res.status === 200) { const copy = res.clone(); caches.open(RUNTIME).then(c => c.put(req, copy)); }
      return res;
    }).catch(() => caches.match(req))));
    return;
  }

  if (url.origin !== location.origin) return;

  // images: cache-first (icons, artwork)
  if (/\.(png|jpg|jpeg|webp)$/i.test(url.pathname)) {
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(res => {
      const copy = res.clone(); caches.open(RUNTIME).then(c => c.put(req, copy)); return res;
    })));
    return;
  }
  // data json: stale-while-revalidate
  if (url.pathname.includes('/data/')) {
    e.respondWith(caches.open(RUNTIME).then(async c => {
      const hit = await c.match(req);
      const net = fetch(req).then(res => { c.put(req, res.clone()); return res; }).catch(() => hit);
      return hit || net;
    }));
    return;
  }
  // shell: cache-first, fall back to network
  e.respondWith(caches.match(req).then(hit => hit || fetch(req)));
});
