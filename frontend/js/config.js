(function () {
    'use strict';
    var override = (typeof window.APP_API_BASE_URL !== 'undefined') ? window.APP_API_BASE_URL : '';
    var base;
    if (override) {
        base = override;
    } else if (window.location.protocol === 'file:') {
        base = 'http://localhost:8000/api';
    } else {
        base = window.location.origin + '/api';
    }
    window.API_BASE_URL = base.replace(/\/+$/, '');
})();

// Reintentos automáticos ante fallos transitorios (5xx / red).

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.fetch || window.__fetchRetry) return;
    window.__fetchRetry = true;
    var origFetch = window.fetch.bind(window);
    var MAX = 8;
    window.fetch = function (input, init) {
        var intento = 0;
        function delay(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
        function exec() {
            intento++;
            return origFetch(input, init).then(function (res) {
                if (res.status >= 500 && intento < MAX) {
                    return delay(Math.min(250 * intento, 800)).then(exec);
                }
                return res;
            }).catch(function (err) {
                if (intento < MAX) {
                    return delay(Math.min(250 * intento, 800)).then(exec);
                }
                throw err;
            });
        }
        return exec();
    };
})();
