// Configuración
const API_BASE_URL = 'http://localhost:8000/api';
// IMPORTANTE: El navegador SIEMPRE usa localhost. 
// Usa 'webhook' si el workflow está ACTIVO en n8n. Usa 'webhook-test' si estás probando manualmente.
const N8N_WEBHOOK_URL = 'http://localhost:5678/webhook/new-ticket'; 

// Elementos del DOM
const ticketForm = document.getElementById('ticketForm');
const asuntoInput = document.getElementById('asunto');
const descripcionInput = document.getElementById('descripcion');
const categoriaSelect = document.getElementById('categoria');
const prioridadSelect = document.getElementById('prioridad');
const btnEnviar = document.getElementById('btnEnviar');
const errorMessage = document.getElementById('errorMessage');
const errorText = document.getElementById('errorText');
const successMessage = document.getElementById('successMessage');
const successText = document.getElementById('successText');
const loadingMessage = document.getElementById('loadingMessage');
const confirmModal = document.getElementById('confirmModal');
const btnCancelar = document.getElementById('btnCancelar');
const btnConfirmar = document.getElementById('btnConfirmar');
const userNameSpan = document.getElementById('userName');
const userAreaSpan = document.getElementById('userArea');
const aiIndicator = document.getElementById('aiIndicator');

let pendingTicketData = null;
let currentUserData = null;

document.addEventListener('DOMContentLoaded', async () => {
    initTheme();
    await loadUserInfo();
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
        document.body.classList.toggle('night-mode', toggle.checked);
        themeLabel.textContent = toggle.checked ? 'Modo Diurno' : 'Modo Nocturno';
        localStorage.setItem('theme', toggle.checked ? 'night' : 'day');
    });
}

