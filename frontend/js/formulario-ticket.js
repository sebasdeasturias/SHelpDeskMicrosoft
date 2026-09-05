// formulario-ticket.js — Creación de tickets con adjuntos de imágenes.
// Reglas de adjuntos: PNG/JPG, máx. 20 MB por archivo, hasta 5 imágenes.
// Usabilidad (ISO/IEC 25000 / 9241): feedback visible de cada acción,
// mensajes de error que indican cómo corregir y control total del usuario.
const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000/api';

// Límites de adjuntos (deben coincidir con el backend adjuntos.py)
const MAX_TAMANO_ARCHIVO = 20 * 1024 * 1024; // 20 MB
const MAX_ADJUNTOS = 5;
const TIPOS_ACEPTADOS = ['image/png', 'image/jpeg'];
const EXT_ACEPTADAS = ['.png', '.jpg', '.jpeg'];

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

// Adjuntos
const btnAdjuntar = document.getElementById('btnAdjuntar');
const adjuntoInput = document.getElementById('adjuntoInput');
const adjuntosLista = document.getElementById('adjuntosLista');
const attachSection = document.querySelector('.attach-section');
const previewAdjuntosItem = document.getElementById('previewAdjuntosItem');
const previewAdjuntos = document.getElementById('previewAdjuntos');

let pendingTicketData = null;
let currentUserData = null;
let adjuntosSeleccionados = []; // { file, url, nombre, tamano }

