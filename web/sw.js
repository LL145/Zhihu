/* 静态资源缓存（Service Worker）：二次打开秒开、断网可用。
 * - 同源资源（页面、worker、app.py、tianwen.zip、wheels）网络优先，
 *   断网回退缓存——推送 main 部署新版后一刷新即得新管线；
 * - Pyodide CDN（URL 带版本号，内容不变）缓存优先，免去每次十余 MB；
 * - 其余请求（OpenRouter 大模型等）一概不拦，Key 不落缓存。 */

"use strict";

const CACHE = "tianwen-static-v1";
const CDN = "https://cdn.jsdelivr.net/pyodide/";

// 页面外壳预缓存：首访的导航请求发生在本 SW 接管之前，不预存则断网
// 后连页面都打不开；其余资产由运行时缓存（首访即全量入缓，见 index.html）
const SHELL = ["./", "index.html", "worker.js", "app.py"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) =>
    Promise.allSettled(SHELL.map((u) => c.add(u)))));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const sameOrigin = new URL(req.url).origin === self.location.origin;
  const cdn = req.url.startsWith(CDN);
  if (!sameOrigin && !cdn) return;
  e.respondWith(cdn ? cacheFirst(req) : networkFirst(req));
});

async function cacheFirst(req) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok || res.type === "opaque") await cache.put(req, res.clone());
  return res;
}

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  try {
    const res = await fetch(req);
    if (res.ok) await cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req, { ignoreSearch: true });
    if (hit) return hit;
    if (req.mode === "navigate") {           // 断网导航回退页面外壳
      const shell = await cache.match("index.html");
      if (shell) return shell;
    }
    throw err;
  }
}
