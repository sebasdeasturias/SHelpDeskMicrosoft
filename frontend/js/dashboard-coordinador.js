// dashboard-coordinador.js
const API = 'http://localhost:8000/api';

const state = {
    tickets: [],
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

    // Si es kanban, refrescar tickets
    if (page === 'kanban') {
        fetchTickets();
    }

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
            <div class="card-title">${t.asunto}</div>
            <div class="card-meta">
                <span class="card-id">#${t.id_solicitud}</span>
                <div class="card-tags">
                    <span class="tag tag-${catMap[t.cat_nombre] || 'network'}">${t.cat_nombre || 'General'}</span>
                </div>
            </div>
            <div class="card-assignee">
                <div class="assignee-avatar" style="background:hsl(${hue},60%,40%)">${init}</div>
                <span class="assignee-name">${t.agente || 'Sin asignar'}</span>
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
            const newStatus = Object.keys(COLUMN_MAP).find(k => COLUMN_MAP[k] === newColKey);

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

    let mensajeCompleto = mensaje;
    if (state.attachedTicket) {
        mensajeCompleto = `[Contexto del ticket #${state.attachedTicket.id_solicitud}: "${state.attachedTicket.asunto}" - ${state.attachedTicket.descripcion}] ${mensaje}`;
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
            body: JSON.stringify({
                mensaje: mensajeCompleto,
                historial: state.chatHistory.slice(-10),
                modelo: 'llama3.2:3b'
            })
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
            <div class="sci-title">#${t.id_solicitud} - ${t.asunto}</div>
            <div class="sci-meta">
                <span class="sci-priority" style="background:rgba(255,255,255,0.2);color:var(--text-dark);">${t.prio_nivel || 'N/A'}</span>
                <span>${t.estado || 'N/A'}</span>
            </div>
        </div>
    `).join('');

    list.querySelectorAll('.selector-card-item').forEach(item => {
        item.addEventListener('click', () => {
            const ticketId = parseInt(item.dataset.id);
            const ticket = state.tickets.find(t => t.id_solicitud === ticketId);
            if (ticket) {
                state.attachedTicket = ticket;
                addChatMessage(`📎 Ticket #${ticket.id_solicitud} adjuntado: "${ticket.asunto}"`, 'system');
            }
            closeCardSelector();
        });
    });
}