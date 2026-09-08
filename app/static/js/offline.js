/*
 * Behaviour for the offline fallback page.
 *
 * Kept out of the template on purpose. /offline is precached by the service
 * worker and replayed from cache long after it was fetched, so an inline block
 * there would depend on the nonce that happened to be cached with it. An
 * external file is nonce-free and covered by script-src 'self'.
 */
(function () {
    'use strict';

    function reload() {
        window.location.reload();
    }

    var retry = document.getElementById('retry');
    if (retry) {
        retry.addEventListener('click', reload);
    }

    window.addEventListener('online', reload);

    // The page can be served from cache after the connection is already back.
    if (navigator.onLine) {
        reload();
    }
}());
