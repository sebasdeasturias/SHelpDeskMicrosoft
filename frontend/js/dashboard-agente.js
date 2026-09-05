// dashboard-agente.js
const API = window.API_BASE_URL || 'http://localhost:8000/api';

function esc(v) {
    return String(v == null ? '' : v)
        .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

const state = {
    tickets: [],
    lastSync: '1970-01-01T00:00:00Z',
    authToken: localStorage.getItem('token') || sessionStorage.getItem('token'),
    chatHistory: [],
    attachedTicket: null,
    isChatLoading: false
};

// Mapeo de estados de la BD a columnas del Kanban
const COLUMN_MAP = {
    'nuevo': 'todo',
    'asignado': 'todo',
    'en_proceso': 'progress',
    'escalado': 'progress',
    'resuelto': 'review',
    'cerrado': 'done'
};

const PRIO_MAP = {
    'crítica': 'critical',
    'alta': 'high',
    'media': 'medium',
    'baja': 'low'
};

// ============================================
// INICIALIZACIÓN
// ============================================
document.addEventListener('DOMContentLoaded', async () => {
    if (!state.authToken) {
        window.location.href = 'login.html';
        return;
    }

    try {
        const response = await fetch(`${API}/auth/me`, {
            headers: { 'Authorization': `Bearer ${state.authToken}` }
        });
        if (!response.ok) {
            throw new Error('Token inválido');
        }

        const userData = await response.json();
        state.userData = userData;
        
        // Verificar que el usuario tenga acceso al dashboard de agente
        if (userData.role !== 'agente' && userData.role !== 'coordinador' && userData.role !== 'administrador') {
            console.warn('Usuario sin permisos de agente, redirigiendo...');
            window.location.href = 'dashboard-solicitante.html';
            return;
        }
    } catch (error) {
        console.error('Error de autenticación:', error);
        localStorage.removeItem('token');
        sessionStorage.removeItem('token');
        window.location.href = 'login.html';
        return;
    }
    
    initTheme();
    initKanban();
    initChat();
    initTicketDetail();
    fetchTickets();
    setInterval(fetchTickets, 5000);
});


function initTheme() {
    const toggle = document.getElementById('themeCheck');
    if (localStorage.getItem('theme') === 'night') {
        document.body.classList.add('night-mode');
        toggle.checked = true;
    }
    toggle.addEventListener('change', () => {
        document.body.classList.toggle('night-mode', toggle.checked);
        localStorage.setItem('theme', toggle.checked ? 'night' : 'day');
    });

    document.getElementById('logoutBtn').addEventListener('click', () => {
        localStorage.removeItem('token');
        sessionStorage.removeItem('token');
        window.location.href = 'login.html';
    });
}

// ============================================
// KANBAN: Fetch y Render
// ============================================
function initKanban() {
    // La lógica de drag & drop se inicializa después del render
}

async function fetchTickets() {
    // FIX BUG #4: no re-renderizar si el usuario está arrastrando
    if (isDragging) return;

    try {
        // FIX BUG #1: traer TODOS los tickets (sin "since").
        // Antes el delta reemplazaba la lista completa y vaciaba el tablero.
        const res = await fetch(`${API}/tickets`, {
            headers: { 'Authorization': `Bearer ${state.authToken}` }
        });
        if (!res.ok) throw new Error('No autorizado');
        let data = await res.json();

        // Defensa en cliente: un agente solo trabaja los tickets que el
        // coordinador le asignó (el backend ya filtra por rol).
        if (state.userData && state.userData.role === 'agente') {
            data = data.filter(t => t.id_agente_asignado === state.userData.user_id);
        }
        state.tickets = data;
        renderBoard();
        updateCounts();
    } catch (e) {
        console.warn('Sync:', e.message);
    }
}

function renderBoard() {
    const cols = { todo: [], progress: [], review: [], done: [] };
    state.tickets.forEach(t => {
        const c = COLUMN_MAP[t.estado];
        if (c) cols[c].push(t);
    });

    Object.keys(cols).forEach(col => {
        document.getElementById(`col-${col}`).innerHTML = cols[col].map(t => createCardHTML(t)).join('');
    });

    initDragDrop();
    bindInfoButtons();
}

function mapPriority(prio) {
    return PRIO_MAP[prio?.toLowerCase()] || 'low';
}

function createCardHTML(t) {
    const init = (t.agente || 'U').split(' ').map(w => w[0]).join('').substring(0, 2);
    const hue = ((t.agente || 'U').charCodeAt(0) * 17) % 360;

    const catMap = {
        'Hardware': 'hardware',
        'Software': 'software',
        'Red': 'network',
        'Red/Internet': 'network',
        'Cuentas/Accesos': 'access',
        'Otros': 'network'
    };

    return `
        <div class="kanban-card" draggable="true" data-id="${t.id_solicitud}" data-col="${COLUMN_MAP[t.estado]}">
            <div class="card-priority-bar priority-${mapPriority(t.prio_nivel)}"></div>
            <button class="card-info-btn" data-id="${t.id_solicitud}" title="Ver todos los detalles del ticket">
                <i class="fas fa-info-circle"></i>
            </button>
            <div class="card-title">${esc(t.asunto)}</div>
            <div class="card-meta">
                <span class="card-id">#${t.id_solicitud}</span>
                <div class="card-tags">
                    <span class="tag tag-${catMap[t.cat_nombre] || 'network'}">${esc(t.cat_nombre) || 'General'}</span>
                </div>
            </div>
            <div class="card-assignee">
                <div class="assignee-avatar" style="background:hsl(${hue},60%,40%)">${init}</div>
                <span class="assignee-name">${esc(t.agente) || 'Sin asignar'}</span>
            </div>
            <div class="card-date">📅 ${new Date(t.fecha_creacion).toLocaleDateString('es-ES')}</div>
        </div>
    `;
}

function updateCounts() {
    // FIX BUG #2: acumular todos los estados que pertenecen a cada columna
    const counts = { todo: 0, progress: 0, review: 0, done: 0 };
    state.tickets.forEach(t => {
        const colKey = COLUMN_MAP[t.estado];
        if (colKey) counts[colKey]++;
    });
    Object.keys(counts).forEach(colKey => {
        const el = document.getElementById(`count-${colKey}`);
        if (el) el.textContent = counts[colKey];
    });
}

// ============================================
// KANBAN: Drag & Drop
// ============================================
let dragged = null;
let isDragging = false;

function initDragDrop() {
    document.querySelectorAll('.kanban-card').forEach(c => {
        c.addEventListener('dragstart', e => {
            isDragging = true;
            dragged = c;
            setTimeout(() => c.classList.add('dragging'), 0);
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', c.dataset.id);
        });
        c.addEventListener('dragend', () => {
            isDragging = false;
            if (dragged) {
                dragged.classList.remove('dragging');
                dragged = null;
            }
            document.querySelectorAll('.kanban-column').forEach(col => col.classList.remove('drag-over'));
            document.querySelectorAll('.drop-placeholder').forEach(ph => ph.remove());
        });
    });

    document.querySelectorAll('.column-body').forEach(body => {
        body.addEventListener('dragover', e => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            const column = body.closest('.kanban-column');
            column.classList.add('drag-over');

            let ph = body.querySelector('.drop-placeholder');
            if (!ph) {
                ph = document.createElement('div');
                ph.className = 'drop-placeholder';
                body.appendChild(ph);
            }
            const afterElement = getAfterElement(body, e.clientY);
            if (afterElement) {
                body.insertBefore(ph, afterElement);
            } else {
                body.appendChild(ph);
            }
        });

        body.addEventListener('dragleave', e => {
            if (!body.contains(e.relatedTarget)) {
                body.closest('.kanban-column').classList.remove('drag-over');
                const ph = body.querySelector('.drop-placeholder');
                if (ph) ph.remove();
            }
        });

        body.addEventListener('drop', async e => {
            e.preventDefault();
            const column = body.closest('.kanban-column');
            column.classList.remove('drag-over');
            const ph = body.querySelector('.drop-placeholder');
            if (ph) ph.remove();
            if (!dragged) return;

            const ticketId = dragged.dataset.id;
            const newColKey = body.id.replace('col-', '');

            // Columna 'Archivado': no es un estado más del tablero, dispara el
            // flujo de archivo (confirmación obligatoria; estado terminal).
            if (newColKey === 'archived') {
                dragged.style.opacity = '1';
                dragged.classList.remove('dragging');
                dragged = null;
                await manejarArchivo(ticketId);
                return;
            }

            // 'Por Hacer' agrupa dos estados: 'nuevo' (sin agente, solo coordinador)
            // y 'asignado' (con agente). Se elige según si el ticket tiene agente.
            let newStatus;
            if (newColKey === 'todo') {
                const ticket = state.tickets.find(t => t.id_solicitud == ticketId);
                newStatus = (ticket && ticket.id_agente_asignado) ? 'asignado' : 'nuevo';
            } else {
                newStatus = Object.keys(COLUMN_MAP).find(k => COLUMN_MAP[k] === newColKey);
            }

            if (newStatus) {
                dragged.style.opacity = '0.5';
                try {
                    await updateTicketStatus(ticketId, newStatus);
                } catch (error) {
                    console.error('Error al actualizar estado:', error);
                } finally {
                    if (dragged) {
                        dragged.style.opacity = '1';
                        dragged.classList.remove('dragging');
                        dragged = null;
                    }
                }
            }
        });
    });
}

