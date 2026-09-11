// badges.js — Badges flotantes interactivas (login, registro, formulario).
//
//   * Al hacer clic (o Enter/Espacio) despliegan una descripción corta.
//   * La badge marcada con data-status="sistema" consulta /api/health y, si el
//     backend no responde, se pone roja con "Sistema fuera de línea".
(function () {
    'use strict';

    const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000/api';
    const INTERVALO_ESTADO_MS = 60000;
    const TIMEOUT_ESTADO_MS = 5000;

    function init() {
        const badges = document.querySelectorAll('.badges-col .badge');
        if (!badges.length) return;

        badges.forEach(badge => {
            badge.setAttribute('role', 'button');
            badge.setAttribute('tabindex', '0');
            badge.setAttribute('aria-expanded', 'false');

            const desc = document.createElement('div');
            desc.className = 'badge-desc';
            desc.textContent = badge.dataset.desc || '';
            desc.hidden = true;
            badge.insertAdjacentElement('afterend', desc);

            const alternar = () => {
                const abrir = desc.hidden;
                desc.hidden = !abrir;
                badge.classList.toggle('activa', abrir);
                badge.setAttribute('aria-expanded', abrir ? 'true' : 'false');
            };

            badge.addEventListener('click', alternar);
            badge.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); alternar(); }
            });
        });

        const estado = document.querySelector('.badge[data-status="sistema"]');
        if (estado) {
            verificarEstado(estado);
            setInterval(() => verificarEstado(estado), INTERVALO_ESTADO_MS);
        }
    }

    function _descDe(badge) {
        const el = badge.nextElementSibling;
        return el && el.classList.contains('badge-desc') ? el : null;
    }

    // Comprueba /api/health con XHR (sin los reintentos del wrapper global:
    // queremos una respuesta rápida y fiable para el estado del sistema).
    function _pingSalud() {
        return new Promise((resolve) => {
            try {
                const xhr = new XMLHttpRequest();
                xhr.open('GET', `${API_BASE_URL}/health`, true);
                xhr.timeout = TIMEOUT_ESTADO_MS;
                xhr.setRequestHeader('Accept', 'application/json');
                xhr.onload = () => resolve(xhr.status === 200);
                xhr.onerror = () => resolve(false);
                xhr.ontimeout = () => resolve(false);
                xhr.send();
            } catch (_) {
                resolve(false);
            }
        });
    }

    async function verificarEstado(badge) {
        const enLinea = await _pingSalud();
        pintarEstado(badge, enLinea);
    }

    function pintarEstado(badge, enLinea) {
        const icono = badge.querySelector('i');
        const txt = badge.querySelector('.badge-txt');
        const desc = _descDe(badge);
        if (enLinea) {
            badge.classList.add('green');
            badge.classList.remove('red');
            if (icono) icono.className = 'fas fa-shield-alt';
            if (txt) txt.textContent = 'Sistemas en línea';
            if (desc) desc.textContent = badge.dataset.desc || '';
            badge.title = 'Servicio operativo (verificación en vivo)';
        } else {
            badge.classList.remove('green');
            badge.classList.add('red');
            if (icono) icono.className = 'fas fa-triangle-exclamation';
            if (txt) txt.textContent = 'Sistema fuera de línea';
            if (desc) desc.textContent = badge.dataset.descOffline || 'No se pudo contactar con el backend.';
            badge.title = 'Sin conexión con el servicio';
        }
    }

    document.addEventListener('DOMContentLoaded', init);
})();
