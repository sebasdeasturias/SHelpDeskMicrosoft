// chat-global.js — Widget compartido del chat con tabs (Chat IA / Chat Global).
//
// Modos según la pantalla:
//   * agente/coordinador: su dashboard ya maneja el chat IA (window.__chatIaPropia
//     = true); aquí solo añadimos la tab Chat Global, el polling y el badge.
//   * admin: este archivo maneja TODO (FAB, tabs, IA básica + chat global).
//   * solicitante: solo Chat Global (el backend le niega el chat IA).
//
// Transporte del chat global: REST + polling con since_id (sin WebSockets:
// suficiente para el volumen de un helpdesk interno y cero infra nueva).
(function () {
    'use strict';

    const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000/api';
    const INTERVALO_POLLING_MS = 4000;
    const MAX_HISTORIAL_IA = 10;

    // Estado del módulo
    let token = null;
    let miUserId = null;
    let mensajes = [];          // cache del chat global
    let sinceId = 0;            // último id visto (polling incremental)
    let tabActiva = 'global';   // 'ia' | 'global'
    let enviando = false;
    let noLeidos = 0;
    let timerPoll = null;
    let historialIA = [];       // solo admin (fallback IA propio)
    let primeraCarga = true;    // el historial inicial no cuenta como no leído

    const ROL_ETIQUETA = {
        solicitante: 'Solicitante',
        agente: 'Agente',
        coordinador: 'Coordinador',
        administrador: 'Administrador'
    };

    function getToken() {
        return localStorage.getItem('token') || sessionStorage.getItem('token');
    }

    function $(id) { return document.getElementById(id); }

    // ¿Esta pantalla maneja su propio chat IA? (agente / coordinador)
    function iaPropia() { return window.__chatIaPropia === true; }

    // ¿Panel solo con chat global? (solicitante: no existe #chatMessages)
    function soloGlobal() { return !$('chatMessages') && !!$('chatGlobalMessages'); }

    document.addEventListener('DOMContentLoaded', init);

    async function init() {
        token = getToken();
        if (!token) return; // el dashboard principal redirige a login
        if (!$('chatPanel') || !$('chatGlobalMessages')) return; // sin chat en esta página

        // Identidad propia (para resaltar mis mensajes)
        try {
            const resp = await fetch(`${API_BASE_URL}/auth/me`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (resp.ok) miUserId = (await resp.json()).user_id;
        } catch (e) { console.error('chat-global: no pude cargar /auth/me', e); }

        initTabs();
        initBindings();
        initFabBadge();
        startPolling();
    }

    // ------------------------------------------------------------
    // TABS (Chat IA ↔ Chat Global)
    // ------------------------------------------------------------
    function initTabs() {
        const tabs = document.querySelectorAll('.chat-tab');
        if (!tabs.length || soloGlobal()) {
            // Solicitante: oculta la barra de tabs si existiera en el HTML
            const barra = document.querySelector('.chat-tabs');
            if (barra) barra.style.display = 'none';
            setTab('global');
            return;
        }
        tabs.forEach(btn => {
            btn.addEventListener('click', () => setTab(btn.dataset.chatTab));
        });
        setTab('ia'); // por defecto como hasta ahora
    }

    function setTab(tab) {
        tabActiva = tab;
        const msgsIA = $('chatMessages');
        const msgsGlobal = $('chatGlobalMessages');
        const attachBtn = $('attachBtn');
        const input = $('chatInput');

        document.querySelectorAll('.chat-tab').forEach(b =>
            b.classList.toggle('active', b.dataset.chatTab === tab));

        if (msgsIA && msgsGlobal) {
            msgsIA.style.display = tab === 'ia' ? '' : 'none';
            msgsGlobal.style.display = tab === 'global' ? '' : 'none';
        }
        // El adjuntar-ticket es exclusivo del chat IA
        if (attachBtn) attachBtn.style.display = tab === 'ia' ? '' : 'none';
        if (input) {
            input.placeholder = tab === 'global'
                ? 'Mensaje para el equipo...'
                : 'Escribe tu mensaje...';
        }
        // Al abrir Chat Global: sin pendientes
        if (tab === 'global') marcarLeido();
    }

    // ------------------------------------------------------------
    // ENLACES DE EVENTOS
    // ------------------------------------------------------------
    function initBindings() {
        const input = $('chatInput');
        const sendBtn = $('chatSendBtn');
        const fab = $('chatFab');
        const panel = $('chatPanel');
        const closeBtn = $('chatClose');

        // Al abrir el panel con la tab global activa: sin pendientes.
        // (MutationObserver funciona aunque el FAB lo enlace otro script)
        if (panel) {
            new MutationObserver(() => {
                if (panel.classList.contains('open') && tabActiva === 'global') marcarLeido();
            }).observe(panel, { attributes: true, attributeFilter: ['class'] });
        }

        // Pantallas sin chat propio (solicitante/admin): aquí manda este widget
        if (!iaPropia()) {
            window.__chatIaPropia = false; // admin usará el fallback IA de abajo

            if (fab && panel) {
                fab.addEventListener('click', () => {
                    const isOpen = panel.classList.toggle('open');
                    fab.classList.toggle('open', isOpen);
                    if (isOpen) { marcarLeido(); if (input) input.focus(); }
                });
            }
            if (closeBtn && panel) {
                closeBtn.addEventListener('click', () => {
                    panel.classList.remove('open');
                    fab.classList.remove('open');
                });
            }
            if (sendBtn) sendBtn.addEventListener('click', enviarDesdeInput);
            if (input) {
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        enviarDesdeInput();
                    }
                });
                input.addEventListener('input', function () {
                    this.style.height = 'auto';
                    this.style.height = Math.min(this.scrollHeight, 80) + 'px';
                });
            }

            // Admin: chat IA básico si su dashboard no lo implementa
            if (!soloGlobal() && $('chatMessages')) initIaFallback();
        }

        // API pública para que los dashboards con IA propia deleguen el envío
        window.ChatGlobal = {
            activo: () => tabActiva === 'global',
            enviarDesdeInput
        };
    }

    // ------------------------------------------------------------
    // FALLBACK CHAT IA (pantalla de administrador)
    // ------------------------------------------------------------
    function initIaFallback() {
        // Los handlers de envío ya están enlazados a enviarDesdeInput();
        // este modo activa la rama IA dentro del mismo flujo.
        window.__chatIaFallback = true;
    }

    async function enviarIA(texto) {
        const msgsIA = $('chatMessages');
        const sendBtn = $('chatSendBtn');
        const input = $('chatInput');

        addMsg(msgsIA, texto, 'user', null, 'Tú');
        historialIA.push({ role: 'user', content: texto });
        input.value = '';
        input.style.height = 'auto';

        const typing = document.createElement('div');
        typing.className = 'typing-indicator';
        typing.innerHTML = '<span></span><span></span><span></span>';
        msgsIA.appendChild(typing);
        scrollAbajo(msgsIA);
        if (sendBtn) sendBtn.disabled = true;

        try {
            const resp = await fetch(`${API_BASE_URL}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    mensaje: texto,
                    historial: historialIA.slice(-MAX_HISTORIAL_IA),
                    modelo: 'llama3.2:3b'
                })
            });

            if (resp.status === 401) { logout(); return; }

            typing.remove();
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                addMsg(msgsIA, err.detail || 'La IA no está disponible en este momento.', 'system', null, null);
                return;
            }
            const data = await resp.json();
            const respuesta = data.respuesta || 'No recibí respuesta del modelo.';
            historialIA.push({ role: 'assistant', content: respuesta });
            addMsg(msgsIA, respuesta, 'bot', null, `IA · ${data.modelo || 'local'}`);
        } catch (e) {
            typing.remove();
            console.error('chat-global: error IA', e);
            addMsg(msgsIA, 'Error de conexión con la IA.', 'system', null, null);
        } finally {
            if (sendBtn) sendBtn.disabled = false;
        }
    }

    // ------------------------------------------------------------
    // DESPACHO DEL ENVÍO SEGÚN TAB ACTIVA
    // ------------------------------------------------------------
    function enviarDesdeInput() {
        const input = $('chatInput');
        const texto = (input.value || '').trim();
        if (!texto || enviando) return;

        if (tabActiva === 'global' || soloGlobal()) {
            enviarGlobal(texto);
        } else if (iaPropia()) {
            // En agente/coordinador el guard de su sendChatMessage delega aquí;
            // si llegara a llamarse igual, no duplicamos el envío IA.
            return;
        } else if (window.__chatIaFallback) {
            enviarIA(texto);
        }
    }

    // ------------------------------------------------------------
    // CHAT GLOBAL
    // ------------------------------------------------------------
    async function enviarGlobal(texto) {
        const input = $('chatInput');
        const sendBtn = $('chatSendBtn');
        const msgs = $('chatGlobalMessages');
        enviando = true;
        if (sendBtn) sendBtn.disabled = true;

        try {
            const resp = await fetch(`${API_BASE_URL}/chat-global/mensajes`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ mensaje: texto })
            });

            if (resp.status === 401) { logout(); return; }
            if (resp.status === 429) {
                const err = await resp.json().catch(() => ({}));
                addMsg(msgs, err.detail || 'Vas muy rápido, espera unos segundos.', 'system', null, null);
                return;
            }
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                addMsg(msgs, err.detail || 'No se pudo enviar el mensaje.', 'system', null, null);
                return;
            }

            const mensaje = await resp.json();
            agregarMensaje(mensaje, true);
            input.value = '';
            input.style.height = 'auto';
        } catch (e) {
            console.error('chat-global: error enviando', e);
            addMsg(msgs, 'Error de conexión. Intenta de nuevo.', 'system', null, null);
        } finally {
            enviando = false;
            if (sendBtn) sendBtn.disabled = false;
        }
    }

    function startPolling() {
        // Carga inicial (últimos 50) y luego polling incremental
        poll();
        timerPoll = setInterval(poll, INTERVALO_POLLING_MS);
    }

    async function poll() {
        if (!token || enviando) return;
        try {
            const resp = await fetch(
                `${API_BASE_URL}/chat-global/mensajes?since_id=${sinceId}&limit=50`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            if (!resp.ok) return;
            const nuevos = await resp.json();
            if (!Array.isArray(nuevos) || !nuevos.length) return;

            const panel = $('chatPanel');
            const panelAbierto = panel && panel.classList.contains('open') && tabActiva === 'global';

            nuevos.forEach(m => agregarMensaje(m, false));
            sinceId = nuevos[nuevos.length - 1].id_mensaje;

            if (primeraCarga) {
                primeraCarga = false; // el historial inicial no es "no leído"
            } else if (!panelAbierto) {
                noLeidos += nuevos.length;
                actualizarBadge();
            }
        } catch (e) {
            // Silencioso: red inestable no debe ensuciar la consola cada 4s
        }
    }

    // ------------------------------------------------------------
    // RENDER
    // ------------------------------------------------------------
    function agregarMensaje(m, esMioRecienEnviado) {
        if (mensajes.some(x => x.id_mensaje === m.id_mensaje)) return;
        mensajes.push(m);
        if (m.id_mensaje > sinceId) sinceId = m.id_mensaje;

        const msgs = $('chatGlobalMessages');
        if (!msgs) return;

        const esMio = miUserId != null && m.user_id === miUserId;
        const div = document.createElement('div');
        div.className = 'chat-msg ' + (esMio ? 'user' : 'bot');
        div.dataset.msgId = m.id_mensaje;

        const cuerpo = document.createElement('div');
        cuerpo.textContent = m.mensaje;
        div.appendChild(cuerpo);

        const meta = document.createElement('div');
        meta.className = 'msg-meta';
        const hora = m.fecha ? new Date(m.fecha).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' }) : '';
        meta.textContent = esMio
            ? `Tú · ${ROL_ETIQUETA[m.rol] || m.rol || ''} · ${hora}`.replace(/\s+·\s+$/, '')
            : `${m.nombre} · ${ROL_ETIQUETA[m.rol] || m.rol || ''} · ${hora}`;
        div.appendChild(meta);

        msgs.appendChild(div);

        // Solo autoscroll si el usuario está cerca del final o es su mensaje
        const cercaDelFinal = msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight < 120;
        if (esMio || esMioRecienEnviado || cercaDelFinal) scrollAbajo(msgs);
    }

    function addMsg(container, texto, tipo, metaTexto, autor) {
        if (!container) return;
        const div = document.createElement('div');
        div.className = 'chat-msg ' + tipo;

        const cuerpo = document.createElement('div');
        cuerpo.textContent = texto;
        div.appendChild(cuerpo);

        if (autor || metaTexto) {
            const meta = document.createElement('div');
            meta.className = 'msg-meta';
            meta.textContent = metaTexto ? `${autor} · ${metaTexto}` : autor;
            div.appendChild(meta);
        }
        container.appendChild(div);
        scrollAbajo(container);
    }

    function scrollAbajo(container) {
        container.scrollTop = container.scrollHeight;
    }

    // ------------------------------------------------------------
    // BADGE DE NO LEÍDOS
    // ------------------------------------------------------------
    function initFabBadge() {
        const fab = $('chatFab');
        if (fab && !fab.querySelector('.fab-badge')) {
            const badge = document.createElement('span');
            badge.className = 'fab-badge';
            badge.hidden = true;
            fab.appendChild(badge);
        }
    }

    function marcarLeido() {
        noLeidos = 0;
        actualizarBadge();
    }

    function actualizarBadge() {
        const badge = document.querySelector('#chatFab .fab-badge');
        if (!badge) return;
        if (noLeidos > 0) {
            badge.textContent = noLeidos > 99 ? '99+' : String(noLeidos);
            badge.hidden = false;
        } else {
            badge.hidden = true;
        }
    }

    function logout() {
        localStorage.removeItem('token');
        sessionStorage.removeItem('token');
        window.location.href = 'login.html';
    }
})();
