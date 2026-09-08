/*
 * Behaviour for the error pages (errors/base_error.html and the templates that
 * extend it). They are standalone documents, rendered without base.html, and
 * their buttons used to be `href="javascript:..."` - which script-src blocks
 * once 'unsafe-inline' is gone, the same way it blocks an inline <script>.
 */
(function () {
    'use strict';

    appActions.register({
        'history-back': function () {
            history.back();
        },
        'reload': function () {
            location.reload();
        },
        // Wait out a rate limit or a restart before retrying. The delay is on
        // the element so 429 and 503 can share one handler.
        'reload-after': function (event, element) {
            var seconds = parseInt(element.dataset.delaySeconds, 10);
            setTimeout(function () {
                location.reload();
            }, (seconds > 0 ? seconds : 5) * 1000);
        },
        // The HTTP-status cat is hotlinked from http.cat. If it fails to load -
        // likely, given the page is often shown while something is broken -
        // drop it rather than leaving a broken-image icon.
        'hide-broken-image': function () {
            this.style.display = 'none';
        }
    });
}());