document.addEventListener('DOMContentLoaded', async () => {
    initTheme();
    initAdjuntos();
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

/* ============================================================
   ADJUNTOS: selección, validación y vista previa
   ============================================================ */
function initAdjuntos() {
    btnAdjuntar.addEventListener('click', () => adjuntoInput.click());
    adjuntoInput.addEventListener('change', () => {
        agregarAdjuntos(Array.from(adjuntoInput.files || []));
        adjuntoInput.value = ''; // permite volver a elegir el mismo archivo
    });

    // Arrastrar y soltar dentro de la zona de adjuntos
    ['dragenter', 'dragover'].forEach(ev =>
        attachSection.addEventListener(ev, (e) => {
            e.preventDefault();
            e.stopPropagation();
            btnAdjuntar.classList.add('dragover');
        })
    );
    ['dragleave', 'drop'].forEach(ev =>
        attachSection.addEventListener(ev, (e) => {
            e.preventDefault();
            e.stopPropagation();
            btnAdjuntar.classList.remove('dragover');
        })
    );
    attachSection.addEventListener('drop', (e) => {
        const archivos = Array.from(e.dataTransfer?.files || []);
        agregarAdjuntos(archivos);
    });
}

function agregarAdjuntos(archivos) {
    if (!archivos.length) return;
    let avisos = [];

    for (const file of archivos) {
        if (adjuntosSeleccionados.length >= MAX_ADJUNTOS) {
            avisos.push(`Solo puedes adjuntar hasta ${MAX_ADJUNTOS} imágenes por ticket.`);
            break;
        }

        const ext = ('.' + (file.name.split('.').pop() || '')).toLowerCase();
        const tipoValido = TIPOS_ACEPTADOS.includes(file.type) && EXT_ACEPTADAS.includes(ext);
        if (!tipoValido) {
            avisos.push(`"${file.name}" no es PNG o JPG. Usa ese formato.`);
            continue;
        }

        if (file.size > MAX_TAMANO_ARCHIVO) {
            avisos.push(`"${file.name}" pesa ${formatTamano(file.size)} y supera el máximo de 20 MB.`);
            continue;
        }

        const duplicado = adjuntosSeleccionados.some(a => a.nombre === file.name && a.tamano === file.size);
        if (duplicado) {
            avisos.push(`"${file.name}" ya está seleccionada.`);
            continue;
        }

        adjuntosSeleccionados.push({
            file,
            url: URL.createObjectURL(file),
            nombre: file.name,
            tamano: file.size
        });
    }

    renderAdjuntos();
    if (avisos.length) showError(avisos.join(' '));
}

function quitarAdjunto(index) {
    const adj = adjuntosSeleccionados[index];
    if (!adj) return;
    URL.revokeObjectURL(adj.url);
    adjuntosSeleccionados.splice(index, 1);
    renderAdjuntos();
}

function limpiarAdjuntos() {
    adjuntosSeleccionados.forEach(a => URL.revokeObjectURL(a.url));
    adjuntosSeleccionados = [];
    renderAdjuntos();
}

function renderAdjuntos() {
    adjuntosLista.innerHTML = '';

    adjuntosSeleccionados.forEach((adj, index) => {
        const li = document.createElement('li');
        li.className = 'adjunto-chip';

        const img = document.createElement('img');
        img.src = adj.url;
        img.alt = `Vista previa de ${adj.nombre}`;

        const info = document.createElement('div');
        info.className = 'adjunto-info';
        const nombre = document.createElement('span');
        nombre.className = 'adjunto-nombre';
        nombre.textContent = adj.nombre;
        nombre.title = adj.nombre;
        const tamano = document.createElement('small');
        tamano.className = 'adjunto-tamano';
        tamano.textContent = formatTamano(adj.tamano);
        info.append(nombre, tamano);

        const btnQuitar = document.createElement('button');
        btnQuitar.type = 'button';
        btnQuitar.className = 'adjunto-quitar';
        btnQuitar.setAttribute('aria-label', `Quitar imagen ${adj.nombre}`);
        btnQuitar.title = 'Quitar';
        btnQuitar.innerHTML = '<i class="fas fa-times" aria-hidden="true"></i>';
        btnQuitar.addEventListener('click', () => quitarAdjunto(index));

        li.append(img, info, btnQuitar);
        adjuntosLista.appendChild(li);
    });

    btnAdjuntar.classList.toggle('lleno', adjuntosSeleccionados.length >= MAX_ADJUNTOS);
    btnAdjuntar.disabled = adjuntosSeleccionados.length >= MAX_ADJUNTOS;
}

function formatTamano(bytes) {
    if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${bytes} B`;
}

/* ============================================================
   CARGA DE USUARIO
   ============================================================ */
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

/* ============================================================
   ENVÍO DEL TICKET
   ============================================================ */
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

    if (adjuntosSeleccionados.length) {
        previewAdjuntosItem.style.display = '';
        const n = adjuntosSeleccionados.length;
        previewAdjuntos.textContent = `${n} imagen${n > 1 ? 'es' : ''} (${formatTamano(
            adjuntosSeleccionados.reduce((s, a) => s + a.tamano, 0)
        )})`;
    } else {
        previewAdjuntosItem.style.display = 'none';
    }

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

        // 2. Subir imágenes adjuntas (si el usuario seleccionó alguna)
        const fallos = await subirAdjuntos(ticketId, token);

        // La notificación al workflow de IA (n8n) la hace el backend tras crear
        // el ticket: el navegador ya no llama a n8n directamente (no es fiable
        // cuando el frontend está en otro origen, p.ej. Vercel).
        const idFormateado = `TK-${String(ticketId).padStart(4, '0')}`;
        if (fallos === 0) {
            const notaIA = adjuntosSeleccionados.length
                ? ' El análisis de IA se ejecutará en segundo plano.'
                : ' ¡Ticket creado exitosamente!';
            showSuccess(`Ticket ${idFormateado} creado con éxito.${adjuntosSeleccionados.length ? ' Tus imágenes fueron adjuntadas.' : ''}${notaIA}`);
        } else {
            showError(`Ticket ${idFormateado} creado, pero ${fallos} imagen(es) no pudieron subirse. Puedes adjuntarlas desde tu ticket.`);
        }
        ticketForm.reset();
        limpiarAdjuntos();
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

async function subirAdjuntos(ticketId, token) {
    const total = adjuntosSeleccionados.length;
    if (!total) return 0;

    let fallos = 0;
    for (let i = 0; i < total; i++) {
        loadingMessage.lastChild.textContent = ` Subiendo imagen ${i + 1} de ${total}...`;

        try {
            const formData = new FormData();
            formData.append('files', adjuntosSeleccionados[i].file, adjuntosSeleccionados[i].nombre);

            const response = await fetch(`${API_BASE_URL}/tickets/${ticketId}/adjuntos`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            if (response.status === 401) {
                localStorage.removeItem('token');
                sessionStorage.removeItem('token');
                window.location.href = 'login.html';
                return fallos;
            }
            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                console.error(`Error subiendo "${adjuntosSeleccionados[i].nombre}":`, err.detail || response.status);
                fallos++;
            }
        } catch (e) {
            console.error('Error de red subiendo adjunto:', e);
            fallos++;
        }
    }
    return fallos;
}

confirmModal.addEventListener('click', (e) => { if (e.target === confirmModal) { confirmModal.style.display = 'none'; pendingTicketData = null; } });

function showError(msg) { errorText.textContent = msg; errorMessage.style.display = 'flex'; successMessage.style.display = 'none'; setTimeout(() => { errorMessage.style.display = 'none'; }, 5000); }
function showSuccess(msg) { successText.textContent = msg; successMessage.style.display = 'flex'; errorMessage.style.display = 'none'; }
function showLoading() { loadingMessage.style.display = 'flex'; errorMessage.style.display = 'none'; successMessage.style.display = 'none'; loadingMessage.innerHTML = '<span class="spinner-ring"></span> Procesando...'; }
function hideLoading() { loadingMessage.style.display = 'none'; }