function getAfterElement(container, y) {
    const draggableElements = [...container.querySelectorAll('.kanban-card:not(.dragging)')];
    return draggableElements.reduce((closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) {
            return { offset: offset, element: child };
        } else {
            return closest;
        }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
}

async function updateTicketStatus(id, newStatus) {
    try {
        const response = await fetch(`${API}/tickets/${id}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${state.authToken}`
            },
            body: JSON.stringify({ estado: newStatus })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const ticketIndex = state.tickets.findIndex(t => t.id_solicitud == id);
        if (ticketIndex !== -1) {
            state.tickets[ticketIndex].estado = newStatus;
            state.tickets[ticketIndex].fecha_actualizacion = new Date().toISOString();
        }
        renderBoard();
        updateCounts();
    } catch (error) {
        console.error('Update failed', error);
        renderBoard();
    }
}

// ============================================
// KANBAN: Archivar (migración 004, modal en js/kanban-archive.js)
// ============================================
async function manejarArchivo(ticketId) {
    if (!window.KanbanArchivo) {
        console.error('kanban-archive.js no está cargado');
        renderBoard();
        return;
    }
    const ticket = state.tickets.find(t => t.id_solicitud == ticketId);
    if (!ticket) return;

    // Solo se archiva un ticket ya completado (lo valida también el backend).
    if (ticket.estado !== 'resuelto' && ticket.estado !== 'cerrado') {
        await KanbanArchivo.avisoNoArchivable(ticket.estado);
        renderBoard(); // la tarjeta vuelve a su columna
        return;
    }

    const confirmado = await KanbanArchivo.confirmar(ticket);
    if (!confirmado) {
        renderBoard(); // cancelado: la tarjeta vuelve a su columna
        return;
    }

    // Al confirmar: el PATCH deja el ticket en 'archivado' (terminal). El
    // tablero lo oculta (COLUMN_MAP no lo mapea) y el listado del backend
    // deja de devolverlo en el siguiente refresco.
    await updateTicketStatus(ticketId, 'archivado');
}

// ============================================
// CHAT IA: Inicialización y Lógica (CORREGIDO)
// ============================================
function initChat() {
    const chatInput = document.getElementById('chatInput');
    const chatSendBtn = document.getElementById('chatSendBtn');
    const attachBtn = document.getElementById('attachBtn');       
    const chatFab = document.getElementById('chatFab');
    const chatPanel = document.getElementById('chatPanel');       
    const chatClose = document.getElementById('chatClose');       

    // Verificar que los elementos existan antes de agregar listeners
    if (!chatInput || !chatSendBtn) {
        console.error('⚠️ Elementos del chat no encontrados en el HTML');
        return;
    }

    // Este dashboard maneja su propio chat IA (el widget compartido solo añade Chat Global)
    window.__chatIaPropia = true;

    // ---- FAB: Abrir/Cerrar el panel ----
    if (chatFab && chatPanel) {
        chatFab.addEventListener('click', () => {
            const isOpen = chatPanel.classList.toggle('open');
            chatFab.classList.toggle('open', isOpen);
            if (isOpen) chatInput.focus();
        });
    }

    // ---- Botón cerrar (✕) del header ----
    if (chatClose && chatPanel) {
        chatClose.addEventListener('click', () => {
            chatPanel.classList.remove('open');
            chatFab.classList.remove('open');
        });
    }

    // ---- Enviar con botón ----
    chatSendBtn.addEventListener('click', sendChatMessage);

    // ---- Enviar con Enter (sin Shift) ----
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    // ---- Auto-resize del textarea ----
    chatInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 80) + 'px';
    });

    // ---- Adjuntar ticket ----
    if (attachBtn) {
        attachBtn.addEventListener('click', openCardSelector);
    }

    // ---- Card selector ----
    const cardSelectorClose = document.getElementById('cardSelectorClose');
    const cardSelectorSearch = document.getElementById('cardSelectorSearch');
    if (cardSelectorClose) {
        cardSelectorClose.addEventListener('click', closeCardSelector);
    }
    if (cardSelectorSearch) {
        cardSelectorSearch.addEventListener('input', filterCardSelector);
    }
}

