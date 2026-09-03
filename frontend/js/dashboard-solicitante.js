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
            
            const statusClass = `status-${ticket.estado.toLowerCase().replace(' ', '_')}`;
            const estadoTexto = ticket.estado.replace('_', ' ').charAt(0).toUpperCase() + ticket.estado.replace('_', ' ').slice(1);
            
            const item = document.createElement('div');
            item.className = 'ticket-item';
            item.innerHTML = `
                <div class="ticket-info">
                    <span class="ticket-id">#TK-${String(ticket.id_solicitud).padStart(4, '0')}</span>
                    <span class="ticket-subject">${escHtml(ticket.asunto)}</span>
                    <span class="ticket-date"><i class="far fa-calendar-alt"></i> ${date} • ${escHtml(ticket.cat_nombre) || 'Sin categoría'}</span>
                </div>
                <div class="ticket-status ${statusClass}">
                    ${escHtml(estadoTexto)}
                </div>
            `;
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