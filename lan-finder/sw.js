/* LAN Finder offline shell - v2.5.0 */
const CACHE_NAME = "lan-finder-shell-v2.5.0";
const SCOPE_PATH = new URL(self.registration.scope).pathname;
const PAGE_URL = new URL("./index.html", self.registration.scope).href;
const AUDIT_URL = new URL("./password-audit.html", self.registration.scope).href;
const ESSENTIALS = [PAGE_URL, AUDIT_URL];
self.addEventListener("install", event => {
 event.waitUntil((async()=>{
  const cache=await caches.open(CACHE_NAME);
  await cache.addAll(ESSENTIALS.map(url=>new Request(url,{cache:"reload"})));
  await self.skipWaiting();
 })());
});
self.addEventListener("activate", event => {
 event.waitUntil((async()=>{
  const keys=await caches.keys();
  await Promise.all(keys.filter(k=>k.startsWith("lan-finder-shell-")&&k!==CACHE_NAME).map(k=>caches.delete(k)));
  await self.clients.claim();
 })());
});
self.addEventListener("fetch", event => {
 const request=event.request;
 if(request.mode!=="navigate")return;
 const url=new URL(request.url);
 if(url.origin!==self.location.origin)return;
 let target;
 if(url.pathname===SCOPE_PATH||url.pathname===SCOPE_PATH+"index.html")target=PAGE_URL;
 else if(url.pathname===SCOPE_PATH+"password-audit.html")target=AUDIT_URL;
 else return;
 event.respondWith((async()=>{
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),4500);
  try{
   const response=await fetch(request,{signal:controller.signal});
   if(response.ok){
    try{const cache=await caches.open(CACHE_NAME);await cache.put(target,response.clone());}
    catch(_){}
   }
   return response;
  }catch(e){
   const cache=await caches.open(CACHE_NAME);
   return (await cache.match(target))||Response.error();
  }finally{clearTimeout(timer);}
 })());
});
