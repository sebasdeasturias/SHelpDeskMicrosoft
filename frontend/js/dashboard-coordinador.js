// dashboard-coordinador.js
const API = window.API_BASE_URL || 'http://localhost:8000/api';

function esc(v) {
    return String(v == null ? '' : v)
        .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

const state = {
    tickets: [],
    reportes: [],
    lastSync: '1970-01-01T00:00:00Z',
    authToken: localStorage.getItem('token') || sessionStorage.getItem('token'),
    chatHistory: [],
    attachedTicket: null,
    isChatLoading: false,
    currentPage: 'kanban',
    userData: null
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
// HELPERS DE API Y RENDER
// ============================================
async function apiFetch(path, options = {}) {
    const headers = {
        'Authorization': `Bearer ${state.authToken}`,
        ...(options.headers || {})
    };
    if (options.body && typeof options.body !== 'string') {
        headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(options.body);
    }
    const res = await fetch(`${API}${path}`, { ...options, headers });
    if (res.status === 401) {
        localStorage.removeItem('token');
        sessionStorage.removeItem('token');
        window.location.href = 'login.html';
        throw new Error('No autorizado');
    }
    if (!res.ok) {
        // Extraer el detalle legible que envía el backend (p.ej. límite diario)
        let msg = `HTTP ${res.status}`;
        try {
            const err = await res.json();
            if (err.detail) msg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
        } catch (_) { /* respuesta sin JSON */ }
        throw new Error(msg);
    }
    return res.json();
}

const CAT_CLASS = {
    'Hardware': 'hardware',
    'Software': 'software',
    'Red': 'network',
    'Red/Internet': 'network',
    'Cuentas/Accesos': 'access',
    'Otros': 'network'
};

function catClass(cat) { return CAT_CLASS[cat] || 'network'; }

function prioClass(prio) {
    const p = (prio || '').toLowerCase();
    if (p === 'crítica' || p === 'critica') return 'critical';
    if (p === 'alta') return 'high';
    if (p === 'media') return 'medium';
    return 'low';
}

function statusClass(est) {
    const e = (est || '').toLowerCase();
    if (e === 'nuevo' || e === 'asignado') return 'nuevo';
    if (e === 'en_proceso' || e === 'escalado') return 'proceso';
    if (e === 'resuelto') return 'resuelto';
    return 'cerrado';
}

function initials(name) {
    return (name || '?').split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
}

function hueFor(name) {
    return ((name || 'U').charCodeAt(0) * 17) % 360;
}

function formatDate(iso) {
    if (!iso) return 'N/A';
    const d = new Date(iso);
    return d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
}

function fmt(min) {
    if (min == null || isNaN(min)) return '—';
    if (min < 60) return `${min} min`;
    const h = Math.round(min / 60);
    return `${h} h`;
}

// ============================================
// INICIALIZACIÓN
// ============================================
document.addEventListener('DOMContentLoaded', async () => {
    if (!state.authToken) {
        window.location.href = 'login.html';
        return;
    }
    
    await loadUserData();
    initTheme();
    initNavigation();
    initKanban();
    initChat();
    initCoordinatorModules();
    initTicketDetail();
    await fetchTickets();
    setInterval(fetchTickets, 5000);
});

// ============================================
// CARGA DE DATOS DEL USUARIO
// ============================================
async function loadUserData() {
    try {
        const response = await fetch(`${API}/auth/me`, {
            headers: { 'Authorization': `Bearer ${state.authToken}` }
        });
        if (!response.ok) throw new Error('No autorizado');
        
        state.userData = await response.json();
        document.getElementById('userName').textContent = state.userData.nombre || state.userData.email;
        
        // Verificar que sea coordinador
        if (state.userData.role !== 'coordinador' && state.userData.role !== 'administrador') {
            // Redirigir según rol real
            const redirectMap = {
                'solicitante': 'dashboard-solicitante.html',
                'agente': 'dashboard-agente.html',
                'administrador': 'dashboard-admin.html'
            };
            window.location.href = redirectMap[state.userData.role] || 'login.html';
        }
    } catch (error) {
        console.error('Error cargando usuario:', error);
        window.location.href = 'login.html';
    }
}

// ============================================
// TEMA Y NAVEGACIÓN
// ============================================
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

function initNavigation() {
    const menuToggle = document.getElementById('menuToggle');
    const dropdownMenu = document.getElementById('dropdownMenu');
    const navBtns = document.querySelectorAll('.nav-btn:not(.dropdown-toggle)');
    const dropdownItems = document.querySelectorAll('.dropdown-item');

    // Toggle del menú desplegable
    menuToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        dropdownMenu.classList.toggle('open');
    });

    // Cerrar menú al hacer clic fuera
    document.addEventListener('click', () => {
        dropdownMenu.classList.remove('open');
    });

    // Navegación por botones principales (Kanban)
    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const page = btn.dataset.page;
            navigateTo(page);
            dropdownMenu.classList.remove('open');
        });
    });

    // Navegación por items del dropdown
    dropdownItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const page = item.dataset.page;
            navigateTo(page);
            dropdownMenu.classList.remove('open');
        });
    });
}

