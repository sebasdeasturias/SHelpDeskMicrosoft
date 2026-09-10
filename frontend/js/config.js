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
// Para desplegar el frontend en Vercel (o cualquier host estático) con el backend
// en otro servidor, define aquí la URL pública estable de tu API.
// URL estable actual: Tailscale Funnel del backend local (no caduca).
window.APP_API_BASE_URL = 'https://desktop-5vclct5.tail5f1502.ts.net/api';
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