async function loadUserInfo() {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    if (!token) { window.location.href = 'login.html'; return; }
    
    try {
        const response = await fetch(`${API_BASE_URL}/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error('No autorizado');
        
        const user = await response.json();
        userNameSpan.textContent = user.nombre || user.email;
        userAreaSpan.textContent = user.area ? `(${user.area})` : '';
        
        currentUserData = {
            id: user.user_id,
            nombre: user.nombre || user.email,
            email: user.email,
            area: user.area,
            rol: user.role
        };
        
        if (user.role !== 'solicitante') {
            showError('Este formulario es solo para solicitantes');
            setTimeout(() => { window.location.href = 'login.html'; }, 2000);
        }
    } catch (error) {
        console.error('Error cargando usuario:', error);
        localStorage.removeItem('token');
        sessionStorage.removeItem('token');
        localStorage.removeItem('user');
        sessionStorage.removeItem('user');
        window.location.href = 'login.html';
    }
}

btnEnviar.addEventListener('click', () => {
    if (!ticketForm.checkValidity()) { ticketForm.reportValidity(); return; }
    
    const asunto = asuntoInput.value.trim();
    const descripcion = descripcionInput.value.trim();
    const categoria = categoriaSelect.value;
    const prioridad = prioridadSelect.value;
    
    if (!asunto || !descripcion || !categoria || !prioridad) {
        showError('Por favor completa todos los campos');
        return;
    }
    
    pendingTicketData = {
        asunto, descripcion,
        id_categoria: parseInt(categoria),
        id_prioridad: parseInt(prioridad),
        categoria_nombre: categoriaSelect.options[categoriaSelect.selectedIndex].text,
        prioridad_nombre: prioridadSelect.options[prioridadSelect.selectedIndex].text
    };
    
    document.getElementById('previewAsunto').textContent = asunto;
    document.getElementById('previewCategoria').textContent = pendingTicketData.categoria_nombre;
    document.getElementById('previewPrioridad').textContent = pendingTicketData.prioridad_nombre;
    confirmModal.style.display = 'flex';
});

btnCancelar.addEventListener('click', () => { confirmModal.style.display = 'none'; pendingTicketData = null; });

btnConfirmar.addEventListener('click', async () => {
    if (!pendingTicketData || !currentUserData) {
        console.error('Faltan datos:', { pendingTicketData, currentUserData });
        return;
    }
    
    confirmModal.style.display = 'none';
    showLoading();
    btnEnviar.disabled = true;
    if (aiIndicator) aiIndicator.style.display = 'flex';
    
    try {
        const token = localStorage.getItem('token') || sessionStorage.getItem('token');
        
        // 1. Guardar en DB
        const dbResponse = await fetch(`${API_BASE_URL}/tickets`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({
                asunto: pendingTicketData.asunto,
                descripcion: pendingTicketData.descripcion,
                id_categoria: pendingTicketData.id_categoria,
                id_prioridad: pendingTicketData.id_prioridad
            })
        });

        if (dbResponse.status === 401) {
            localStorage.removeItem('token');
            sessionStorage.removeItem('token');
            window.location.href = 'login.html';
            return;
        }
        
        if (!dbResponse.ok) {
            const error = await dbResponse.json();
            throw new Error(error.detail || 'Error al crear el ticket');
        }
        
        const dbResult = await dbResponse.json();
        const ticketId = dbResult.ticket_id;
        console.log('✅ Ticket creado en DB con ID:', ticketId);
        
        // 2. Enviar a n8n
        const n8nPayload = {
            event: 'new_ticket_created',
            timestamp: new Date().toISOString(),
            ticket_id: ticketId,
            backend_url: API_BASE_URL,
            ticket: {
                asunto: pendingTicketData.asunto,
                descripcion: pendingTicketData.descripcion,
                categoria: { id: pendingTicketData.id_categoria, nombre: pendingTicketData.categoria_nombre },
                prioridad: { id: pendingTicketData.id_prioridad, nombre: pendingTicketData.prioridad_nombre },
                estado: 'nuevo',
                fecha_creacion: new Date().toISOString()
            },
            solicitante: {
                id: currentUserData.id,
                nombre: currentUserData.nombre,
                email: currentUserData.email,
                area: currentUserData.area
            }
        };
        
        // Llamada a n8n (sin await para que sea fire-and-forget y no bloquee la UI)
        sendToN8N(n8nPayload);
        
        showSuccess(`¡Ticket creado exitosamente! ID: TK-${String(ticketId).padStart(4, '0')}`);
        ticketForm.reset();
        setTimeout(() => { window.location.href = 'dashboard-solicitante.html'; }, 3000);
        
    } catch (error) {
        console.error('Error:', error);
        showError(error.message || 'Error al crear el ticket');
    } finally {
        hideLoading();
        if (aiIndicator) aiIndicator.style.display = 'none';
        btnEnviar.disabled = false;
        pendingTicketData = null;
    }
});

async function sendToN8N(payload) {
    try {
        console.log('📤 Enviando a n8n:', N8N_WEBHOOK_URL, payload);
        const response = await fetch(N8N_WEBHOOK_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (response.ok) console.log('✅ n8n recibió los datos');
        else console.warn('⚠️ n8n respondió:', response.status);
    } catch (error) {
        console.error('❌ Error de red con n8n:', error);
    }
}

confirmModal.addEventListener('click', (e) => { if (e.target === confirmModal) { confirmModal.style.display = 'none'; pendingTicketData = null; } });

function showError(msg) { errorText.textContent = msg; errorMessage.style.display = 'flex'; successMessage.style.display = 'none'; setTimeout(() => { errorMessage.style.display = 'none'; }, 5000); }
function showSuccess(msg) { successText.textContent = msg; successMessage.style.display = 'flex'; errorMessage.style.display = 'none'; }
function showLoading() { loadingMessage.style.display = 'flex'; errorMessage.style.display = 'none'; successMessage.style.display = 'none'; }
function hideLoading() { loadingMessage.style.display = 'none'; }
