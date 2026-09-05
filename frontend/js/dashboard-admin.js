// dashboard-admin.js — Panel del Administrador
const API = window.API_BASE_URL || 'http://localhost:8000/api';

const state = {
    authToken: localStorage.getItem('token') || sessionStorage.getItem('token'),
    userData: null,
    usuarios: [],
    workflows: [],
    respaldos: [],
    currentPage: 'resumen'
};

const ROLES = ['solicitante', 'agente', 'coordinador', 'administrador'];

// ============================================
// API
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
        let msg = `HTTP ${res.status}`;
        try {
            const err = await res.json();
            if (err.detail) msg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
        } catch (_) {}
        throw new Error(msg);
    }
    const ct = res.headers.get('content-type') || '';
    return ct.includes('application/json') ? res.json() : res.blob();
}

// ============================================
// INICIALIZACIÓN
// ============================================
document.addEventListener('DOMContentLoaded', async () => {
    if (!state.authToken) {
        window.location.href = 'login.html';
        return;
    }
    try {
        const me = await apiFetch('/auth/me');
        state.userData = me;
        if (me.role !== 'administrador') {
            const destino = {
                'coordinador': 'dashboard-coordinador.html',
                'agente': 'dashboard-agente.html',
                'solicitante': 'dashboard-solicitante.html'
            }[me.role] || 'login.html';
            window.location.href = destino;
            return;
        }
        document.getElementById('userName').textContent = me.nombre || me.email;
    } catch (e) {
        console.error('Error de autenticación:', e);
        return;
    }

    initTheme();
    initNavigation();
    initModal();
    bindAcciones();
    await loadResumen();
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
// NAVEGACIÓN
// ============================================
const LOADERS = {
    'resumen': loadResumen,
    'usuarios': loadUsuarios,
    'bd': loadBD,
    'respaldos': loadRespaldos,
    'logs': () => {},
    'n8n': loadN8N,
    'ia': loadIA
};

function initNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => navigateTo(btn.dataset.page));
    });
}

function navigateTo(page) {
    state.currentPage = page;
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.page === page));
    document.querySelectorAll('.page-content').forEach(p => p.classList.toggle('active', p.id === `page-${page}`));
    if (LOADERS[page]) LOADERS[page]();
}

