const CACHE='fantacoach-shell-v05';
const SHELL=['/','/index.html','/manifest.webmanifest','/icons/icon-192.png','/icons/icon-512.png','/icons/apple-touch-icon.png'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',event=>{
  const req=event.request;
  const url=new URL(req.url);
  if(req.method!=='GET') return;
  if(url.pathname.startsWith('/api/')){
    event.respondWith(fetch(req));
    return;
  }
  if(req.mode==='navigate'){
    event.respondWith(fetch(req).catch(()=>caches.match('/index.html')));
    return;
  }
  event.respondWith(caches.match(req).then(hit=>hit||fetch(req).then(resp=>{const clone=resp.clone();caches.open(CACHE).then(c=>c.put(req,clone));return resp;})));
});
