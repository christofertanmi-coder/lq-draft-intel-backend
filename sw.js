// Service worker minimal — cuma buat memenuhi syarat "installable" PWA di Android/Chrome.
// Tidak melakukan caching/offline (semua request tetap ke jaringan), biar data selalu fresh.
self.addEventListener('install', ()=> self.skipWaiting());
self.addEventListener('activate', (e)=> e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', ()=>{}); // pass-through, wajib ada supaya dianggap installable
