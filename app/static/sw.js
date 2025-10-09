// NFL Pick'em Service Worker - Enhanced PWA version
const CACHE_NAME = 'nfl-pickem-v3';
const RUNTIME_CACHE = 'nfl-pickem-runtime-v3';

// Assets to cache on install
const PRECACHE_URLS = [
  '/',
  '/static/css/main.css',
  '/static/js/main.js',
  '/static/images/nfl-logo.png',
  '/static/images/icon-192x192.png',
  '/static/images/icon-512x512.png',
  '/static/manifest.json',
  '/offline'
];

// Install event - cache essential assets
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        console.log('Service Worker: Precaching essential assets');
        return cache.addAll(PRECACHE_URLS.map(url => new Request(url, {
          cache: 'reload'
        })));
      })
      .catch(function(error) {
        console.log('Service Worker: Precache failed:', error);
      })
      .then(function() {
        return self.skipWaiting();
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', function(event) {
  const currentCaches = [CACHE_NAME, RUNTIME_CACHE];
  event.waitUntil(
    caches.keys()
      .then(function(cacheNames) {
        return Promise.all(
          cacheNames.map(function(cacheName) {
            if (!currentCaches.includes(cacheName)) {
              console.log('Service Worker: Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      })
      .then(function() {
        return self.clients.claim();
      })
  );
});

// Fetch event - network first for API, cache first for assets
self.addEventListener('fetch', function(event) {
  const url = new URL(event.request.url);
  
  // Skip cross-origin requests
  if (url.origin !== location.origin) {
    return;
  }
  
  // Skip non-GET requests
  if (event.request.method !== 'GET') {
    return;
  }
  
  // API requests - network first with timeout
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstWithTimeout(event.request, 5000));
    return;
  }
  
  // Live score updates - always from network
  if (url.pathname.includes('/scores/live')) {
    event.respondWith(fetch(event.request).catch(() => {
      return new Response(JSON.stringify({ error: 'Offline', games: [] }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }));
    return;
  }
  
  // Static assets - cache first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(event.request));
    return;
  }
  
  // HTML pages - network first, fallback to cache
  if (event.request.headers.get('accept').includes('text/html')) {
    event.respondWith(networkFirstWithTimeout(event.request, 3000));
    return;
  }
  
  // Everything else - network first
  event.respondWith(networkFirst(event.request));
});

// Network first strategy with timeout
function networkFirstWithTimeout(request, timeout = 3000) {
  return new Promise(function(resolve, reject) {
    const timeoutId = setTimeout(function() {
      console.log('Service Worker: Network timeout, trying cache');
      caches.match(request).then(function(response) {
        if (response) {
          resolve(response);
        } else {
          reject(new Error('Network timeout and no cache'));
        }
      });
    }, timeout);
    
    fetch(request)
      .then(function(response) {
        clearTimeout(timeoutId);
        
        // Cache successful responses
        if (response && response.status === 200) {
          const responseToCache = response.clone();
          caches.open(RUNTIME_CACHE).then(function(cache) {
            cache.put(request, responseToCache);
          });
        }
        
        resolve(response);
      })
      .catch(function(error) {
        clearTimeout(timeoutId);
        console.log('Service Worker: Network fetch failed, trying cache');
        
        caches.match(request).then(function(response) {
          if (response) {
            resolve(response);
          } else {
            // Return offline page for HTML requests
            if (request.headers.get('accept').includes('text/html')) {
              caches.match('/offline').then(function(offlineResponse) {
                resolve(offlineResponse || new Response('Offline'));
              });
            } else {
              reject(error);
            }
          }
        });
      });
  });
}

// Network first strategy
function networkFirst(request) {
  return fetch(request)
    .then(function(response) {
      // Cache successful responses
      if (response && response.status === 200) {
        const responseToCache = response.clone();
        caches.open(RUNTIME_CACHE).then(function(cache) {
          cache.put(request, responseToCache);
        });
      }
      return response;
    })
    .catch(function() {
      return caches.match(request);
    });
}

// Cache first strategy
function cacheFirst(request) {
  return caches.match(request)
    .then(function(response) {
      if (response) {
        return response;
      }
      
      return fetch(request).then(function(response) {
        // Cache the fetched resource
        if (response && response.status === 200) {
          const responseToCache = response.clone();
          caches.open(RUNTIME_CACHE).then(function(cache) {
            cache.put(request, responseToCache);
          });
        }
        return response;
      });
    });
}

// Handle messages from the client
self.addEventListener('message', function(event) {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'CACHE_URLS') {
    const urls = event.data.urls;
    event.waitUntil(
      caches.open(RUNTIME_CACHE).then(function(cache) {
        return cache.addAll(urls);
      })
    );
  }
});

// Background sync for offline picks (if supported)
self.addEventListener('sync', function(event) {
  if (event.tag === 'sync-picks') {
    event.waitUntil(syncPicks());
  }
});

function syncPicks() {
  // This would sync any picks made while offline
  // Implementation depends on your offline storage strategy
  console.log('Service Worker: Syncing offline picks');
  return Promise.resolve();
}

// Push notification support (optional)
self.addEventListener('push', function(event) {
  if (event.data) {
    const data = event.data.json();
    const options = {
      body: data.body || 'New NFL Pick\'em notification',
      icon: '/static/images/icon-192x192.png',
      badge: '/static/images/icon-96x96.png',
      vibrate: [200, 100, 200],
      data: {
        url: data.url || '/'
      }
    };
    
    event.waitUntil(
      self.registration.showNotification(data.title || 'NFL Pick\'em', options)
    );
  }
});

// Notification click handler
self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  
  event.waitUntil(
    clients.openWindow(event.notification.data.url || '/')
  );
});