async function sendChatMessage() {
    // Si la tab activa es Chat Global, el widget compartido (chat-global.js) maneja el envío
    if (window.ChatGlobal && window.ChatGlobal.activo()) { window.ChatGlobal.enviarDesdeInput(); return; }

    const chatInput = document.getElementById('chatInput');
    const mensaje = chatInput.value.trim();
    if (!mensaje || state.isChatLoading) return;

    // Agregar mensaje del usuario
    addChatMessage(mensaje, 'user');
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Si hay ticket adjunto, el backend inyectará el contexto completo
    // (ticket + solicitante + análisis IA) a partir del ticket_id
    const payload = {
        mensaje: mensaje,
        historial: state.chatHistory.slice(-10),
        modelo: 'llama3.2:3b'
    };
    if (state.attachedTicket) {
        payload.ticket_id = state.attachedTicket.id_solicitud;
    }

    // Guardar en historial
    state.chatHistory.push({ role: 'user', content: mensaje });

    // Mostrar typing
    state.isChatLoading = true;
    document.getElementById('chatSendBtn').disabled = true;
    showTyping();

    try {
        const response = await fetch(`${API}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${state.authToken}`
            },
            body: JSON.stringify(payload)
        });

        if (response.status === 401) {
            localStorage.removeItem('token');
            sessionStorage.removeItem('token');
            window.location.href = 'login.html';
            return;
        }

        hideTyping();

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        const respuesta = data.respuesta || 'No recibí respuesta del modelo.';

        // Agregar respuesta del bot
        const botMsg = addChatMessage(respuesta, 'bot');

        // Agregar metadata si existe
        if (data.tokens || data.modelo) {
            const meta = document.createElement('div');
            meta.className = 'msg-meta';
            meta.textContent = `${data.modelo || 'IA'} • ${data.tokens?.tokens_generados || '?'} tokens • ${data.tokens?.tiempo_total_ms || '?'}ms`;
            botMsg.appendChild(meta);
        }

        // Guardar en historial
        state.chatHistory.push({ role: 'assistant', content: respuesta });

        // Limpiar ticket adjunto después de usarlo
        if (state.attachedTicket) {
            state.attachedTicket = null;
        }

    } catch (error) {
        hideTyping();
        addChatMessage(`❌ Error al conectar con la IA: ${error.message}. Verifica que el backend y n8n estén corriendo.`, 'system');
        console.error('Chat error:', error);
    } finally {
        state.isChatLoading = false;
        document.getElementById('chatSendBtn').disabled = false;
        chatInput.focus();
    }
}

