// frontend/js/config.js — Configuración global del frontend SHelpDesk.
// Se carga en TODAS las páginas (antes que el resto de scripts). Define la URL
// base de la API que usan todos los módulos (window.API_BASE_URL).
//
// Orden de resolución:
//  1. window.APP_API_BASE_URL, si lo defines aquí abajo (recomendado al desplegar).
//  2. Mismo origen + "/api" cuando la página se sirve por http(s) (útil si un
//     proxy sirve frontend y backend juntos bajo el mismo dominio).
//  3. http://localhost:8000/api cuando abres los HTML desde el disco (file://,
//     desarrollo local con docker compose).
//
// DESPLIEGUE EN VERCEL: el frontend llama a su MISMO origen (/api) y Vercel
// proxya esa ruta al backend con un rewrite definido en vercel.json. Así se
// evita el bloqueo de Chrome "Local Network Access" (una página pública no
// puede llamar directamente a la IP privada de Tailscale) y también el CORS.
// Por eso aquí NO se define una URL absoluta.
//
// Para otros hosts estáticos, descomenta y pon la URL pública de tu API:
//   window.APP_API_BASE_URL = 'https://api.tudominio.com/api';
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
// Motivo: el proxy de Vercel hacia el Funnel de Tailscale falla de forma
// intermitente con DNS_HOSTNAME_EMPTY (502); un reintento inmediato lo salva.
// No reintenta errores 4xx (son de negocio: credenciales, permisos, etc.).
(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.fetch || window.__fetchRetry) return;
    window.__fetchRetry = true;
    var origFetch = window.fetch.bind(window);
    var MAX = 5;
    window.fetch = function (input, init) {
        var intento = 0;
        function delay(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
        function exec() {
            intento++;
            return origFetch(input, init).then(function (res) {
                if (res.status >= 500 && intento < MAX) {
                    return delay(250 * intento).then(exec);
                }
                return res;
            }).catch(function (err) {
                if (intento < MAX) {
                    return delay(250 * intento).then(exec);
                }
                throw err;
            });
        }
        return exec();
    };
})();