// ============================================
// HELPERS UI
// ============================================
function mostrarToast(msg) {
    let toast = document.getElementById('adminToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'adminToast';
        toast.className = 'coord-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('show'), 3500);
}

function initModal() {
    document.getElementById('modalCancelar').addEventListener('click', cerrarModal);
    document.getElementById('modalOverlay').addEventListener('click', e => {
        if (e.target.id === 'modalOverlay') cerrarModal();
    });
}

let _modalAceptar = null;

function abrirModal({ titulo, cuerpo, aceptarTexto = 'Aceptar', peligroso = false, onAceptar }) {
    document.getElementById('modalTitulo').textContent = titulo;
    document.getElementById('modalCuerpo').innerHTML = cuerpo;
    const btn = document.getElementById('modalAceptar');
    btn.textContent = aceptarTexto;
    btn.classList.toggle('danger', peligroso);
    _modalAceptar = onAceptar;
    document.getElementById('modalOverlay').classList.add('open');
}

function cerrarModal() {
    document.getElementById('modalOverlay').classList.remove('open');
    _modalAceptar = null;
}

document.getElementById('modalAceptar').addEventListener('click', () => {
    if (_modalAceptar) _modalAceptar();
    cerrarModal();
});

function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

// ============================================
// RESUMEN
// ============================================
async function loadResumen() {
    try {
        const [stats, usuarios] = await Promise.all([
            apiFetch('/coordinator/estadisticas'),
            apiFetch('/coordinator/usuarios')
        ]);
        state.usuarios = usuarios;
        const k = stats.kpis || {};
        const activos = usuarios.filter(u => u.estado === 'activo').length;

        const kpis = [
            ['blue', 'fa-ticket-alt', 'Tickets Totales Mes', k.total_tickets_mes ?? 0],
            ['green', 'fa-shield-halved', 'Cumplimiento de SLA', k.cumplimiento_sla != null ? `${k.cumplimiento_sla}%` : '—'],
            ['yellow', 'fa-users-gear', 'Usuarios Totales', usuarios.length],
            ['purple', 'fa-user-check', 'Usuarios Activos', activos]
        ];
        document.getElementById('kpiResumen').innerHTML = kpis.map(([color, icon, label, value]) => `
            <div class="kpi-card">
                <div class="kpi-icon ${color}"><i class="fas ${icon}"></i></div>
                <div class="kpi-content">
                    <span class="kpi-label">${label}</span>
                    <span class="kpi-value">${escapeHtml(value)}</span>
                </div>
            </div>`).join('');

        const porRol = {};
        usuarios.forEach(u => {
            porRol[u.rol] = porRol[u.rol] || { total: 0, activos: 0, inactivos: 0 };
            porRol[u.rol].total++;
            porRol[u.rol][u.estado === 'activo' ? 'activos' : 'inactivos']++;
        });
        document.getElementById('rolesBody').innerHTML = Object.entries(porRol).map(([rol, d]) => `
            <tr>
                <td><span class="role-pill ${escapeHtml(rol)}">${escapeHtml(rol)}</span></td>
                <td><strong>${d.total}</strong></td>
                <td>${d.activos}</td>
                <td>${d.inactivos}</td>
            </tr>`).join('');
    } catch (e) {
        mostrarToast(`Error al cargar resumen: ${e.message}`);
    }
}

// ============================================
// USUARIOS
// ============================================
async function loadUsuarios() {
    try {
        state.usuarios = await apiFetch('/coordinator/usuarios');
        renderUsuarios();
    } catch (e) {
        mostrarToast(`Error al cargar usuarios: ${e.message}`);
    }
}

function renderUsuarios() {
    const body = document.getElementById('usuariosBody');
    document.getElementById('usuariosCount').textContent = `${state.usuarios.length} usuarios`;
    body.innerHTML = state.usuarios.map(u => {
        const temporal = u.admin_temporal_hasta
            ? `<span class="item-meta">hasta ${new Date(u.admin_temporal_hasta).toLocaleString('es-ES')}${u.rol_anterior ? ` (vuelve a ${escapeHtml(u.rol_anterior)})` : ''}</span>`
            : '<span class="item-meta">—</span>';
        return `
        <tr data-uid="${u.id_usuario}">
            <td><strong>#${u.id_usuario}</strong></td>
            <td>${escapeHtml(u.nombre)}</td>
            <td>${escapeHtml(u.email)}</td>
            <td><span class="role-pill ${escapeHtml(u.rol)}">${escapeHtml(u.rol)}</span>${u.rol_anterior ? '<br><span class="item-meta">temporal</span>' : ''}</td>
            <td>${escapeHtml(u.area || 'N/A')}</td>
            <td><span class="status-pill ${escapeHtml(u.estado)}">${escapeHtml(u.estado)}</span></td>
            <td>${temporal}</td>
            <td>
                <button class="btn-mini" data-accion="rol"><i class="fas fa-user-shield"></i> Rol</button>
                <button class="btn-mini" data-accion="estado"><i class="fas fa-power-off"></i> ${u.estado === 'activo' ? 'Desactivar' : 'Activar'}</button>
                <button class="btn-mini" data-accion="password"><i class="fas fa-key"></i></button>
                <button class="btn-mini danger" data-accion="eliminar"><i class="fas fa-trash"></i></button>
            </td>
        </tr>`;
    }).join('');

    body.querySelectorAll('button[data-accion]').forEach(btn => {
        btn.addEventListener('click', () => {
            const uid = parseInt(btn.closest('tr').dataset.uid, 10);
            const usuario = state.usuarios.find(x => x.id_usuario === uid);
            const accion = btn.dataset.accion;
            if (accion === 'rol') modalCambiarRol(usuario);
            else if (accion === 'estado') toggleEstado(usuario);
            else if (accion === 'password') modalResetPassword(usuario);
            else if (accion === 'eliminar') modalEliminar(usuario);
        });
    });
}

function bindAcciones() {
    document.getElementById('btnNuevoUsuario').addEventListener('click', () => {
        const f = document.getElementById('formNuevoUsuario');
        f.style.display = f.style.display === 'none' ? 'block' : 'none';
    });
    document.getElementById('btnRefrescarUsuarios').addEventListener('click', loadUsuarios);
    document.getElementById('btnCrearUsuario').addEventListener('click', crearUsuario);
    document.getElementById('btnRefrescarBD').addEventListener('click', loadBD);
    document.getElementById('btnCrearRespaldo').addEventListener('click', crearRespaldo);
    document.getElementById('btnVerLogs').addEventListener('click', verLogs);
    document.getElementById('btnRefrescarN8N').addEventListener('click', loadN8N);
    document.getElementById('btnIaPull').addEventListener('click', iaPull);
    document.getElementById('btnIaParams').addEventListener('click', guardarIaParams);
}

async function crearUsuario() {
    const payload = {
        nombre: document.getElementById('nuNombre').value.trim(),
        email: document.getElementById('nuEmail').value.trim(),
        area: document.getElementById('nuArea').value.trim(),
        rol: document.getElementById('nuRol').value,
        password: document.getElementById('nuPass').value
    };
    if (!payload.nombre || !payload.email || !payload.password) {
        mostrarToast('Nombre, correo y contraseña son obligatorios');
        return;
    }
    try {
        await apiFetch('/coordinator/usuarios', { method: 'POST', body: payload });
        mostrarToast(`Usuario ${payload.email} creado con rol ${payload.rol}`);
        ['nuNombre', 'nuEmail', 'nuArea', 'nuPass'].forEach(id => document.getElementById(id).value = '');
        document.getElementById('formNuevoUsuario').style.display = 'none';
        loadUsuarios();
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    }
}

function modalCambiarRol(u) {
    abrirModal({
        titulo: `Cambiar rol — ${u.nombre}`,
        cuerpo: `
            <p>Rol actual: <span class="role-pill ${escapeHtml(u.rol)}">${escapeHtml(u.rol)}</span></p>
            <label class="filter-group" style="margin-top:10px;"><label>Nuevo rol</label>
                <select class="glass-select" id="modalNuevoRol">
                    ${ROLES.map(r => `<option value="${r}" ${r === u.rol ? 'selected' : ''}>${r}</option>`).join('')}
                </select>
            </label>
            <div style="margin-top:10px;">
                <label style="display:flex; gap:8px; align-items:center; color:var(--text-dark);">
                    <input type="checkbox" id="modalTemporal"> Temporal (solo al promover a administrador)
                </label>
                <input class="glass-input" id="modalHoras" type="number" min="1" max="720" value="24" disabled
                    style="margin-top:8px;" title="Duración en horas">
            </div>`,
        aceptarTexto: 'Aplicar',
        onAceptar: async () => {
            const rol = document.getElementById('modalNuevoRol').value;
            const temporal = document.getElementById('modalTemporal').checked;
            const horas = parseInt(document.getElementById('modalHoras').value, 10) || 24;
            document.getElementById('modalTemporal').addEventListener('change', () => {});
            try {
                const r = await apiFetch(`/coordinator/usuarios/${u.id_usuario}/rol`, {
                    method: 'PATCH',
                    body: { rol, temporal_horas: temporal ? horas : null }
                });
                mostrarToast(r.temporal_horas
                    ? `${u.nombre} es administrador por ${r.temporal_horas} h (volverá a ${r.rol_anterior})`
                    : `Rol de ${u.nombre}: ${rol}`);
                loadUsuarios();
            } catch (e) {
                mostrarToast(`Error: ${e.message}`);
            }
        }
    });
    document.getElementById('modalTemporal').addEventListener('change', e => {
        document.getElementById('modalHoras').disabled = !e.target.checked;
    });
}

function toggleEstado(u) {
    const nuevo = u.estado === 'activo' ? 'inactivo' : 'activo';
    abrirModal({
        titulo: `${nuevo === 'activo' ? 'Activar' : 'Desactivar'} usuario`,
        cuerpo: `<p>¿Marcar a <strong>${escapeHtml(u.nombre)}</strong> (${escapeHtml(u.email)}) como <strong>${nuevo}</strong>?</p>`,
        aceptarTexto: 'Sí, aplicar',
        peligroso: nuevo === 'inactivo',
        onAceptar: async () => {
            try {
                await apiFetch(`/coordinator/usuarios/${u.id_usuario}`, { method: 'PATCH', body: { estado: nuevo } });
                mostrarToast(`${u.nombre} ahora está ${nuevo}`);
                loadUsuarios();
            } catch (e) {
                mostrarToast(`Error: ${e.message}`);
            }
        }
    });
}

function modalResetPassword(u) {
    abrirModal({
        titulo: `Restablecer contraseña — ${u.nombre}`,
        cuerpo: `<p>Nueva contraseña para <strong>${escapeHtml(u.email)}</strong> (mínimo 8 caracteres):</p>
                 <input class="glass-input" id="modalPass" type="password">`,
        aceptarTexto: 'Restablecer',
        onAceptar: async () => {
            const pass = document.getElementById('modalPass').value;
            try {
                await apiFetch(`/coordinator/usuarios/${u.id_usuario}`, { method: 'PATCH', body: { password: pass } });
                mostrarToast(`Contraseña de ${u.nombre} restablecida`);
            } catch (e) {
                mostrarToast(`Error: ${e.message}`);
            }
        }
    });
}

function modalEliminar(u) {
    abrirModal({
        titulo: 'Eliminar usuario',
        cuerpo: `<p>¿Eliminar <strong>${escapeHtml(u.nombre)}</strong> (${escapeHtml(u.email)}) <strong>definitivamente</strong>?</p>
                 <p class="hint">Si tiene tickets o registros asociados, la BD lo impedirá: desactívalo en su lugar.</p>`,
        aceptarTexto: 'Eliminar',
        peligroso: true,
        onAceptar: async () => {
            try {
                await apiFetch(`/coordinator/usuarios/${u.id_usuario}`, { method: 'DELETE' });
                mostrarToast(`${u.nombre} eliminado`);
                loadUsuarios();
            } catch (e) {
                mostrarToast(`Error: ${e.message}`);
            }
        }
    });
}

// ============================================
// BASE DE DATOS
// ============================================
async function loadBD() {
    try {
        const tablas = await apiFetch('/coordinator/bd/tablas');
        document.getElementById('bdBody').innerHTML = tablas.map(t => `
            <tr><td><strong>${escapeHtml(t.tabla)}</strong></td><td>${t.filas ?? 0}</td></tr>`).join('');
    } catch (e) {
        mostrarToast(`Error al cargar tablas: ${e.message}`);
    }
}

// ============================================
// RESPALDOS
// ============================================
async function loadRespaldos() {
    try {
        state.respaldos = await apiFetch('/coordinator/respaldos');
        document.getElementById('respaldosCount').textContent = `${state.respaldos.length} respaldos`;
        document.getElementById('respaldosBody').innerHTML = state.respaldos.map(r => `
            <tr data-nombre="${escapeHtml(r.nombre)}">
                <td><strong>${escapeHtml(r.nombre)}</strong></td>
                <td>${(r.bytes / 1e6).toFixed(2)} MB</td>
                <td>${escapeHtml(r.fecha)}</td>
                <td>
                    <button class="btn-mini" data-accion="descargar"><i class="fas fa-download"></i></button>
                    <button class="btn-mini danger" data-accion="eliminar"><i class="fas fa-trash"></i></button>
                    <button class="btn-mini danger" data-accion="restaurar"><i class="fas fa-rotate-left"></i> Restaurar</button>
                </td>
            </tr>`).join('');

        document.querySelectorAll('#respaldosBody button[data-accion]').forEach(btn => {
            btn.addEventListener('click', () => {
                const nombre = btn.closest('tr').dataset.nombre;
                const accion = btn.dataset.accion;
                if (accion === 'descargar') descargarRespaldo(nombre);
                else if (accion === 'eliminar') {
                    abrirModal({
                        titulo: 'Eliminar respaldo',
                        cuerpo: `<p>¿Eliminar <strong>${escapeHtml(nombre)}</strong> permanentemente?</p>`,
                        aceptarTexto: 'Eliminar', peligroso: true,
                        onAceptar: async () => {
                            try {
                                await apiFetch(`/coordinator/respaldos/${encodeURIComponent(nombre)}`, { method: 'DELETE' });
                                mostrarToast('Respaldo eliminado');
                                loadRespaldos();
                            } catch (e) { mostrarToast(`Error: ${e.message}`); }
                        }
                    });
                } else if (accion === 'restaurar') {
                    abrirModal({
                        titulo: 'Restaurar base de datos',
                        cuerpo: `<p>Se ejecutará <code>pg_restore --clean</code> con <strong>${escapeHtml(nombre)}</strong>.</p>
                                 <p><strong>LA BD ACTUAL SERÁ REEMPLAZADA</strong> y todos los usuarios tendrán que volver a iniciar sesión.</p>`,
                        aceptarTexto: 'Restaurar ahora', peligroso: true,
                        onAceptar: async () => {
                            try {
                                mostrarToast('Restaurando (puede tardar un minuto)...');
                                await apiFetch(`/coordinator/respaldos/${encodeURIComponent(nombre)}/restaurar`, { method: 'POST' });
                                mostrarToast('Base de datos restaurada');
                            } catch (e) { mostrarToast(`Error: ${e.message}`); }
                        }
                    });
                }
            });
        });
    } catch (e) {
        mostrarToast(`Error al cargar respaldos: ${e.message}`);
    }
}

async function crearRespaldo() {
    const btn = document.getElementById('btnCrearRespaldo');
    btn.disabled = true;
    try {
        mostrarToast('Ejecutando pg_dump...');
        const r = await apiFetch('/coordinator/respaldos', { method: 'POST' });
        mostrarToast(`Respaldo creado: ${r.archivo}`);
        loadRespaldos();
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    } finally {
        btn.disabled = false;
    }
}

async function descargarRespaldo(nombre) {
    try {
        mostrarToast('Preparando descarga...');
        const blob = await apiFetch(`/coordinator/respaldos/${encodeURIComponent(nombre)}/descargar`);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = nombre;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    }
}

// ============================================
// LOGS
// ============================================
async function verLogs() {
    const contenedor = document.getElementById('logContenedor').value;
    const tail = document.getElementById('logTail').value;
    document.getElementById('logTitulo').textContent = `Logs: ${contenedor} (últimas ${tail} líneas)`;
    document.getElementById('logSalida').textContent = 'Cargando...';
    try {
        const r = await apiFetch(`/coordinator/logs/${contenedor}?tail=${tail}`);
        document.getElementById('logSalida').textContent = r.logs;
    } catch (e) {
        document.getElementById('logSalida').textContent = `Error: ${e.message}`;
    }
}

// ============================================
// N8N
// ============================================
async function loadN8N() {
    const lista = document.getElementById('n8nLista');
    lista.innerHTML = '<div class="item-glass"><span class="item-meta">Cargando workflows...</span></div>';
    try {
        state.workflows = await apiFetch('/coordinator/n8n/workflows');
        if (state.workflows.length === 0) {
            lista.innerHTML = '<div class="item-glass"><span class="item-meta">No hay workflows en esta instancia</span></div>';
            return;
        }
        lista.innerHTML = state.workflows.map(w => `
            <div class="item-glass" data-wid="${escapeHtml(String(w.id))}">
                <div>
                    <span class="item-titulo"><span class="punto" style="background:${w.activo ? '#22c55e' : '#9ca3af'};"></span>${escapeHtml(w.nombre)}</span>
                    <div class="item-meta">ID: ${escapeHtml(String(w.id))} · ${w.activo ? 'Activo' : 'Inactivo'}</div>
                </div>
                <button class="btn-mini" data-accion="toggle">${w.activo ? 'Desactivar' : 'Activar'}</button>
            </div>`).join('');

        lista.querySelectorAll('button[data-accion="toggle"]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const wid = btn.closest('.item-glass').dataset.wid;
                const wf = state.workflows.find(w => String(w.id) === wid);
                try {
                    await apiFetch(`/coordinator/n8n/workflows/${encodeURIComponent(wid)}/toggle`,
                        { method: 'POST', body: { activo: !wf.activo } });
                    mostrarToast(`Workflow '${wf.nombre}' ${wf.activo ? 'desactivado' : 'activado'}`);
                    loadN8N();
                } catch (e) {
                    mostrarToast(`Error: ${e.message}`);
                }
            });
        });
    } catch (e) {
        lista.innerHTML = `<div class="item-glass"><span class="item-meta">Error: ${escapeHtml(e.message)}</span></div>`;
    }
}

