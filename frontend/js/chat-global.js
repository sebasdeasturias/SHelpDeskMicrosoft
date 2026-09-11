// chat-global.js — Widget compartido del chat con tabs (Chat IA / Chat Global / Privado).
//
// Modos según la pantalla:
//   * agente/coordinador: su dashboard ya maneja el chat IA (window.__chatIaPropia
//     = true); aquí añadimos Chat Global, Chat Privado, el polling y el badge.
//   * admin: este archivo maneja TODO (FAB, tabs, IA básica + chat global + privado).
//   * solicitante: solo Chat Global (el backend le niega IA y chat privado).
//
// Transporte: REST + polling con since_id (sin WebSockets). El chat privado es
// exclusivo de personal interno (agente/coordinador/administrador).
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
    let tabActiva = 'global';   // 'ia' | 'global' | 'privado'
    let noLeidos = 0;
    let timerPoll = null;
    let historialIA = [];       // solo admin (fallback IA propio)
    let primeraCarga = true;    // el historial inicial no cuenta como no leído

    // Chat privado
    let privadoSoporte = false;
    let contactosPriv = [];
    let privadoSel = null;      // { id, nombre }
    let privadoSinceId = 0;
    let privadoNoLeidos = 0;
    let cargandoContactos = false;
    let timerPrivPoll = null;

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

    function privadoDisponible() {
        return !!($('chatPrivadoLista') && $('chatPrivadoMessages'));
    }

    document.addEventListener('DOMContentLoaded', init);

    async function init() {
        token = getToken();
        if (!token) return; // el dashboard principal redirige a login
        if (!$('chatPanel') || !$('chatGlobalMessages')) return; // sin chat en esta página

        privadoSoporte = privadoDisponible();

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
        initPrivado();
        startPolling();
        if (privadoSoporte) startPollingPrivado();
    }

    // ------------------------------------------------------------
    // TABS (Chat IA ↔ Chat Global ↔ Privado)
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
        const listaPriv = $('chatPrivadoLista');
        const convPriv = $('chatPrivadoConv');
        const attachBtn = $('attachBtn');
        const input = $('chatInput');

        document.querySelectorAll('.chat-tab').forEach(b =>
            b.classList.toggle('active', b.dataset.chatTab === tab));

        // Se muestra con 'flex' (no con ''): la regla CSS ".chat-global-msgs
        // { display:none }" ocultaba el panel global al quitar el inline, y la
        // textbox quedaba arriba sin área de mensajes. 'flex' (inline) la anula.
        if (msgsIA) msgsIA.style.display = tab === 'ia' ? 'flex' : 'none';
        if (msgsGlobal) msgsGlobal.style.display = tab === 'global' ? 'flex' : 'none';
        if (listaPriv) listaPriv.style.display = (tab === 'privado' && !privadoSel) ? 'flex' : 'none';
        if (convPriv) convPriv.style.display = (tab === 'privado' && privadoSel) ? 'flex' : 'none';

        // El adjuntar-ticket es exclusivo del chat IA
        if (attachBtn) attachBtn.style.display = tab === 'ia' ? '' : 'none';
        if (input) {
            input.disabled = false;
            if (tab === 'global') input.placeholder = 'Mensaje para el equipo...';
            else if (tab === 'privado') input.placeholder = privadoSel ? 'Mensaje privado...' : 'Selecciona un contacto...';
            else input.placeholder = 'Escribe tu mensaje...';
        }

        // Al abrir Chat Global: sin pendientes
        if (tab === 'global') marcarLeido();
        if (tab === 'privado') {
            cargarContactos();
            if (privadoSel) enfocarInputPrivado(); else desactivarInputPrivado();
        }
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

        // Al abrir el panel con la tab global/privada activa: sin pendientes.
        // (MutationObserver funciona aunque el FAB lo enlace otro script)
        if (panel) {
            new MutationObserver(() => {
                if (!panel.classList.contains('open')) return;
                if (tabActiva === 'global') marcarLeido();
                else if (tabActiva === 'privado' && privadoSel) {
                    cargarConversacion().then(pollPrivadoNoLeidos);
                }
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
            activo: () => tabActiva === 'global' || tabActiva === 'privado',
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
        const input = $('chatInput');

        addMsg(msgsIA, texto, 'user', null, 'Tú');
        historialIA.push({ role: 'user', content: texto });
        input.value = '';
        input.style.height = 'auto';

        // Typing propio de esta petición: permite enviar la siguiente sin esperar
        const typing = document.createElement('div');
        typing.className = 'typing-indicator';
        typing.innerHTML = '<span></span><span></span><span></span>';
        msgsIA.appendChild(typing);
        scrollAbajo(msgsIA);

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
        }
    }

    // ------------------------------------------------------------
    // DESPACHO DEL ENVÍO SEGÚN TAB ACTIVA
    // ------------------------------------------------------------
    function enviarDesdeInput() {
        const input = $('chatInput');
        const texto = (input.value || '').trim();
        if (!texto) return;

        if (tabActiva === 'privado') {
            enviarPrivado(texto);
        } else if (tabActiva === 'global' || soloGlobal()) {
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
        const msgs = $('chatGlobalMessages');

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
        }
    }

    function startPolling() {
        // Carga inicial (últimos 50) y luego polling incremental
        poll();
        timerPoll = setInterval(poll, INTERVALO_POLLING_MS);
    }

    async function poll() {
        if (!token) return;
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
    // CHAT PRIVADO 1 A 1
    // ------------------------------------------------------------
    function initPrivado() {
        if (!privadoSoporte) return;
        const volver = $('chatPrivadoVolver');
        if (volver) volver.addEventListener('click', mostrarContactos);
        desactivarInputPrivado();
    }

    async function cargarContactos() {
        if (!privadoSoporte || cargandoContactos) return;
        cargandoContactos = true;
        try {
            const resp = await fetch(`${API_BASE_URL}/chat-privado/contactos`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (resp.status === 401) { logout(); return; }
            if (!resp.ok) return;
            contactosPriv = await resp.json();
            renderContactos();
        } catch (e) {
            console.error('chat-global: error cargando contactos privados', e);
        } finally {
            cargandoContactos = false;
        }
    }

    function iniciales(nombre) {
        return (nombre || '?').split(' ').filter(Boolean)
            .map(w => w[0]).join('').substring(0, 2).toUpperCase();
    }

    function renderContactos() {
        const cont = $('chatPrivadoContactos');
        if (!cont) return;
        cont.innerHTML = '';

        if (!contactosPriv.length) {
            const vacio = document.createElement('div');
            vacio.className = 'chat-msg system';
            vacio.textContent = 'No hay otros usuarios disponibles para chat privado.';
            cont.appendChild(vacio);
            return;
        }

        contactosPriv.forEach(c => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'chat-privado-item';
            item.dataset.id = c.id_usuario;

            const av = document.createElement('span');
            av.className = 'chat-privado-avatar';
            av.textContent = iniciales(c.nombre);
            item.appendChild(av);

            const info = document.createElement('span');
            info.className = 'chat-privado-info';
            const nom = document.createElement('span');
            nom.className = 'chat-privado-nombre';
            nom.textContent = c.nombre || 'Usuario';
            const sub = document.createElement('span');
            sub.className = 'chat-privado-sub';
            sub.textContent = c.ultimo_mensaje
                ? c.ultimo_mensaje
                : (ROL_ETIQUETA[c.rol] || c.rol || '');
            info.appendChild(nom);
            info.appendChild(sub);
            item.appendChild(info);

            if (c.no_leidos > 0) {
                const badge = document.createElement('span');
                badge.className = 'chat-privado-badge';
                badge.textContent = c.no_leidos > 99 ? '99+' : String(c.no_leidos);
                item.appendChild(badge);
            }

            item.addEventListener('click', () => abrirConversacion(c.id_usuario, c.nombre));
            cont.appendChild(item);
        });
    }

    function mostrarContactos() {
        privadoSel = null;
        privadoSinceId = 0;
        const lista = $('chatPrivadoLista');
        const conv = $('chatPrivadoConv');
        if (lista) lista.style.display = 'flex';
        if (conv) conv.style.display = 'none';
        desactivarInputPrivado();
        cargarContactos();
    }

    async function abrirConversacion(id, nombre) {
        privadoSel = { id: id, nombre: nombre };
        privadoSinceId = 0;
        const lista = $('chatPrivadoLista');
        const conv = $('chatPrivadoConv');
        if (lista) lista.style.display = 'none';
        if (conv) conv.style.display = 'flex';
        const nombreEl = $('chatPrivadoNombre');
        if (nombreEl) nombreEl.textContent = nombre || 'Usuario';
        const msgs = $('chatPrivadoMessages');
        if (msgs) msgs.innerHTML = '';
        enfocarInputPrivado();
        await cargarConversacion();
        await pollPrivadoNoLeidos();
    }

    async function cargarConversacion() {
        if (!privadoSel) return;
        try {
            const resp = await fetch(
                `${API_BASE_URL}/chat-privado/conversacion/${privadoSel.id}?since_id=${privadoSinceId}&limit=50`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            if (resp.status === 401) { logout(); return; }
            if (!resp.ok) return;
            const nuevos = await resp.json();
            if (!Array.isArray(nuevos) || !nuevos.length) return;
            nuevos.forEach(m => agregarMensajePrivado(m));
            privadoSinceId = nuevos[nuevos.length - 1].id_mensaje;
        } catch (e) {
            // Silencioso: red inestable no debe ensuciar la consola
        }
    }

    function agregarMensajePrivado(m) {
        const msgs = $('chatPrivadoMessages');
        if (!msgs) return;
        if (msgs.querySelector(`[data-msg-id="${m.id_mensaje}"]`)) return;

        const esMio = miUserId != null && m.id_emisor === miUserId;
        const div = document.createElement('div');
        div.className = 'chat-msg ' + (esMio ? 'user' : 'bot');
        div.dataset.msgId = m.id_mensaje;

        const cuerpo = document.createElement('div');
        cuerpo.textContent = m.mensaje;
        div.appendChild(cuerpo);

        const meta = document.createElement('div');
        meta.className = 'msg-meta';
        const hora = m.fecha ? new Date(m.fecha).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' }) : '';
        const autor = esMio ? 'Tú' : (privadoSel ? privadoSel.nombre : '');
        meta.textContent = hora ? `${autor} · ${hora}` : autor;
        div.appendChild(meta);

        msgs.appendChild(div);
        scrollAbajo(msgs);
    }

    async function enviarPrivado(texto) {
        if (!privadoSel) return;
        const input = $('chatInput');
        const msgs = $('chatPrivadoMessages');

        try {
            const resp = await fetch(`${API_BASE_URL}/chat-privado/conversacion/${privadoSel.id}`, {
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
            agregarMensajePrivado(mensaje);
            if (mensaje.id_mensaje > privadoSinceId) privadoSinceId = mensaje.id_mensaje;
            input.value = '';
            input.style.height = 'auto';
        } catch (e) {
            console.error('chat-global: error enviando privado', e);
            addMsg(msgs, 'Error de conexión. Intenta de nuevo.', 'system', null, null);
        }
    }

    function enfocarInputPrivado() {
        const input = $('chatInput');
        if (!input) return;
        input.disabled = false;
        input.placeholder = 'Mensaje privado...';
        input.focus();
    }

    function desactivarInputPrivado() {
        const input = $('chatInput');
        if (!input) return;
        input.disabled = true;
        input.placeholder = 'Selecciona un contacto...';
    }

    function startPollingPrivado() {
        pollPrivadoNoLeidos();
        timerPrivPoll = setInterval(() => {
            pollPrivadoNoLeidos();
            const panel = $('chatPanel');
            const abierto = panel && panel.classList.contains('open')
                && tabActiva === 'privado' && privadoSel;
            if (abierto) cargarConversacion();
        }, INTERVALO_POLLING_MS);
    }

    async function pollPrivadoNoLeidos() {
        if (!privadoSoporte) return;
        try {
            const resp = await fetch(`${API_BASE_URL}/chat-privado/no-leidos`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!resp.ok) return;
            const data = await resp.json();
            privadoNoLeidos = data.total || 0;
            actualizarBadge();
        } catch (e) {
            // Silencioso
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
    // BADGE DE NO LEÍDOS (global + privado)
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
        const total = noLeidos + privadoNoLeidos;
        if (total > 0) {
            badge.textContent = total > 99 ? '99+' : String(total);
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