function navigateTo(page) {
    // Actualizar estado
    state.currentPage = page;

    // Ocultar todas las páginas
    document.querySelectorAll('.page-content').forEach(el => {
        el.classList.remove('active');
    });

    // Mostrar la página seleccionada
    const targetPage = document.getElementById(`page-${page}`);
    if (targetPage) {
        targetPage.classList.add('active');
    }

    // Actualizar botón activo
    document.querySelectorAll('.nav-btn:not(.dropdown-toggle)').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.page === page);
    });

    // Resaltar el dropdown "Gestión Agentes" si la página pertenece a su grupo
    const paginasAgentes = ['asignar', 'supervisar', 'chat-ia', 'rag', 'mi-perfil'];
    const dropdownToggle = document.getElementById('menuToggle');
    if (dropdownToggle) {
        dropdownToggle.classList.toggle('active', paginasAgentes.includes(page));
    }

    // Si es kanban, refrescar tickets
    if (page === 'kanban') {
        fetchTickets();
    }

    // Si es el perfil, cargar datos del coordinador
    if (page === 'mi-perfil') {
        renderPerfil();
    }

    // Cargar datos reales de la BD para cada módulo de coordinación
    const loaders = {
        'streamlit': loadEstadisticas,
        'reportes': loadReportes,
        'asignar': loadAsignacion,
        'supervisar': loadSupervisar,
        'sla': loadSLA
    };
    if (loaders[page]) loaders[page]();

    console.log(`📄 Navegando a: ${page}`);
}

// ============================================
// KANBAN: Fetch y Render
// ============================================
let isDragging = false;

function initKanban() {
    // Se inicializa después del render
}

