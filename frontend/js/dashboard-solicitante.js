const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000/api';

function escHtml(v) {
    return String(v == null ? '' : v)
        .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

document.addEventListener('DOMContentLoaded', async () => {
    initTheme();
    await checkAuthAndLoadData();
    
    document.getElementById('refreshBtn').addEventListener('click', loadTickets);
    document.getElementById('logoutBtn').addEventListener('click', logout);
    const cardHist = document.getElementById('cardVerHistorial');
    if (cardHist) cardHist.addEventListener('click', () => {
        document.getElementById('historySection').scrollIntoView({ behavior: 'smooth' });
    });

    initSolucionModal();
});

function initTheme() {
    const toggle = document.getElementById('checkbox');
    const themeLabel = document.querySelector('.theme-label');
    
    if (localStorage.getItem('theme') === 'night') {
        document.body.classList.add('night-mode');
        toggle.checked = true;
        themeLabel.textContent = 'Modo Diurno';
    }
    
    toggle.addEventListener('change', () => {
        if (toggle.checked) {
            document.body.classList.add('night-mode');
            themeLabel.textContent = 'Modo Diurno';
        } else {
            document.body.classList.remove('night-mode');
            themeLabel.textContent = 'Modo Nocturno';
        }
        localStorage.setItem('theme', toggle.checked ? 'night' : 'day');
    });
}

async function checkAuthAndLoadData() {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    if (!token) {
        window.location.href = 'login.html';
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!response.ok) throw new Error('No autorizado');
        
        const user = await response.json();
        document.getElementById('userName').textContent = user.nombre || user.email;
        document.getElementById('welcomeName').textContent = user.nombre ? user.nombre.split(' ')[0] : 'Usuario';
        
        // Guardamos el user_id en el dataset del body para filtrar luego
        document.body.dataset.userId = user.user_id;
        
        await loadTickets();
    } catch (error) {
        console.error('Error de autenticación:', error);
        localStorage.removeItem('token');
        sessionStorage.removeItem('token');
        localStorage.removeItem('user');
        sessionStorage.removeItem('user');
        window.location.href = 'login.html';
    }
}

async function loadTickets() {
    const loadingEl = document.getElementById('loadingTickets');
    const listEl = document.getElementById('ticketsList');
    const emptyEl = document.getElementById('emptyState');
    const currentUserId = parseInt(document.body.dataset.userId);
    
    loadingEl.style.display = 'block';
    listEl.innerHTML = '';
    emptyEl.style.display = 'none';
    
    try {
        const token = localStorage.getItem('token') || sessionStorage.getItem('token');
        const response = await fetch(`${API_BASE_URL}/tickets`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.status === 401) {
            localStorage.removeItem('token');
            sessionStorage.removeItem('token');
            window.location.href = 'login.html';
            return;
        }
        
        if (!response.ok) throw new Error('Error al cargar tickets');
        
        const allTickets = await response.json();
        
        // Filtrar solo los tickets de este solicitante
        const myTickets = allTickets.filter(t => t.id_solicitante === currentUserId)
                                    .sort((a, b) => new Date(b.fecha_creacion) - new Date(a.fecha_creacion));
        
        loadingEl.style.display = 'none';
        
        if (myTickets.length === 0) {
            emptyEl.style.display = 'block';
            return;
        }
        
        myTickets.forEach(ticket => {
            const date = new Date(ticket.fecha_creacion).toLocaleDateString('es-ES', {
                year: 'numeric', month: 'short', day: 'numeric'
            });
            
            const statusClass = 'status-' + String(ticket.estado || '').toLowerCase().replace(/[^a-z_]/g, '');
            const estadoTexto = ticket.estado.replace('_', ' ').charAt(0).toUpperCase() + ticket.estado.replace('_', ' ').slice(1);
            const tieneSolucion = !!(ticket.solucion && String(ticket.solucion).trim());
            
            const item = document.createElement('div');
            item.className = 'ticket-item';
            item.innerHTML = `
                <div class="ticket-info">
                    <span class="ticket-id">#TK-${String(ticket.id_solicitud).padStart(4, '0')}</span>
                    <span class="ticket-subject">${escHtml(ticket.asunto)}</span>
                    <span class="ticket-date"><i class="far fa-calendar-alt"></i> ${date} • ${escHtml(ticket.cat_nombre) || 'Sin categoría'}</span>
                </div>
                <div class="ticket-actions">
                    <div class="ticket-status ${statusClass}">
                        ${escHtml(estadoTexto)}
                    </div>
                    ${tieneSolucion ? `<button class="btn-ver-solucion" type="button"><i class="fas fa-lightbulb"></i> Ver solución</button>` : ''}
                </div>
            `;

            const btnSolucion = item.querySelector('.btn-ver-solucion');
            if (btnSolucion) {
                btnSolucion.addEventListener('click', () => mostrarSolucion(ticket));
            }

            listEl.appendChild(item);
        });
        
    } catch (error) {
        console.error('Error cargando tickets:', error);
        loadingEl.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error al cargar los tickets.';
    }
}

function logout() {
    localStorage.removeItem('token');
    sessionStorage.removeItem('token');
    window.location.href = 'login.html';
}

function initSolucionModal() {
    const overlay = document.getElementById('solucionOverlay');
    const closeBtn = document.getElementById('solucionClose');
    if (!overlay) return;
    if (closeBtn) {
        closeBtn.addEventListener('click', () => overlay.classList.remove('open'));
    }
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.classList.remove('open');
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') overlay.classList.remove('open');
    });
}

function mostrarSolucion(ticket) {
    const overlay = document.getElementById('solucionOverlay');
    if (!overlay) return;
    document.getElementById('solucionId').textContent = ticket ? '#' + ticket.id_solicitud : '';
    const body = document.getElementById('solucionBody');
    const solucion = ticket && ticket.solucion ? String(ticket.solucion).trim() : '';
    body.textContent = solucion || 'Este ticket aún no tiene una solución registrada.';
    if (!solucion) body.classList.add('solucion-empty'); else body.classList.remove('solucion-empty');
    overlay.classList.add('open');
}




// ████ █████ ████   ███   ████  ███   ████ █████ ████  █████  ███    
//█ ░░░░█░░░░░█░░░█ █ ░░█ █ ░░░░█ ░░█ █ ░░░░ ░█░░░█░░░█ █░░░░░█ ░░█   
// ███░░████░░████░░█████░ ███░░█████░ ███░░░ █░░░████░░████░░█████░  
//  ░░█ █░░░░ █░░░█ █░░░█░░ ░░█ █░░░█░░ ░░█   █░░ █░░█░ █░░░░ █░░░█░░ 
//████░░█████░████░░█░░░█░████░░█░░░█░████░░  █░░ █░░░█░█████░█░░░█░░ 
// ░░░░ ░░░░░░ ░░░░ ░░░  ░░░░░░ ░░░  ░░░░░░ ░  ░░  ░░  ░ ░░░░░ ░░  ░░ 
//  ░░░░  ░░░░░ ░░░░  ░   ░ ░░░░  ░   ░ ░░░░    ░   ░   ░ ░░░░░ ░   ░ 