function addChatMessage(text, type) {
    const container = document.getElementById('chatMessages');
    const msg = document.createElement('div');
    msg.className = `chat-msg ${type}`;
    msg.textContent = text;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
    return msg;
}

function showTyping() {
    const container = document.getElementById('chatMessages');
    const typing = document.createElement('div');
    typing.className = 'typing-indicator';
    typing.id = 'typingIndicator';
    typing.innerHTML = '<span></span><span></span><span></span>';
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;
}

function hideTyping() {
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
}

// ============================================
// CARD SELECTOR: Adjuntar ticket al chat
// ============================================
function openCardSelector() {
    const overlay = document.getElementById('cardSelectorOverlay');
    overlay.classList.add('open');
    renderCardSelectorList(state.tickets);
    document.getElementById('cardSelectorSearch').value = '';
    document.getElementById('cardSelectorSearch').focus();
}

function closeCardSelector() {
    document.getElementById('cardSelectorOverlay').classList.remove('open');
}

function filterCardSelector(e) {
    const query = e.target.value.toLowerCase();
    const filtered = state.tickets.filter(t =>
        t.asunto.toLowerCase().includes(query) ||
        String(t.id_solicitud).includes(query)
    );
    renderCardSelectorList(filtered);
}

function renderCardSelectorList(tickets) {
    const list = document.getElementById('cardSelectorList');
    if (tickets.length === 0) {
        list.innerHTML = '<div style="color:var(--text-placeholder);text-align:center;padding:20px;">No se encontraron tickets</div>';
        return;
    }

    list.innerHTML = tickets.map(t => `
        <div class="selector-card-item" data-id="${t.id_solicitud}">
            <div class="sci-title">#${t.id_solicitud} - ${esc(t.asunto)}</div>
            <div class="sci-meta">
                <span class="sci-priority" style="background:rgba(255,255,255,0.2);color:var(--text-dark);">${esc(t.prio_nivel) || 'N/A'}</span>
                <span>${esc(t.estado) || 'N/A'}</span>
            </div>
        </div>
    `).join('');

    // Agregar evento click a cada item
    list.querySelectorAll('.selector-card-item').forEach(item => {
        item.addEventListener('click', () => {
            const ticketId = parseInt(item.dataset.id);
            const ticket = state.tickets.find(t => t.id_solicitud === ticketId);
            if (ticket) {
                state.attachedTicket = ticket;
                addChatMessage(`📎 Ticket #${ticket.id_solicitud} adjuntado. La IA recibirá el contexto completo (ticket, solicitante y análisis IA).`, 'system');
            }
            closeCardSelector();
        });
    });
}