async function fetchTickets() {
    if (isDragging || state.currentPage !== 'kanban') return;

    try {
        const res = await fetch(`${API}/tickets`, {
            headers: { 'Authorization': `Bearer ${state.authToken}` }
        });
        if (!res.ok) throw new Error('No autorizado');
        state.tickets = await res.json();
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
        const container = document.getElementById(`col-${col}`);
        if (container) {
            container.innerHTML = cols[col].map(t => createCardHTML(t)).join('');
        }
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
            // 'Por Hacer' agrupa dos estados: 'nuevo' (sin agente) y 'asignado'
            // (con agente). Se elige según si el ticket tiene agente asignado.
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
// CHAT IA: Inicialización y Lógica
// ============================================
function initChat() {
    const chatInput = document.getElementById('chatInput');
    const chatSendBtn = document.getElementById('chatSendBtn');
    const attachBtn = document.getElementById('attachBtn');
    const chatFab = document.getElementById('chatFab');
    const chatPanel = document.getElementById('chatPanel');
    const chatClose = document.getElementById('chatClose');

    if (!chatInput || !chatSendBtn) {
        console.error('⚠️ Elementos del chat no encontrados');
        return;
    }

    chatFab.addEventListener('click', () => {
        const isOpen = chatPanel.classList.toggle('open');
        chatFab.classList.toggle('open', isOpen);
        if (isOpen) chatInput.focus();
    });

    chatClose.addEventListener('click', () => {
        chatPanel.classList.remove('open');
        chatFab.classList.remove('open');
    });

    chatSendBtn.addEventListener('click', sendChatMessage);

    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    chatInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 80) + 'px';
    });

    if (attachBtn) {
        attachBtn.addEventListener('click', openCardSelector);
    }

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
    const chatInput = document.getElementById('chatInput');
    const mensaje = chatInput.value.trim();
    if (!mensaje || state.isChatLoading) return;

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

    state.chatHistory.push({ role: 'user', content: mensaje });

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

        const botMsg = addChatMessage(respuesta, 'bot');

        if (data.tokens || data.modelo) {
            const meta = document.createElement('div');
            meta.className = 'msg-meta';
            meta.textContent = `${data.modelo || 'IA'} • ${data.tokens?.tokens_generados || '?'} tokens • ${data.tokens?.tiempo_total_ms || '?'}ms`;
            botMsg.appendChild(meta);
        }

        state.chatHistory.push({ role: 'assistant', content: respuesta });

        if (state.attachedTicket) {
            state.attachedTicket = null;
        }

    } catch (error) {
        hideTyping();
        addChatMessage(`❌ Error al conectar con la IA: ${error.message}`, 'system');
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
// CARD SELECTOR
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
// MÓDULOS DE COORDINACIÓN
// (Reportes, Asignación, Permisos, SLA, RAG)
// ============================================
function initCoordinatorModules() {
    // --- Reportes ---
    const btnPDF = document.getElementById('btnExportPDF');
    const btnCSV = document.getElementById('btnExportCSV');
    if (btnPDF) btnPDF.addEventListener('click', exportarReportePDF);
    if (btnCSV) btnCSV.addEventListener('click', exportarReporteCSV);

    // Fechas por defecto: últimos 30 días (dinámicas, sin valores estáticos)
    const fd = document.getElementById('repFechaDesde');
    const fh = document.getElementById('repFechaHasta');
    if (fd && fh) {
        const hoy = new Date();
        const desde = new Date(hoy.getTime() - 29 * 86400000);
        fd.value = desde.toISOString().slice(0, 10);
        fh.value = hoy.toISOString().slice(0, 10);
    }
    ['repCategoria', 'repPrioridad', 'repEstado', 'repFechaDesde', 'repFechaHasta'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', loadReportes);
    });

    // --- Asignación ---
    const btnAuto = document.getElementById('btnAutoAsignarIA');
    if (btnAuto) btnAuto.addEventListener('click', autoAsignarIA);

    // Delegación para asignar tickets desde la cola
    const asigQueue = document.getElementById('asigQueueBody');
    if (asigQueue) {
        asigQueue.addEventListener('click', async (e) => {
            const btn = e.target.closest('.btn-mini-save');
            if (!btn) return;
            const row = btn.closest('tr');
            const ticketId = row.getAttribute('data-ticket-id');
            const select = row.querySelector('.glass-select-mini');
            const agenteId = select ? select.value : null;
            if (!ticketId || !agenteId) {
                mostrarToast('⚠️ Selecciona un agente para asignar el ticket');
                return;
            }
            await asignarTicket(ticketId, agenteId);
        });
    }

    // --- Permisos ---
    const btnPermisos = document.getElementById('btnGuardarPermisos');
    if (btnPermisos) btnPermisos.addEventListener('click', guardarPermisos);

    // --- SLA ---
    const btnSLA = document.getElementById('btnGuardarSLA');
    if (btnSLA) btnSLA.addEventListener('click', guardarSLA);

    // --- RAG ---
    const btnRAG = document.getElementById('btnBuscarRAG');
    const ragInput = document.getElementById('ragSearchInput');
    if (btnRAG) btnRAG.addEventListener('click', buscarRAG);
    if (ragInput) {
        ragInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') buscarRAG();
        });
    }
    const btnIndexarRAG = document.getElementById('btnIndexarRAG');
    if (btnIndexarRAG) btnIndexarRAG.addEventListener('click', indexarTicketsRAG);
}

