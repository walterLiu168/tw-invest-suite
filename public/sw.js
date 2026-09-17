// Service Worker for tw-invest-suite: never cache daily JSON as current data.
const CACHE_NAME = 'tw-invest-v2';
const BASE = new URL(self.registration.scope);
const STATIC_CACHE = ['readme.html','analyze.html','assets/textsize.css','assets/textsize.js'].map(p => new URL(p, BASE).href);
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_CACHE)).catch(() => {}));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('tw-invest-') && k !== CACHE_NAME).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== BASE.origin || !url.pathname.startsWith(BASE.pathname)) return;
  const path = url.pathname.slice(BASE.pathname.length);
  // Leave the GrooveLab music app and unrelated routes outside this worker.
  if (!/^(?:data\/|assets\/textsize\.|analyze\/|(?:analyze|readme|watchlist|patterns|sectors|chips|chips-advanced|chips-history|concepts|monitor)\.html$)/.test(path)) return;
  if (path.endsWith('.json')) {
    event.respondWith(fetch(req,{cache:'no-store'}));
    return;
  }
  if (path.endsWith('.html')) {
    event.respondWith(fetch(req).then(res => {
      if(res.ok) {
        const copy = res.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(req,copy));
      }
      return res;
    }).catch(() => caches.match(req)));
    return;
  }
  event.respondWith(caches.match(req).then(cached => cached || fetch(req)));
});