// ============================================
// DETALLE COMPLETO DEL TICKET (Botón "i")
// ============================================
function initTicketDetail() {
    const overlay = document.getElementById('ticketDetailOverlay');
    const closeBtn = document.getElementById('ticketDetailClose');
    if (!overlay) return;
    if (closeBtn) {
        closeBtn.addEventListener('click', () => overlay.classList.remove('open'));
    }
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.classList.remove('open');
    });
}

function bindInfoButtons() {
    document.querySelectorAll('.card-info-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            openTicketDetail(parseInt(btn.dataset.id));
        });
    });
}

async function openTicketDetail(ticketId) {
    const overlay = document.getElementById('ticketDetailOverlay');
    const body = document.getElementById('ticketDetailBody');
    document.getElementById('ticketDetailId').textContent = `#${ticketId}`;
    body.innerHTML = '<div class="detail-loading"><i class="fas fa-spinner fa-spin"></i> Cargando detalles del ticket...</div>';
    overlay.classList.add('open');

    try {
        const res = await fetch(`${API}/tickets/${ticketId}`, {
            headers: { 'Authorization': `Bearer ${state.authToken}` }
        });
        if (res.status === 401) {
            localStorage.removeItem('token');
            sessionStorage.removeItem('token');
            window.location.href = 'login.html';
            return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        body.innerHTML = buildTicketDetailHTML(data);
    } catch (err) {
        console.error('Error cargando detalle:', err);
        body.innerHTML = `<div class="detail-loading">❌ Error al cargar los detalles: ${err.message}</div>`;
    }
}

function buildTicketDetailHTML(d) {
    const t = d.ticket;
    const sol = d.solicitante;
    const ag = d.agente_asignado;
    const ia = d.analisis_ia;

    const fecha = (iso) => iso ? new Date(iso).toLocaleString('es-ES') : 'N/A';

    let html = `
        <div class="detail-section">
            <h4>📄 Información del Ticket</h4>
            <div class="detail-desc"><strong>${esc(t.asunto)}</strong></div>
            <div class="detail-desc">${esc(t.descripcion)}</div>
            <div class="detail-row"><span class="detail-key">Estado</span><span class="detail-val">${esc(t.estado)}</span></div>
            <div class="detail-row"><span class="detail-key">Categoría</span><span class="detail-val">${esc(t.categoria) || 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Prioridad</span><span class="detail-val">${esc(t.prioridad) || 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Creado</span><span class="detail-val">${fecha(t.fecha_creacion)}</span></div>
            <div class="detail-row"><span class="detail-key">Actualizado</span><span class="detail-val">${fecha(t.fecha_actualizacion)}</span></div>
        </div>

        <div class="detail-section">
            <h4>👤 Solicitante</h4>
            ${sol ? `
            <div class="detail-row"><span class="detail-key">Nombre</span><span class="detail-val">${esc(sol.nombre)}</span></div>
            <div class="detail-row"><span class="detail-key">Email</span><span class="detail-val">${esc(sol.email)}</span></div>
            <div class="detail-row"><span class="detail-key">Área</span><span class="detail-val">${esc(sol.area) || 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Rol</span><span class="detail-val">${esc(sol.rol)}</span></div>
            <div class="detail-row"><span class="detail-key">Estado cuenta</span><span class="detail-val">${esc(sol.estado)}</span></div>
            <div class="detail-row"><span class="detail-key">Registrado</span><span class="detail-val">${fecha(sol.fecha_registro)}</span></div>
            <div class="detail-row"><span class="detail-key">Último acceso</span><span class="detail-val">${fecha(sol.fecha_ultimo_acceso)}</span></div>
            ` : '<div class="detail-row"><span class="detail-val">Sin datos del solicitante</span></div>'}
        </div>

        <div class="detail-section">
            <h4>🛠️ Agente Asignado</h4>
            ${ag ? `
            <div class="detail-row"><span class="detail-key">Nombre</span><span class="detail-val">${esc(ag.nombre)}</span></div>
            <div class="detail-row"><span class="detail-key">Email</span><span class="detail-val">${esc(ag.email)}</span></div>
            <div class="detail-row"><span class="detail-key">Especialidad</span><span class="detail-val">${esc(ag.especialidad) || 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Carga actual</span><span class="detail-val">${ag.carga_trabajo} ticket(s)</span></div>
            ` : '<div class="detail-row"><span class="detail-val">Sin asignar</span></div>'}
        </div>

        <div class="detail-section">
            <h4>🤖 Análisis IA Local (Ollama)</h4>
            ${ia ? `
            <div class="detail-row"><span class="detail-key">Categoría IA</span><span class="detail-val">${esc(ia.categoria_ia) || 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Prioridad IA</span><span class="detail-val">${esc(ia.prioridad_ia) || 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Confianza</span><span class="detail-val">${ia.confianza != null ? (ia.confianza * 100).toFixed(1) + '%' : 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Modelo</span><span class="detail-val">${esc(ia.modelo_ia) || 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Tokens usados</span><span class="detail-val">${ia.tokens_usados != null ? ia.tokens_usados : 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Tiempo ejecución</span><span class="detail-val">${ia.tiempo_ejecucion_ms != null ? ia.tiempo_ejecucion_ms + ' ms' : 'N/A'}</span></div>
            <div class="detail-row"><span class="detail-key">Fecha análisis</span><span class="detail-val">${fecha(ia.fecha_clasificacion)}</span></div>
            <div class="detail-row"><span class="detail-key">Revisión manual</span><span class="detail-val">${ia.revision_manual ? 'Sí' : 'No'}</span></div>
            ${ia.comentario_revision ? `<div class="detail-row"><span class="detail-key">Comentario revisión</span><span class="detail-val">${esc(ia.comentario_revision)}</span></div>` : ''}
            ` : '<div class="detail-row"><span class="detail-val">La IA aún no ha analizado este ticket</span></div>'}
        </div>
    `;

    if (d.historial && d.historial.length > 0) {
        html += `
        <div class="detail-section">
            <h4>🕘 Historial de Estados</h4>
            ${d.historial.map(h => `
                <div class="detail-row">
                    <span class="detail-key">${esc(h.estado_anterior) || '—'} → ${esc(h.estado_nuevo)}</span>
                    <span class="detail-val">${fecha(h.fecha)}</span>
                </div>
            `).join('')}
        </div>`;
    }

    return html;
}