async function indexarTicketsRAG() {
    const btn = document.getElementById('btnIndexarRAG');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Indexando...';
    }
    try {
        const r = await apiFetch('/coordinator/rag/indexar', { method: 'POST' });
        if (r.sin_trabajo) {
            mostrarToast('Todos los tickets resueltos ya están indexados');
        } else {
            mostrarToast(`Indexados ${r.indexados} ticket(s) con ${r.modelo}` +
                (r.errores ? ` · ${r.errores} error(es)` : ''));
        }
    } catch (e) {
        mostrarToast(`Error al indexar: ${e.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-database"></i> Indexar tickets';
        }
    }
}

async function obtenerTicketsFiltrados() {
    // Consulta real al backend con los filtros actuales
    const q = new URLSearchParams({
        categoria: document.getElementById('repCategoria')?.value || 'todas',
        prioridad: document.getElementById('repPrioridad')?.value || 'todas',
        estado: document.getElementById('repEstado')?.value || 'todos',
    });
    const fd = document.getElementById('repFechaDesde')?.value;
    const fh = document.getElementById('repFechaHasta')?.value;
    if (fd) q.set('fecha_desde', fd);
    if (fh) q.set('fecha_hasta', fh);
    const tickets = await apiFetch(`/coordinator/reportes?${q.toString()}`);
    state.reportes = tickets;
    return tickets;
}

async function exportarReporteCSV() {
    let tickets;
    try {
        tickets = await obtenerTicketsFiltrados();
    } catch (e) {
        mostrarToast(`⚠️ Error al obtener reporte: ${e.message}`);
        return;
    }
    if (tickets.length === 0) {
        mostrarToast('⚠️ No hay tickets que coincidan con los filtros');
        return;
    }

    const headers = ['ID', 'Asunto', 'Categoria', 'Prioridad', 'Estado', 'Agente', 'Fecha Creacion'];
    const rows = tickets.map(t => [
        t.id_solicitud,
        `"${(t.asunto || '').replace(/"/g, '""')}"`,
        t.categoria || t.cat_nombre || '',
        t.prioridad || t.prio_nivel || '',
        t.estado || '',
        t.agente || 'Sin asignar',
        t.fecha_creacion ? new Date(t.fecha_creacion).toLocaleDateString('es-ES') : ''
    ]);

    const csv = [headers.join(';'), ...rows.map(r => r.join(';'))].join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `reporte_tickets_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);

    mostrarToast(`📊 Reporte CSV exportado (${tickets.length} tickets)`);
}

async function exportarReportePDF() {
    let tickets;
    try {
        tickets = await obtenerTicketsFiltrados();
    } catch (e) {
        mostrarToast(`⚠️ Error al obtener reporte: ${e.message}`);
        return;
    }
    if (tickets.length === 0) {
        mostrarToast('⚠️ No hay tickets que coincidan con los filtros');
        return;
    }

    const filas = tickets.map(t => `
        <tr>
            <td>${t.id_solicitud}</td>
            <td>${esc(t.asunto) || ''}</td>
            <td>${esc(t.categoria) || esc(t.cat_nombre) || ''}</td>
            <td>${esc(t.prioridad) || esc(t.prio_nivel) || ''}</td>
            <td>${esc(t.estado) || ''}</td>
            <td>${esc(t.agente) || 'Sin asignar'}</td>
            <td>${t.fecha_creacion ? new Date(t.fecha_creacion).toLocaleDateString('es-ES') : ''}</td>
        </tr>
    `).join('');

    const coordinador = state.userData?.nombre || 'Coordinador';
    const w = window.open('', '_blank');
    if (!w) {
        mostrarToast('⚠️ El navegador bloqueó la ventana de impresión');
        return;
    }

    w.document.write(`
        <html>
        <head>
            <title>Reporte HelpDesk IT</title>
            <style>
                body { font-family: 'Segoe UI', Arial, sans-serif; padding: 24px; color: #1a1a2e; }
                h1 { color: #11425e; margin-bottom: 4px; }
                p.meta { color: #666; font-size: 12px; }
                table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 12px; }
                th, td { border: 1px solid #ccc; padding: 6px 8px; text-align: left; }
                th { background: #e8f4fb; }
            </style>
        </head>
        <body>
            <h1>Reporte de Tickets — HelpDesk IT</h1>
            <p class="meta">Generado: ${new Date().toLocaleString('es-ES')} • Coordinador: ${esc(coordinador)} • Total: ${tickets.length} tickets</p>
            <table>
                <thead>
                    <tr><th>ID</th><th>Asunto</th><th>Categoría</th><th>Prioridad</th><th>Estado</th><th>Agente</th><th>Fecha</th></tr>
                </thead>
                <tbody>${filas}</tbody>
            </table>
            <script>window.onload = function () { window.print(); }<\/script>
        </body>
        </html>
    `);
    w.document.close();

    mostrarToast(`📄 Generando PDF (${tickets.length} tickets)...`);
}

// ============================================
// ESTADÍSTICAS / KPIs (Streamlit)
// ============================================
async function loadEstadisticas() {
    const kpiGrid = document.querySelector('#page-streamlit .kpi-grid');
    const catBody = document.getElementById('chartCategoriasBody');
    const agBody = document.getElementById('chartAgentesBody');
    try {
        const data = await apiFetch('/coordinator/estadisticas');
        renderEstadisticas(data, kpiGrid, catBody, agBody);
    } catch (e) {
        console.error('Error cargando estadísticas:', e);
        if (kpiGrid) kpiGrid.innerHTML = `<div style="color:var(--text-placeholder);text-align:center;padding:20px;">Error: ${e.message}</div>`;
    }
}

function renderEstadisticas(d, kpiGrid, catBody, agBody) {
    const k = d.kpis || {};
    const sla = k.cumplimiento_sla != null ? `${k.cumplimiento_sla}%` : '—';
    const tme = k.tiempo_medio_solucion_min != null ? fmt(k.tiempo_medio_solucion_min) : '—';
    const agentes = `${k.agentes_activos} / ${k.agentes_totales}`;

    if (kpiGrid) {
        kpiGrid.innerHTML = `
            <div class="kpi-card">
                <div class="kpi-icon blue"><i class="fas fa-ticket-alt"></i></div>
                <div class="kpi-content">
                    <span class="kpi-label">Tickets Totales Mes</span>
                    <span class="kpi-value">${k.total_tickets_mes ?? 0}</span>
                    <span class="kpi-trend neutral"><i class="fas fa-chart-line"></i> ${k.tickets_activos ?? 0} activos ahora</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon green"><i class="fas fa-shield-alt"></i></div>
                <div class="kpi-content">
                    <span class="kpi-label">Cumplimiento de SLA</span>
                    <span class="kpi-value">${sla}</span>
                    <span class="kpi-trend neutral"><i class="fas fa-info-circle"></i> Resueltos dentro del plazo</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon yellow"><i class="fas fa-stopwatch"></i></div>
                <div class="kpi-content">
                    <span class="kpi-label">Tiempo Medio Solución</span>
                    <span class="kpi-value">${tme}</span>
                    <span class="kpi-trend neutral"><i class="fas fa-clock"></i> Tickets resueltos</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon purple"><i class="fas fa-user-check"></i></div>
                <div class="kpi-content">
                    <span class="kpi-label">Agentes Activos</span>
                    <span class="kpi-value">${agentes}</span>
                    <span class="kpi-trend neutral"><i class="fas fa-users"></i> Personal de soporte</span>
                </div>
            </div>
        `;
    }

    if (catBody) {
        const cats = d.categorias || [];
        if (cats.length === 0) {
            catBody.innerHTML = '<div style="color:var(--text-placeholder);text-align:center;padding:20px;">Sin tickets en el último mes</div>';
        } else {
            const max = Math.max(...cats.map(c => c.total), 1);
            const colors = ['blue', 'orange', 'cyan', 'red', 'green'];
            catBody.innerHTML = cats.map((c, i) => `
                <div class="bar-chart-row">
                    <span class="bar-label">${esc(c.categoria)}</span>
                    <div class="bar-track"><div class="bar-fill ${colors[i % colors.length]}" style="width: ${(c.total / max * 100).toFixed(0)}%;"></div></div>
                    <span class="bar-value">${c.total}</span>
                </div>
            `).join('');
        }
    }

    if (agBody) {
        const ags = d.agentes_eficiencia || [];
        if (ags.length === 0) {
            agBody.innerHTML = '<div style="color:var(--text-placeholder);text-align:center;padding:20px;">Sin personal de soporte</div>';
        } else {
            agBody.innerHTML = ags.map(a => {
                const max = Math.max(a.carga_trabajo, 1);
                const pct = Math.round((a.carga_trabajo / max) * 100);
                return `
                <div class="agent-efficiency-row">
                    <div class="agent-avatar-mini" style="background: hsl(${hueFor(a.nombre)},60%,40%);">${initials(a.nombre)}</div>
                    <div class="agent-eff-info">
                        <div class="eff-top"><span>${esc(a.nombre)} (${esc(a.especialidad)})</span> <strong>${a.resueltos} resueltos</strong></div>
                        <div class="bar-track"><div class="bar-fill green" style="width: ${pct}%;"></div></div>
                    </div>
                </div>`;
            }).join('');
        }
    }
}

// ============================================
// REPORTES
// ============================================
async function loadReportes() {
    const body = document.getElementById('reportTableBody');
    const count = document.getElementById('repTotalCount');
    try {
        const tickets = await obtenerTicketsFiltrados();
        if (count) count.textContent = tickets.length;
        if (body) {
            if (tickets.length === 0) {
                body.innerHTML = '<tr><td colspan="7" style="color:var(--text-placeholder);text-align:center;padding:16px;">No hay tickets que coincidan con los filtros</td></tr>';
            } else {
                body.innerHTML = tickets.map(t => `
                    <tr>
                        <td><strong>#${t.id_solicitud}</strong></td>
                        <td>${esc(t.asunto) || ''}</td>
                        <td><span class="tag tag-${catClass(t.categoria || t.cat_nombre)}">${esc(t.categoria) || esc(t.cat_nombre) || 'General'}</span></td>
                        <td><span class="priority-pill ${prioClass(t.prioridad || t.prio_nivel)}">${esc(t.prioridad) || esc(t.prio_nivel) || 'Baja'}</span></td>
                        <td><span class="status-pill ${statusClass(t.estado)}">${esc(t.estado)}</span></td>
                        <td>${esc(t.agente) || '<em>Sin asignar</em>'}</td>
                        <td>${formatDate(t.fecha_creacion)}</td>
                    </tr>
                `).join('');
            }
        }
    } catch (e) {
        console.error('Error cargando reportes:', e);
        if (body) body.innerHTML = '<tr><td colspan="7" style="color:var(--text-placeholder);text-align:center;padding:16px;">Error al cargar reportes</td></tr>';
    }
}

// ============================================
// ASIGNACIÓN DE TICKETS
// ============================================
async function loadAsignacion() {
    const grid = document.querySelector('#page-asignar .agent-workload-grid');
    const queue = document.getElementById('asigQueueBody');
    try {
        const data = await apiFetch('/coordinator/asignacion');
        renderAsignacion(data, grid, queue);
    } catch (e) {
        console.error('Error cargando asignación:', e);
        if (queue) queue.innerHTML = `<tr><td colspan="6" style="color:var(--text-placeholder);text-align:center;padding:16px;">Error: ${e.message}</td></tr>`;
    }
}

function renderAsignacion(d, grid, queue) {
    const agentes = d.agentes || [];
    const maxDiario = d.max_diario || 3;
    if (grid) {
        if (agentes.length === 0) {
            grid.innerHTML = '<div class="agent-card-glass"><div style="color:var(--text-placeholder);text-align:center;">Sin agentes de soporte</div></div>';
        } else {
            grid.innerHTML = agentes.map(a => {
                const capped = Math.min(a.carga_trabajo, 10);
                const pct = Math.round((capped / 10) * 100);
                const fill = pct >= 70 ? 'yellow' : (pct >= 45 ? 'orange' : 'green');
                const estado = a.estado === 'activo' ? 'online' : 'busy';
                const label = a.estado === 'activo' ? 'Disponible' : 'Ocupado';
                const alCupo = (a.asignados_hoy || 0) >= maxDiario;
                return `
                <div class="agent-card-glass">
                    <div class="agent-card-top">
                        <div class="agent-avatar" style="background: linear-gradient(135deg, hsl(${hueFor(a.nombre)},60%,40%), hsl(${hueFor(a.nombre)},60%,25%));">${initials(a.nombre)}</div>
                        <div class="agent-details">
                            <h4>${esc(a.nombre)}</h4>
                            <span class="agent-spec"><i class="fas fa-microchip"></i> ${esc(a.especialidad)}</span>
                        </div>
                        <span class="agent-status-badge ${estado}">${label}</span>
                    </div>
                    <div class="workload-bar-wrap">
                        <div class="workload-info"><span>Carga de Trabajo:</span> <strong>${a.carga_trabajo} ticket(s)</strong></div>
                        <div class="bar-track"><div class="bar-fill ${fill}" style="width: ${pct}%;"></div></div>
                        <div class="workload-info"><span>Asignados hoy:</span> <strong>${a.asignados_hoy || 0} / ${maxDiario}${alCupo ? ' — cupo diario completo' : ''}</strong></div>
                    </div>
                </div>`;
            }).join('');
        }
    }

    if (queue) {
        const pendientes = d.sin_asignar || [];
        if (pendientes.length === 0) {
            queue.innerHTML = '<tr><td colspan="6" style="color:var(--text-placeholder);text-align:center;padding:16px;">No hay tickets pendientes de asignación</td></tr>';
        } else {
            queue.innerHTML = pendientes.map(t => `
                <tr data-ticket-id="${t.id_solicitud}">
                    <td><strong>#${t.id_solicitud}</strong></td>
                    <td>${esc(t.asunto)}</td>
                    <td><span class="tag tag-${catClass(t.categoria)}">${esc(t.categoria)}</span></td>
                    <td><span class="priority-pill ${prioClass(t.prioridad)}">${esc(t.prioridad)}</span></td>
                    <td>${t.recomendacion ? `<span class="ai-badge-chip"><i class="fas fa-robot"></i> ${esc(t.recomendacion.nombre)} (${t.recomendacion.afinidad}% afinidad)</span>` : '<em>Sin sugerencia</em>'}</td>
                    <td>
                        <div class="assign-action-wrap">
                            <select class="glass-select-mini">
                                ${agentes.map(a => {
                                    const lleno = (a.asignados_hoy || 0) >= maxDiario;
                                    return `<option value="${a.id_usuario}" ${lleno ? 'disabled' : ''}>${esc(a.nombre)} (${a.asignados_hoy || 0}/${maxDiario} hoy)</option>`;
                                }).join('')}
                            </select>
                            <button class="btn-mini-save" title="Asignar agente"><i class="fas fa-check"></i></button>
                        </div>
                    </td>
                </tr>
            `).join('');
        }
    }
}

async function asignarTicket(ticketId, agenteId, silencioso = false) {
    try {
        const res = await apiFetch(`/coordinator/asignar/${ticketId}`, {
            method: 'POST',
            body: { agente_id: parseInt(agenteId, 10) }
        });
        if (!silencioso) mostrarToast(`Ticket #${ticketId} asignado correctamente`);
        loadAsignacion();
        fetchTickets();
        return res;
    } catch (e) {
        if (!silencioso) mostrarToast(`Error al asignar: ${e.message}`);
        throw e;
    }
}

async function autoAsignarIA() {
    try {
        const data = await apiFetch('/coordinator/asignacion');
        const pendientes = data.sin_asignar || [];
        if (pendientes.length === 0) {
            mostrarToast('No hay tickets pendientes por asignar');
            return;
        }
        let asignados = 0, omitidos = 0, ultimoError = '';
        for (const t of pendientes) {
            if (t.recomendacion && t.recomendacion.id_usuario) {
                try {
                    await asignarTicket(t.id_solicitud, t.recomendacion.id_usuario, true);
                    asignados++;
                } catch (err) {
                    omitidos++;
                    ultimoError = err.message;
                }
            }
        }
        if (asignados > 0) {
            mostrarToast(`La IA asignó ${asignados} ticket(s) automáticamente` +
                (omitidos ? ` · ${omitidos} omitido(s): ${ultimoError}` : ''));
        } else if (omitidos > 0) {
            mostrarToast(`Ningún ticket asignado (${omitidos} omitido(s)): ${ultimoError}`);
        }
    } catch (e) {
        mostrarToast(`Error en balanceo automático: ${e.message}`);
    }
}

// ============================================
// SUPERVISIÓN / PERMISOS
// ============================================
async function loadSupervisar() {
    const body = document.getElementById('supervisarBody');
    try {
        const agentes = await apiFetch('/coordinator/agentes');
        if (body) {
            if (agentes.length === 0) {
                body.innerHTML = '<tr><td colspan="7" style="color:var(--text-placeholder);text-align:center;padding:16px;">Sin personal de soporte</td></tr>';
            } else {
                body.innerHTML = agentes.map(a => `
                    <tr data-agente-id="${a.id_usuario}">
                        <td><strong>${esc(a.nombre)}</strong><br><small style="color:var(--text-placeholder);">${esc(a.rol)}</small></td>
                        <td>${esc(a.email)}</td>
                        <td>${esc(a.especialidad)}</td>
                        <td>${a.nivel_jerarquia || 'Técnico'}</td>
                        <td>
                            <label class="glass-switch">
                                <input type="checkbox" data-permiso="supervision" ${a.permisos_supervision ? 'checked' : ''}>
                                <span class="slider-switch"></span>
                            </label>
                        </td>
                        <td>
                            <label class="glass-switch">
                                <input type="checkbox" data-permiso="especiales" ${a.permisos_especiales ? 'checked' : ''}>
                                <span class="slider-switch"></span>
                            </label>
                        </td>
                        <td><span class="status-pill resuelto">${a.estado}</span></td>
                    </tr>
                `).join('');
            }
        }
    } catch (e) {
        console.error('Error cargando agentes:', e);
        if (body) body.innerHTML = `<tr><td colspan="7" style="color:var(--text-placeholder);text-align:center;padding:16px;">Error: ${e.message}</td></tr>`;
    }
}

async function guardarPermisos() {
    const rows = document.querySelectorAll('#supervisarBody tr[data-agente-id]');
    if (rows.length === 0) {
        mostrarToast('⚠️ No hay agentes para guardar');
        return;
    }
    let guardados = 0;
    try {
        for (const row of rows) {
            const id = row.getAttribute('data-agente-id');
            const ps = !!row.querySelector('input[data-permiso="supervision"]')?.checked;
            const pe = !!row.querySelector('input[data-permiso="especiales"]')?.checked;
            await apiFetch(`/coordinator/agentes/${id}/permisos`, {
                method: 'POST',
                body: { permisos_supervision: ps, permisos_especiales: pe }
            });
            guardados++;
        }
        mostrarToast(`✅ Permisos de ${guardados} agente(s) guardados correctamente`);
    } catch (e) {
        mostrarToast(`❌ Error al guardar permisos: ${e.message}`);
    }
}

// ============================================
// SLAs
// ============================================
async function loadSLA() {
    try {
        const slaList = await apiFetch('/coordinator/sla');
        const cards = document.querySelectorAll('#page-sla .sla-card-item');
        cards.forEach((card, idx) => {
            const data = slaList[idx];
            if (!data) return;
            card.setAttribute('data-prio', data.id_prioridad);
            const inputs = card.querySelectorAll('input.glass-input-num');
            if (inputs[0]) inputs[0].value = data.tiempo_respuesta_min;
            if (inputs[1]) inputs[1].value = data.tiempo_solucion_min;
            const rules = card.querySelectorAll('input[type="checkbox"]');
            rules.forEach(cb => { cb.checked = !!data.activo; });
        });
    } catch (e) {
        console.error('Error cargando SLA:', e);
        mostrarToast(`⚠️ Error al cargar SLA: ${e.message}`);
    }
}

async function guardarSLA() {
    const cards = document.querySelectorAll('#page-sla .sla-card-item');
    const items = [];
    cards.forEach(card => {
        const prio = parseInt(card.getAttribute('data-prio'), 10);
        if (!prio) return;
        const inputs = card.querySelectorAll('input.glass-input-num');
        const activo = !!card.querySelector('input[type="checkbox"]')?.checked;
        items.push({
            id_prioridad: prio,
            tiempo_respuesta_min: parseInt(inputs[0]?.value, 10) || 0,
            tiempo_solucion_min: parseInt(inputs[1]?.value, 10) || 0,
            activo: activo
        });
    });
    if (items.length === 0) {
        mostrarToast('⚠️ No hay políticas SLA para guardar');
        return;
    }
    try {
        await apiFetch('/coordinator/sla', {
            method: 'POST',
            body: { sla: items }
        });
        mostrarToast('⏱️ Políticas SLA guardadas correctamente');
    } catch (e) {
        mostrarToast(`❌ Error al guardar SLA: ${e.message}`);
    }
}

// ============================================
// RAG
// ============================================
async function buscarRAG() {
    const q = document.getElementById('ragSearchInput')?.value.trim();
    const list = document.getElementById('ragResultsList');
    if (!q) {
        mostrarToast('⚠️ Escribe una consulta para buscar en RAG');
        return;
    }
    if (list) list.innerHTML = '<div style="color:var(--text-placeholder);text-align:center;padding:20px;"><i class="fas fa-spinner fa-spin"></i> Buscando...</div>';
    try {
        const results = await apiFetch(`/coordinator/rag?query=${encodeURIComponent(q)}`);
        renderRAG(results, list);
    } catch (e) {
        console.error('Error buscando RAG:', e);
        if (list) list.innerHTML = `<div style="color:var(--text-placeholder);text-align:center;padding:20px;">❌ Error: ${e.message}</div>`;
        mostrarToast(`❌ Error en RAG: ${e.message}`);
    }
}

function renderRAG(results, list) {
    if (!list) return;
    if (!results || results.length === 0) {
        list.innerHTML = '<div style="color:var(--text-placeholder);text-align:center;padding:20px;">No se encontraron soluciones similares</div>';
        return;
    }
    list.innerHTML = results.map(r => `
        <div class="rag-result-card">
            <div class="rag-result-top">
                <h4>Solución para: ${esc(r.asunto)}</h4>
                <span class="similarity-badge">${(r.similitud * 100).toFixed(1)}% Similitud</span>
            </div>
            <p><strong>Detalle del ticket:</strong> ${esc(r.descripcion)}</p>
            <p><strong>Estado:</strong> ${esc(r.estado)} • <strong>Categoría:</strong> ${esc(r.categoria)}</p>
            <span class="rag-meta-tag"><i class="fas fa-check-circle"></i> Ticket fuente: #${r.id_solicitud} • Atención: ${esc(r.agente)}</span>
        </div>
    `).join('');
}

function enviarPromptSugerido(texto) {
    const chatPanel = document.getElementById('chatPanel');
    const chatFab = document.getElementById('chatFab');
    const chatInput = document.getElementById('chatInput');
    if (!chatPanel || !chatInput) return;

    chatPanel.classList.add('open');
    if (chatFab) chatFab.classList.add('open');
    chatInput.value = texto;
    chatInput.focus();
    sendChatMessage();
}

function renderPerfil() {
    if (!state.userData) return;
    const nombre = document.getElementById('profileNombre');
    const email = document.getElementById('profileEmail');
    if (nombre) nombre.textContent = state.userData.nombre || state.userData.email;
    if (email) email.textContent = state.userData.email || '';
}

function mostrarToast(msg) {
    let toast = document.getElementById('coordToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'coordToast';
        toast.className = 'coord-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('show'), 3200);
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