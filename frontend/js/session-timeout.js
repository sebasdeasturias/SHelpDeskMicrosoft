/*
 * Cierre de sesión por inactividad.
 *
 * Reglas (aplican a todos los roles):
 *  - 10 minutos sin mover el ratón ni teclear -> aviso modal.
 *  - El aviso concede 2 minutos para pulsar "Extender sesión".
 *  - La actividad mientras el aviso está abierto NO lo cierra: solo el botón.
 *  - Si el aviso llega a 0, se borra la sesión y se redirige a login.html.
 *
 * La actividad se comparte entre pestañas del mismo navegador mediante
 * localStorage, para que trabajar en una pestaña no cierre la sesión en otra.
 */
(function () {
    'use strict';

    if (window.__sessionIdleGuard) return;

    var IDLE_MS = 10 * 60 * 1000;
    var WARN_MS = 2 * 60 * 1000;
    var ACTIVITY_KEY = 'helpdesk_ultima_actividad';
    var CHECK_MS = 1000;
    var WRITE_THROTTLE_MS = 5000;
    var ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'wheel', 'scroll', 'touchstart'];

    var lastActivity = 0;
    var warningAt = 0;
    var warningOpen = false;
    var ending = false;
    var overlay = null;
    var countdownEl = null;
    var progressEl = null;
    var extendBtn = null;
    var lastRenderedSecond = -1;
    var lastWrite = 0;
    var intervalId = null;
    var started = false;

    function getToken() {
        try {
            return localStorage.getItem('token') || sessionStorage.getItem('token');
        } catch (e) {
            return null;
        }
    }

    function readStoredActivity() {
        try {
            var raw = localStorage.getItem(ACTIVITY_KEY);
            var ts = parseInt(raw, 10);
            return isNaN(ts) ? 0 : ts;
        } catch (e) {
            return 0;
        }
    }

    function storeActivity(ts, force) {
        var now = Date.now();
        if (!force && now - lastWrite < WRITE_THROTTLE_MS) return;
        lastWrite = now;
        try {
            localStorage.setItem(ACTIVITY_KEY, String(ts));
        } catch (e) {
            /* almacenamiento no disponible */
        }
    }

    function onActivity() {
        // Con el aviso abierto, la actividad no cuenta: solo "Extender sesión".
        if (warningOpen || ending) return;
        lastActivity = Date.now();
        storeActivity(lastActivity, false);
    }

    function formatTime(seconds) {
        var mm = Math.floor(seconds / 60);
        var ss = seconds % 60;
        return mm + ':' + (ss < 10 ? '0' : '') + ss;
    }

    function injectStyles() {
        if (document.getElementById('stxStyles')) return;
        var style = document.createElement('style');
        style.id = 'stxStyles';
        style.textContent = [
            'body.stx-modal-open { overflow: hidden; }',
            '.stx-overlay { position: fixed; inset: 0; z-index: 2147483000; display: flex; align-items: center; justify-content: center; padding: 20px; background: rgba(4, 12, 24, 0.72); -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px); opacity: 0; visibility: hidden; transition: opacity 0.25s ease, visibility 0.25s ease; }',
            '.stx-overlay.stx-open { opacity: 1; visibility: visible; }',
            '.stx-card { box-sizing: border-box; width: 100%; max-width: 430px; padding: 28px 28px 24px; border-radius: 18px; border: 1px solid rgba(255, 255, 255, 0.6); background: rgba(255, 255, 255, 0.97); color: #11425e; box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45); text-align: center; font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif; transform: translateY(10px) scale(0.98); transition: transform 0.25s ease; }',
            '.stx-overlay.stx-open .stx-card { transform: none; }',
            'body.night-mode .stx-card { background: #1b1b30; color: #e6e6ff; border-color: rgba(120, 120, 180, 0.5); }',
            '.stx-icon { display: flex; align-items: center; justify-content: center; width: 56px; height: 56px; margin: 0 auto 16px; border-radius: 50%; color: #b45309; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.35); }',
            'body.night-mode .stx-icon { color: #fbbf24; background: rgba(251, 191, 36, 0.12); border-color: rgba(251, 191, 36, 0.3); }',
            '.stx-icon svg { width: 30px; height: 30px; }',
            '.stx-title { margin: 0 0 10px; font-size: 1.35rem; line-height: 1.3; }',
            '.stx-text { margin: 0 0 20px; font-size: 0.95rem; line-height: 1.55; color: #3b6a86; }',
            'body.night-mode .stx-text { color: #b9b9dd; }',
            '.stx-countdown-row { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 8px; }',
            '.stx-countdown-label { font-size: 0.82rem; letter-spacing: 0.06em; text-transform: uppercase; opacity: 0.75; }',
            '.stx-countdown { font-size: 1.75rem; font-weight: 700; font-variant-numeric: tabular-nums; color: #b45309; }',
            'body.night-mode .stx-countdown { color: #fbbf24; }',
            '.stx-progress { height: 6px; margin-bottom: 22px; border-radius: 999px; background: rgba(100, 130, 150, 0.22); overflow: hidden; }',
            '.stx-progress-bar { width: 100%; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #f59e0b, #ef4444); transition: width 1s linear; }',
            '.stx-extend { width: 100%; padding: 13px 18px; border: 0; border-radius: 10px; color: #ffffff; background: linear-gradient(180deg, #2a9dbf, #17607f); box-shadow: 0 8px 20px rgba(26, 116, 149, 0.35); font-family: inherit; font-size: 1rem; font-weight: 700; cursor: pointer; transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease; }',
            '.stx-extend:hover { transform: translateY(-1px); filter: brightness(1.06); box-shadow: 0 10px 24px rgba(26, 116, 149, 0.45); }',
            '.stx-extend:active { transform: none; }',
            '.stx-extend:focus-visible { outline: 3px solid rgba(96, 165, 250, 0.8); outline-offset: 3px; }',
            'body.night-mode .stx-extend { background: linear-gradient(180deg, #3b6fa8, #1c3357); }',
            '.stx-note { margin: 14px 0 0; font-size: 0.8rem; line-height: 1.45; opacity: 0.75; }',
            '@media (max-width: 480px) { .stx-card { padding: 24px 20px 20px; } .stx-title { font-size: 1.2rem; } }',
            '@media (prefers-reduced-motion: reduce) { .stx-overlay, .stx-card, .stx-progress-bar, .stx-extend { transition: none; } }'
        ].join('\n');
        document.head.appendChild(style);
    }

    function buildOverlay() {
        if (overlay) return;
        injectStyles();

        overlay = document.createElement('div');
        overlay.className = 'stx-overlay';
        overlay.id = 'sessionTimeoutOverlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-labelledby', 'stxTitle');
        overlay.setAttribute('aria-describedby', 'stxDesc');
        overlay.setAttribute('aria-hidden', 'true');
        overlay.innerHTML = [
            '<div class="stx-card">',
            '  <div class="stx-icon" aria-hidden="true">',
            '    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">',
            '      <circle cx="12" cy="12" r="9"></circle>',
            '      <path d="M12 7v5l3.5 2"></path>',
            '    </svg>',
            '  </div>',
            '  <h2 class="stx-title" id="stxTitle">Tu sesión está por cerrarse</h2>',
            '  <p class="stx-text" id="stxDesc">No detectamos actividad en los últimos 10 minutos. Por seguridad, tu sesión se cerrará automáticamente en 2 minutos.</p>',
            '  <div class="stx-countdown-row">',
            '    <span class="stx-countdown-label">Tiempo restante</span>',
            '    <span class="stx-countdown" id="stxCountdown">2:00</span>',
            '  </div>',
            '  <div class="stx-progress" aria-hidden="true"><div class="stx-progress-bar" id="stxProgress"></div></div>',
            '  <button type="button" class="stx-extend" id="stxExtend">Extender sesión</button>',
            '  <p class="stx-note">Si no extiendes la sesión, se cerrará y serás redirigido a la pantalla de inicio de sesión.</p>',
            '</div>'
        ].join('\n');

        document.body.appendChild(overlay);

        countdownEl = overlay.querySelector('#stxCountdown');
        progressEl = overlay.querySelector('#stxProgress');
        extendBtn = overlay.querySelector('#stxExtend');

        extendBtn.addEventListener('click', extendSession);

        overlay.addEventListener('keydown', function (e) {
            if (e.key === 'Tab') {
                e.preventDefault();
                extendBtn.focus();
            }
        });

        document.addEventListener('focusin', function (e) {
            if (warningOpen && overlay && !overlay.contains(e.target)) {
                extendBtn.focus();
            }
        });
    }

    function updateCountdown() {
        var remaining = Math.max(0, WARN_MS - (Date.now() - warningAt));
        var seconds = Math.ceil(remaining / 1000);
        if (seconds === lastRenderedSecond) return;
        lastRenderedSecond = seconds;
        if (countdownEl) countdownEl.textContent = formatTime(seconds);
        if (progressEl) progressEl.style.width = ((remaining / WARN_MS) * 100).toFixed(2) + '%';
    }

    function showWarning() {
        if (warningOpen || ending) return;

        // Si el aviso se muestra con retraso (pestaña en segundo plano), el plazo
        // sigue contando desde el minuto 10 de inactividad, no desde que se pintó.
        warningAt = lastActivity + IDLE_MS;
        if (Date.now() - warningAt >= WARN_MS) {
            finishSession();
            return;
        }

        buildOverlay();
        warningOpen = true;
        lastRenderedSecond = -1;
        updateCountdown();

        overlay.classList.add('stx-open');
        overlay.setAttribute('aria-hidden', 'false');
        document.body.classList.add('stx-modal-open');

        setTimeout(function () {
            if (warningOpen && extendBtn) extendBtn.focus();
        }, 50);
    }

    function hideWarning() {
        if (!overlay) return;
        warningOpen = false;
        overlay.classList.remove('stx-open');
        overlay.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('stx-modal-open');
    }

    function extendSession() {
        if (ending) return;
        hideWarning();
        lastActivity = Date.now();
        lastRenderedSecond = -1;
        storeActivity(lastActivity, true);
    }

    function redirectToLogin() {
        try {
            var current = window.location.pathname.split('/').pop() || '';
            if (current === 'login.html') return;
        } catch (e) {
            /* ubicación no disponible */
        }
        try {
            window.location.replace('login.html');
        } catch (e) {
            window.location.href = 'login.html';
        }
    }

    function finishSession() {
        if (ending) return;
        ending = true;
        warningOpen = false;
        if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
        }
        try {
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            sessionStorage.removeItem('token');
            sessionStorage.removeItem('user');
            localStorage.removeItem(ACTIVITY_KEY);
        } catch (e) {
            /* almacenamiento no disponible */
        }
        redirectToLogin();
    }

    function tick() {
        if (ending) return;

        if (!getToken()) {
            redirectToLogin();
            return;
        }

        var now = Date.now();

        if (warningOpen) {
            updateCountdown();
            if (now - warningAt >= WARN_MS) finishSession();
            return;
        }

        if (now - lastActivity >= IDLE_MS) showWarning();
    }

    function start() {
        if (started) return;
        started = true;

        if (!getToken()) return;

        var now = Date.now();
        var stored = readStoredActivity();
        if (stored > 0 && stored <= now && now - stored < IDLE_MS) {
            lastActivity = stored;
        } else {
            lastActivity = now;
            storeActivity(lastActivity, true);
        }

        ACTIVITY_EVENTS.forEach(function (eventName) {
            document.addEventListener(eventName, onActivity, { passive: true });
        });

        // Actividad en otra pestaña: mantiene viva esta sesión y retira el aviso.
        window.addEventListener('storage', function (e) {
            if (e.key === ACTIVITY_KEY && e.newValue) {
                var ts = parseInt(e.newValue, 10);
                if (!isNaN(ts) && ts > lastActivity) {
                    lastActivity = ts;
                    if (warningOpen) hideWarning();
                }
            } else if (e.key === 'token' && !e.newValue && !getToken()) {
                finishSession();
            }
        });

        // Los navegadores frenan los timers en pestañas ocultas: al volver,
        // comprobamos el estado real de inmediato.
        document.addEventListener('visibilitychange', function () {
            if (!document.hidden) tick();
        });
        window.addEventListener('focus', tick);
        window.addEventListener('pageshow', tick);

        intervalId = setInterval(tick, CHECK_MS);
        tick();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