// ============================================
// IA
// ============================================
async function loadIA() {
    const lista = document.getElementById('iaModelos');
    lista.innerHTML = '<div class="item-glass"><span class="item-meta">Cargando modelos...</span></div>';
    try {
        const data = await apiFetch('/coordinator/ia');
        document.getElementById('iaTemp').value = data.config.temperatura ?? 0.8;
        document.getElementById('iaPredict').value = data.config.num_predict ?? 512;
        document.getElementById('iaTopP').value = data.config.top_p ?? 0.9;

        lista.innerHTML = data.modelos.map(m => `
            <div class="item-glass">
                <div>
                    <span class="item-titulo">${escapeHtml(m.name)}
                        ${m.name === data.modelo_activo
                            ? '<span class="role-pill administrador">(activo)</span>' : ''}</span>
                    <div class="item-meta">${(m.size / 1e9).toFixed(2)} GB</div>
                </div>
                <div>
                    ${m.name !== data.modelo_activo
                        ? `<button class="btn-mini" data-accion="usar" data-modelo="${escapeHtml(m.name)}">Usar</button>` : ''}
                    <button class="btn-mini" data-accion="probar" data-modelo="${escapeHtml(m.name)}">Probar</button>
                </div>
            </div>`).join('');

        lista.querySelectorAll('button[data-accion]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const modelo = btn.dataset.modelo;
                if (btn.dataset.accion === 'usar') {
                    try {
                        await apiFetch('/coordinator/ia/modelo', { method: 'POST', body: { modelo } });
                        mostrarToast(`Modelo activo del chat: ${modelo}`);
                        loadIA();
                    } catch (e) { mostrarToast(`Error: ${e.message}`); }
                } else {
                    btn.disabled = true;
                    btn.textContent = 'Probando...';
                    try {
                        const r = await apiFetch('/coordinator/ia/probar', { method: 'POST', body: { modelo } });
                        abrirModal({
                            titulo: `Respuesta de ${modelo}`,
                            cuerpo: `<p>${escapeHtml(r.respuesta)}</p>`,
                            aceptarTexto: 'Cerrar',
                            onAceptar: () => {}
                        });
                    } catch (e) { mostrarToast(`Error: ${e.message}`); }
                    btn.disabled = false;
                    btn.textContent = 'Probar';
                }
            });
        });
    } catch (e) {
        lista.innerHTML = `<div class="item-glass"><span class="item-meta">Error: ${escapeHtml(e.message)}</span></div>`;
    }
}

async function iaPull() {
    const modelo = document.getElementById('iaPullNombre').value.trim();
    if (!modelo) {
        mostrarToast('Escribe el nombre del modelo a descargar');
        return;
    }
    const btn = document.getElementById('btnIaPull');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-ring"></span> Descargando...';
    try {
        mostrarToast(`Descargando ${modelo} (puede tardar varios minutos)...`);
        const r = await apiFetch('/coordinator/ia/pull', { method: 'POST', body: { modelo } });
        mostrarToast(`${r.modelo}: ${r.detalle}`);
        document.getElementById('iaPullNombre').value = '';
        loadIA();
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-download"></i> Descargar';
    }
}

async function guardarIaParams() {
    try {
        await apiFetch('/coordinator/ia/params', {
            method: 'POST',
            body: {
                temperatura: parseFloat(document.getElementById('iaTemp').value),
                num_predict: parseInt(document.getElementById('iaPredict').value, 10),
                top_p: parseFloat(document.getElementById('iaTopP').value)
            }
        });
        mostrarToast('Parámetros guardados. Se aplican en el próximo mensaje del chat.');
    } catch (e) {
        mostrarToast(`Error: ${e.message}`);
    }
}
