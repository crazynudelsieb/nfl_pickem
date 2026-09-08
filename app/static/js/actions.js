/*
 * Delegated event dispatch.
 *
 * The templates used to wire behaviour with inline `onclick="..."` attributes.
 * A CSP nonce covers a <script> block but never an event-handler attribute, so
 * as long as those existed `script-src` had to carry 'unsafe-inline' - which
 * means any injected <script> would have run too. The markup now names an
 * action instead:
 *
 *     <button data-action="...">   (click)
 *     <select data-action-change="...">   (change)
 *
 * and the page's own (nonced) script registers what that name does:
 *
 *     appActions.register({ 'the-name': function () { ... } });
 *
 * Resolution happens at event time, so a page may register its actions long
 * after the markup is parsed, and markup rendered later still works without
 * re-binding. Unknown names are ignored rather than throwing, so a stale
 * data-action left behind by a template edit degrades to a dead control
 * instead of breaking every other handler on the page.
 */
(function () {
    'use strict';

    var registry = Object.create(null);

    window.appActions = {
        register: function (actions) {
            Object.keys(actions).forEach(function (name) {
                registry[name] = actions[name];
            });
        },
        // Mostly for tests and for one handler calling another by name.
        get: function (name) {
            return registry[name];
        }
    };

    function handlerFor(event, attribute) {
        var target = event.target;
        if (!target || typeof target.closest !== 'function') {
            return null;
        }
        var element = target.closest('[' + attribute + ']');
        if (!element) {
            return null;
        }
        var handler = registry[element.getAttribute(attribute)];
        return typeof handler === 'function' ? { element: element, handler: handler } : null;
    }

    function delegate(type, attribute, options) {
        document.addEventListener(type, function (event) {
            var match = handlerFor(event, attribute);
            if (!match) {
                return;
            }
            // Anchors used purely as buttons are written href="#"; stop the
            // jump to the top of the page that would otherwise follow.
            if (match.element.tagName === 'A' && match.element.getAttribute('href') === '#') {
                event.preventDefault();
            }
            match.handler.call(match.element, event, match.element);
        }, options);
    }

    delegate('click', 'data-action');
    delegate('change', 'data-action-change');
    delegate('submit', 'data-action-submit');
    // `error` does not bubble off an <img>, so this one has to listen on the
    // capture phase to see it at all.
    delegate('error', 'data-action-error', true);
}());
